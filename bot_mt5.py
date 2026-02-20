"""
bot_mt5.py — Bot de Oro (XAUUSD) para MetaTrader 5
====================================================
Ejecuta la estrategia Asian Range Breakout directamente en MT5.
Funciona con cuentas demo y cuentas de prop firm (FTMO, etc.)

Uso:
    python bot_mt5.py                     # Demo con saldo virtual
    python bot_mt5.py --live              # Modo real (prop firm)
    python bot_mt5.py --lot 0.1           # Lote fijo
    python bot_mt5.py --risk 1.5          # Riesgo % por trade

Requisitos:
    - MetaTrader 5 debe estar ABIERTO y conectado
    - pip install MetaTrader5
"""

import MetaTrader5 as mt5
import pandas as pd
import time
import argparse
import csv
import os
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

import logger

# ─────────────────────────────────────────────────────────────────────────────
# PARÁMETROS DE LA ESTRATEGIA (Asian Range Breakout)
# ─────────────────────────────────────────────────────────────────────────────

# Configuración por símbolo
SYMBOL_CONFIGS = {
    "XAUUSD": {
        "aliases":     ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"],
        "min_range":   3.0,      # Rango mínimo USD
        "max_range":   20.0,     # Rango máximo USD
        "tp_mult":     2.5,      # TP = rango × 2.5
        "sl_buffer":   0.001,    # Buffer SL
    },
    "XAGUSD": {
        "aliases":     ["XAGUSD", "SILVER", "XAGUSDm", "XAGUSD.a"],
        "min_range":   0.15,     # Plata tiene rangos más pequeños
        "max_range":   1.50,     # Rango máximo
        "tp_mult":     2.5,
        "sl_buffer":   0.001,
    },
}

# Parámetros comunes Asian Breakout
ASIAN_START_H  = 0              # Inicio sesión asiática (UTC)
ASIAN_END_H    = 6              # Fin sesión asiática (UTC)
LONDON_START_H = 7              # Inicio ventana de entrada
LONDON_END_H   = 10             # Fin ventana de entrada
EMA_PERIOD     = 50             # EMA de tendencia (1H)
SKIP_MONDAY    = True           # No operar lunes
MAX_ENTRY_CANDLES = 4           # Máx velas para entrar en London

# Mejoras Prop Firm (v3)
BE_TRIGGER_R       = 1.0        # Break-even cuando ganancia = 1× riesgo
TRAIL_DISTANCE_MULT = 0.5       # Trailing stop a 0.5× rango
EOD_CLOSE_H        = 16         # Cierre forzado 16:00 UTC

# Gestión de riesgo
DEFAULT_RISK_PCT   = 1.5        # % del balance por operación
DEFAULT_LOT        = 0.01       # Lote mínimo por defecto

TRADE_LOG_FILE = "mt5_trades.csv"

# ─────────────────────────────────────────────────────────────────────────────
# CONEXIÓN A MT5
# ─────────────────────────────────────────────────────────────────────────────

def connect_mt5() -> bool:
    """Conecta a MetaTrader 5. MT5 debe estar abierto."""
    if not mt5.initialize():
        logger.error(f"❌ No se pudo conectar a MT5: {mt5.last_error()}")
        logger.info("   Asegúrate de que MetaTrader 5 esté ABIERTO.")
        return False

    info = mt5.account_info()
    if info is None:
        logger.error("❌ No se puede obtener info de la cuenta")
        return False

    logger.success(f"✅ Conectado a MT5")
    logger.info(f"   Cuenta:    {info.login}")
    logger.info(f"   Servidor:  {info.server}")
    logger.info(f"   Balance:   ${info.balance:,.2f}")
    logger.info(f"   Tipo:      {'Demo' if info.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else 'Real'}")
    return True


def find_symbol(base_name: str) -> str | None:
    """Busca un símbolo en MT5 probando aliases."""
    config = SYMBOL_CONFIGS.get(base_name, {})
    aliases = config.get("aliases", [base_name])
    for name in aliases:
        info = mt5.symbol_info(name)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(name, True)
            logger.info(f"   {base_name}: {name} (spread: {info.spread} pts)")
            return name
    logger.error(f"❌ No se encontró {base_name} en el broker")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# DATOS DE MERCADO
