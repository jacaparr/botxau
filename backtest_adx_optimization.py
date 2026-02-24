
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta

CAPITAL = 50000
RISK_PCT = 0.005 # 0.5%
DAYS = 365

def run_optimized_test(adx_xau_min, adx_eur_max):
    if not mt5.initialize(): return None
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    # Data
    r_x15 = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M15, from_dt, to_dt)
    r_x1h = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, from_dt, to_dt)
    r_e1h = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_H1, from_dt, to_dt)
    
    dfx15 = pd.DataFrame(r_x15); dfx15["time"] = pd.to_datetime(dfx15["time"], unit="s", utc=True); dfx15.set_index("time", inplace=True)
    dfx1h = pd.DataFrame(r_x1h); dfx1h["time"] = pd.to_datetime(dfx1h["time"], unit="s", utc=True); dfx1h.set_index("time", inplace=True)
    dfe1h = pd.DataFrame(r_e1h); dfe1h["time"] = pd.to_datetime(dfe1h["time"], unit="s", utc=True); dfe1h.set_index("time", inplace=True)
    
    # Calculate ADX for XAU (1h)
    dfx1h['adx'] = ta.adx(dfx1h['high'], dfx1h['low'], dfx1h['close'])['ADX_14']
    
    trades = []
    
    # XAU Logic
    ema50 = dfx1h["close"].ewm(span=50, adjust=False).mean()
    for d in sorted(set(dfx15.index.date)):
        if d.weekday() >= 5: continue
        day_df = dfx15[dfx15.index.date == d]
        
        # Check ADX on the 1h chart before session
        adx_val = dfx1h.loc[dfx1h.index.date < d]
        if adx_val.empty or adx_val.iloc[-1]['adx'] < adx_xau_min: continue
        
        asian = day_df[(day_df.index.hour >= 0) & (day_df.index.hour < 6)]
        if len(asian) < 4: continue
        hi, lo = float(asian["high"].max()), float(asian["low"].min())
        rng = hi - lo
        if rng < 3.0 or rng > 20.0: continue
        
        e50 = ema50.loc[ema50.index.date <= d].iloc[-1]
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
        trades.append(CAPITAL * RISK_PCT * ((exit_p - entry)/(entry - sl) if s == "LONG" else (entry - exit_p)/(sl - entry)))

    # EUR Logic
    dfe1h['adx'] = ta.adx(dfe1h['high'], dfe1h['low'], dfe1h['close'])['ADX_14']
    bb = ta.bbands(dfe1h['close'])
    rsi = ta.rsi(dfe1h['close'])
    atr = ta.atr(dfe1h['high'], dfe1h['low'], dfe1h['close'])
    
    for i in range(40, len(dfe1h)-1, 4):
        last = dfe1h.iloc[i]
        if last['adx'] > adx_eur_max: continue
        if rsi.iloc[i] < 30 and last['close'] < bb.iloc[i, 0]:
            s, entry, sl, tp = "LONG", last['close'], last['close'] - atr.iloc[i]*1.5, bb.iloc[i, 1]
        elif rsi.iloc[i] > 70 and last['close'] > bb.iloc[i, 2]:
            s, entry, sl, tp = "SHORT", last['close'], last['close'] + atr.iloc[i]*1.5, bb.iloc[i, 1]
        else: continue
        
        next_d = dfe1h.iloc[i+1:i+20]
        exit_p = entry
        for _, r in next_d.iterrows():
            if s == "LONG":
                if r["low"] <= sl: exit_p = sl; break
                if r["high"] >= tp: exit_p = tp; break
            else:
                if r["high"] >= sl: exit_p = sl; break
                if r["low"] <= tp: exit_p = tp; break
        trades.append(CAPITAL * RISK_PCT * ((exit_p - entry)/(entry - sl) if s == "LONG" else (entry - exit_p)/(sl - entry)))
        
    mt5.shutdown()
    return sum(trades), len(trades)

if __name__ == "__main__":
    print("Optimization Run (1 Year)...")
    base_pnl, base_trades = run_optimized_test(20, 25)
    opt_pnl, opt_trades = run_optimized_test(30, 20)
    
    print(f"\nBASE (ADX XAU>20, EUR<25): PNL ${base_pnl:.2f} ({base_trades} trades)")
    print(f"OPT  (ADX XAU>30, EUR<20): PNL ${opt_pnl:.2f} ({opt_trades} trades)")
