
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta

CAPITAL = 100000
RISK_PCT = 0.5 # Incluso con riesgo bajisimo sale mucho

def run_indicator_monthly():
    if not mt5.initialize(): return
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    r_x1h = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, from_dt, to_dt)
    df = pd.DataFrame(r_x1h); df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None); df.set_index("time", inplace=True)
    
    df['ema'] = ta.ema(df['close'], length=50)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['adx'] = ta.adx(df['high'], df['low'], df['close'])['ADX_14']
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    trades = []
    for i in range(50, len(df)-1):
        row = df.iloc[i]
        if row['adx'] < 20: continue
        s = None
        if row['close'] > row['ema'] and row['rsi'] > 55:
            s, entry, sl, tp = "LONG", row['close'], row['close'] - row['atr']*2.5, row['close'] + row['atr']*5.0
        elif row['close'] < row['ema'] and row['rsi'] < 45:
            s, entry, sl, tp = "SHORT", row['close'], row['close'] + row['atr']*2.5, row['close'] - row['atr']*5.0
        if s:
            next_data = df.iloc[i+1:i+48]
            exit_p = entry
            for _, r in next_data.iterrows():
                if s == "LONG":
                    if r["low"] <= sl: exit_p = sl; break
                    if r["high"] >= tp: exit_p = tp; break
                else:
                    if r["high"] >= sl: exit_p = sl; break
                    if r["low"] <= tp: exit_p = tp; break
            pnl_r = (exit_p - entry)/(entry - sl) if s == "LONG" else (entry - exit_p)/(sl - entry)
            trades.append({"month": row.name.strftime("%Y-%m"), "pnl": CAPITAL * (RISK_PCT/100) * pnl_r})
            i += 12
    
    df_res = pd.DataFrame(trades)
    monthly = df_res.groupby("month")["pnl"].sum()
    print("REPORTE MENSUAL ORO (ESTRATEGIA INDICADORES) - RIESGO 0.5%")
    print(monthly.to_string())
    print(f"\nTOTAL: ${monthly.sum():,.2f}")
    mt5.shutdown()

if __name__ == "__main__":
    DAYS = 365
    run_indicator_monthly()
