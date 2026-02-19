"""
strategy_xau.py — Asian Range Breakout para XAUUSDT (v3 — prop firm ready)
==========================================================================
Estrategia específica para oro basada en el rango asiático:

  1. 🌙 SESIÓN ASIÁTICA (00:00 – 06:00 UTC):
       Marca el HIGH y LOW del precio durante esta sesión.
       → El oro consolida casi siempre en este período.

  2. 🇬🇧 LONDON OPEN (07:00 – 10:00 UTC):
       Si el precio cierra POR ENCIMA del high asiático → LONG
       Si el precio cierra POR DEBAJO del low  asiático → SHORT
       → Aquí es cuando el dinero institucional entra en el mercado.

  3. 🎯 GESTIÓN DE RIESGO:
       SL  = Lado opuesto del rango asiático (+ pequeño buffer)
       TP  = 2.5× el tamaño del rango

FILTROS DE CALIDAD (v2):
  ✅ Rango mínimo $30      — elimina señales en días de baja volatilidad
  ✅ Rango máximo $200     — evita días con noticias extremas (Fed, CPI)
  ✅ Tendencia 1H EMA50    — solo LONG si precio > EMA50, solo SHORT si < EMA50
  ✅ Sin lunes             — evita la volatilidad errática de apertura semanal
  ✅ Max 4 velas de entrada — no entrar tarde en London

MEJORAS PROP FIRM (v3):
  🛡️ Break-Even           — SL se mueve a entrada cuando precio avanza 1R
  📈 Trailing Stop         — SL persigue al precio a 0.5× rango de distancia
  ⏰ Cierre EOD            — Cierre forzado a las 16:00 UTC (fin sesión NY)
"""

import pandas as pd
from datetime import timezone
import logger


# ─────────────────────────────────────────────────────────────────────────────
# PARÁMETROS
# ─────────────────────────────────────────────────────────────────────────────

ASIAN_START_H  = 0    # Hora UTC inicio sesión asiática
ASIAN_END_H    = 6    # Hora UTC fin sesión asiática
LONDON_START_H = 7    # Hora UTC inicio London Open (ventana de entrada)
LONDON_END_H   = 10   # Hora UTC fin ventana de entrada London

TP_MULTIPLIER  = 2.5  # R:R documentado con 82% win rate
SL_BUFFER_PCT  = 0.001  # 0.1% buffer extra sobre el rango para el SL

# ── Filtros de calidad (v2) ───────────────────────────────────────────────
MIN_RANGE_USD  = 30    # Rango asiático mínimo para operar ($)
MAX_RANGE_USD  = 200   # Rango asiático máximo — días muy volátiles se saltan
EMA_TREND_PERIOD = 50  # EMA de tendencia (sobre velas 1H)
SKIP_MONDAY    = True  # No operar el lunes (apertura semanal caótica)
MAX_LONDON_CANDLES = 4 # Máximo de velas de London antes de descartar señal

# ── Mejoras Prop Firm (v3) ────────────────────────────────────────────────
BE_TRIGGER_R       = 1.0   # Mover SL a entrada cuando ganancia = 1× riesgo
TRAIL_DISTANCE_MULT = 0.5  # Trailing stop a 0.5× rango de distancia
EOD_CLOSE_H        = 16    # Hora UTC para cierre forzado (fin sesión NY)


