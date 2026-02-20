"""
backtest_eurusd.py — Backtest London Breakout para EURUSD en MT5
=================================================================
Prueba la estrategia London Breakout con datos historicos reales de MT5.
La estrategia es la misma idea que el Asian Breakout del oro:
  1. Mide el rango asiatico (00:00-06:00 UTC)
  2. Busca breakout en London (07:00-10:00 UTC)
  3. SL al otro lado del rango, TP = rango x multiplicador

Uso:
    python backtest_eurusd.py --days 365
    python backtest_eurusd.py --days 180 --tp 2.0
"""

import MetaTrader5 as mt5
import pandas as pd
import argparse
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

# ── Parametros a optimizar ──
CONFIGS_TO_TEST = [
    # name, min_range, max_range, tp_mult, ema_filter, skip_monday
    ("Base",            0.0015, 0.0050, 2.0, True,  True),
    ("TP-1.5",          0.0015, 0.0050, 1.5, True,  True),
    ("TP-2.5",          0.0015, 0.0050, 2.5, True,  True),
    ("TP-3.0",          0.0015, 0.0050, 3.0, True,  True),
    ("Tight-range",     0.0020, 0.0040, 2.0, True,  True),
    ("Wide-range",      0.0010, 0.0060, 2.0, True,  True),
    ("No-EMA",          0.0015, 0.0050, 2.0, False, True),
    ("All-days",        0.0015, 0.0050, 2.0, True,  False),
    ("Conservative",    0.0020, 0.0040, 1.5, True,  True),
]

ASIAN_START_H  = 0
ASIAN_END_H    = 6
LONDON_START_H = 7
LONDON_END_H   = 10
MAX_ENTRY_CANDLES = 4
EMA_PERIOD     = 50
SL_BUFFER      = 0.0002  # 2 pips buffer
CAPITAL        = 100000
RISK_PCT       = 0.015   # 1.5%


@dataclass
class Trade:
    date: str
    signal: str
    entry: float
    sl: float
    tp: float
    exit_price: float
    result: str
    pnl_usd: float
    pnl_r: float
    range_size: float


