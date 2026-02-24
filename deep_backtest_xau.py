
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta

CAPITAL = 100000
DAYS = 730

def backtest_xau_breakout(risk_pct, tp_mult, adx_min=0):
    if not mt5.initialize(): return None
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    symbol = "XAUUSD"
    for s in ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"]:
        if mt5.symbol_info(s): symbol = s; break
            
    r_x15 = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M15, from_dt, to_dt)
    r_x1h = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, from_dt, to_dt)
    
    if r_x15 is None or r_x1h is None: return 0, 0, 0
    
    df15 = pd.DataFrame(r_x15); df15["time"] = pd.to_datetime(df15["time"], unit="s", utc=True).dt.tz_localize(None); df15.set_index("time", inplace=True)
    df1h = pd.DataFrame(r_x1h); df1h["time"] = pd.to_datetime(df1h["time"], unit="s", utc=True).dt.tz_localize(None); df1h.set_index("time", inplace=True)
    
    if adx_min > 0:
        df1h['adx'] = ta.adx(df1h['high'], df1h['low'], df1h['close'])['ADX_14']
    
    ema50 = df1h["close"].ewm(span=50, adjust=False).mean()
    
    trades = []
    balance = CAPITAL
    max_balance = CAPITAL
    max_dd = 0
    
    for d in sorted(set(df15.index.date)):
        day_df = df15[df15.index.date == d]
        
        # Filtro de Tendencia (opcional)
        if adx_min > 0:
            adx_today = df1h.loc[df1h.index.date < d]
            if adx_today.empty or adx_today.iloc[-1]['adx'] < adx_min: continue
        
        # Rango Asiático (00:00 - 06:00)
        asian = day_df[(day_df.index.hour >= 0) & (day_df.index.hour < 6)]
        if len(asian) < 4: continue
        hi, lo = float(asian["high"].max()), float(asian["low"].min())
        rng = hi - lo
        if rng < 3.0 or rng > 25.0: continue
        
        # EMA Filter
        idx_e = ema50.index.date <= d
        if not idx_e.any(): continue
        e50 = ema50.loc[idx_e].iloc[-1]
        
        # London Breakout (07:00 - 10:00)
        london = day_df[(day_df.index.hour >= 7) & (day_df.index.hour < 10)]
        setup = None
        for t, candle in london.iterrows():
            close = float(candle["close"])
            if close > hi and close > e50:
                setup = {"s": "LONG", "entry": close, "sl": lo - 0.5, "tp": close + rng*tp_mult}
                break
            elif close < lo and close < e50:
                setup = {"s": "SHORT", "entry": close, "sl": hi + 0.5, "tp": close - rng*tp_mult}
                break
        
        if setup:
            # Simulación de Trade
            rest = day_df[day_df.index > t]
            exit_p = setup["entry"]
            for _, r in rest.iterrows():
                if setup["s"] == "LONG":
                    if r["low"] <= setup["sl"]: exit_p = setup["sl"]; break
                    if r["high"] >= setup["tp"]: exit_p = setup["tp"]; break
                else:
                    if r["high"] >= setup["sl"]: exit_p = setup["sl"]; break
                    if r["low"] <= setup["tp"]: exit_p = setup["tp"]; break
                    
            pnl_r = (exit_p - setup["entry"])/(setup["entry"] - setup["sl"]) if setup["s"] == "LONG" else (setup["entry"] - exit_p)/(setup["sl"] - setup["entry"])
            pnl_usd = (balance * risk_pct/100) * pnl_r
            balance += pnl_usd
            max_balance = max(max_balance, balance)
            dd = (max_balance - balance) / max_balance * 100
            max_dd = max(max_dd, dd)
            trades.append(pnl_usd)
            
    mt5.shutdown()
    return (balance - CAPITAL) / CAPITAL * 100, max_dd, len(trades)

if __name__ == "__main__":
    print(f"Buscando el 70% Anual - Asian Breakout Gold (100k)")
    results = []
    risks = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    multipliers = [2.0, 2.5, 3.0, 4.0, 5.0]
    
    for r in risks:
        for m in multipliers:
            res = backtest_xau_breakout(r, m)
            if res:
                pnl, dd, tr = res
                results.append({"risk": r, "tp_mult": m, "pnl": pnl, "dd": dd, "trades": tr})
                print(f"Risk {r}% | TP x{m} -> PnL: {pnl:+.2f}% | DD: {dd:.2f}% | {tr} trades")

    print("\n--- MEJORES RESULTADOS ---")
    sorted_res = sorted(results, key=lambda x: x["pnl"], reverse=True)
    for res in sorted_res[:5]:
        print(f"Riesgo {res['risk']}% | TP x{res['tp_mult']} | Profit: {res['pnl']:+.2f}% | Drawdown: {res['dd']:.2f}%")