# ─────────────────────────────────────────────────────────────────────────────

def get_candles(symbol: str, timeframe, count: int = 200) -> pd.DataFrame:
    """Descarga velas históricas de MT5."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    return df


def get_ema(df: pd.DataFrame, period: int = 50) -> float:
    """Calcula la EMA actual."""
    if len(df) < period:
        return 0
    return df["close"].ewm(span=period, adjust=False).mean().iloc[-1]


# ─────────────────────────────────────────────────────────────────────────────
# LÓGICA DE LA ESTRATEGIA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TradeSetup:
    signal: str       # "LONG" o "SHORT"
    entry: float
    sl: float
    tp: float
    range_size: float


def check_asian_breakout(symbol: str, base_name: str) -> TradeSetup | None:
    """
    Verifica si hay señal de Asian Breakout.
    Retorna el setup si hay señal, None si no.
    """
    now = datetime.now(timezone.utc)
    config = SYMBOL_CONFIGS[base_name]

    # ── Filtro: No operar lunes
    if SKIP_MONDAY and now.weekday() == 0:
        return None

    # ── Filtro: Solo operar durante London (7-10 UTC)
    if not (LONDON_START_H <= now.hour < LONDON_END_H):
        return None

    # ── Obtener velas 15m del día
    df_15m = get_candles(symbol, mt5.TIMEFRAME_M15, 200)
    if df_15m.empty:
        return None

    today = now.date()

    # ── Calcular rango asiático de hoy
    asian = df_15m[
        (df_15m.index.date == today) &
        (df_15m.index.hour >= ASIAN_START_H) &
        (df_15m.index.hour < ASIAN_END_H)
    ]
    if len(asian) < 4:
        return None

    hi = float(asian["high"].max())
    lo = float(asian["low"].min())
    rng = hi - lo

    # ── Filtros de rango (por símbolo)
    if rng < config["min_range"] or rng > config["max_range"]:
        return None

    # ── Filtro: Tendencia EMA50 (1H)
    df_1h = get_candles(symbol, mt5.TIMEFRAME_H1, 100)
    if df_1h.empty:
        return None
    ema50 = get_ema(df_1h, EMA_PERIOD)

    # ── Buscar breakout en London
    london = df_15m[
        (df_15m.index.date == today) &
        (df_15m.index.hour >= LONDON_START_H) &
        (df_15m.index.hour < LONDON_END_H)
    ]
    if len(london) > MAX_ENTRY_CANDLES:
        return None

    tp_mult = config["tp_mult"]
    sl_buf = config["sl_buffer"]

    for _, candle in london.iterrows():
        close = float(candle["close"])

        if close > hi and close > ema50:
            sl = lo - lo * sl_buf
            tp = close + rng * tp_mult
            return TradeSetup("LONG", close, sl, tp, rng)

        elif close < lo and close < ema50:
            sl = hi + hi * sl_buf
            tp = close - rng * tp_mult
            return TradeSetup("SHORT", close, sl, tp, rng)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# EJECUCIÓN DE ÓRDENES
# ─────────────────────────────────────────────────────────────────────────────

def calc_lot_size(symbol: str, sl_distance: float, risk_pct: float) -> float:
    """Calcula el tamaño del lote basado en el riesgo."""
    info = mt5.account_info()
    sym_info = mt5.symbol_info(symbol)
    if not info or not sym_info:
        return DEFAULT_LOT

    risk_amount = info.balance * (risk_pct / 100)

    # Valor del pip/punto
    tick_value = sym_info.trade_tick_value
    tick_size = sym_info.trade_tick_size

    if tick_value == 0 or tick_size == 0 or sl_distance == 0:
        return DEFAULT_LOT

    # Lote = riesgo / (distancia_SL × valor_por_tick / tamaño_tick)
    lot = risk_amount / (sl_distance * tick_value / tick_size)

    # Redondear al step del lote
    lot_step = sym_info.volume_step
    lot = max(sym_info.volume_min, min(sym_info.volume_max, round(lot / lot_step) * lot_step))
    return round(lot, 2)


def open_trade(symbol: str, setup: TradeSetup, risk_pct: float) -> bool:
    """Abre una operación en MT5."""
    sl_distance = abs(setup.entry - setup.sl)
    lot = calc_lot_size(symbol, sl_distance, risk_pct)

    order_type = mt5.ORDER_TYPE_BUY if setup.signal == "LONG" else mt5.ORDER_TYPE_SELL

    # Obtener precio actual
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        logger.error(f"❌ No se puede obtener precio de {symbol}")
        return False

    price = tick.ask if setup.signal == "LONG" else tick.bid

    request = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    symbol,
        "volume":    lot,
        "type":      order_type,
        "price":     price,
        "sl":        round(setup.sl, 2),
        "tp":        round(setup.tp, 2),
        "deviation": 20,     # Slippage máximo en puntos
        "magic":     123456,  # ID del bot
        "comment":   "XAU-ARB-v3",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)

    if result is None:
        logger.error(f"❌ Error enviando orden: {mt5.last_error()}")
        return False

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        logger.error(f"❌ Orden rechazada: {result.retcode} — {result.comment}")
        return False

    arrow = "📈" if setup.signal == "LONG" else "📉"
    logger.success(
        f"{arrow} {setup.signal} ABIERTO | {symbol} | "
        f"Precio: {price:.2f} | Lote: {lot} | "
        f"SL: {setup.sl:.2f} | TP: {setup.tp:.2f}"
    )
    return True


def check_open_positions(symbol: str) -> list:
    """Devuelve las posiciones abiertas del bot en este símbolo."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    # Solo las del bot (magic number = 123456)
    return [p for p in positions if p.magic == 123456]


