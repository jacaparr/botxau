"""
strategy_eurusd.py — Estrategia Mean Reversion para EURUSD
===========================================================
Basada en investigación: Bandas de Bollinger + RSI + Filtro de Tendencia ADX.
Diseñada para capturar reversiones cuando el precio está sobre-extendido.
"""

import pandas as pd
import pandas_ta as ta

def calculate_indicators(df: pd.DataFrame):
    """Calcula indicadores necesarios para la estrategia."""
    try:
        # 1. Bollinger Bands (20, 2)
        bbands = ta.bbands(df['close'], length=20, std=2)
        if bbands is not None and not bbands.empty:
            # Usar nombres de columnas reales si existen, o iloc si no
            df['bb_lower'] = bbands.iloc[:, 0] 
            df['bb_mid'] = bbands.iloc[:, 1]   
            df['bb_upper'] = bbands.iloc[:, 2] 
    except Exception as e:
        print(f"[DEBUG] Error in BB: {e}")
        
    try:
        # 2. RSI (14)
        df['rsi'] = ta.rsi(df['close'], length=14)
    except Exception as e:
        print(f"[DEBUG] Error in RSI: {e}")
        
    try:
        # 3. ADX (14)
        adx = ta.adx(df['high'], df['low'], df['close'], length=14)
        if adx is not None and not adx.empty:
            if isinstance(adx, pd.DataFrame):
                df['adx'] = adx.iloc[:, 0] 
            else:
                df['adx'] = adx
        else:
            df['adx'] = 0.0
    except Exception as e:
        print(f"[DEBUG] Error in ADX: {e}")
        
    try:
        # 4. ATR
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    except Exception as e:
        print(f"[DEBUG] Error in ATR: {e}")
    
    return df

def check_signals(df_in: pd.DataFrame):
    """
    Verifica señales de compra/venta.
    Retorna (signal, entry, sl, tp) o None.
    """
    if not isinstance(df_in, pd.DataFrame) or len(df_in) < 35:
        return None
        
    try:
        # Asegurarnos de trabajar con los últimos datos como Series
        last = df_in.iloc[-1]
    except Exception:
        return None
    
    # Parámetros de la estrategia
    RSI_OVERSOLD = 30
    RSI_OVERBOUGHT = 70
    ADX_MAX = 25  
    
    # Usar .get() o verificar columnas para evitar errores si faltan indicadores
    req_cols = ['bb_lower', 'bb_upper', 'bb_mid', 'rsi', 'adx', 'atr', 'close']
    for col in req_cols:
        if col not in last or pd.isna(last[col]):
            return None

    close = float(last['close'])
    bb_lower = float(last['bb_lower'])
    bb_upper = float(last['bb_upper'])
    bb_mid = float(last['bb_mid'])
    rsi = float(last['rsi'])
    adx = float(last['adx'])
    atr = float(last['atr'])

    # --- Señal LONG (Compra) ---
    if close < bb_lower and rsi < RSI_OVERSOLD and adx < ADX_MAX:
        entry = close
        sl = entry - (atr * 1.5) 
        tp = bb_mid             
        return ("LONG", entry, sl, tp)

    # --- Señal SHORT (Venta) ---
    if close > bb_upper and rsi > RSI_OVERBOUGHT and adx < ADX_MAX:
        entry = close
        sl = entry + (atr * 1.5)
        tp = bb_mid
        return ("SHORT", entry, sl, tp)
        
    return None