def run_backtest(df_15m, df_1h, min_range, max_range, tp_mult,
                 use_ema, skip_monday):
    """Backtest London Breakout en EURUSD."""
    trades = []
    bal = CAPITAL
    dates = sorted(set(df_15m.index.date))
    risk_usd = CAPITAL * RISK_PCT

    for day in dates:
        # Skip weekends
        if pd.Timestamp(day).weekday() >= 5:
            continue
        # Skip Monday
        if skip_monday and pd.Timestamp(day).weekday() == 0:
            continue

        day_df = df_15m[df_15m.index.date == day]

        # 1. Rango asiatico
        asian = day_df[
            (day_df.index.hour >= ASIAN_START_H) &
            (day_df.index.hour < ASIAN_END_H)
        ]
        if len(asian) < 8:  # Necesitamos suficientes velas
            continue

        hi = float(asian["high"].max())
        lo = float(asian["low"].min())
        rng = hi - lo

        # Filtro de rango
        if rng < min_range or rng > max_range:
            continue

        # 2. EMA trend filter
        if use_ema:
            day_1h = df_1h[df_1h.index.date == day]
            if len(day_1h) < 2:
                continue
            ema_vals = df_1h["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
            ema_today = ema_vals.loc[ema_vals.index.date <= day]
            if len(ema_today) < EMA_PERIOD:
                continue
            ema50 = float(ema_today.iloc[-1])
        else:
            ema50 = None

        # 3. Buscar breakout en London
        london = day_df[
            (day_df.index.hour >= LONDON_START_H) &
            (day_df.index.hour < LONDON_END_H)
        ]
        if len(london) == 0:
            continue

        signal = None
        entry = 0
        for eidx, (_, candle) in enumerate(london.iterrows()):
            if eidx >= MAX_ENTRY_CANDLES:
                break
            close = float(candle["close"])

            if close > hi:
                if use_ema and ema50 and close < ema50:
                    continue
                signal = "LONG"
                entry = close
                break
            elif close < lo:
                if use_ema and ema50 and close > ema50:
                    continue
                signal = "SHORT"
                entry = close
                break

        if not signal:
            continue

        # 4. SL y TP
        if signal == "LONG":
            sl = lo - SL_BUFFER
            tp = entry + rng * tp_mult
        else:
            sl = hi + SL_BUFFER
            tp = entry - rng * tp_mult

        # 5. Simular resultado
        rest = day_df[day_df.index > london.index[min(eidx, len(london)-1)]]
        result = "OPEN"
        exit_p = entry

        if not rest.empty:
            for _, row in rest.iterrows():
                h, l = float(row["high"]), float(row["low"])

                if signal == "LONG":
                    if l <= sl:
                        result, exit_p = "LOSS", sl
                        break
                    elif h >= tp:
                        result, exit_p = "WIN", tp
                        break
                else:
                    if h >= sl:
                        result, exit_p = "LOSS", sl
                        break
                    elif l <= tp:
                        result, exit_p = "WIN", tp
                        break
            else:
                exit_p = float(rest["close"].iloc[-1])

        # 6. PnL
        if signal == "LONG":
            pnl_r = (exit_p - entry) / (entry - sl) if entry != sl else 0
        else:
            pnl_r = (entry - exit_p) / (sl - entry) if sl != entry else 0

        pnl_usd = risk_usd * pnl_r
        bal += pnl_usd

        trades.append(Trade(str(day), signal, entry, sl, tp, exit_p,
                           result, round(pnl_usd, 2), round(pnl_r, 2),
                           round(rng * 10000, 1)))  # rango en pips

    return trades, bal


def print_results(name, trades, bal, days):
    """Imprime resultados de un backtest."""
    if not trades:
        print(f"  {name:<16} | Sin trades")
        return None

    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    opens = [t for t in trades if t.result == "OPEN"]
    closed = wins + losses
    pnl = sum(t.pnl_usd for t in trades)
    wr = len(wins) / len(closed) * 100 if closed else 0
    pnl_pct = pnl / CAPITAL * 100
    monthly = pnl_pct / (days / 30)

    # Max DD
    eq, pk, mdd = CAPITAL, CAPITAL, 0
    for t in trades:
        eq += t.pnl_usd
        pk = max(pk, eq)
        mdd = max(mdd, (pk - eq) / pk * 100)

    # Profit factor
    win_sum = sum(t.pnl_usd for t in wins)
    loss_sum = abs(sum(t.pnl_usd for t in losses))
    pf = win_sum / loss_sum if loss_sum > 0 else 999

    ok = "ADD" if pnl > 0 and wr > 48 and mdd < 5 else "---"

    print(f"  {name:<16} | {len(closed):>3}t | WR:{wr:>5.1f}% | "
          f"PnL:{pnl_pct:>+7.2f}% | /mo:{monthly:>+5.2f}% | "
          f"DD:{mdd:>5.2f}% | PF:{pf:>5.2f} | {ok}")

    return {"name": name, "trades": len(closed), "wr": wr,
            "pnl": pnl_pct, "monthly": monthly, "mdd": mdd, "pf": pf, "ok": ok}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365)
    args = parser.parse_args()

    if not mt5.initialize():
        print("Error: MT5 no esta abierto")
        exit(1)

    sym = mt5.symbol_info("EURUSD")
    if not sym:
        print("Error: EURUSD no disponible")
        mt5.shutdown()
        exit(1)
    if not sym.visible:
        mt5.symbol_select("EURUSD", True)

    # Descargar datos
    utc_to = datetime.now(timezone.utc)
    utc_from = utc_to - timedelta(days=args.days + 10)

    print(f"\nDescargando {args.days} dias de EURUSD 15m...")
    rates_15m = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_M15, utc_from, utc_to)
    rates_1h = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_H1, utc_from, utc_to)

    if rates_15m is None or rates_1h is None:
        print("Error descargando datos")
        mt5.shutdown()
        exit(1)

    df_15m = pd.DataFrame(rates_15m)
    df_15m["time"] = pd.to_datetime(df_15m["time"], unit="s", utc=True)
    df_15m.set_index("time", inplace=True)

    df_1h = pd.DataFrame(rates_1h)
    df_1h["time"] = pd.to_datetime(df_1h["time"], unit="s", utc=True)
    df_1h.set_index("time", inplace=True)

    print(f"Datos: {len(df_15m)} velas 15m, {len(df_1h)} velas 1h")
    print(f"\n{'='*90}")
    print(f"  BACKTEST EURUSD LONDON BREAKOUT - {args.days} DIAS")
    print(f"  Capital: ${CAPITAL:,} | Riesgo: {RISK_PCT*100}%")
    print(f"{'='*90}")
    print(f"  {'Config':<16} | {'Tr':>3}  | {'WR':>7} | {'PnL':>9} | {'/ mo':>7} | "
          f"{'DD':>7} | {'PF':>7} | OK?")
    print(f"  {'-'*82}")

    all_results = []
    for name, min_r, max_r, tp_m, use_ema, skip_mon in CONFIGS_TO_TEST:
        trades, bal = run_backtest(df_15m, df_1h, min_r, max_r, tp_m,
                                   use_ema, skip_mon)
        result = print_results(name, trades, bal, args.days)
        if result:
            all_results.append(result)

    # Mejor config
    if all_results:
        best = max(all_results, key=lambda x: x["pnl"] if x["mdd"] < 5 else -999)
        print(f"\n  MEJOR CONFIG: {best['name']}")
        print(f"  -> {best['trades']} trades, WR: {best['wr']:.1f}%, "
              f"PnL: {best['pnl']:+.2f}%, DD: {best['mdd']:.2f}%")

    print(f"\n{'='*90}\n")
    mt5.shutdown()
