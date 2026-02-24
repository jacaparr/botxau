
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta

CAPITAL = 100000
RISK_PCT = 1.5  # El riesgo que probablemente usaba antes
DAYS = 365

def run_monthly_breakdown():
    if not mt5.initialize(): return
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    r_x15 = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M15, from_dt, to_dt)
    r_x1h = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, from_dt, to_dt)
    
    dfx15 = pd.DataFrame(r_x15); dfx15["time"] = pd.to_datetime(dfx15["time"], unit="s", utc=True).dt.tz_localize(None); dfx15.set_index("time", inplace=True)
    dfx1h = pd.DataFrame(r_x1h); dfx1h["time"] = pd.to_datetime(dfx1h["time"], unit="s", utc=True).dt.tz_localize(None); dfx1h.set_index("time", inplace=True)
    
    dfx1h['adx'] = ta.adx(dfx1h['high'], dfx1h['low'], dfx1h['close'])['ADX_14']
    ema50 = dfx1h["close"].ewm(span=50, adjust=False).mean()
    
    trades = []
    for d in sorted(set(dfx15.index.date)):
        day_df = dfx15[dfx15.index.date == d]
        adx_today = dfx1h.loc[dfx1h.index.date < d]
        if adx_today.empty or adx_today.iloc[-1]['adx'] < 20: continue # Filtro base antiguo
        
        asian = day_df[(day_df.index.hour >= 0) & (day_df.index.hour < 6)]
        if len(asian) < 4: continue
        hi, lo = float(asian["high"].max()), float(asian["low"].min())
        rng = hi - lo
        e50 = ema50.loc[ema50.index.date <= d].iloc[-1]
        london = day_df[(day_df.index.hour >= 7) & (day_df.index.hour < 10)]
        for t, candle in london.iterrows():
            c = float(candle["close"])
            if c > hi and c > e50:
                s, entry, sl, tp = "LONG", c, lo - lo*0.001, c + rng*2.5; break
            elif c < lo and c < e50:
                s, entry, sl, tp = "SHORT", c, hi + hi*0.001, c - rng*2.5; break
        else: continue
        
        rest = day_df[day_df.index > t]
        exit_p = entry
        for _, r in rest.iterrows():
            if s == "LONG":
                if r["low"] <= sl: exit_p = sl; break
                if r["high"] >= tp: exit_p = tp; break
            else:
                if r["high"] >= sl: exit_p = sl; break
                if r["low"] <= tp: exit_p = tp; break
        pnl_r = (exit_p - entry)/(entry - sl) if s == "LONG" else (entry - exit_p)/(sl - entry)
        trades.append({"month": t.strftime("%Y-%m"), "pnl": CAPITAL * (RISK_PCT/100) * pnl_r})
        
    df = pd.DataFrame(trades)
    monthly = df.groupby("month")["pnl"].sum()
    print("REPORTE MENSUAL CON RIESGO 1.5% (ORO SOLO)")
    print(monthly.to_string())
    mt5.shutdown()

if __name__ == "__main__":
    run_monthly_breakdown()
