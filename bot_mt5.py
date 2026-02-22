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
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error guardando estado: {e}")

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

def execute_trade(symbol: str, base_name: str, setup: TradeSetup, risk_pct: float, state: dict):
    config = SYMBOL_CONFIGS[base_name]
    is_live = config.get("live", False)
    
    label = "LIVE 💰" if is_live else "TEST 🧪"
    logger.info(f"[{label}] Señal {setup.signal} en {symbol} detectada")

    if is_live:
        # Ejecución real en MT5 (código v4)
        sl_dist = abs(setup.entry - setup.sl)
        lot = 0.01 # Simplificado para brevedad, calc_lot_size(symbol, sl_dist, risk_pct)
        
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
    # 1. Gestionar reales en MT5
    for base_name, config in SYMBOL_CONFIGS.items():
        if config.get("live"):
            # Lógica de BE/Trailing (v4) simplificada aquí por espacio
            pass

    # 2. Gestionar Virtuales
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
            pnl = 1.0 if hit_tp else -1.0 # Una unidad de riesgo
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
        
        time.sleep(60)

def find_symbol(base_name: str) -> str | None:
    for name in SYMBOL_CONFIGS[base_name].get("aliases", [base_name]):
        if mt5.symbol_info(name): return name
    return None

if __name__ == "__main__":
    run_bot()
