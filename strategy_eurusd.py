"""
strategy_eurusd.py — Estrategia Mean Reversion para EURUSD
===========================================================
Basada en investigacion: Bandas de Bollinger + RSI + Filtro de Tendencia ADX.
Disenada para capturar reversiones cuando el precio esta sobre-extendido.
Sin dependencias de pandas_ta — calculo puro con pandas/numpy.
"""

import pandas as pd
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# INDICADORES (pure pandas, sin pandas_ta)
# ─────────────────────────────────────────────────────────────────────────────

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
    up      = high.diff()
    down    = -low.diff()
    pdm     = pd.Series(0.0, index=high.index)
    mdm     = pd.Series(0.0, index=high.index)
    pdm[(up > down) & (up > 0)]   = up[(up > down) & (up > 0)]
    mdm[(down > up) & (down > 0)] = down[(down > up) & (down > 0)]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr14  = tr.rolling(length).mean()
    pdi    = 100 * pdm.rolling(length).mean() / atr14.replace(0, np.nan)
    mdi    = 100 * mdm.rolling(length).mean() / atr14.replace(0, np.nan)
    dx     = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return dx.rolling(length).mean()

def _bbands(series: pd.Series, length: int = 20, std: float = 2.0):
    """Retorna (lower, mid, upper)."""
    mid   = series.rolling(window=length).mean()
    sigma = series.rolling(window=length).std(ddof=0)
    return mid - std * sigma, mid, mid + std * sigma

# ─────────────────────────────────────────────────────────────────────────────

def calculate_indicators(df: pd.DataFrame):
    """Calcula indicadores necesarios para la estrategia."""
    # 1. Bollinger Bands (20, 2)
    lo, mid, hi = _bbands(df['close'], length=20, std=2.0)
    df['bb_lower'] = lo
    df['bb_mid']   = mid
    df['bb_upper'] = hi

    # 2. RSI (14)
    df['rsi'] = _rsi(df['close'], length=14)

    # 3. ADX (14)
    df['adx'] = _adx(df['high'], df['low'], df['close'], length=14)

    # 4. ATR (14)
    df['atr'] = _atr(df['high'], df['low'], df['close'], length=14)

    return df

def check_signals(df_in: pd.DataFrame):
    """
    Verifica señales de compra/venta.
    Retorna (signal, entry, sl, tp) o None.
    """
    if not isinstance(df_in, pd.DataFrame) or len(df_in) < 35:
        return None

    try:
        last = df_in.iloc[-1]
    except Exception:
        return None

    RSI_OVERSOLD  = 30
    RSI_OVERBOUGHT = 70
    ADX_MAX        = 20

    req_cols = ['bb_lower', 'bb_upper', 'bb_mid', 'rsi', 'adx', 'atr', 'close']
    for col in req_cols:
        if col not in last or pd.isna(last[col]):
            return None

    close    = float(last['close'])
    bb_lower = float(last['bb_lower'])
    bb_upper = float(last['bb_upper'])
    bb_mid   = float(last['bb_mid'])
    rsi      = float(last['rsi'])
    adx      = float(last['adx'])
    atr      = float(last['atr'])

    # --- Señal LONG ---
    if close < bb_lower and rsi < RSI_OVERSOLD and adx < ADX_MAX:
        entry = close
        sl    = entry - (atr * 1.5)
        tp    = bb_mid
        return ("LONG", entry, sl, tp)

    # --- Señal SHORT ---
    if close > bb_upper and rsi > RSI_OVERBOUGHT and adx < ADX_MAX:
        entry = close
        sl    = entry + (atr * 1.5)
        tp    = bb_mid
        return ("SHORT", entry, sl, tp)

    return None
