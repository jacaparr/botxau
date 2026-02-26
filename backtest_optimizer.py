"""
backtest_optimizer.py -- Comparativa de Combinaciones para Reto Prop Firm $25K
================================================================================
Prueba automaticamente todas las combinaciones de simbolos y riesgos.
Encuentra la configuracion optima para pasar el 10% en el menor tiempo posible
sin violar los limites de drawdown del prop firm (DD diario 4%, total 8%).
"""

import sys, io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except: pass

import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import itertools

CAPITAL      = 25_000.0
DAILY_DD_LIM = 0.04
TOTAL_DD_LIM = 0.08
EOD_CLOSE_H  = 16
ADX_MIN      = 20.0
SL_ATR_MULT  = 2.5
TP_ATR_MULT  = 5.0
DAYS         = 180

# ─── Indicadores ──────────────────────────────────────────────────────────────
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
def _bb(s,n=20,std=2.):
    m=s.rolling(n).mean(); sg=s.rolling(n).std(ddof=0); return m-std*sg, m+std*sg

def signal_trend(row):
    if row['adx']<ADX_MIN: return None
    if row['close']>row['ema'] and row['rsi']>55: return "L"
    if row['close']<row['ema'] and row['rsi']<45: return "S"
    return None

def signal_reversion(row):
    if row['adx']>25: return None
    if row['close']<row['bbl'] and row['rsi']<32: return "L"
    if row['close']>row['bbh'] and row['rsi']>68: return "S"
    return None

# ─── Cargar datos una sola vez ────────────────────────────────────────────────
SYMBOL_DATA = {}  # cache

ALL_CANDIDATES = {
    "XAUUSD": {"aliases": ["XAUUSD","GOLD","XAUUSDm","XAUUSD.a"],   "strat": "T"},
    "NAS100": {"aliases": ["NAS100","USTEC","US100","NDX","NAS100m"],"strat": "T"},
    "EURUSD": {"aliases": ["EURUSD","EURUSDm"],                      "strat": "R"},
    "GBPUSD": {"aliases": ["GBPUSD","GBPUSDm"],                      "strat": "R"},
    "US30":   {"aliases": ["US30","DJI","US30m","DJ30"],             "strat": "T"},
}

def load_all():
    print("[...] Descargando datos de MT5...")
    for name, cfg in ALL_CANDIDATES.items():
        for alias in cfg["aliases"]:
            if mt5.symbol_info(alias):
                to_dt   = datetime.now(timezone.utc)
                from_dt = to_dt - timedelta(days=DAYS)
                rates   = mt5.copy_rates_range(alias, mt5.TIMEFRAME_H1, from_dt, to_dt)
                if rates is not None and len(rates) > 60:
                    df = pd.DataFrame(rates)
                    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None)
                    df.set_index("time", inplace=True)
                    df['ema'] = _ema(df['close'],50); df['rsi'] = _rsi(df['close'],14)
                    df['adx'] = _adx(df['high'],df['low'],df['close'],14)
                    df['atr'] = _atr(df['high'],df['low'],df['close'],14)
                    lo, hi   = _bb(df['close'],20,2.)
                    df['bbl'] = lo; df['bbh'] = hi
                    df.dropna(inplace=True)
                    SYMBOL_DATA[name] = {"df": df, "strat": cfg["strat"], "alias": alias}
                    print(f"  [OK] {alias}: {len(df)} velas")
                    break
        if name not in SYMBOL_DATA:
            print(f"  [SKIP] {name} no disponible")

def build_events(sym_name, risk_pct):
    """Genera lista de (timestamp, sym_name, idx, signal, risk_pct, df)"""
    if sym_name not in SYMBOL_DATA: return []
    df    = SYMBOL_DATA[sym_name]["df"]
    strat = SYMBOL_DATA[sym_name]["strat"]
    evts  = []
    for idx, (ts, row) in enumerate(df.iterrows()):
        if ts.hour >= EOD_CLOSE_H - 1: continue
        sig = signal_trend(row) if strat=="T" else signal_reversion(row)
        if sig:
            evts.append((ts, sym_name, idx, sig, risk_pct, df))
    return evts

