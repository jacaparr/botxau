import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

# --- CONFIG ---
SYMBOL = "XAUUSD"
CAPITAL = 100000
RISK_PCT = 0.0015 # 0.15%
RR_RATIO = 2.0
NY_OFFSET = -5

def find_symbol(base_name: str) -> str | None:
    aliases = [base_name, "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"]
    for name in aliases:
        if mt5.symbol_info(name): return name
    return None

def run_hybrid_audit():
    if not mt5.initialize():
        print("Error MT5")
        return

    sym = find_symbol("XAUUSD")
    if not sym:
        print("XAUUSD not found")
        return

    # Necesitamos 5m para el ICT, pero usaremos EMA de H1 (equivalente en 5m)
    # EMA 50 en H1 = EMA 600 en 5m (12 velas de 5m por hora * 50)
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 80000)
    if rates is None:
        print("No rates")
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Indicadores
    df['ema_trend'] = df['close'].ewm(span=600, adjust=False).mean() # Bias de H1
    
    balance = CAPITAL
    hit_10_flag = False
    days_to_10 = 0
    start_date = df.iloc[0]['time']
    trades = []
    
    current_day = None
    daily_high = 0
    daily_low = 0
    
    for i in range(2, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        t = row['time']
        
        # Reset diario y liquidez (13:30 - 15:00 UTC)
        day_str = t.strftime("%Y-%m-%d")
        if day_str != current_day:
            current_day = day_str
            temp_df = df[ (df['time'] >= t.replace(hour=13, minute=30)) & (df['time'] < t.replace(hour=15, minute=0)) ]
            if not temp_df.empty:
                daily_high = temp_df['high'].max()
                daily_low = temp_df['low'].min()

        # LOGICA HIBRIDA:
        # 1. Bias de Tendencia (EMA 50 de H1)
        # 2. Entrada Silver Bullet (NY AM + Sweep + FVG)
        
        # Ventana SB (15:00 - 16:00 UTC)
        if 15 <= t.hour < 16 and daily_high > 0:
            c1 = df.iloc[i-2]
            c2 = df.iloc[i-1]
            c3 = row
            
            # BIAS: Solo Long si estamos sobre la EMA lenta
            trend_long = c3['close'] > c3['ema_trend']
            trend_short = c3['close'] < c3['ema_trend']
            
            fvg_bull = c3['low'] > c1['high']
            fvg_bear = c3['high'] < c1['low']
            
            swept_high = c3['high'] > daily_high
            swept_low = c3['low'] < daily_low

            # COMPRA HIBRIDA: Tendencia alcista + Barrido de bajos + FVG
            if trend_long and swept_low and fvg_bull:
                pnl = balance * RISK_PCT * RR_RATIO
                trades.append({'time': t, 'pnl': pnl})
                balance += pnl
                if balance >= (CAPITAL * 1.10) and not hit_10_flag:
                    hit_10_flag = True
                    days_to_10 = (t - start_date).days
            
            # VENTA HIBRIDA: Tendencia bajista + Barrido de altos + FVG
            elif trend_short and swept_high and fvg_bear:
                pnl = balance * RISK_PCT * RR_RATIO
                trades.append({'time': t, 'pnl': pnl})
                balance += pnl
                if balance >= (CAPITAL * 1.10) and not hit_10_flag:
                    hit_10_flag = True
                    days_to_10 = (t - start_date).days

    print(f"\n--- AUDITORIA ESTRATEGIA HIBRIDA (Trend + ICT) ---")
    print(f"Resultado Final: ${balance:,.2f}")
    print(f"Trades totales: {len(trades)}")
    if hit_10_flag:
        print(f"[OK] OBJETIVO 10% ALCANZADO en {days_to_10} dias")
    else:
        print(f"[X] OBJETIVO 10% NO ALCANZADO en el periodo")

if __name__ == "__main__":
    run_hybrid_audit()
    mt5.shutdown()
