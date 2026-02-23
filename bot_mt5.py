"""
bot_mt5.py — Bot Multi-Estrategia (XAUUSD Live + EURUSD Test) (v5)
=====================================================================
Ejecuta múltiples estrategias en paralelo directamente en MT5.

NUEVO en v5:
  🧪 Virtual Paper Trading: Prueba estrategias en tiempo real sin riesgo.
  🧩 Multi-Strategy: Soporta Asian Breakout (Oro) y Mean Reversion (Forex).
  💾 Logging independiente por símbolo.

Uso:
    python bot_mt5.py --risk 1.5
"""

import MetaTrader5 as mt5
import pandas as pd
import time
import argparse
import csv
import os
import json
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict

import logger
import telegram_notify as tg
import strategy_eurusd as strat_eur

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE SÍMBOLOS Y ESTRATEGIAS
# ─────────────────────────────────────────────────────────────────────────────

SYMBOL_CONFIGS = {
    "XAUUSD": {
        "aliases":     ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"],
        "strategy":    "ASIAN_BREAKOUT",
        "live":        True,        # Target: MT5 Account (Demo or Real)
        "min_range":   3.0,
        "max_range":   20.0,
        "tp_mult":     2.5,
        "sl_buffer":   0.001,
    },
    "EURUSD": {
        "aliases":     ["EURUSD", "EURUSDm", "EURUSD.a"],
        "strategy":    "MEAN_REVERSION",
        "live":        True,        # Target: MT5 Account (Demo or Real)
        "timeframe":   mt5.TIMEFRAME_H1,
    }
}

# Parámetros Comunes
ASIAN_START_H  = 0
ASIAN_END_H    = 6
LONDON_START_H = 7
LONDON_END_H   = 10
EMA_PERIOD     = 50
SKIP_MONDAY    = True
MAX_ENTRY_CANDLES = 4

# Gestión de Riesgo Prop Firm
BE_TRIGGER_R       = 1.0
TRAIL_DISTANCE_MULT = 0.5
EOD_CLOSE_H        = 16

STATE_FILE     = "bot_state_mt5_v5.json"
MAX_RECONNECT_ATTEMPTS = 10
RECONNECT_DELAY_SECS   = 30
DAILY_SUMMARY_HOUR     = 17

# ─────────────────────────────────────────────────────────────────────────────
# ESTADO PERSISTENTE
# ─────────────────────────────────────────────────────────────────────────────

def save_state(state: dict):
    state["last_update"] = datetime.now(timezone.utc).isoformat()
    state["running"] = True
    try:
        # Añadir Radar de Señales
        state["radar"] = calculate_radar()

        # Añadir info de cuenta si está conectado
        acct = mt5.account_info()
        if acct:
            state["account"] = {
                "balance": acct.balance,
                "equity": acct.equity,
                "profit": acct.profit,
                "currency": acct.currency
            }
        
        # Obtener posiciones reales
        positions = mt5.positions_get()
        state["live_positions"] = []
        if positions:
            for p in positions:
                state["live_positions"].append({
                    "symbol": p.symbol,
                    "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                    "volume": p.volume,
                    "price_open": p.price_open,
                    "profit": p.profit
                })

        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error guardando estado: {e}")