def sim_trade(df, idx, sig, entry, sl, tp):
    for f_idx, (f_ts, f_row) in enumerate(df.iloc[idx+1:].iterrows()):
        if sig=="L":
            if f_row['low']<=sl:  return sl, f_ts
            if f_row['high']>=tp: return tp, f_ts
        else:
            if f_row['high']>=sl: return sl, f_ts
            if f_row['low']<=tp:  return tp, f_ts
        if f_ts.hour >= EOD_CLOSE_H:
            return float(f_row['close']), f_ts
    return None, None

def run_backtest(config):
    """
    config: list of (sym_name, risk_pct)
    Returns: dict with summary stats
    """
    # Build & sort all events
    all_evts = []
    for sym_name, risk_pct in config:
        all_evts += build_events(sym_name, risk_pct)
    all_evts.sort(key=lambda x: x[0])

    balance       = CAPITAL
    peak          = CAPITAL
    day_start_bal = {}
    trades        = []
    blown         = False
    last_exit     = {s: None for s,_ in config}

    for ts, sym_name, idx, sig, risk_pct, df in all_evts:
        if last_exit[sym_name] and ts <= last_exit[sym_name]: continue

        row    = df.iloc[idx]
        entry  = float(row['close'])
        atr_v  = float(row['atr'])
        sl     = entry - atr_v*SL_ATR_MULT if sig=="L" else entry + atr_v*SL_ATR_MULT
        tp     = entry + atr_v*TP_ATR_MULT if sig=="L" else entry - atr_v*TP_ATR_MULT
        sl_d   = abs(entry-sl)
        if sl_d == 0: continue

        today = ts.date()
        d_s   = day_start_bal.get(today, balance)
        if (d_s-balance)/d_s >= DAILY_DD_LIM: continue
        if (peak-balance)/peak >= TOTAL_DD_LIM: continue

        risk_amt          = balance * (risk_pct/100)
        exit_p, exit_ts   = sim_trade(df, idx, sig, entry, sl, tp)
        if exit_ts is None: continue

        pnl_r   = (exit_p-entry)/sl_d if sig=="L" else (entry-exit_p)/sl_d
        pnl_usd = risk_amt * pnl_r

        prev_bal   = balance
        balance   += pnl_usd
        peak       = max(peak, balance)
        last_exit[sym_name] = exit_ts

        if exit_ts.date() not in day_start_bal:
            day_start_bal[exit_ts.date()] = balance - pnl_usd

        total_dd_pct = max(0,(peak-balance)/peak)*100

        trades.append({
            "pnl": pnl_usd,
            "balance": balance,
            "total_dd": total_dd_pct,
            "symbol": sym_name,
        })

        if balance <= CAPITAL*(1-TOTAL_DD_LIM):
            blown = True; break

    if not trades:
        return None

    wins   = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    pnl    = sum(t["pnl"] for t in trades)
    pnl_p  = pnl/CAPITAL*100
    wr     = len(wins)/len(trades)*100 if trades else 0
    max_dd = max(t["total_dd"] for t in trades)
    pf     = abs(sum(t["pnl"] for t in wins)/sum(t["pnl"] for t in losses)) if losses and sum(t["pnl"] for t in losses)!=0 else 99.9
    months = 6*(10/pnl_p) if pnl_p > 0 else 999

    return {
        "pnl_pct": pnl_p,
        "balance": balance,
        "trades":  len(trades),
        "wr":      wr,
        "max_dd":  max_dd,
        "pf":      pf,
        "months":  months,
        "blown":   blown,
    }