# ─────────────────────────────────────────────────────────────────────────────
# LÓGICA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def check_signal_xau(df: pd.DataFrame, symbol: str = "XAUUSDT",
                     df_1h: pd.DataFrame | None = None) -> tuple[str | None, float, float]:
    """
    Evalúa si hay una señal de rotura del rango asiático.

    Requiere velas de 15m para tener resolución suficiente.
    Opcionalmente acepta df_1h para el filtro de tendencia.

    Args:
        df:     DataFrame 15m con open/high/low/close/volume, index UTC.
        symbol: Nombre del par.
        df_1h:  DataFrame 1H opcional para filtro de tendencia EMA50.

    Returns:
        (signal, sl_price, tp_price) — signal ∈ {"LONG", "SHORT", None}
    """
    if df.empty or len(df) < 30:
        return None, 0.0, 0.0

    # Asegurar que el índice es UTC
    if df.index.tzinfo is None:
        df = df.copy()
        df.index = df.index.tz_localize("UTC")

    now_utc = df.index[-1]
    now_h   = now_utc.hour
    weekday = now_utc.weekday()  # 0=Lunes, 4=Viernes

    # ── Filtro: sin lunes ─────────────────────────────────────────────────
    if SKIP_MONDAY and weekday == 0:
        logger.info(f"{symbol} [XAU]: Lunes — señal bloqueada (apertura semanal)")
        return None, 0.0, 0.0

    # ── Solo operar en ventana London Open ────────────────────────────────
    if not (LONDON_START_H <= now_h < LONDON_END_H):
        logger.info(
            f"{symbol} [XAU]: Fuera de ventana London ({now_h:02d}:xx UTC). "
            f"Ventana: {LONDON_START_H:02d}:00–{LONDON_END_H:02d}:00"
        )
        return None, 0.0, 0.0

    # ── Extraer rango de la sesión asiática de HOY ────────────────────────
    today = now_utc.date()
    asian_mask = (
        (df.index.date == today) &
        (df.index.hour >= ASIAN_START_H) &
        (df.index.hour <  ASIAN_END_H)
    )
    asian_df = df[asian_mask]

    if asian_df.empty or len(asian_df) < 4:
        logger.info(f"{symbol} [XAU]: Pocas velas asiáticas ({len(asian_df)}). Saltando.")
        return None, 0.0, 0.0

    asian_high = float(asian_df["high"].max())
    asian_low  = float(asian_df["low"].min())
    range_size = asian_high - asian_low

    # ── Filtro: rango mínimo ──────────────────────────────────────────────
    if range_size < MIN_RANGE_USD:
        logger.info(
            f"{symbol} [XAU]: Rango asiático demasiado pequeño "
            f"(${range_size:.2f} < mín ${MIN_RANGE_USD}). Saltando día."
        )
        return None, 0.0, 0.0

    # ── Filtro: rango máximo ──────────────────────────────────────────────
    if range_size > MAX_RANGE_USD:
        logger.info(
            f"{symbol} [XAU]: Rango asiático demasiado grande "
            f"(${range_size:.2f} > máx ${MAX_RANGE_USD}). Días de noticias extremas."
        )
        return None, 0.0, 0.0

    # ── Filtro: tendencia EMA50 en 1H ────────────────────────────────────
    trend_bias = None   # None = sin filtro, "LONG" o "SHORT"
    if df_1h is not None and not df_1h.empty and len(df_1h) >= EMA_TREND_PERIOD:
        ema50 = df_1h["close"].ewm(span=EMA_TREND_PERIOD, adjust=False).mean()
        last_close_1h = float(df_1h["close"].iloc[-1])
        last_ema50    = float(ema50.iloc[-1])
        if last_close_1h > last_ema50:
            trend_bias = "LONG"
        else:
            trend_bias = "SHORT"
        logger.info(
            f"{symbol} [XAU]: EMA50(1H) = {last_ema50:.2f} | "
            f"Precio = {last_close_1h:.2f} | Tendencia: {trend_bias}"
        )

    # ── Velas de London (ventana de entrada) ─────────────────────────────
    london_mask = (
        (df.index.date == today) &
        (df.index.hour >= LONDON_START_H) &
        (df.index.hour <  LONDON_END_H)
    )
    london_df = df[london_mask]

    if london_df.empty:
        return None, 0.0, 0.0

    if len(london_df) > MAX_LONDON_CANDLES:
        logger.info(f"{symbol} [XAU]: London ya lleva {len(london_df)} velas. Evitando entrada tardía.")
        return None, 0.0, 0.0

    last_candle = london_df.iloc[-1]
    close = float(last_candle["close"])

    logger.info(
        f"{symbol} [XAU]: H asiático={asian_high:.2f} | L asiático={asian_low:.2f} | "
        f"Rango=${range_size:.2f} | Cierre={close:.2f}"
    )

    # ── SEÑAL LONG ────────────────────────────────────────────────────────
    if close > asian_high:
        # Filtro tendencia: solo LONG si la tendencia macro es alcista o sin datos
        if trend_bias == "SHORT":
            logger.info(f"{symbol} [XAU]: Señal LONG bloqueada — EMA50 en tendencia bajista")
            return None, 0.0, 0.0

        sl_price = asian_low  - (range_size * SL_BUFFER_PCT)
        tp_price = close + (range_size * TP_MULTIPLIER)

        logger.info(
            f"{symbol} [XAU] 📈 ROTURA ALCISTA | "
            f"Cierre {close:.2f} > {asian_high:.2f} | "
            f"SL: {sl_price:.2f} | TP: {tp_price:.2f}"
        )
        return "LONG", round(sl_price, 2), round(tp_price, 2)

    # ── SEÑAL SHORT ───────────────────────────────────────────────────────
    if close < asian_low:
        # Filtro tendencia: solo SHORT si la tendencia macro es bajista o sin datos
        if trend_bias == "LONG":
            logger.info(f"{symbol} [XAU]: Señal SHORT bloqueada — EMA50 en tendencia alcista")
            return None, 0.0, 0.0

        sl_price = asian_high + (range_size * SL_BUFFER_PCT)
        tp_price = close - (range_size * TP_MULTIPLIER)

        logger.info(
            f"{symbol} [XAU] 📉 ROTURA BAJISTA | "
            f"Cierre {close:.2f} < {asian_low:.2f} | "
            f"SL: {sl_price:.2f} | TP: {tp_price:.2f}"
        )
        return "SHORT", round(sl_price, 2), round(tp_price, 2)

    # Sin rotura todavía
    dist_to_high = asian_high - close
    dist_to_low  = close - asian_low
    logger.info(
        f"{symbol} [XAU]: Sin rotura | "
        f"↑${dist_to_high:.2f} hasta H | ↓${dist_to_low:.2f} hasta L"
    )
    return None, 0.0, 0.0


def get_xau_sl_tp(entry_price: float, asian_high: float, asian_low: float,
                  signal: str) -> tuple[float, float]:
    """Calcula SL y TP para una posición XAU ya abierta."""
    range_size = asian_high - asian_low
    buffer = range_size * SL_BUFFER_PCT
    if signal == "LONG":
        sl = asian_low - buffer
        tp = entry_price + range_size * TP_MULTIPLIER
    else:
        sl = asian_high + buffer
        tp = entry_price - range_size * TP_MULTIPLIER
    return round(sl, 2), round(tp, 2)