def calculate_radar() -> list:
    """Calcula la proximidad de señales para el dashboard."""
    radar_data = []
    
    # 1. XAUUSD (Asian Breakout)
    try:
        symbol = find_symbol("XAUUSD")
        if symbol:
            now = datetime.now(timezone.utc)
            df_15m = get_candles(symbol, mt5.TIMEFRAME_M15, 100)
            tick = mt5.symbol_info_tick(symbol)
            if not df_15m.empty and tick:
                today = now.date()
                asian = df_15m[(df_15m.index.date == today) & (df_15m.index.hour >= ASIAN_START_H) & (df_15m.index.hour < ASIAN_END_H)]
                
                hi, lo = (float(asian["high"].max()), float(asian["low"].min())) if len(asian) >= 4 else (0, 0)
                
                # Proximidad a los bordes del rango (0-100)
                long_score = 0
                short_score = 0
                if hi > 0 and LONDON_START_H <= now.hour < LONDON_END_H:
                    # Si el precio está cerca del HI (Long)
                    dist_hi = abs(tick.ask - hi)
                    long_score = max(0, min(100, 100 - (dist_hi / (hi*0.001)) * 100)) if hi > 0 else 0
                    # Si el precio está cerca del LO (Short)
                    dist_lo = abs(tick.bid - lo)
                    short_score = max(0, min(100, 100 - (dist_lo / (lo*0.001)) * 100)) if lo > 0 else 0

                radar_data.append({
                    "symbol": "XAUUSD",
                    "label": "Oro (Asian Breakout)",
                    "long_score": round(long_score, 1),
                    "short_score": round(short_score, 1),
                    "in_window": LONDON_START_H <= now.hour < LONDON_END_H,
                    "details": f"Range: {hi:.2f} - {lo:.2f}" if hi > 0 else "Calculando rango..."
                })
    except: pass

    # 2. EURUSD (Mean Reversion)
    try:
        symbol = find_symbol("EURUSD")
        if symbol:
            df = get_candles(symbol, mt5.TIMEFRAME_H1, 100)
            if not df.empty:
                df = strat_eur.calculate_indicators(df)
                last = df.iloc[-1]
                rsi = float(last['rsi'])
                adx = float(last['adx'])
                close = float(last['close'])
                bb_l, bb_u = float(last['bb_lower']), float(last['bb_upper'])
                
                # Long: RSI < 30, Price < BB_Lower, ADX < 25
                l_rsi_score = max(0, min(100, (35 - rsi) / 10 * 100))
                l_bb_score = max(0, min(100, (bb_l * 1.001 - close) / (bb_l * 0.002) * 100))
                l_score = (l_rsi_score * 0.5 + l_bb_score * 0.5) if adx < 25 else 0
                
                # Short: RSI > 70, Price > BB_Upper, ADX < 25
                s_rsi_score = max(0, min(100, (rsi - 65) / 10 * 100))
                s_bb_score = max(0, min(100, (close - bb_u * 0.999) / (bb_u * 0.002) * 100))
                s_score = (s_rsi_score * 0.5 + s_bb_score * 0.5) if adx < 25 else 0

                radar_data.append({
                    "symbol": "EURUSD",
                    "label": "EURUSD (Mean Reversion)",
                    "long_score": round(l_score, 1),
                    "short_score": round(s_score, 1),
                    "details": f"RSI: {rsi:.1f} | ADX: {adx:.1f}"
                })
    except: pass

    return radar_data

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "last_ranges": {},
        "trades_today": 0,
        "pnl_today": 0.0,
        "virtual_trades_today": 0,
        "virtual_pnl_today": 0.0,
        "last_trade_date": "",
        "daily_summary_sent": "",
    }

# ─────────────────────────────────────────────────────────────────────────────
# CONEXIÓN Y MERCADO
# ─────────────────────────────────────────────────────────────────────────────

def connect_mt5() -> bool:
    if not mt5.initialize():
        logger.error(f"❌ No se pudo conectar a MT5: {mt5.last_error()}")
        return False
    info = mt5.account_info()
    if info is None:
        return False
    logger.success(f"✅ Conectado a MT5 | Cuenta: {info.login} | Balance: ${info.balance:,.2f}")
    return True

def ensure_connected() -> bool:
    try:
        if mt5.account_info() is not None: return True
    except: pass
    logger.warning("⚠️ Conexión perdida. Reconectando...")
    for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
        try: mt5.shutdown()
        except: pass
        time.sleep(RECONNECT_DELAY_SECS)
        if connect_mt5(): return True
    return False

def get_candles(symbol: str, timeframe, count: int = 200) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0: return pd.DataFrame()
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    return df

# ─────────────────────────────────────────────────────────────────────────────
# ESTRATEGIAS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeSetup:
    signal: str
    entry: float
    sl: float
    tp: float
    range_size: float = 0.0

