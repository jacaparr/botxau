
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta

CAPITAL = 100000
DAYS = 365

def run_indicator_test(risk_pct):
    if not mt5.initialize(): return 0, 0, 0
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    r_x1h = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, from_dt, to_dt)
    df = pd.DataFrame(r_x1h); df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None); df.set_index("time", inplace=True)
    
    # Indicators from backtest_mt5.py
    df['ema'] = ta.ema(df['close'], length=50)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['adx'] = ta.adx(df['high'], df['low'], df['close'])['ADX_14']
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    trades = []
    bal = CAPITAL
    max_bal = CAPITAL
    mdd = 0
    
    for i in range(50, len(df)-1):
        row = df.iloc[i]
        if row['adx'] < 20: continue
        
        s = None
        if row['close'] > row['ema'] and row['rsi'] > 55:
            s, entry, sl, tp = "LONG", row['close'], row['close'] - row['atr']*2.5, row['close'] + row['atr']*5.0
        elif row['close'] < row['ema'] and row['rsi'] < 45:
            s, entry, sl, tp = "SHORT", row['close'], row['close'] + row['atr']*2.5, row['close'] - row['atr']*5.0
            
        if s:
            # Simular trade
            next_data = df.iloc[i+1:i+48] # max 2 days
            exit_p = entry
            for _, r in next_data.iterrows():
                if s == "LONG":
                    if r["low"] <= sl: exit_p = sl; break
                    if r["high"] >= tp: exit_p = tp; break
                else:
                    if r["high"] >= sl: exit_p = sl; break
                    if r["low"] <= tp: exit_p = tp; break
            
            pnl_r = (exit_p - entry)/(entry - sl) if s == "LONG" else (entry - exit_p)/(sl - entry)
            pnl_usd = CAPITAL * (risk_pct/100) * pnl_r
            bal += pnl_usd
            max_bal = max(max_bal, bal)
            mdd = max(mdd, (max_bal - bal) / max_bal * 100)
            trades.append(pnl_usd)
            i += 24 # evitar trades solapados exagerados
            
    mt5.shutdown()
    return sum(trades), mdd, len(trades)

if __name__ == "__main__":
    pnl, dd, tr = run_indicator_test(0.5)
    print(f"ORO INDICADORES (Riesgo 0.5%): +${pnl:,.2f} ({pnl/CAPITAL*100:+.2f}%) | MDD: {dd:.2f}% | {tr} trades")
    pnl2, dd2, tr2 = run_indicator_test(1.5)
    print(f"ORO INDICADORES (Riesgo 1.5%): +${pnl2:,.2f} ({pnl2/CAPITAL*100:+.2f}%) | MDD: {dd2:.2f}% | {tr2} trades")
