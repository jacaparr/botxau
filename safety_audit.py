
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import numpy as np
from datetime import datetime, timezone, timedelta

CAPITAL = 100000
DAYS = 365

def audit_safety(risk_pct):
    if not mt5.initialize(): return
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    symbol = "XAUUSD"
    for s in ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"]:
        if mt5.symbol_info(s): symbol = s; break
            
    r_x1h = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, from_dt, to_dt)
    df = pd.DataFrame(r_x1h)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None)
    df.set_index("time", inplace=True)
    
    df['ema'] = ta.ema(df['close'], length=50)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['adx'] = ta.adx(df['high'], df['low'], df['close'])['ADX_14']
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    trades = []
    equity_curve = [CAPITAL]
    daily_pnls = {}
    
    for i in range(50, len(df)-1):
        row = df.iloc[i]
        if row['adx'] < 20: continue
        
        s_type = None
        if row['close'] > row['ema'] and row['rsi'] > 55:
            s_type, entry, sl, tp = "LONG", row['close'], row['close'] - row['atr']*2.5, row['close'] + row['atr']*5.0
        elif row['close'] < row['ema'] and row['rsi'] < 45:
            s_type, entry, sl, tp = "SHORT", row['close'], row['close'] + row['atr']*2.5, row['close'] - row['atr']*5.0
            
        if s_type:
            next_data = df.iloc[i+1:min(i+49, len(df))]
            exit_p = entry
            for _, r in next_data.iterrows():
                if s_type == "LONG":
                    if r["low"] <= sl: exit_p = sl; break
                    if r["high"] >= tp: exit_p = tp; break
                else:
                    if r["high"] >= sl: exit_p = sl; break
                    if r["low"] <= tp: exit_p = tp; break
            
            pnl_r = (exit_p - entry)/(entry - sl) if s_type == "LONG" else (entry - exit_p)/(sl - entry)
            pnl_usd = CAPITAL * (risk_pct/100) * pnl_r
            
            day = row.name.date()
            daily_pnls[day] = daily_pnls.get(day, 0) + pnl_usd
            equity_curve.append(equity_curve[-1] + pnl_usd)
            trades.append(pnl_usd)
            i += 12

    # Cálculos de Seguridad
    equity_array = np.array(equity_curve)
    peaks = np.maximum.accumulate(equity_array)
    drawdowns = (peaks - equity_array) / peaks * 100
    max_dd = np.max(drawdowns)
    
    daily_dd_max = 0
    for day, pnl in daily_pnls.items():
        daily_dd = abs(min(0, pnl)) / CAPITAL * 100
        daily_dd_max = max(daily_dd_max, daily_dd)

    total_profit = sum(trades)
    avg_monthly = total_profit / 12
    
    print(f"\n--- AUDITORÍA PARA RIESGO {risk_pct}% ---")
    print(f"Beneficio Total: ${total_profit:,.2f}")
    print(f"Promedio Mensual: ${avg_monthly:,.2f}")
    print(f"Drawdown Máximo Total: {max_dd:.2f}% (Límite Fondeo: 10%)")
    print(f"Drawdown Máximo Diario: {daily_dd_max:.2f}% (Límite Fondeo: 5%)")
    print(f"Status: {'✅ SEGURO' if max_dd < 7 and daily_dd_max < 4 else '❌ PELIGROSO'}")

if __name__ == "__main__":
    audit_safety(0.2)
    audit_safety(0.1)
    audit_safety(0.06)
    audit_safety(0.05)
    mt5.shutdown()