def get_signal_asian_breakout(symbol: str, base_name: str) -> TradeSetup | None:
    now = datetime.now(timezone.utc)
    config = SYMBOL_CONFIGS[base_name]
    if SKIP_MONDAY and now.weekday() == 0: return None
    if not (LONDON_START_H <= now.hour < LONDON_END_H): return None

    df_15m = get_candles(symbol, mt5.TIMEFRAME_M15, 200)
    if df_15m.empty: return None

    today = now.date()
    asian = df_15m[(df_15m.index.date == today) & (df_15m.index.hour >= ASIAN_START_H) & (df_15m.index.hour < ASIAN_END_H)]
    if len(asian) < 4: return None

    hi, lo = float(asian["high"].max()), float(asian["low"].min())
    rng = hi - lo
    if rng < config["min_range"] or rng > config["max_range"]: return None

    rates_1h = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 100)
    if rates_1h is None: return None
    df_1h = pd.DataFrame(rates_1h)
    ema50 = df_1h['close'].ewm(span=50, adjust=False).mean().iloc[-1]

    london = df_15m[(df_15m.index.date == today) & (df_15m.index.hour >= LONDON_START_H) & (df_15m.index.hour < LONDON_END_H)]
    if len(london) > MAX_ENTRY_CANDLES: return None

    for _, candle in london.iterrows():
        close = float(candle["close"])
        if close > hi and close > ema50:
            return TradeSetup("LONG", close, lo - lo*config["sl_buffer"], close + rng*config["tp_mult"], rng)
        elif close < lo and close < ema50:
            return TradeSetup("SHORT", close, hi + hi*config["sl_buffer"], close - rng*config["tp_mult"], rng)
    return None

def get_signal_mean_reversion(symbol: str, base_name: str) -> TradeSetup | None:
    config = SYMBOL_CONFIGS[base_name]
    df = get_candles(symbol, config["timeframe"], 100)
    if df.empty: return None
    
    df = strat_eur.calculate_indicators(df)
    res = strat_eur.check_signals(df)
    if res:
        sig, entry, sl, tp = res
        return TradeSetup(sig, entry, sl, tp)
    return None

# ─────────────────────────────────────────────────────────────────────────────
# EJECUCIÓN (Live vs Virtual)
# ─────────────────────────────────────────────────────────────────────────────

def calc_lot_size(symbol: str, sl_dist: float, risk_pct: float) -> float:
    """Calcula el tamaño de lote basado en el riesgo y la distancia del SL."""
    acct = mt5.account_info()
    if not acct:
        return 0.01
    risk_amount = acct.balance * (risk_pct / 100)
    sym_info = mt5.symbol_info(symbol)
    if not sym_info or sl_dist <= 0:
        return 0.01
    # Valor por punto × volumen = profit por punto
    tick_value = sym_info.trade_tick_value
    tick_size = sym_info.trade_tick_size
    if tick_value <= 0 or tick_size <= 0:
        return 0.01
    sl_ticks = sl_dist / tick_size
    lot = risk_amount / (sl_ticks * tick_value)
    # Redondear al step del lote y clamp
    lot_step = sym_info.volume_step
    lot = max(sym_info.volume_min, min(sym_info.volume_max, round(lot / lot_step) * lot_step))
    return round(lot, 2)


