
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta

# CAPITAL DE PRUEBA
CAPITAL = 100000
DAYS = 365

def run_performance_test(risk_pct, adx_xau, adx_eur):
    if not mt5.initialize(): return 0, 0
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    # Data (1h for filters, 15m for XAU entries)
    r_x15 = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M15, from_dt, to_dt)
    r_x1h = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, from_dt, to_dt)
    r_e1h = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_H1, from_dt, to_dt)
    
    dfx15 = pd.DataFrame(r_x15); dfx15["time"] = pd.to_datetime(dfx15["time"], unit="s", utc=True).dt.tz_localize(None); dfx15.set_index("time", inplace=True)
    dfx1h = pd.DataFrame(r_x1h); dfx1h["time"] = pd.to_datetime(dfx1h["time"], unit="s", utc=True).dt.tz_localize(None); dfx1h.set_index("time", inplace=True)
    dfe1h = pd.DataFrame(r_e1h); dfe1h["time"] = pd.to_datetime(dfe1h["time"], unit="s", utc=True).dt.tz_localize(None); dfe1h.set_index("time", inplace=True)
    
    # Indicators
    dfx1h['adx'] = ta.adx(dfx1h['high'], dfx1h['low'], dfx1h['close'])['ADX_14']
    dfe1h['adx'] = ta.adx(dfe1h['high'], dfe1h['low'], dfe1h['close'])['ADX_14']
    dfe1h['rsi'] = ta.rsi(dfe1h['close'], length=14)
    bb = ta.bbands(dfe1h['close'], length=20, std=2)
    atr_e = ta.atr(dfe1h['high'], dfe1h['low'], dfe1h['close'], length=14)
    
    trades = []
    
    # XAU Logic
    ema50 = dfx1h["close"].ewm(span=50, adjust=False).mean()
    for d in sorted(set(dfx15.index.date)):
        day_df = dfx15[dfx15.index.date == d]
        adx_today = dfx1h.loc[dfx1h.index.date < d]
        if adx_today.empty or adx_today.iloc[-1]['adx'] < adx_xau: continue
        
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
        trades.append(CAPITAL * (risk_pct/100) * pnl_r)

    # EUR Logic
    for i in range(40, len(dfe1h)-1, 4):
        last = dfe1h.iloc[i]
        if last['adx'] > adx_eur: continue
        if last['rsi'] < 30 and last['close'] < bb.iloc[i, 0]:
            s, entry, sl, tp = "LONG", last['close'], last['close'] - atr_e.iloc[i]*1.5, bb.iloc[i, 1]
        elif last['rsi'] > 70 and last['close'] > bb.iloc[i, 2]:
            s, entry, sl, tp = "SHORT", last['close'], last['close'] + atr_e.iloc[i]*1.5, bb.iloc[i, 1]
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
        pnl_r = (exit_p - entry)/(entry - sl) if s == "LONG" else (entry - exit_p)/(sl - entry)
        trades.append(CAPITAL * (risk_pct/100) * pnl_r)
        
    mt5.shutdown()
    return sum(trades), len(trades)

if __name__ == "__main__":
    print(f"Analizando 3 Perfiles de Riesgo (1 Año, Capital ${CAPITAL:,})")
    
    # 1. Conservador (El que acabamos de hacer)
    c_pnl, c_tr = run_performance_test(0.5, 30, 20)
    # 2. Equilibrado (Riesgo 1.5%, Filtros Base)
    e_pnl, e_tr = run_performance_test(1.5, 20, 25)
    # 3. Agresivo (Riesgo 2.5%, Sin filtros estrictos)
    a_pnl, a_tr = run_performance_test(2.5, 10, 40)
    
    print(f"\n1. CONSERVADOR (Riesgo 0.5%): +${c_pnl:,.2f} ({c_pnl/CAPITAL*100:+.2f}%) | {c_tr} trades")
    print(f"2. EQUILIBRADO (Riesgo 1.5%): +${e_pnl:,.2f} ({e_pnl/CAPITAL*100:+.2f}%) | {e_tr} trades")
    print(f"3. AGRESIVO    (Riesgo 2.5%): +${a_pnl:,.2f} ({a_pnl/CAPITAL*100:+.2f}%) | {a_tr} trades")
