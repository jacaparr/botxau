import sys, io
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

# Configuración UTF-8
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except: pass

CAPITAL      = 25_000.0
DAILY_DD_LIM = 0.04
TOTAL_DD_LIM = 0.08
EOD_CLOSE_H  = 16
ADX_MIN      = 20.0
SL_ATR_MULT  = 2.5
TP_ATR_MULT  = 5.0
DAYS         = 365 

def _ema(s,n):  return s.ewm(span=n,adjust=False).mean()
def _rsi(s,n=14):
    d=s.diff(); g=d.clip(lower=0).rolling(n).mean(); l=(-d.clip(upper=0)).rolling(n).mean()
    return 100-100/(1+g/l.replace(0,np.nan))
def _atr(h,l,c,n=14):
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()
def _adx(h,lo,c,n=14):
    up=h.diff(); dn=-lo.diff()
    pdm=pd.Series(0.,index=h.index); mdm=pd.Series(0.,index=h.index)
    pdm[(up>dn)&(up>0)]=up[(up>dn)&(up>0)]; mdm[(dn>up)&(dn>0)]=dn[(dn>up)&(dn>0)]
    tr=pd.concat([h-lo,(h-c.shift()).abs(),(lo-c.shift()).abs()],axis=1).max(axis=1)
    a=tr.rolling(n).mean(); pi=100*pdm.rolling(n).mean()/a.replace(0,np.nan)
    mi=100*mdm.rolling(n).mean()/a.replace(0,np.nan)
    return (100*(pi-mi).abs()/(pi+mi).replace(0,np.nan)).rolling(n).mean()

CANDIDATES = {
    "XAUUSD": ["XAUUSD", "GOLD", "XAUUSDm"],
    "XAGUSD": ["XAGUSD", "SILVER"],
    "EURUSD": ["EURUSD", "EURUSDm"],
    "GBPUSD": ["GBPUSD", "GBPUSDm"],
    "USDJPY": ["USDJPY", "USDJPYm"],
    "AUDUSD": ["AUDUSD", "AUDUSDm"],
    "USDCAD": ["USDCAD", "USDCADm"],
    "USDCHF": ["USDCHF", "USDCHFm"],
    "NAS100": ["NAS100", "USTEC", "US100", "NDX"],
    "US30":   ["US30", "DJI", "US30m"],
    "GER40":  ["GER40", "DE40", "DAX", "DAX40"],
    "BTCUSD": ["BTCUSD", "BTCUSD.a", "BTCUSDT"],
    "ETHUSD": ["ETHUSD", "ETHUSD.a", "ETHUSDT"],
    "WTI":    ["WTI", "USOIL", "UKOIL", "OIL"],
}

def get_best_alias(aliases):
    for a in aliases:
        if mt5.symbol_info(a): return a
    return None

def run_backtest(symbol_name, risk_pct):
    if not mt5.initialize(): return None
    alias = get_best_alias(CANDIDATES[symbol_name])
    if not alias: 
        mt5.shutdown()
        return None
        
    to_dt   = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    rates   = mt5.copy_rates_range(alias, mt5.TIMEFRAME_H1, from_dt, to_dt)
    mt5.shutdown()
    
    if rates is None or len(rates) < 100: return None
    
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None)
    df.set_index("time", inplace=True)
    df['ema'] = _ema(df['close'],50)
    df['rsi'] = _rsi(df['close'],14)
    df['adx'] = _adx(df['high'],df['low'],df['close'],14)
    df['atr'] = _atr(df['high'],df['low'],df['close'],14)
    df.dropna(inplace=True)
    
    balance = CAPITAL
    peak = CAPITAL
    trades = []
    last_exit = None
    
    for idx, (ts, row) in enumerate(df.iterrows()):
        if last_exit and ts <= last_exit: continue
        if ts.hour >= EOD_CLOSE_H - 1: continue
        
        sig = None
        if row['adx'] >= ADX_MIN:
            if row['close'] > row['ema'] and row['rsi'] > 55: sig = "L"
            elif row['close'] < row['ema'] and row['rsi'] < 45: sig = "S"
            
        if not sig: continue
        
        entry = float(row['close'])
        atr_v = float(row['atr'])
        sl = entry - atr_v*SL_ATR_MULT if sig=="L" else entry + atr_v*SL_ATR_MULT
        tp = entry + atr_v*TP_ATR_MULT if sig=="L" else entry - atr_v*TP_ATR_MULT
        sl_d = abs(entry-sl)
        if sl_d == 0: continue
        
        risk_amt = balance * (risk_pct/100)
        
        exit_p, exit_ts = None, None
        for f_idx, (f_ts, f_row) in enumerate(df.iloc[idx+1:].iterrows()):
            if sig=="L":
                if f_row['low']<=sl:  exit_p, exit_ts = sl, f_ts; break
                if f_row['high']>=tp: exit_p, exit_ts = tp, f_ts; break
            else:
                if f_row['high']>=sl: exit_p, exit_ts = sl, f_ts; break
                if f_row['low']<=tp:  exit_p, exit_ts = tp, f_ts; break
            if f_ts.hour >= EOD_CLOSE_H:
                exit_p, exit_ts = float(f_row['close']), f_ts; break
        
        if not exit_ts: continue
        
        pnl_r = (exit_p-entry)/sl_d if sig=="L" else (entry-exit_p)/sl_d
        pnl_usd = risk_amt * pnl_r
        
        balance += pnl_usd
        peak = max(peak, balance)
        last_exit = exit_ts
        trades.append({"pnl": pnl_usd, "ts": exit_ts, "dd": (peak-balance)/peak})
        
        if balance <= CAPITAL*(1-TOTAL_DD_LIM): break

    if not trades: return None
    
    total_pnl = balance - CAPITAL
    pnl_pct = (total_pnl / CAPITAL) * 100
    avg_monthly = pnl_pct / (DAYS/30)
    
    pos_pnl = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    neg_pnl = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    pf = pos_pnl / neg_pnl if neg_pnl > 0 else 99.0
    
    return {
        "pnl_pct": pnl_pct,
        "avg_monthly": avg_monthly,
        "max_dd": max(t["dd"] for t in trades) * 100,
        "trades_count": len(trades),
        "pf": pf
    }

print(f"{'SYM':<8} | {'PnL 1y':>8} | {'Avg/Mo':>7} | {'MaxDD':>7} | {'Trades':>6} | {'PF':>5}")
print("-" * 60)

results = []
for sym in CANDIDATES:
    res = run_backtest(sym, 0.45)
    if res:
        print(f"{sym:<8} | {res['pnl_pct']:>7.1f}% | {res['avg_monthly']:>6.1f}% | {res['max_dd']:>6.2f}% | {res['trades_count']:>6} | {res['pf']:>4.1f}")
        results.append((sym, res))

print("\n--- ANALISIS DE CESTA MULTI-SIMBOLO ---")
# Simulación simple de suma de rendimientos (suponiendo baja correlación en trades)
top_3 = sorted(results, key=lambda x: x[1]['avg_monthly'], reverse=True)[:3]
total_avg = sum(s[1]['avg_monthly'] for s in top_3)
est_months = 10 / total_avg if total_avg > 0 else 99
print(f"Top 3 Basket ({', '.join([s[0] for s in top_3])}):")
print(f" - Ganancia Mensual Est: {total_avg:.1f}%")
print(f" - Tiempo para el 10%: {est_months:.1f} meses")