def execute_trade(symbol: str, base_name: str, setup: TradeSetup, risk_pct: float, state: dict):
    config = SYMBOL_CONFIGS[base_name]
    is_live = config.get("live", False)
    
    label = "LIVE 💰" if is_live else "TEST 🧪"
    logger.info(f"[{label}] Señal {setup.signal} en {symbol} detectada")

    if is_live:
        # Ejecución real en MT5
        sl_dist = abs(setup.entry - setup.sl)
        lot = calc_lot_size(symbol, sl_dist, risk_pct)
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": mt5.ORDER_TYPE_BUY if setup.signal == "LONG" else mt5.ORDER_TYPE_SELL,
            "price": mt5.symbol_info_tick(symbol).ask if setup.signal == "LONG" else mt5.symbol_info_tick(symbol).bid,
            "sl": round(setup.sl, 2),
            "tp": round(setup.tp, 2),
            "magic": 123456,
            "comment": "XAU-LIVE-v5",
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            tg.notify_trade_opened(symbol, setup.signal, setup.entry, setup.sl, setup.tp, lot, risk_pct)
            state["trades_today"] += 1
            save_state(state)
            return True
        else:
            err_msg = f"Error enviando orden: {res.retcode if res else 'None'}" 
            logger.error(err_msg)
            tg.notify_error(err_msg)
    else:
        # VIRTUAL PAPER TRADING
        # Solo notificamos por Telegram y guardamos en estado virtual
        tg._send_message(f"🧪 <b>TEST TRADE</b>\n{symbol} {setup.signal}\nEntrada: {setup.entry:.5f}\nSL: {setup.sl:.5f}\nTP: {setup.tp:.5f}")
        logger.success(f"🧪 [VIRTUAL] Trade abierto en {symbol}")
        
        if "virtual_positions" not in state: state["virtual_positions"] = []
        state["virtual_positions"].append({
            "symbol": symbol,
            "base_name": base_name,
            "signal": setup.signal,
            "entry": setup.entry,
            "sl": setup.sl,
            "tp": setup.tp,
            "time": datetime.now(timezone.utc).isoformat()
        })
        state["virtual_trades_today"] += 1
        save_state(state)
        return True
    return False

def manage_positions(state: dict):
    now = datetime.now(timezone.utc)
    
    # 1. Gestionar posiciones reales en MT5 (Break-Even + Trailing + EOD)
    positions = mt5.positions_get()
    if positions:
        for pos in positions:
            # Solo gestionar trades de nuestro bot (magic 123456)
            if pos.magic != 123456:
                continue
            
            symbol = pos.symbol
            is_long = pos.type == mt5.POSITION_TYPE_BUY
            entry = pos.price_open
            current_sl = pos.sl
            current_tp = pos.tp
            tick = mt5.symbol_info_tick(symbol)
            if not tick:
                continue
            
            curr_price = tick.bid if is_long else tick.ask
            sl_dist = abs(entry - current_sl) if current_sl > 0 else 0
            
            if sl_dist <= 0:
                continue
            
            # ── Cierre EOD (16:00 UTC) ─────────────────────────────
            if now.hour >= EOD_CLOSE_H:
                close_request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": pos.volume,
                    "type": mt5.ORDER_TYPE_SELL if is_long else mt5.ORDER_TYPE_BUY,
                    "position": pos.ticket,
                    "price": curr_price,
                    "magic": 123456,
                    "comment": "EOD-CLOSE",
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                res = mt5.order_send(close_request)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    pnl = pos.profit
                    tg.notify_eod_close(symbol, pnl)
                    logger.info(f"⏰ EOD cierre {symbol} | PnL: ${pnl:.2f}")
                continue
            
            # ── Break-Even: mover SL a entrada cuando ganancia >= 1R ──
            profit_dist = (curr_price - entry) if is_long else (entry - curr_price)
            be_triggered = profit_dist >= (sl_dist * BE_TRIGGER_R)
            sl_at_be = abs(current_sl - entry) < (sl_dist * 0.1)  # ya está en BE
            
            if be_triggered and not sl_at_be:
                new_sl = entry + (0.5 if is_long else -0.5)  # Pequeño buffer
                modify_request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "symbol": symbol,
                    "position": pos.ticket,
                    "sl": round(new_sl, 2),
                    "tp": current_tp,
                    "magic": 123456,
                }
                res = mt5.order_send(modify_request)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    tg.notify_break_even(symbol, new_sl)
                    logger.info(f"🛡️ BE activado {symbol} | SL → {new_sl:.2f}")
                continue
            
            # ── Trailing Stop: perseguir precio a 0.5× rango ──────
            if sl_at_be or (current_sl > entry if is_long else current_sl < entry):
                trail_dist = sl_dist * TRAIL_DISTANCE_MULT
                if is_long:
                    new_trail_sl = curr_price - trail_dist
                    if new_trail_sl > current_sl:
                        modify_request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "symbol": symbol,
                            "position": pos.ticket,
                            "sl": round(new_trail_sl, 2),
                            "tp": current_tp,
                            "magic": 123456,
                        }
                        res = mt5.order_send(modify_request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            tg.notify_trailing_stop(symbol, new_trail_sl)
                            logger.info(f"📈 Trailing {symbol} | SL → {new_trail_sl:.2f}")
                else:
                    new_trail_sl = curr_price + trail_dist
                    if new_trail_sl < current_sl:
                        modify_request = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "symbol": symbol,
                            "position": pos.ticket,
                            "sl": round(new_trail_sl, 2),
                            "tp": current_tp,
                            "magic": 123456,
                        }
                        res = mt5.order_send(modify_request)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            tg.notify_trailing_stop(symbol, new_trail_sl)
                            logger.info(f"📈 Trailing {symbol} | SL → {new_trail_sl:.2f}")

    # 2. Gestionar posiciones virtuales (Paper Trading)
    if "virtual_positions" not in state: state["virtual_positions"] = []
    active_virtual = []
    
    for pos in state["virtual_positions"]:
        symbol = pos["symbol"]
        tick = mt5.symbol_info_tick(symbol)
        if not tick: 
            active_virtual.append(pos)
            continue
            
        curr = tick.bid if pos["signal"] == "LONG" else tick.ask
        hit_tp = (pos["signal"] == "LONG" and curr >= pos["tp"]) or (pos["signal"] == "SHORT" and curr <= pos["tp"])
        hit_sl = (pos["signal"] == "LONG" and curr <= pos["sl"]) or (pos["signal"] == "SHORT" and curr >= pos["sl"])
        
        if hit_tp or hit_sl:
            res = "WIN ✅" if hit_tp else "LOSS ❌"
            pnl = 1.0 if hit_tp else -1.0
            tg._send_message(f"🧪 <b>TEST CERRADO</b>\n{symbol}\nResultado: {res}\nPrecio: {curr:.5f}")
            logger.info(f"🧪 [VIRTUAL] {symbol} cerrado: {res}")
            state["virtual_pnl_today"] += pnl
        else:
            active_virtual.append(pos)
            
    state["virtual_positions"] = active_virtual
    save_state(state)

