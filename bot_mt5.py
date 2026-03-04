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
from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict

# Forzar codificación UTF-8 para evitar errores en terminales Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except: pass

import logger
import telegram_notify as tg
import strategy_eurusd as strat_eur
import numpy as np
from dotenv import load_dotenv

# Cargar variables de entorno (.env)
load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# INDICADORES PUROS (sin pandas_ta, compatible con cualquier Python)
# ─────────────────────────────────────────────────────────────────────────────

def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()

def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(window=length).mean()
    loss  = (-delta.clip(upper=0)).rolling(window=length).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=length).mean()

def _adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    up   = high.diff()
    down = -low.diff()
    pdm  = pd.Series(0.0, index=high.index)
    mdm  = pd.Series(0.0, index=high.index)
    pdm[(up > down) & (up > 0)]   = up[(up > down) & (up > 0)]
    mdm[(down > up) & (down > 0)] = down[(down > up) & (down > 0)]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr14 = tr.rolling(length).mean()
    pdi   = 100 * pdm.rolling(length).mean() / atr14.replace(0, np.nan)
    mdi   = 100 * mdm.rolling(length).mean() / atr14.replace(0, np.nan)
    dx    = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.rolling(length).mean()

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE SÍMBOLOS Y ESTRATEGIAS
# ─────────────────────────────────────────────────────────────────────────────

