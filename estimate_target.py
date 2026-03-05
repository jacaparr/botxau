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
DAYS         = 365  # Usamos 1 año para mayor precisión en la media mensual

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

def run_sim(symbol, risk_pct):
    if not mt5.initialize(): return None
    
    aliases = ["XAUUSD","GOLD","XAUUSDm","XAUUSD.a"]
    target_sym = None
    for a in aliases:
        if mt5.symbol_info(a):
            target_sym = a
            break
    if not target_sym: 
        mt5.shutdown()
        return None
        
    to_dt   = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    rates   = mt5.copy_rates_range(target_sym, mt5.TIMEFRAME_H1, from_dt, to_dt)
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
    day_start_bal = {}
    trades = []
    
    last_exit = None
    
    for idx, (ts, row) in enumerate(df.iterrows()):
        if last_exit and ts <= last_exit: continue
        if ts.hour >= EOD_CLOSE_H - 1: continue
        
        # Signal Trend
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
        
        # Drawdown check
        today = ts.date()
        d_s = day_start_bal.get(today, balance)
        if (d_s-balance)/d_s >= DAILY_DD_LIM: continue
        
        risk_amt = balance * (risk_pct/100)
        
        # Sim trade
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
        
        if exit_ts.date() not in day_start_bal:
            day_start_bal[exit_ts.date()] = balance - pnl_usd
            
        trades.append({"pnl": pnl_usd, "ts": exit_ts, "dd": (peak-balance)/peak})
        
        if balance <= CAPITAL*(1-TOTAL_DD_LIM): break

    if not trades: return None
    
    total_pnl = balance - CAPITAL
    pnl_pct = (total_pnl / CAPITAL) * 100
    avg_monthly_pnl_pct = pnl_pct / (DAYS / 30)
    months_to_10 = 10 / avg_monthly_pnl_pct if avg_monthly_pnl_pct > 0 else 999
    
    return {
        "pnl_pct": pnl_pct,
        "months": months_to_10,
        "max_dd": max(t["dd"] for t in trades) * 100,
        "trades": len(trades)
    }

print("\n--- ESTIMACIÓN DE TIEMPO PARA OBJETIVO 10% ($2,500) ---")
for r in [0.45, 0.50, 0.60]:
    res = run_sim("XAUUSD", r)
    if res:
        print(f"Riesgo {r:.2f}% | PnL 12m: {res['pnl_pct']:.1f}% | MaxDD: {res['max_dd']:.2f}% | Meses para 10%: {res['months']:.1f} meses")
    else:
        print(f"Riesgo {r:.2f}% | Error en simulación")