# ─────────────────────────────────────────────────────────────────────────────
# LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run_bot():
    if not connect_mt5(): return
    state = load_state()
    active_symbols = {bn: find_symbol(bn) for bn in SYMBOL_CONFIGS if find_symbol(bn)}
    
    tg.notify_bot_started(list(active_symbols.keys()), 1.5)

    while True:
        if not ensure_connected(): break
        
        manage_positions(state)
        
        for base_name, symbol in active_symbols.items():
            config = SYMBOL_CONFIGS[base_name]
            
            # Solo buscar entrada si no hay posición (real o virtual según corresponda)
            has_pos = False
            if config.get("live"):
                has_pos = len(mt5.positions_get(symbol=symbol, magic=123456) or []) > 0
            else:
                has_pos = any(p["symbol"] == symbol for p in state.get("virtual_positions", []))
                
            if not has_pos:
                setup = None
                if config["strategy"] == "ASIAN_BREAKOUT":
                    setup = get_signal_asian_breakout(symbol, base_name)
                elif config["strategy"] == "MEAN_REVERSION":
                    setup = get_signal_mean_reversion(symbol, base_name)
                    
                if setup:
                    execute_trade(symbol, base_name, setup, 1.5, state)
        
        save_state(state) # Actualizar estado para el dashboard
        time.sleep(60)

def find_symbol(base_name: str) -> str | None:
    for name in SYMBOL_CONFIGS[base_name].get("aliases", [base_name]):
        if mt5.symbol_info(name): return name
    return None

if __name__ == "__main__":
    run_bot()
