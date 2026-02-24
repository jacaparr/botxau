
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import pandas_ta as ta

# --- CONFIG ---
CAPITAL = 100000
RISK_PCT = 0.005 # 0.5%
DAYS = 365

# XAU
XAU_TP_MULT = 2.0 
# EUR
import strategy_eurusd as strat_eur

def run_test():
    if not mt5.initialize(): return "Error MT5"
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    r_x15 = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M15, from_dt, to_dt)
    r_x1h = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, from_dt, to_dt)
    r_e1h = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_H1, from_dt, to_dt)
    
    dfx15 = pd.DataFrame(r_x15); dfx15["time"] = pd.to_datetime(dfx15["time"], unit="s", utc=True); dfx15.set_index("time", inplace=True)
    dfx1h = pd.DataFrame(r_x1h); dfx1h["time"] = pd.to_datetime(dfx1h["time"], unit="s", utc=True); dfx1h.set_index("time", inplace=True)
    dfe1h = pd.DataFrame(r_e1h); dfe1h["time"] = pd.to_datetime(dfe1h["time"], unit="s", utc=True); dfe1h.set_index("time", inplace=True)
    
    trades = []
    
    # XAU Logic (Simplified)
    ema50 = dfx1h["close"].ewm(span=50, adjust=False).mean()
    adx_xau = ta.adx(dfx1h['high'], dfx1h['low'], dfx1h['close'])['ADX_14']
    for d in sorted(set(dfx15.index.date)):
        if d.weekday() >= 5: continue
        day_df = dfx15[dfx15.index.date == d]
        
        # Filtro Francotirador: ADX > 30
        adx_today = adx_xau.loc[adx_xau.index.date < d]
        if adx_today.empty or adx_today.iloc[-1] < 30: continue

        asian = day_df[(day_df.index.hour >= 0) & (day_df.index.hour < 6)]
        if len(asian) < 4: continue
        hi, lo = float(asian["high"].max()), float(asian["low"].min())
        rng = hi - lo
        if rng < 3.0 or rng > 20.0: continue
        
        ema_today = ema50.loc[ema50.index.date <= d]
        if ema_today.empty: continue
        e50 = ema_today.iloc[-1]
        
        london = day_df[(day_df.index.hour >= 7) & (day_df.index.hour < 10)]
        for t, candle in london.iterrows():
            c = float(candle["close"])
            if c > hi and c > e50:
                s, entry, sl, tp = "LONG", c, lo - lo*0.001, c + rng*2.0; break
            elif c < lo and c < e50:
                s, entry, sl, tp = "SHORT", c, hi + hi*0.001, c - rng*2.0; break
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
        trades.append({"time": t, "pnl": CAPITAL * RISK_PCT * pnl_r})

    # EUR Logic (Simplified)
    for i in range(40, len(dfe1h)-1, 6):
        window = dfe1h.iloc[:i+1]
        res = strat_eur.check_signals(strat_eur.calculate_indicators(window.copy()))
        if not res: continue
        s, entry, sl, tp = res
        next_d = dfe1h.iloc[i+1:i+20]
        exit_p = entry
        for _, r in next_d.iterrows():
            if s == "LONG":
                if r["low"] <= sl: exit_p = sl; break
                if r["high"] >= tp: exit_p = tp; break
            else:
                if r["high"] >= sl: exit_p = sl; break
                if r["low"] <= tp: exit_p = tp; break
        pnl_r = (exit_p - entry)/(entry - sl) if s == "LONG" else (entry - exit_p)/(sl - entry)
        trades.append({"time": window.index[-1], "pnl": CAPITAL * RISK_PCT * pnl_r})
        
    mt5.shutdown()
    return trades

if __name__ == "__main__":
    t_list = run_test()
    if isinstance(t_list, str): print(t_list); exit()
    df = pd.DataFrame(t_list)
    df.to_csv("full_trades_log.csv", index=False)
    df["month"] = df["time"].dt.to_period("M")
    stats = df.groupby("month")["pnl"].agg(["count", "sum"])
    stats["pnl_pct"] = (stats["sum"] / CAPITAL) * 100
    
    print("FINISHED")
    print(stats.to_string())
