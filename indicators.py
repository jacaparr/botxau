"""
indicators.py — Cálculo de indicadores técnicos
EMA, RSI, ADX, ATR usando pandas-ta
"""

import pandas as pd
import pandas_ta as ta
from config import EMA_FAST, EMA_SLOW, RSI_PERIOD, ADX_PERIOD, ATR_PERIOD, VOL_MA_PERIOD


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Añade todos los indicadores necesarios al DataFrame OHLCV.
    
    Columnas requeridas en df: open, high, low, close, volume
    Columnas añadidas: ema_fast, ema_slow, rsi, adx, atr, vol_ma, ema_cross
    """
    df = df.copy()

    # ── EMAs ──────────────────────────────────────────────────────────────
    df["ema_fast"] = ta.ema(df["close"], length=EMA_FAST)
    df["ema_slow"] = ta.ema(df["close"], length=EMA_SLOW)

    # ── RSI ───────────────────────────────────────────────────────────────
    df["rsi"] = ta.rsi(df["close"], length=RSI_PERIOD)

    # ── ADX ───────────────────────────────────────────────────────────────
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=ADX_PERIOD)
    # pandas-ta retorna columnas: ADX_14, DMP_14, DMN_14
    adx_col = [c for c in adx_df.columns if c.startswith("ADX_")]
    df["adx"] = adx_df[adx_col[0]] if adx_col else None

    # ── ATR ───────────────────────────────────────────────────────────────
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=ATR_PERIOD)

    # ── Volumen medio ─────────────────────────────────────────────────────
    df["vol_ma"] = df["volume"].rolling(window=VOL_MA_PERIOD).mean()

    # ── Cruce de EMAs ─────────────────────────────────────────────────────
    # +1 = cruce alcista (fast cruza sobre slow)
    # -1 = cruce bajista (fast cruza bajo slow)
    #  0 = sin cruce
    df["ema_above"] = (df["ema_fast"] > df["ema_slow"]).astype(int)
    df["ema_cross"] = df["ema_above"].diff()
    # ema_cross == 1  → cruce alcista en esta vela
    # ema_cross == -1 → cruce bajista en esta vela

    return df.dropna()


def get_last_signal_data(df: pd.DataFrame) -> dict:
    """
    Retorna los valores del indicador de la última vela CERRADA (penúltima fila).
    Usamos la penúltima para evitar señales en vela abierta.
    """
    if len(df) < 2:
        return {}

    row = df.iloc[-2]  # Última vela cerrada
    return {
        "ema_fast":  row["ema_fast"],
        "ema_slow":  row["ema_slow"],
        "ema_cross": row["ema_cross"],
        "rsi":       row["rsi"],
        "adx":       row["adx"],
        "atr":       row["atr"],
        "volume":    row["volume"],
        "vol_ma":    row["vol_ma"],
        "close":     row["close"],
    }


if __name__ == "__main__":
    # ── Self-test con datos sintéticos ────────────────────────────────────
    import numpy as np

    print("🧪 Test de indicadores con datos sintéticos...")
    n = 100
    np.random.seed(42)
    prices = 50000 + np.cumsum(np.random.randn(n) * 200)

    test_df = pd.DataFrame({
        "open":   prices * 0.999,
        "high":   prices * 1.002,
        "low":    prices * 0.998,
        "close":  prices,
        "volume": np.random.uniform(100, 500, n),
    })

    result = add_indicators(test_df)
    last = get_last_signal_data(result)

    print(f"  EMA Fast ({EMA_FAST}): {last['ema_fast']:.2f}")
    print(f"  EMA Slow ({EMA_SLOW}): {last['ema_slow']:.2f}")
    print(f"  RSI ({RSI_PERIOD}):    {last['rsi']:.2f}")
    print(f"  ADX ({ADX_PERIOD}):    {last['adx']:.2f}")
    print(f"  ATR ({ATR_PERIOD}):    {last['atr']:.2f}")
    print(f"  EMA Cross:             {last['ema_cross']}")
    print("✅ Test completado sin errores.")
