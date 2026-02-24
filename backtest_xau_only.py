
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta

CAPITAL = 100000
DAYS = 365

def run_xau_only_test(risk_pct, adx_min, tp_mult):
    if not mt5.initialize(): return 0, 0, 0
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    r_x15 = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M15, from_dt, to_dt)
    r_x1h = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, from_dt, to_dt)
    
    dfx15 = pd.DataFrame(r_x15); dfx15["time"] = pd.to_datetime(dfx15["time"], unit="s", utc=True).dt.tz_localize(None); dfx15.set_index("time", inplace=True)
    dfx1h = pd.DataFrame(r_x1h); dfx1h["time"] = pd.to_datetime(dfx1h["time"], unit="s", utc=True).dt.tz_localize(None); dfx1h.set_index("time", inplace=True)
    
    dfx1h['adx'] = ta.adx(dfx1h['high'], dfx1h['low'], dfx1h['close'])['ADX_14']
    ema50 = dfx1h["close"].ewm(span=50, adjust=False).mean()
    
    trades = []
    bal = CAPITAL
    max_bal = CAPITAL
    mdd = 0
    
    for d in sorted(set(dfx15.index.date)):
        day_df = dfx15[dfx15.index.date == d]
        adx_today = dfx1h.loc[dfx1h.index.date < d]
        if adx_today.empty or adx_today.iloc[-1]['adx'] < adx_min: continue
        
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
                s, entry, sl, tp = "LONG", c, lo - lo*0.001, c + rng*tp_mult; break
            elif c < lo and c < e50:
                s, entry, sl, tp = "SHORT", c, hi + hi*0.001, c - rng*tp_mult; break
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
        pnl_usd = CAPITAL * (risk_pct/100) * pnl_r
        bal += pnl_usd
        max_bal = max(max_bal, bal)
        mdd = max(mdd, (max_bal - bal) / max_bal * 100)
        trades.append(pnl_usd)
        
    mt5.shutdown()
    return sum(trades), mdd, len(trades)

if __name__ == "__main__":
    print(f"ANÁLISIS ANUAL EXCLUSIVO ORO (XAUUSD) - $100K")
    
    # 1. Francotirador (Riesgo 0.5%, ADX 30, TP 2.5)
    f_pnl, f_dd, f_tr = run_xau_only_test(0.5, 30, 2.5)
    # 2. Equilibrado (Riesgo 1.0%, ADX 25, TP 2.5)
    e_pnl, e_dd, e_tr = run_xau_only_test(1.0, 25, 2.5)
    # 3. Potencial 70% (Riesgo 2.0%, ADX 20, TP 2.5)
    a_pnl, a_dd, a_tr = run_xau_only_test(2.0, 20, 2.5)
    
    print(f"\n1. MODO FRANCOTIRADOR (Seguro): +${f_pnl:,.2f} ({f_pnl/CAPITAL*100:+.2f}%) | MDD: {f_dd:.2f}% | {f_tr} trades")
    print(f"2. MODO EQUILIBRADO  (Fondeo): +${e_pnl:,.2f} ({e_pnl/CAPITAL*100:+.2f}%) | MDD: {e_dd:.2f}% | {e_tr} trades")
    print(f"3. MODO AGRESIVO     (70%??):  +${a_pnl:,.2f} ({a_pnl/CAPITAL*100:+.2f}%) | MDD: {a_dd:.2f}% | {a_tr} trades")
