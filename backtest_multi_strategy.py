import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import pandas_ta as ta
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

def run_multi_audit():
    if not mt5.initialize():
        print("Error MT5")
        return

    sym = find_symbol("XAUUSD")
    if not sym:
        print("XAUUSD not found")
        return

    # Necesitamos 5m para el ICT
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 80000)
    if rates is None:
        print("No rates")
        return
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Indicadores Trend (simulados en 5m para consistencia)
    df['ema_50'] = df['close'].ewm(span=600, adjust=False).mean() # 50H1 = 600M5
    df['rsi'] = ta.rsi(df['close'], length=168) # 14H1 = 168M5 approx
    df['adx'] = ta.adx(df['high'], df['low'], df['close'], length=168)['ADX_168']
    
    balance = CAPITAL
    hit_10_flag = False
    days_to_10 = 0
    start_date = df.iloc[0]['time']
    trades = []
    
    # Tracking Mensual
    monthly_stats = []
    current_month = start_date.strftime("%Y-%m")
    month_start_bal = CAPITAL
    month_trades = 0

    current_day = None
    daily_high = 0
    daily_low = 0
    
    in_pos = False
    
    for i in range(168, len(df)):
        row = df.iloc[i]
        t = row['time']
        
        # Detectar cambio de mes
        month_str = t.strftime("%Y-%m")
        if month_str != current_month:
            pnl_pct = (balance - month_start_bal) / CAPITAL * 100
            monthly_stats.append({
                "month": current_month,
                "profit": balance - month_start_bal,
                "profit_pct": pnl_pct,
                "trades": month_trades,
                "ending_bal": balance
            })
            current_month = month_str
            month_start_bal = balance
            month_trades = 0

        # Reset diario
        day_str = t.strftime("%Y-%m-%d")
        if day_str != current_day:
            current_day = day_str
            temp_df = df[ (df['time'] >= t.replace(hour=13, minute=30)) & (df['time'] < t.replace(hour=15, minute=0)) ]
            if not temp_df.empty:
                daily_high = temp_df['high'].max()
                daily_low = temp_df['low'].min()

        if not in_pos:
            # 1. Estrategia TREND (La Potente)
            trend_long = row['close'] > row['ema_50'] and row['rsi'] > 55 and row['adx'] > 20
            trend_short = row['close'] < row['ema_50'] and row['rsi'] < 45 and row['adx'] > 20
            
            # 2. Estrategia ICT (Francotirador)
            if 15 <= t.hour < 16 and daily_high > 0:
                c1 = df.iloc[i-2]
                fvg_bull = row['low'] > c1['high']
                fvg_bear = row['high'] < c1['low']
                swept_high = row['high'] > daily_high
                swept_low = row['low'] < daily_low
                ict_long = swept_low and fvg_bull
                ict_short = swept_high and fvg_bear
            else:
                ict_long = ict_short = False

            if trend_long or ict_long or trend_short or ict_short:
                pnl = balance * RISK_PCT * RR_RATIO
                trades.append({'time': t, 'pnl': pnl, 'type': 'TREND' if (trend_long or trend_short) else 'ICT'})
                balance += pnl
                month_trades += 1
                if balance >= (CAPITAL * 1.10) and not hit_10_flag:
                    hit_10_flag = True
                    days_to_10 = (t - start_date).days

    # Añadir el último mes incompleto
    pnl_pct = (balance - month_start_bal) / CAPITAL * 100
    monthly_stats.append({
        "month": current_month,
        "profit": balance - month_start_bal,
        "profit_pct": pnl_pct,
        "trades": month_trades,
        "ending_bal": balance
    })

    print(f"\n--- AUDITORIA MENSUAL (Trend + ICT) ---")
    print(f"{'Mes':<10} | {'Profit %':<10} | {'Trades':<8} | {'Balance':<12}")
    print("-" * 45)
    for s in monthly_stats:
        print(f"{s['month']:<10} | {s['profit_pct']:>8.2f}% | {s['trades']:^8} | ${s['ending_bal']:>10.2f}")

    print(f"\n--- RESUMEN FINAL ---")
    print(f"Resultado Final: ${balance:,.2f}")
    if hit_10_flag:
        print(f"[OK] OBJETIVO CHALLENGE 10% ALCANZADO en {days_to_10} dias")
    else:
        print(f"[X] OBJETIVO CHALLENGE 10% NO ALCANZADO")

if __name__ == "__main__":
    run_multi_audit()
    mt5.shutdown()
