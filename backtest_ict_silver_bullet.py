import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

# --- CONFIG ---
SYMBOL = "XAUUSD"
CAPITAL = 100000
RISK_PCT = 0.0015 # 0.15% en decimal
DAYS_TO_TEST = 365
RR_RATIO = 2.0
NY_OFFSET = -5

def find_symbol(base_name: str) -> str | None:
    aliases = [base_name, "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"]
    for name in aliases:
        if mt5.symbol_info(name): return name
    return None

def run_ict_audit():
    if not mt5.initialize():
        print("Error MT5")
        return

    sym = find_symbol("XAUUSD")
    if not sym:
        print("XAUUSD not found")
        return

    # Necesitamos 5m para ver los FVG con precisión
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 50000)
    if rates is None:
        print("No rates")
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    balance = CAPITAL
    hit_10_flag = False
    days_to_10 = 0
    start_date = df.iloc[0]['time']
    max_equity = CAPITAL
    max_dd = 0
    trades = []
    
    # Ventana Silver Bullet NY AM: 10:00 - 11:00 AM NY
    # En UTC (Standard -5): 15:00 - 16:00 UTC
    
    current_day = None
    daily_high = 0
    daily_low = 0
    
    for i in range(2, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        t = row['time']
        
        # Reset diario y cálculo de liquidez previa (8:30 - 10:00 AM NY / 13:30 - 15:00 UTC)
        day_str = t.strftime("%Y-%m-%d")
        if day_str != current_day:
            current_day = day_str
            # Liquidez externa (rango previo)
            temp_df = df[ (df['time'] >= t.replace(hour=13, minute=30)) & (df['time'] < t.replace(hour=15, minute=0)) ]
            if not temp_df.empty:
                daily_high = temp_df['high'].max()
                daily_low = temp_df['low'].min()
            else:
                daily_high, daily_low = 0, 0

        # Ventana Silver Bullet (15:00 - 16:00 UTC)
        if 15 <= t.hour < 16 and daily_high > 0:
            # 1. ¿Liquidez barrida?
            swept_high = row['high'] > daily_high
            swept_low = row['low'] < daily_low
            
            # 2. ¿Fair Value Gap (FVG)?
            # FVG Bullish: Low(i) > High(i-2)
            # FVG Bearish: High(i) < Low(i-2)
            c1 = df.iloc[i-2]
            c2 = df.iloc[i-1]
            c3 = row
            
            fvg_bull = c3['low'] > c1['high']
            fvg_bear = c3['high'] < c1['low']
            
            # Solo operamos si ya barrió liquidez contraria (Logic simplificada ICT)
            if swept_high and fvg_bear:
                # Entrada en el gap
                entry = c1['low']
                sl = c2['high'] # Por encima de la vela que hizo el gap
                dist = sl - entry
                if dist > 0:
                    tp = entry - (dist * RR_RATIO)
                    trades.append({'time': t, 'type': 'SHORT', 'pnl': balance * RISK_PCT * RR_RATIO / 100})
                    balance += balance * RISK_PCT * RR_RATIO
            elif swept_low and fvg_bull:
                entry = c1['high']
                sl = c2['low']
                dist = entry - sl
                if dist > 0:
                    tp = entry + (dist * RR_RATIO)
                    trades.append({'time': t, 'type': 'LONG', 'pnl': balance * RISK_PCT * RR_RATIO / 100})
                    balance += balance * RISK_PCT * RR_RATIO
                    if balance >= (CAPITAL * 1.10) and not hit_10_flag:
                        hit_10_flag = True
                        days_to_10 = (t - start_date).days

    print(f"\n--- AUDITORIA ICT SILVER BULLET (0.15% Risk) ---")
    print(f"Resultado Final: ${balance:,.2f}")
    win_rate = (len([t for t in trades if t['pnl'] > 0]) / len(trades)) * 100 if trades else 0
    print(f"Trades totales: {len(trades)}")
    print(f"Win Rate: {win_rate:.1f}%")
    if hit_10_flag:
        print(f"[OK] OBJETIVO 10% ALCANZADO en {days_to_10} dias")
    else:
        print(f"[X] OBJETIVO 10% NO ALCANZADO en el periodo")

if __name__ == "__main__":
    run_ict_audit()
    mt5.shutdown()