def close_position(position) -> bool:
    """Cierra una posición abierta."""
    tick = mt5.symbol_info_tick(position.symbol)
    if not tick:
        return False

    close_type = mt5.ORDER_TYPE_SELL if position.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if position.type == mt5.POSITION_TYPE_BUY else tick.ask

    request = {
        "action":    mt5.TRADE_ACTION_DEAL,
        "symbol":    position.symbol,
        "volume":    position.volume,
        "type":      close_type,
        "position":  position.ticket,
        "price":     price,
        "deviation": 20,
        "magic":     123456,
        "comment":   "XAU-ARB-close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        pnl = position.profit
        emoji = "✅" if pnl >= 0 else "❌"
        logger.info(f"{emoji} CERRADO | {position.symbol} | PnL: {pnl:+.2f}")
        _log_trade(position, price)
        return True
    return False


def modify_sl(position, new_sl: float) -> bool:
    """Modifica el SL de una posición (para Break-Even y Trailing)."""
    request = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "symbol":   position.symbol,
        "position": position.ticket,
        "sl":       round(new_sl, 2),
        "tp":       round(position.tp, 2),
        "magic":    123456,
    }
    result = mt5.order_send(request)
    return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE


# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN v3: Break-Even, Trailing, EOD Close
# ─────────────────────────────────────────────────────────────────────────────

def manage_open_positions(symbol: str, range_size: float):
    """Gestiona posiciones abiertas: BE, Trailing, EOD."""
    positions = check_open_positions(symbol)
    if not positions:
        return

    now = datetime.now(timezone.utc)
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        return

    for pos in positions:
        current_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask
        sl_distance = abs(pos.price_open - pos.sl)
        is_long = pos.type == mt5.POSITION_TYPE_BUY

        # ── EOD Close a las 16:00 UTC
        if now.hour >= EOD_CLOSE_H:
            logger.info(f"⏰ EOD Close — cerrando posición {pos.ticket}")
            close_position(pos)
            continue

        # ── Break-Even: mover SL a entrada cuando ganancia ≥ 1R
        profit_distance = (current_price - pos.price_open) if is_long else (pos.price_open - current_price)

        if profit_distance >= sl_distance * BE_TRIGGER_R:
            be_sl = pos.price_open + 0.50 if is_long else pos.price_open - 0.50
            if (is_long and pos.sl < be_sl) or (not is_long and pos.sl > be_sl):
                if modify_sl(pos, be_sl):
                    logger.info(f"🛡️ Break-Even activado | SL → {be_sl:.2f}")

            # ── Trailing Stop: seguir al precio
            trail_dist = range_size * TRAIL_DISTANCE_MULT
            if is_long:
                trail_sl = current_price - trail_dist
                if trail_sl > pos.sl:
                    if modify_sl(pos, trail_sl):
                        logger.info(f"📈 Trailing Stop → {trail_sl:.2f}")
            else:
                trail_sl = current_price + trail_dist
                if trail_sl < pos.sl:
                    if modify_sl(pos, trail_sl):
                        logger.info(f"📉 Trailing Stop → {trail_sl:.2f}")


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def _log_trade(position, exit_price: float):
    """Guarda el trade en CSV."""
    file_exists = os.path.exists(TRADE_LOG_FILE)
    with open(TRADE_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["time", "symbol", "side", "entry", "exit", "lot", "pnl", "comment"])
        side = "LONG" if position.type == mt5.POSITION_TYPE_BUY else "SHORT"
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            position.symbol, side,
            position.price_open, exit_price,
            position.volume, round(position.profit, 2),
            position.comment
        ])


