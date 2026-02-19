"""
strategy.py — Lógica de señales de entrada/salida
Estrategia: EMA 9/20 crossover + RSI 14 + ADX 14 + Filtro de volumen + Funding Rate
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING
import pandas as pd

from config import get_symbol_config, XAUUSDT_TRADE_HOURS
from indicators import add_indicators, get_last_signal_data
import logger

if TYPE_CHECKING:
    from exchange import BinanceFuturesExchange

# Umbral de funding rate: si |rate| > este valor, aplicamos el sesgo
FUNDING_RATE_THRESHOLD = 0.0001  # 0.01% — tasa significativa


def _is_xauusdt_trading_hours() -> bool:
    """Verifica si estamos en horario de trading para el oro (sesión Londres+NY)."""
    hour_utc = datetime.now(timezone.utc).hour
    return XAUUSDT_TRADE_HOURS["start"] <= hour_utc < XAUUSDT_TRADE_HOURS["end"]


def check_signal(df: pd.DataFrame, symbol: str,
                 exchange: "BinanceFuturesExchange | None" = None) -> str | None:
    """
    Analiza el DataFrame y retorna la señal de trading.

    Args:
        df:       DataFrame OHLCV con indicadores
        symbol:   Par de trading
        exchange: Instancia de BinanceFuturesExchange (para consultar Funding Rate)

    Returns:
        "LONG"  — Señal de compra
        "SHORT" — Señal de venta/corto
        None    — Sin señal
    """
    cfg = get_symbol_config(symbol)

    # ── Filtro horario para XAUUSDT ──────────────────────────────────
    if symbol == "XAUUSDT" and not _is_xauusdt_trading_hours():
        logger.info(f"{symbol}: Fuera de horario de trading del oro. Sin señal.")
        return None

    # ── Calcular indicadores ────────────────────────────────────────
    df = add_indicators(df)
    if df.empty or len(df) < 2:
        logger.warning(f"{symbol}: Datos insuficientes para calcular señal.")
        return None

    data = get_last_signal_data(df)

    ema_cross = data["ema_cross"]
    rsi       = data["rsi"]
    adx       = data["adx"]
    volume    = data["volume"]
    vol_ma    = data["vol_ma"]

    # ── Funding Rate (sesgo de mercado) ───────────────────────────────
    # Si el funding rate es muy positivo → el mercado está muy largo → evitar LONG
    # Si el funding rate es muy negativo → el mercado está muy corto → evitar SHORT
    funding_bias = None  # None = sin sesgo, "LONG" o "SHORT" = sesgo a favor
    if exchange is not None:
        try:
            rate = exchange.get_funding_rate(symbol)
            if abs(rate) >= FUNDING_RATE_THRESHOLD:
                if rate > 0:
                    funding_bias = "SHORT"  # Longs pagan → sesgo SHORT
                else:
                    funding_bias = "LONG"   # Shorts pagan → sesgo LONG
                logger.info(
                    f"{symbol}: 💰 Funding Rate {rate*100:+.4f}% → Sesgo: {funding_bias}"
                )
        except Exception:
            pass  # Si falla, ignorar el filtro y continuar normalmente

    # ── Log de estado actual ────────────────────────────────────────
    logger.info(
        f"{symbol} | EMA Cross: {ema_cross:+.0f} | RSI: {rsi:.1f} | "
        f"ADX: {adx:.1f} | Vol: {volume:.0f} (MA: {vol_ma:.0f})"
    )

    # ── Filtro ADX: solo operar en tendencia fuerte ─────────────────────
    if adx < cfg["adx_min"]:
        logger.info(f"{symbol}: ADX {adx:.1f} < {cfg['adx_min']} → Mercado lateral, sin señal.")
        return None

    # ── Filtro de volumen ──────────────────────────────────────────
    if volume < vol_ma * 0.8:
        logger.info(f"{symbol}: Volumen bajo ({volume:.0f} < {vol_ma * 0.8:.0f}), sin señal.")
        return None

    # ── SEÑAL LONG ─────────────────────────────────────────────────
    # EMA 9 cruza sobre EMA 20 + RSI > umbral
    if ema_cross == 1 and rsi > cfg["rsi_long"]:
        # Funding Rate: si hay sesgo SHORT fuerte, no abrimos LONG
        if funding_bias == "SHORT":
            logger.info(
                f"{symbol}: Señal LONG bloqueada por Funding Rate positivo "
                f"(mercado sobrecargado de longs)."
            )
            return None
        logger.success(
            f"{symbol}: 📈 SEÑAL LONG | RSI: {rsi:.1f} > {cfg['rsi_long']} | "
            f"ADX: {adx:.1f} | EMA cruce alcista ✅"
        )
        return "LONG"

    # ── SEÑAL SHORT ────────────────────────────────────────────────
    # EMA 9 cruza bajo EMA 20 + RSI < umbral
    if ema_cross == -1 and rsi < cfg["rsi_short"]:
        # Funding Rate: si hay sesgo LONG fuerte, no abrimos SHORT
        if funding_bias == "LONG":
            logger.info(
                f"{symbol}: Señal SHORT bloqueada por Funding Rate negativo "
                f"(mercado sobrecargado de shorts)."
            )
            return None
        logger.success(
            f"{symbol}: 📉 SEÑAL SHORT | RSI: {rsi:.1f} < {cfg['rsi_short']} | "
            f"ADX: {adx:.1f} | EMA cruce bajista ✅"
        )
        return "SHORT"

    return None


def get_entry_price(df: pd.DataFrame) -> float:
    """Retorna el precio de cierre de la última vela cerrada."""
    df = add_indicators(df)
    return get_last_signal_data(df)["close"]


def get_atr(df: pd.DataFrame) -> float:
    """Retorna el ATR de la última vela cerrada."""
    df = add_indicators(df)
    return get_last_signal_data(df)["atr"]