SYMBOL_CONFIGS = {
    "XAUUSD": {
        "aliases":     ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"],
        "strategy":    "ENSEMBLE",
        "live":        True,
        "timeframe":   mt5.TIMEFRAME_H1,
        "adx_min":     20.0,
    },
    "XAGUSD": {
        "aliases":     ["XAGUSD", "SILVER", "XAGUSDm", "XAGUSD.a"],
        "strategy":    "ENSEMBLE",
        "live":        True,
        "timeframe":   mt5.TIMEFRAME_H1,
        "adx_min":     20.0,
    },
    "EURUSD": {
        "aliases":     ["EURUSD", "EURUSDm", "EURUSD.a"],
        "strategy":    "ENSEMBLE",
        "live":        True,
        "timeframe":   mt5.TIMEFRAME_H1,
        "adx_min":     20.0,
    },
    "GBPUSD": {
        "aliases":     ["GBPUSD", "GBPUSDm", "GBPUSD.a"],
        "strategy":    "ENSEMBLE",
        "live":        True,
        "timeframe":   mt5.TIMEFRAME_H1,
        "adx_min":     20.0,
    },
    "USDJPY": {
        "aliases":     ["USDJPY", "USDJPYm", "USDJPY.a"],
        "strategy":    "ENSEMBLE",
        "live":        True,
        "timeframe":   mt5.TIMEFRAME_H1,
        "adx_min":     20.0,
    },
    "AUDUSD": {
        "aliases":     ["AUDUSD", "AUDUSDm", "AUDUSD.a"],
        "strategy":    "ENSEMBLE",
        "live":        True,
        "timeframe":   mt5.TIMEFRAME_H1,
        "adx_min":     20.0,
    },
    "USDCAD": {
        "aliases":     ["USDCAD", "USDCADm", "USDCAD.a"],
        "strategy":    "ENSEMBLE",
        "live":        True,
        "timeframe":   mt5.TIMEFRAME_H1,
        "adx_min":     20.0,
    },
    "USDCHF": {
        "aliases":     ["USDCHF", "USDCHFm", "USDCHF.a"],
        "strategy":    "ENSEMBLE",
        "live":        True,
        "timeframe":   mt5.TIMEFRAME_H1,
        "adx_min":     20.0,
    },
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
BE_TRIGGER_R       = 0.7
TRAIL_DISTANCE_MULT = 0.4
EOD_CLOSE_H        = 16

# 🛡️ PROTECCIÓN PROP FIRM (Parámetros configurables via .env)
PROP_FIRM = {
    "starting_balance": float(os.getenv("PROP_STARTING_BALANCE", 100000.0)),
    "daily_dd_limit":   float(os.getenv("PROP_DAILY_DD_LIMIT", 0.04)),
    "max_dd_limit":     float(os.getenv("PROP_MAX_DD_LIMIT", 0.08)),
    "base_risk":        float(os.getenv("PROP_BASE_RISK", 0.45)),
    "reduced_risk":     float(os.getenv("PROP_REDUCED_RISK", 0.05)),
    "max_consecutive_losses": int(os.getenv("PROP_MAX_LOSSES", 2)),
}

STATE_FILE     = "bot_state_mt5_v5.json"
TRADE_HISTORY_FILE = "trade_history.csv"  # Historial persistente de 30 días
MAX_RECONNECT_ATTEMPTS = 10
RECONNECT_DELAY_SECS   = 30
DAILY_SUMMARY_HOUR     = 17

# ─────────────────────────────────────────────────────────────────────────────
# ESTADO PERSISTENTE
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# HISTORIAL PERSISTENTE DE TRADES (CSV, 30 días)
# ─────────────────────────────────────────────────────────────────────────────

def save_trade_history(trade: dict) -> bool:
    """
    Guarda el trade en el CSV histórico SOLO si no existe ya (por ticket).
    Retorna True si fue guardado como nuevo, False si ya existía (duplicado).
    """
    fieldnames = [
        "ticket", "symbol", "direction", "volume",
        "time_open", "price_open", "sl", "tp",
        "time_close", "price_close", "pnl", "balance_after"
    ]
    ticket_id = str(trade.get("ticket", ""))
    
    # ✅ CHECK DE DUPLICADO: leer tickets existentes antes de escribir
    existing_tickets = set()
    if Path(TRADE_HISTORY_FILE).exists():
        try:
            with open(TRADE_HISTORY_FILE, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    existing_tickets.add(str(row.get("ticket", "")))
        except Exception:
            pass
    
    if ticket_id and ticket_id in existing_tickets:
        return False  # Ya existe, no duplicar
    
    # Añadir nueva fila solo si es nuevo
    file_exists = Path(TRADE_HISTORY_FILE).exists()
    with open(TRADE_HISTORY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({k: trade.get(k, "") for k in fieldnames})
    
    # Purgar registros > 30 días
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    try:
        with open(TRADE_HISTORY_FILE, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        rows = [r for r in rows if r.get("time_close", "") >= cutoff.isoformat()[:10]]
        with open(TRADE_HISTORY_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except Exception:
        pass
    return True

def load_trade_history(days: int = 30) -> list:
    """Carga el historial de trades de los últimos N días."""
    if not Path(TRADE_HISTORY_FILE).exists():
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = []
    try:
        with open(TRADE_HISTORY_FILE, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("time_close", "") >= cutoff.isoformat()[:10]:
                    result.append(row)
    except Exception:
        pass
    return result


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

        # Obtener historial de trades cerrados hoy con datos completos
        try:
            today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            now_utc = datetime.now(timezone.utc)
            deals = mt5.history_deals_get(today, now_utc)
            orders = mt5.history_orders_get(today, now_utc)
            
            # Mapear positions para obtener datos de apertura
            pos_map = {}  # ticket -> order data
            if orders:
                for o in orders:
                    pos_map[o.position_id] = o
            
            closed = []
            if deals:
                for d in deals:
                    if d.entry == 1 and d.symbol:  # 1 = cierre de posición
                        open_order = pos_map.get(d.position_id)
                        time_open = ""
                        price_open = d.price  # fallback
                        sl = 0.0
                        tp = 0.0
                        
                        if open_order:
                            time_open = str(datetime.fromtimestamp(open_order.time_setup, tz=timezone.utc))
                            sl = round(open_order.sl, 2)
                            tp = round(open_order.tp, 2)
                            # Buscar el deal de apertura para precio real
                            open_deals = mt5.history_deals_get(position=d.position_id)
                            if open_deals:
                                for od in open_deals:
                                    if od.entry == 0:  # 0 = apertura
                                        price_open = round(od.price, 5)
                                        time_open = str(datetime.fromtimestamp(od.time, tz=timezone.utc))
                                        break
                        
                        trade_record = {
                            "ticket": d.position_id,
                            "time_close": str(datetime.fromtimestamp(d.time, tz=timezone.utc)),
                            "time_open": time_open,
                            "symbol": d.symbol,
                            "direction": "LONG" if d.type == 0 else "SHORT",
                            "volume": round(d.volume, 2),
                            "price_open": price_open,
                            "price_close": round(d.price, 5),
                            "sl": sl,
                            "tp": tp,
                            "pnl": round(d.profit, 2),
                            "balance_after": round(acct.balance if acct else 0, 2)
                        }
                        closed.append(trade_record)
                        # Guardar en CSV solo si es un ticket NUEVO (evita duplicados en cada save_state)
                        ticket_key = str(d.position_id)
                        saved_tickets = state.setdefault("_saved_tickets", [])
                        if ticket_key not in saved_tickets:
                            if save_trade_history(trade_record):
                                saved_tickets.append(ticket_key)
                                logger.info(f"💾 Historial guardado: {d.symbol} #{ticket_key} PnL={trade_record['pnl']}")
                        # Limpiar tickets de días anteriores del tracker en memoria
                        if len(saved_tickets) > 500:
                            state["_saved_tickets"] = saved_tickets[-200:]
            
            state["closed_trades_today"] = closed
            # Incluir últimos 30 días en el estado para el dashboard
            state["trade_history"] = load_trade_history(30)
        except Exception as e:
            logger.error(f"Error cargando historial: {e}")
            state["closed_trades_today"] = []
            state["trade_history"] = []

        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error guardando estado: {e}")

def calculate_radar() -> list:
    """Calcula la proximidad de señales para todos los símbolos activos."""
    radar_data = []
    
    for sym_key, config in SYMBOL_CONFIGS.items():
        if not config.get("live"): continue
        
        try:
            symbol = find_symbol(sym_key)
            if not symbol: continue
            
            df = get_candles(symbol, config["timeframe"], 100)
            if df.empty: continue
            
            # Cálculo de indicadores base
            df['ema'] = _ema(df['close'], 50)
            df['rsi'] = _rsi(df['close'], 14)
            df['adx'] = _adx(df['high'], df['low'], df['close'])
            
            last = df.iloc[-1]
            rsi = float(last['rsi'])
            ema = float(last['ema'])
            close = float(last['close'])
            adx = float(last['adx'])
            adx_min = config.get("adx_min", 20.0)
            
            # ICT Signal (Principalmente para Oro y Mayores)
            ict = get_signal_ict_silver_bullet(symbol, sym_key)
            ict_label = f" | ICT: {ict.signal}" if ict else ""
            
            # Trend Scores
            l_score = 0
            if close > ema and adx >= adx_min:
                l_score = max(0, min(100, (rsi - 45) / 10 * 100))
            
            s_score = 0
            if close < ema and adx >= adx_min:
                s_score = max(0, min(100, (55 - rsi) / 10 * 100))
            
            # Sobrescribir con 100% si hay ICT activo
            final_long = 100 if (ict and ict.signal == "LONG") else l_score
            final_short = 100 if (ict and ict.signal == "SHORT") else s_score
            
            radar_data.append({
                "symbol": sym_key,
                "label": f"{sym_key} ({config['strategy']})",
                "long_score": round(final_long, 1),
                "short_score": round(final_short, 1),
                "details": f"RSI: {rsi:.1f} | ADX: {adx:.1f}{ict_label}"
            })
        except:
            continue
            
    return radar_data

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


class PropFirmGuard:
    """Protección inteligente contra violaciones de drawdown en prop firms."""
    
    def __init__(self, state: dict):
        acct = mt5.account_info()
        self.balance = acct.balance if acct else PROP_FIRM["starting_balance"]
        self.equity = acct.equity if acct else self.balance
        
        # Balance de referencia (el más alto registrado o el inicial)
        self.starting_balance = state.get("prop_starting_balance", PROP_FIRM["starting_balance"])
        self.peak_balance = state.get("prop_peak_balance", self.starting_balance)
        self.peak_balance = max(self.peak_balance, self.balance)
        
        # Balance al inicio del día
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if state.get("prop_day") != today:
            state["prop_day"] = today
            state["prop_day_start_balance"] = self.balance
            state["consecutive_losses"] = state.get("consecutive_losses", 0)
        self.day_start_balance = state.get("prop_day_start_balance", self.balance)
        
        # Pérdidas consecutivas
        self.consecutive_losses = state.get("consecutive_losses", 0)
        
        # Calcular drawdowns actuales
        self.daily_dd = (self.day_start_balance - self.equity) / self.day_start_balance if self.day_start_balance > 0 else 0
        self.total_dd = (self.peak_balance - self.equity) / self.peak_balance if self.peak_balance > 0 else 0
        
        # Guardar en estado
        state["prop_peak_balance"] = self.peak_balance
        state["prop_starting_balance"] = self.starting_balance
    
    def can_trade(self) -> tuple[bool, str]:
        """Verifica si es seguro abrir un nuevo trade."""
        dd_daily_limit = PROP_FIRM["daily_dd_limit"]
        dd_max_limit = PROP_FIRM["max_dd_limit"]
        
        if self.daily_dd >= dd_daily_limit:
            return False, f"🚨 DAILY DD alcanzado: {self.daily_dd:.2%} >= {dd_daily_limit:.0%}"
        
        if self.total_dd >= dd_max_limit:
            return False, f"🚨 MAX DD alcanzado: {self.total_dd:.2%} >= {dd_max_limit:.0%}"
        
        return True, "OK"
    
    def get_risk_pct(self) -> float:
        """Calcula el riesgo dinámico según la situación."""
        base = PROP_FIRM["base_risk"]
        reduced = PROP_FIRM["reduced_risk"]
        
        # Reducir riesgo si acumulamos pérdidas consecutivas
        if self.consecutive_losses >= PROP_FIRM["max_consecutive_losses"]:
            logger.warning(f"⚠️ {self.consecutive_losses} pérdidas seguidas → Riesgo reducido a {reduced}%")
            return reduced
        
        # Reducir riesgo si el daily DD supera el 50% del límite
        if self.daily_dd >= PROP_FIRM["daily_dd_limit"] * 0.5:
            logger.warning(f"⚠️ Daily DD al {self.daily_dd:.1%} → Riesgo reducido a {reduced}%")
            return reduced
        
        # Reducir riesgo si el total DD supera el 50% del límite
        if self.total_dd >= PROP_FIRM["max_dd_limit"] * 0.5:
            logger.warning(f"⚠️ Total DD al {self.total_dd:.1%} → Riesgo reducido a {reduced}%")
            return reduced
        
        return base
    
    def get_status_dict(self) -> dict:
        """Estado para el dashboard."""
        return {
            "daily_dd": round(self.daily_dd * 100, 2),
            "daily_dd_limit": PROP_FIRM["daily_dd_limit"] * 100,
            "total_dd": round(self.total_dd * 100, 2),
            "total_dd_limit": PROP_FIRM["max_dd_limit"] * 100,
            "current_risk": self.get_risk_pct(),
            "consecutive_losses": self.consecutive_losses,
            "peak_balance": self.peak_balance,
            "day_start_balance": self.day_start_balance,
            "can_trade": self.can_trade()[0],
            "status_msg": self.can_trade()[1],
        }

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
    
    # Nuevo Filtro Francotirador: ADX > 30
    adx_series = _adx(df_1h['high'], df_1h['low'], df_1h['close'])
    adx_val = adx_series.iloc[-1]
    if adx_val < config.get("adx_min", 20.0): return None

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

def get_signal_indicator_trend(symbol: str, base_name: str) -> TradeSetup | None:
    """Estrategia Potente basada en EMA 50 + RSI 14 (Trend Following)."""
    now = datetime.now(timezone.utc)
    
    # 🕒 FILTRO DE HORA: Evitar entrar después de las 15:00 UTC para no cerrar inmediatamente a las 16:00
    if now.hour >= EOD_CLOSE_H:
        return None

    config = SYMBOL_CONFIGS[base_name]
    df = get_candles(symbol, config["timeframe"], 100)
    if df.empty: return None
    
    # Calcular Indicadores (EMA, RSI, ADX, ATR)
    df['ema'] = _ema(df['close'], 50)
    df['rsi'] = _rsi(df['close'], 14)
    df['adx'] = _adx(df['high'], df['low'], df['close'])
    df['atr'] = _atr(df['high'], df['low'], df['close'])
    
    last = df.iloc[-1]
    if last['adx'] < config.get("adx_min", 20.0): return None
    
    # Señal LONG: Precio > EMA50 y RSI > 55
    if last['close'] > last['ema'] and last['rsi'] > 55:
        entry = float(last['close'])
        sl = entry - float(last['atr']) * 2.5
        tp = entry + float(last['atr']) * 5.0
        return TradeSetup("LONG", entry, sl, tp)
        
    # Señal SHORT: Precio < EMA50 y RSI < 45
    elif last['close'] < last['ema'] and last['rsi'] < 45:
        entry = float(last['close'])
        sl = entry + float(last['atr']) * 2.5
        tp = entry - float(last['atr']) * 5.0
        return TradeSetup("SHORT", entry, sl, tp)
        
    return None

def get_signal_ict_silver_bullet(symbol: str, base_name: str) -> TradeSetup | None:
    """Estrategia ICT Silver Bullet (10-11 AM NY). Especialidad: Oro."""
    now = datetime.now(timezone.utc)
    
    # Ventana Silver Bullet (15:00 - 16:00 UTC)
    if not (15 <= now.hour < 16):
        return None

    # Necesitamos 5m para el detalle del FVG
    df_5m = get_candles(symbol, mt5.TIMEFRAME_M5, 100)
    if df_5m.empty: return None

    # 1. Definir liquidez previa (8:30 - 10:00 AM NY / 13:30 - 15:00 UTC)
    today = now.date()
    pre_market = df_5m[(df_5m.index.date == today) & (df_5m.index.hour >= 13) & (df_5m.index.minute >= 30) | 
                       (df_5m.index.date == today) & (df_5m.index.hour == 14)]
    
    # Filtro más simple para liquidez pre-sesión
    pre_df = df_5m[(df_5m.index.date == today) & (df_5m.index.hour >= 13) & (df_5m.index.hour < 15)]
    if pre_df.empty: return None
    
    daily_high = float(pre_df["high"].max())
    daily_low = float(pre_df["low"].min())

    # 2. Buscar FVG en las últimas velas
    c1 = df_5m.iloc[-3]
    c2 = df_5m.iloc[-2]
    c3 = df_5m.iloc[-1]
    
    fvg_bull = c3['low'] > c1['high']
    fvg_bear = c3['high'] < c1['low']
    
    swept_high = c3['high'] > daily_high
    swept_low = c3['low'] < daily_low

    if swept_low and fvg_bull:
        entry = float(c3['close'])
        sl = float(c2['low'])
        tp = entry + abs(entry - sl) * 2.0
        logger.info(f"🎯 ICT Silver Bullet LONG detectado en {symbol}")
        return TradeSetup("LONG", entry, sl, tp)
    
    elif swept_high and fvg_bear:
        entry = float(c3['close'])
        sl = float(c2['high'])
        tp = entry - abs(sl - entry) * 2.0
        logger.info(f"🎯 ICT Silver Bullet SHORT detectado en {symbol}")
        return TradeSetup("SHORT", entry, sl, tp)

    return None

def get_signal_ensemble(symbol: str, base_name: str) -> TradeSetup | None:
    """Combina ICT Silver Bullet y Indicator Trend (Prioriza ICT)."""
    # 1. Intentar ICT (Precisión Quirúrgica)
    setup = get_signal_ict_silver_bullet(symbol, base_name)
    if setup:
        return setup
    
    # 2. Si no hay ICT, usar la Tendencia Potente (Frecuencia)
    return get_signal_indicator_trend(symbol, base_name)

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
        
        # Detectar el mejor modo de ejecución (filling mode) soportado por el broker
        s_info = mt5.symbol_info(symbol)
        filling = mt5.ORDER_FILLING_IOC # Default
        if s_info:
            if s_info.filling_mode & 1: # SYMBOL_FILLING_FOK
                filling = mt5.ORDER_FILLING_FOK
            elif s_info.filling_mode & 2: # SYMBOL_FILLING_IOC
                filling = mt5.ORDER_FILLING_IOC

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
            "type_filling": filling,
        }
        res = mt5.order_send(request)
        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
            tg.notify_trade_opened(symbol, setup.signal, setup.entry, setup.sl, setup.tp, lot, risk_pct)
            state["trades_today"] += 1
            save_state(state)
            return True
        else:
            retcode = res.retcode if res else "None"
            
            # Mapeo de errores comunes para ayudar al usuario
            error_details = ""
            if retcode == 10031: error_details = " (Auto-trading desactivado en MT5)"
            elif retcode == 10018: error_details = " (Mercado cerrado o sin liquidez)"
            elif retcode == 10013: error_details = " (Invalid Request - Revisa parámetros)"
            
            err_msg = f"Error enviando orden: {retcode}{error_details}" 
            logger.error(err_msg)
            
            # Silenciamos en Telegram errores de mercado cerrado o auto-trading desactivado si ya se avisó
            # Pero la primera vez es bueno que el usuario sepa POR QUÉ falló
            silent_codes = [10018, 10027, mt5.TRADE_RETCODE_MARKET_CLOSED]
            if retcode not in silent_codes:
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
# FILTRO DE CORRELACIÓN USD
# ─────────────────────────────────────────────────────────────────────────────

# Pares donde USD es la divisa BASE (LONG = comprar USD)
USD_BASE_PAIRS  = {"USDJPY", "USDCAD", "USDCHF", "USDCNH"}
# Pares donde USD es la divisa COTIZADA (LONG = vender USD)
USD_QUOTE_PAIRS = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "XAUUSD", "XAGUSD"}

def get_usd_direction(symbol: str, trade_type: str) -> int:
    """
    Retorna la dirección neta del USD para este trade:
      +1 = LONG USD (apostamos alcista en el dólar)
      -1 = SHORT USD (apostamos bajista en el dólar)
       0 = sin exposición USD (par exótico, ni USD base ni cotización)
    """
    base_sym = symbol.upper()[:6]  # Normalizar (eliminar sufijos .a, m...)
    is_long  = (trade_type == mt5.POSITION_TYPE_BUY) if isinstance(trade_type, int) else (trade_type == "LONG")
    
    if any(base_sym.startswith(p[:6]) for p in USD_BASE_PAIRS):
        return +1 if is_long else -1   # USDXXX LONG = comprar USD
    if any(base_sym.startswith(p[:6]) for p in USD_QUOTE_PAIRS):
        return -1 if is_long else +1   # XXXUSD LONG = vender USD
    # Par sin USD (rareza)
    return 0

def get_net_usd_direction() -> int:
    """
    Calcula la dirección neta del USD a partir de las posiciones ABIERTAS
    en MT5 (solo trades del bot, magic=123456).
    Retorna:
      +1 si hay más peso LONG USD que SHORT USD
      -1 si hay más peso SHORT USD
       0 si no hay posiciones abiertas con USD
    """
    positions = mt5.positions_get() or []
    net = 0
    for p in positions:
        if p.magic != 123456:
            continue
        direction = get_usd_direction(p.symbol, p.type)
        net += direction
    if net > 0: return +1
    if net < 0: return -1
    return 0

def would_conflict_usd(base_name: str, signal: str) -> bool:
    """
    Devuelve True si el nuevo trade crea conflicto de correlación USD.
    Regla: si ya tenemos posiciones en dirección X del USD, NO abrir
    un trade en dirección opuesta.
    """
    # Primero, calcular la nueva dirección propuesta
    new_dir = get_usd_direction(base_name, signal)
    if new_dir == 0:
        return False  # Par sin USD: no aplica el filtro
    
    # Dirección agregada de posiciones ya abiertas
    existing_dir = get_net_usd_direction()
    if existing_dir == 0:
        return False  # No hay posiciones abiertas: sin conflicto
    
    # Conflicto si queremos ir en dirección opuesta al neto actual
    if new_dir != existing_dir:
        return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# LOOP
# ─────────────────────────────────────────────────────────────────────────────

def run_bot():
    if not connect_mt5(): return
    state = load_state()
    active_symbols = {bn: find_symbol(bn) for bn in SYMBOL_CONFIGS if find_symbol(bn)}
    
    tg.notify_bot_started(list(active_symbols.keys()), PROP_FIRM["base_risk"])

    while True:
        if not ensure_connected(): break
        
        manage_positions(state)
        
        # 🛡️ Prop Firm Guard
        guard = PropFirmGuard(state)
        state["prop_firm"] = guard.get_status_dict()
        
        can_trade, reason = guard.can_trade()
        if not can_trade:
            logger.warning(f"🛑 TRADING BLOQUEADO: {reason}")
            if not state.get("dd_alert_sent_today"):
                tg.notify_error(f"🛑 TRADING BLOQUEADO\n{reason}\nDaily DD: {guard.daily_dd:.2%}\nTotal DD: {guard.total_dd:.2%}")
                state["dd_alert_sent_today"] = True
            save_state(state)
            time.sleep(60)
            continue
        
        risk_pct = guard.get_risk_pct()
        
        for base_name, symbol in active_symbols.items():
            config = SYMBOL_CONFIGS[base_name]
            
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
                elif config["strategy"] == "INDICATOR_TREND":
                    setup = get_signal_indicator_trend(symbol, base_name)
                elif config["strategy"] == "ENSEMBLE":
                    setup = get_signal_ensemble(symbol, base_name)
                    
                if setup:
                    # 🔒 FILTRO DE CORRELACIÓN USD: Bloquear si el trade conflicta con posiciones abiertas
                    if config.get("live") and would_conflict_usd(base_name, setup.signal):
                        net_dir = "LONG" if get_net_usd_direction() > 0 else "SHORT"
                        logger.warning(f"⛔ [{base_name}] Bloqueado: conflicto USD ({setup.signal} vs posición neta {net_dir} USD)")
                    else:
                        execute_trade(symbol, base_name, setup, risk_pct, state)
        
        # Reset diario
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if state.get("last_trade_date") != today:
            state["last_trade_date"] = today
            state["trades_today"] = 0
            state["pnl_today"] = 0.0
            state["virtual_trades_today"] = 0
            state["virtual_pnl_today"] = 0.0
            state["dd_alert_sent_today"] = False
        
        save_state(state)
        time.sleep(60)

def find_symbol(base_name: str) -> str | None:
    for name in SYMBOL_CONFIGS[base_name].get("aliases", [base_name]):
        if mt5.symbol_info(name): return name
    return None

if __name__ == "__main__":
    run_bot()