# ─────────────────────────────────────────────────────────────────────────────
# LOOP PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def run_bot(risk_pct: float = DEFAULT_RISK_PCT, check_seconds: int = 60):
    """Loop principal del bot."""

    # 1. Conectar a MT5
    if not connect_mt5():
        return

    # 2. Buscar símbolos
    active_symbols = {}  # {base_name: mt5_symbol_name}
    for base_name in SYMBOL_CONFIGS:
        mt5_name = find_symbol(base_name)
        if mt5_name:
            active_symbols[base_name] = mt5_name

    if not active_symbols:
        logger.error("❌ No se encontró ningún símbolo")
        mt5.shutdown()
        return

    last_ranges = {s: 0 for s in active_symbols}  # Para trailing

    print(f"\n{'═'*60}")
    print(f"  🥇🥈 BOT ORO + PLATA — Asian Range Breakout v3")
    print(f"{'═'*60}")
    for base, mt5_name in active_symbols.items():
        print(f"  {base}: {mt5_name}")
    print(f"  Riesgo/trade: {risk_pct}%")
    print(f"  Estrategia:   Asian Breakout + BE + Trailing + EOD")
    print(f"  Ciclo:        cada {check_seconds}s")
    print(f"  Log:          {TRADE_LOG_FILE}")
    print(f"{'═'*60}")
    print(f"  Presiona Ctrl+C para detener.\n")

    try:
        while True:
            now = datetime.now(timezone.utc)
            info = mt5.account_info()
            if info:
                ts = now.strftime("%H:%M:%S")
                logger.info(f"-- {ts} UTC | Balance: ${info.balance:,.2f} | Equity: ${info.equity:,.2f} --")

            for base_name, mt5_symbol in active_symbols.items():
                # Gestionar posiciones abiertas (BE, Trailing, EOD)
                if last_ranges[base_name] > 0:
                    manage_open_positions(mt5_symbol, last_ranges[base_name])

                # Buscar nueva senal si no hay posicion abierta
                open_pos = check_open_positions(mt5_symbol)
                if not open_pos:
                    setup = check_asian_breakout(mt5_symbol, base_name)
                    if setup:
                        logger.info(f"[{base_name}] Senal detectada! {setup.signal} | Rango: {setup.range_size:.2f}")
                        if open_trade(mt5_symbol, setup, risk_pct):
                            last_ranges[base_name] = setup.range_size

            time.sleep(check_seconds)

    except KeyboardInterrupt:
        print("\nBot detenido.")
        info = mt5.account_info()
        if info:
            print(f"   Balance final: ${info.balance:,.2f}")
            print(f"   Equity final:  ${info.equity:,.2f}")
        mt5.shutdown()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bot de Oro para MetaTrader 5")
    parser.add_argument("--risk", type=float, default=DEFAULT_RISK_PCT,
                        help=f"Riesgo %% por trade (default: {DEFAULT_RISK_PCT})")
    parser.add_argument("--interval", type=int, default=60,
                        help="Segundos entre ciclos (default: 60)")
    args = parser.parse_args()

    run_bot(risk_pct=args.risk, check_seconds=args.interval)

