"""
backtest_multi_symbol.py -- Backtest 6 Meses Multi-Simbolo
============================================================
Simula XAUUSD + NAS100 + EURUSD en la misma cuenta $25K del reto.
Todos los trades comparten el mismo balance y limites de drawdown.

Config:
  XAUUSD  -> 0.40% riesgo (Indicator Trend: EMA50 + RSI + ADX)
  NAS100  -> 0.20% riesgo (Indicator Trend: EMA50 + RSI + ADX)
  EURUSD  -> 0.10% riesgo (Mean Reversion: BB + RSI + ADX)
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

# ─── CONFIG ───────────────────────────────────────────────────────────────────
CAPITAL_INICIAL = 25_000.0
DAILY_DD_LIMIT  = 0.04   # 4%
TOTAL_DD_LIMIT  = 0.08   # 8%
EOD_CLOSE_H     = 16
ADX_MIN         = 20.0
SL_ATR_MULT     = 2.5
TP_ATR_MULT     = 5.0
DAYS            = 180

SYMBOLS = [
    {"name": "XAUUSD", "aliases": ["XAUUSD","GOLD","XAUUSDm","XAUUSD.a","GOLD.a"],
     "risk": 0.40, "strategy": "TREND"},
    {"name": "NAS100", "aliases": ["NAS100","USTEC","NAS100m","US100","NDX"],
     "risk": 0.20, "strategy": "TREND"},
    {"name": "EURUSD", "aliases": ["EURUSD","EURUSDm"],
     "risk": 0.10, "strategy": "REVERSION"},
]

# ─── INDICADORES ──────────────────────────────────────────────────────────────
def _ema(s, n):    return s.ewm(span=n, adjust=False).mean()

def _rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).rolling(n).mean(); l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + g / l.replace(0, np.nan))

def _atr(h, l, c, n=14):
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()

def _adx(h, l, c, n=14):
    up = h.diff(); dn = -l.diff()
    pdm = pd.Series(0.0, index=h.index); mdm = pd.Series(0.0, index=h.index)
    pdm[(up>dn)&(up>0)] = up[(up>dn)&(up>0)]; mdm[(dn>up)&(dn>0)] = dn[(dn>up)&(dn>0)]
    tr = pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()], axis=1).max(axis=1)
    a = tr.rolling(n).mean()
    pi = 100*pdm.rolling(n).mean()/a.replace(0,np.nan); mi = 100*mdm.rolling(n).mean()/a.replace(0,np.nan)
    return (100*(pi-mi).abs()/(pi+mi).replace(0,np.nan)).rolling(n).mean()

def _bbands(s, n=20, std=2.0):
    m = s.rolling(n).mean(); sg = s.rolling(n).std(ddof=0)
    return m - std*sg, m, m + std*sg

# ─── SEÑALES ──────────────────────────────────────────────────────────────────
def get_signal_trend(row):
    """Indicator Trend: EMA50 + RSI + ADX."""
    if row['adx14'] < ADX_MIN: return None
    if row['close'] > row['ema50'] and row['rsi14'] > 55: return "LONG"
    if row['close'] < row['ema50'] and row['rsi14'] < 45: return "SHORT"
    return None

def get_signal_reversion(row):
    """Mean Reversion: BB + RSI + ADX."""
    if row['adx14'] > 25: return None  # Mercado tendencial, no operar reversion
    if row['close'] < row['bb_lo'] and row['rsi14'] < 32: return "LONG"
    if row['close'] > row['bb_hi'] and row['rsi14'] > 68: return "SHORT"
    return None

# ─── DATOS ────────────────────────────────────────────────────────────────────
def get_data(symbol, aliases):
    for alias in aliases:
        if mt5.symbol_info(alias):
            to_dt   = datetime.now(timezone.utc)
            from_dt = to_dt - timedelta(days=DAYS)
            rates   = mt5.copy_rates_range(alias, mt5.TIMEFRAME_H1, from_dt, to_dt)
            if rates is not None and len(rates) > 50:
                df = pd.DataFrame(rates)
                df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
                df.set_index("time", inplace=True)
                df['ema50'] = _ema(df['close'], 50)
                df['rsi14'] = _rsi(df['close'], 14)
                df['adx14'] = _adx(df['high'], df['low'], df['close'], 14)
                df['atr14'] = _atr(df['high'], df['low'], df['close'], 14)
                lo, _, hi = _bbands(df['close'], 20, 2.0)
                df['bb_lo'] = lo; df['bb_hi'] = hi
                df.dropna(inplace=True)
                return alias, df
    return None, None

# ─── SIMULAR TRADE ────────────────────────────────────────────────────────────
def simulate_trade(df, idx, signal, entry, sl, tp):
    future = df.iloc[idx+1:]
    for f_idx, (f_ts, f_row) in enumerate(future.iterrows()):
        if signal == "LONG":
            if f_row['low']  <= sl: return sl, f_ts, idx+1+f_idx
            if f_row['high'] >= tp: return tp, f_ts, idx+1+f_idx
        else:
            if f_row['high'] >= sl: return sl, f_ts, idx+1+f_idx
            if f_row['low']  <= tp: return tp, f_ts, idx+1+f_idx
        if f_ts.hour >= EOD_CLOSE_H:
            return float(f_row['close']), f_ts, idx+1+f_idx
    return None, None, idx+1

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def run():
    print("\n" + "="*100)
    print("  BACKTEST MULTI-SIMBOLO 6 MESES | $25K Prop Firm")
    print(f"  XAUUSD 0.40% | NAS100 0.20% | EURUSD 0.10% | DD Limites: 4%/8%")
    print("="*100 + "\n")

    if not mt5.initialize():
        print("[ERROR] No se pudo conectar a MT5.")
        return

    # Cargar datos de todos los simbolos
    all_signals = []  # Lista unificada de (timestamp, sym_config, df, idx)
    for sym in SYMBOLS:
        found, df = get_data(sym["name"], sym["aliases"])
        if df is None:
            print(f"  [SKIP] {sym['name']} no disponible en MT5")
            continue
        print(f"  [OK] {found}: {len(df)} velas H1 cargadas")
        sym["found"] = found
        sym["df"]    = df

    mt5.shutdown()

    # Combinar signals de todos los simbolos ordenados cronologicamente
    all_events = []
    for sym in SYMBOLS:
        if "df" not in sym: continue
        df = sym["df"]
        strategy = sym["strategy"]
        for idx, (ts, row) in enumerate(df.iterrows()):
            if ts.hour >= (EOD_CLOSE_H - 1): continue
            signal = get_signal_trend(row) if strategy == "TREND" else get_signal_reversion(row)
            if signal:
                all_events.append((ts, sym, df, idx, signal))

    # Ordenar por timestamp
    all_events.sort(key=lambda x: x[0])

    # Estado del backtest
    balance       = CAPITAL_INICIAL
    peak_balance  = CAPITAL_INICIAL
    day_start_bal = {}
    trades        = []
    account_blown = False
    blow_reason   = ""
    # Rastrear ultima salida por simbolo para no solapar trades
    last_exit_idx = {s["name"]: 0 for s in SYMBOLS}
    last_exit_ts  = {s["name"]: None for s in SYMBOLS}

    print(f"\n{'#':<4} {'Fecha':^20} {'Sym':^8} {'Señal':^6} {'Entrada':>9} {'SL':>9} {'TP':>9} "
          f"{'Salida':>9} {'PnL $':>8} {'Balance':>11} {'DDd':>6} {'DDt':>6} {'Estado':^12}")
    print("-"*140)

    for ts, sym, df, idx, signal in all_events:
        sym_name = sym["name"]

        # No solapar trades del mismo simbolo
        if last_exit_ts[sym_name] and ts <= last_exit_ts[sym_name]:
            continue

        entry   = float(df.iloc[idx]['close'])
        atr_val = float(df.iloc[idx]['atr14'])
        sl      = entry - atr_val*SL_ATR_MULT if signal=="LONG" else entry + atr_val*SL_ATR_MULT
        tp      = entry + atr_val*TP_ATR_MULT if signal=="LONG" else entry - atr_val*TP_ATR_MULT
        sl_dist = abs(entry - sl)
        if sl_dist == 0: continue

        today     = ts.date()
        day_start = day_start_bal.get(today, balance)
        daily_dd  = (day_start - balance) / day_start if day_start > 0 else 0
        total_dd  = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0

        if daily_dd >= DAILY_DD_LIMIT or total_dd >= TOTAL_DD_LIMIT:
            continue  # Guard activo

        risk_amt   = balance * (sym["risk"] / 100)
        exit_price, exit_ts, exit_idx = simulate_trade(df, idx, signal, entry, sl, tp)
        if exit_ts is None: continue

        pnl_r   = (exit_price-entry)/sl_dist if signal=="LONG" else (entry-exit_price)/sl_dist
        pnl_usd = risk_amt * pnl_r

        prev_bal     = balance
        balance     += pnl_usd
        peak_balance  = max(peak_balance, balance)
        last_exit_ts[sym_name] = exit_ts

        exit_date = exit_ts.date()
        if exit_date not in day_start_bal:
            day_start_bal[exit_date] = balance - pnl_usd

        day_dd_post   = max(0, (day_start_bal.get(today, prev_bal) - balance) / day_start_bal.get(today, prev_bal)) * 100
        total_dd_post = max(0, (peak_balance - balance) / peak_balance) * 100

        if balance <= CAPITAL_INICIAL * (1 - TOTAL_DD_LIMIT):
            account_blown = True
            blow_reason   = f"Total DD > {TOTAL_DD_LIMIT*100:.0f}%"
            status = "[BLOWN]"
        elif day_dd_post >= DAILY_DD_LIMIT * 100:
            status = "[STOP DIA]"
        elif total_dd_post >= TOTAL_DD_LIMIT * 50:
            status = "[CUIDADO]"
        else:
            status = "[OK]"

        win = "OK" if pnl_usd > 0 else "XX"
        num = len(trades) + 1
        print(f"{num:<4} {str(ts)[:19]:^20} {sym_name:^8} {signal+' '+win:^8} {entry:>9.2f} "
              f"{sl:>9.2f} {tp:>9.2f} {exit_price:>9.2f} {pnl_usd:>+8.2f} "
              f"${balance:>10,.2f} {day_dd_post:>5.2f}% {total_dd_post:>5.2f}% {status:^12}")

        trades.append({"date": str(ts)[:10], "time": str(ts)[:19], "symbol": sym_name,
                        "signal": signal, "pnl_usd": pnl_usd, "balance": balance,
                        "daily_dd": day_dd_post, "total_dd": total_dd_post})

        if account_blown:
            print(f"\n[!!!] CUENTA DESCALIFICADA: {blow_reason} en trade #{num} -- {str(ts)[:10]}")
            break

    # ─── RESUMEN ──────────────────────────────────────────────────────────────
    print("\n" + "="*100)
    print("  RESUMEN FINAL MULTI-SIMBOLO")
    print("="*100)

    if not trades:
        print("  [!] Sin trades. Revisa MT5 y los simbolos disponibles.")
        return

    by_sym  = {}
    for t in trades:
        by_sym.setdefault(t["symbol"], []).append(t)

    wins   = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    pnl_total = sum(t["pnl_usd"] for t in trades)
    wr        = len(wins)/len(trades)*100 if trades else 0
    max_dd    = max(t["total_dd"] for t in trades)
    avg_win   = sum(t["pnl_usd"] for t in wins)/len(wins) if wins else 0
    avg_loss  = sum(t["pnl_usd"] for t in losses)/len(losses) if losses else 0
    pf        = abs(sum(t["pnl_usd"] for t in wins)/sum(t["pnl_usd"] for t in losses)) if losses and sum(t["pnl_usd"] for t in losses)!=0 else float('inf')

    print(f"\n  Periodo:          {trades[0]['date']}  ->  {trades[-1]['date']}")
    print(f"  Capital inicial:  ${CAPITAL_INICIAL:>12,.2f}")
    print(f"  Balance final:    ${balance:>12,.2f}")
    print(f"  PnL Total:        ${pnl_total:>+12,.2f}  ({pnl_total/CAPITAL_INICIAL*100:+.2f}%)")
    print(f"\n  Total Trades:     {len(trades)}")
    print(f"  Ganadores:        {len(wins)}  ({wr:.1f}%)")
    print(f"  Perdedores:       {len(losses)}  ({100-wr:.1f}%)")
    print(f"  Ganancia media:   ${avg_win:>+.2f}")
    print(f"  Perdida media:    ${avg_loss:>+.2f}")
    print(f"  Profit Factor:    {pf:.2f}")
    print(f"\n  Max Drawdown:     {max_dd:.2f}%  (limite: {TOTAL_DD_LIMIT*100:.0f}%)")

    print("\n  --- POR SIMBOLO ---")
    for sym_name, sym_trades in by_sym.items():
        s_wins  = [t for t in sym_trades if t["pnl_usd"] > 0]
        s_pnl   = sum(t["pnl_usd"] for t in sym_trades)
        s_wr    = len(s_wins)/len(sym_trades)*100 if sym_trades else 0
        print(f"  {sym_name:<10}  Trades: {len(sym_trades):>3}  WR: {s_wr:>5.1f}%  PnL: ${s_pnl:>+8.2f}")

    print("\n  --- VEREDICTO PROP FIRM ---")
    target_pct = 10.0
    pnl_pct    = pnl_total / CAPITAL_INICIAL * 100
    if account_blown:
        print(f"  [FAIL] CUENTA PERDIDA: {blow_reason}")
        print(f"         >> Reducir riesgo o filtrar simbolos correlacionados")
    else:
        print(f"  [OK] LA CUENTA SOBREVIVIO LOS 6 MESES")
        if pnl_total >= CAPITAL_INICIAL * (target_pct/100):
            print(f"  [PASS] RETO SUPERADO: +{pnl_pct:.2f}% vs objetivo +{target_pct:.0f}%")
            meses_proy = 6 * (target_pct / pnl_pct)
            print(f"  [INFO] Tiempo estimado para el reto real: ~{meses_proy:.1f} meses")
        else:
            meses_proy = 6 * (target_pct / pnl_pct) if pnl_pct > 0 else 999
            print(f"  [INFO] Reto NO superado: +{pnl_pct:.2f}% vs +{target_pct:.0f}%")
            print(f"         Ritmo actual: el reto se pasaria en ~{meses_proy:.1f} meses")

    print("\n" + "="*100 + "\n")

if __name__ == "__main__":
    run()