# ─── Configuraciones a probar ─────────────────────────────────────────────────
CONFIGS = [
    # Solo XAUUSD - distintos riesgos
    ("Solo XAUUSD  0.15%",   [("XAUUSD", 0.15)]),
    ("Solo XAUUSD  0.40%",   [("XAUUSD", 0.40)]),
    ("Solo XAUUSD  0.60%",   [("XAUUSD", 0.60)]),
    ("Solo XAUUSD  0.80%",   [("XAUUSD", 0.80)]),
    ("Solo XAUUSD  1.00%",   [("XAUUSD", 1.00)]),
    # XAUUSD + NAS100
    ("XAUUSD+NAS100  0.40+0.20",  [("XAUUSD",0.40),("NAS100",0.20)]),
    ("XAUUSD+NAS100  0.50+0.25",  [("XAUUSD",0.50),("NAS100",0.25)]),
    ("XAUUSD+NAS100  0.60+0.30",  [("XAUUSD",0.60),("NAS100",0.30)]),
    # XAUUSD + EURUSD
    ("XAUUSD+EURUSD  0.40+0.10",  [("XAUUSD",0.40),("EURUSD",0.10)]),
    ("XAUUSD+EURUSD  0.50+0.15",  [("XAUUSD",0.50),("EURUSD",0.15)]),
    # XAUUSD + NAS100 + EURUSD (3 simbolos)
    ("3x  XAUUSD0.40+NAS0.20+EUR0.10",  [("XAUUSD",0.40),("NAS100",0.20),("EURUSD",0.10)]),
    ("3x  XAUUSD0.50+NAS0.25+EUR0.15",  [("XAUUSD",0.50),("NAS100",0.25),("EURUSD",0.15)]),
    ("3x  XAUUSD0.60+NAS0.30+EUR0.10",  [("XAUUSD",0.60),("NAS100",0.30),("EURUSD",0.10)]),
    # XAUUSD + NAS100 + US30
    ("3x  XAUUSD0.40+NAS0.20+US30_0.20",[("XAUUSD",0.40),("NAS100",0.20),("US30",0.20)]),
    # 4 simbolos
    ("4x  XAU0.35+NAS0.15+EUR0.10+GBP0.10", [("XAUUSD",0.35),("NAS100",0.15),("EURUSD",0.10),("GBPUSD",0.10)]),
    ("4x  XAU0.40+NAS0.20+EUR0.10+US30_0.20", [("XAUUSD",0.40),("NAS100",0.20),("EURUSD",0.10),("US30",0.20)]),
]

def main():
    print("\n" + "="*110)
    print("  OPTIMIZADOR PROP FIRM $25K -- Comparativa de Combinaciones")
    print("="*110)

    if not mt5.initialize():
        print("[ERROR] MT5 no disponible"); return

    load_all()
    mt5.shutdown()

    if not SYMBOL_DATA:
        print("[ERROR] Sin datos"); return

    print(f"\n  {'Configuracion':<45} {'PnL%':>7} {'Trades':>7} {'WR%':>6} {'MaxDD%':>7} {'PF':>5} {'Meses10%':>9} {'Estado':>10}")
    print("  " + "-"*105)

    results = []
    for name, config in CONFIGS:
        # Filtrar simbolos no disponibles
        config_ok = [(s,r) for s,r in config if s in SYMBOL_DATA]
        if not config_ok:
            continue
        r = run_backtest(config_ok)
        if not r:
            continue

        blown_str = "[BLOWN]" if r["blown"] else ("[PASS]" if r["pnl_pct"]>=10 else "[OK]")
        flag = " <<< PASA" if r["pnl_pct"]>=10 and not r["blown"] else ""
        flag = " <<< OPTIMO" if r["pnl_pct"]>=10 and not r["blown"] and r["max_dd"]<4 else flag
        results.append((name, r, flag))

        print(f"  {name:<45} {r['pnl_pct']:>6.2f}% {r['trades']:>7} {r['wr']:>5.1f}% {r['max_dd']:>6.2f}% {r['pf']:>5.2f} {r['months']:>8.1f}m  {blown_str}{flag}")

    # Mejor resultado no blown
    valid = [(n,r) for n,r,_ in results if not r["blown"] and r["max_dd"]<TOTAL_DD_LIM*100]
    if valid:
        best = min(valid, key=lambda x: x[1]["months"])
        print("\n" + "="*110)
        print(f"  RECOMENDACION OPTIMA: {best[0]}")
        print(f"  PnL 6m: +{best[1]['pnl_pct']:.2f}%  |  MaxDD: {best[1]['max_dd']:.2f}%  |  Tiempo estimado reto: {best[1]['months']:.1f} meses")
        print("="*110 + "\n")

if __name__ == "__main__":
    main()
