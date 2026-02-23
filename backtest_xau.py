"""
backtest_xau.py — Backtest Asian Range Breakout XAUUSDT (v3 — prop firm ready)

Mejoras v3:
  🛡️ Break-Even: SL se mueve a entrada cuando el precio avanza 1R
  📈 Trailing Stop: SL persigue al precio a 0.5× rango de distancia
  ⏰ EOD Close: Cierre forzado a las 16:00 UTC (fin sesión NY)
"""
import argparse
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import pandas as pd
from binance.client import Client

# ── Parámetros ────────────────────────────────────────────────────────────
ASIAN_START_H  = 0
ASIAN_END_H    = 6
LONDON_START_H = 7
LONDON_END_H   = 10
TP_MULTIPLIER  = 2.5
SL_BUFFER_PCT  = 0.001
RISK_PER_TRADE = 0.015
MIN_RANGE_USD  = 10
MAX_RANGE_USD  = 300
EMA_PERIOD     = 50
SKIP_MONDAY    = True
MAX_ENTRY_CANDLES = 4

# ── Parámetros v3 (Prop Firm) ─────────────────────────────────────────────
BE_TRIGGER_R       = 1.0   # Mover SL a entrada cuando ganancia = 1× riesgo
TRAIL_DISTANCE_MULT = 0.5  # Trailing stop a 0.5× rango de distancia
EOD_CLOSE_H        = 16    # Hora UTC para cierre forzado (fin sesión NY)

SYMBOL = "XAUUSDT"
client = Client("", "")

def download(symbol, interval, days):
    print(f"📥 Descargando {days}d de {symbol} {interval}...")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    try:
        raw = client.futures_historical_klines(symbol, interval,
              start.strftime("%d %b %Y"), end.strftime("%d %b %Y"))
    except Exception as e:
        print(f"❌ Error: {e}"); return pd.DataFrame()
    if not raw:
        print("❌ Sin datos"); return pd.DataFrame()
    df = pd.DataFrame(raw, columns=["ts","open","high","low","close","volume",
         "ct","qv","tr","tbb","tbq","ig"])
    df = df[["ts","open","high","low","close","volume"]].copy()
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    for c in ["open","high","low","close","volume"]: df[c] = df[c].astype(float)
    df.set_index("ts", inplace=True)
    print(f"✅ {len(df)} velas ({df.index[0].date()} → {df.index[-1].date()})")
    return df

@dataclass
class Trade:
    date: str; signal: str; entry: float; sl: float; tp: float
    exit_price: float; result: str; pnl_usd: float; pnl_r: float
    range_size: float; be_triggered: bool = False; filtered_reason: str = ""

def run_backtest(df_15m, df_1h, capital, use_filters=True, use_v3=False):
    trades = []
    bal = capital
    dates = sorted(set(df_15m.index.date))
    
    # Calcular EMA50 sobre 1H
    ema50 = None
    if df_1h is not None and len(df_1h) >= EMA_PERIOD:
        ema50 = df_1h["close"].ewm(span=EMA_PERIOD, adjust=False).mean()

    if use_v3:
        label = "V3 PROP FIRM"
    elif use_filters:
        label = "CON FILTROS"
    else:
        label = "SIN FILTROS"
    print(f"\n{'═'*70}")
    print(f"  BACKTEST XAUUSDT — Asian Range Breakout [{label}]")
    print(f"  Capital: ${capital:,.2f} | Período: {dates[0]} → {dates[-1]} ({len(dates)}d)")
    print(f"{'═'*70}")

    for day in dates:
        day_df = df_15m[df_15m.index.date == day]
        weekday = pd.Timestamp(day).weekday()

        # Filtro lunes
        if use_filters and SKIP_MONDAY and weekday == 0:
            continue

        asian = day_df[(day_df.index.hour >= ASIAN_START_H) & (day_df.index.hour < ASIAN_END_H)]
        if len(asian) < 4: continue
        
        ah = float(asian["high"].max())
        al = float(asian["low"].min())
        rng = ah - al
        if rng <= 0: continue

        # Filtro rango mínimo/máximo
        if use_filters:
            if rng < MIN_RANGE_USD:
                continue
            if rng > MAX_RANGE_USD:
                continue

        # Filtro EMA50 tendencia
        trend = None
        if use_filters and ema50 is not None:
            day_ema = ema50[ema50.index.date <= day]
            if not day_ema.empty:
                last_1h = df_1h[df_1h.index.date <= day]
                if not last_1h.empty:
                    trend = "LONG" if float(last_1h["close"].iloc[-1]) > float(day_ema.iloc[-1]) else "SHORT"

        london = day_df[(day_df.index.hour >= LONDON_START_H) & (day_df.index.hour < LONDON_END_H)]
        if london.empty: continue

        signal = None; sl = 0; tp = 0; entry = 0; eidx = None
        for i, (ts, row) in enumerate(london.iterrows()):
            if i >= MAX_ENTRY_CANDLES: break
            c = float(row["close"])
            if c > ah:
                signal, entry, eidx = "LONG", c, i
                sl = al - rng * SL_BUFFER_PCT
                tp = c + rng * TP_MULTIPLIER
                break
            if c < al:
                signal, entry, eidx = "SHORT", c, i
                sl = ah + rng * SL_BUFFER_PCT
                tp = c - rng * TP_MULTIPLIER
                break

        if signal is None: continue

        # Filtro tendencia: LONG solo si trend != SHORT, SHORT solo si trend != LONG
        if use_filters and trend is not None:
            if signal == "LONG" and trend == "SHORT": continue
            if signal == "SHORT" and trend == "LONG": continue

        # Simular resultado
        rest = day_df[day_df.index > london.index[eidx]]
        result = "OPEN"; exit_p = entry
        current_sl = sl
        be_triggered = False
        sl_dist_orig = abs(entry - sl)

        if not rest.empty:
            for _, row in rest.iterrows():
                h, l = float(row["high"]), float(row["low"])
                candle_hour = row.name.hour if hasattr(row.name, 'hour') else 23

                # ── v3: EOD Close a las 16:00 UTC ─────────────────────
                if use_v3 and candle_hour >= EOD_CLOSE_H:
                    exit_p = float(row["close"])
                    pnl_check = (exit_p - entry) if signal == "LONG" else (entry - exit_p)
                    if pnl_check > 0:
                        result = "WIN"
                    elif be_triggered:
                        result = "BE"
                    else:
                        result = "LOSS"
                    break

                # ── v3: Trailing Stop ─────────────────────────────────
                if use_v3 and be_triggered:
                    trail_dist = rng * TRAIL_DISTANCE_MULT
                    if signal == "LONG":
                        new_trail_sl = h - trail_dist
                        if new_trail_sl > current_sl:
                            current_sl = new_trail_sl
                    else:
                        new_trail_sl = l + trail_dist
                        if new_trail_sl < current_sl:
                            current_sl = new_trail_sl

                # ── v3: Break-Even trigger ────────────────────────────
                if use_v3 and not be_triggered:
                    if signal == "LONG" and h >= entry + sl_dist_orig * BE_TRIGGER_R:
                        current_sl = entry + 0.50  # +$0.50 para cubrir comisiones
                        be_triggered = True
                    elif signal == "SHORT" and l <= entry - sl_dist_orig * BE_TRIGGER_R:
                        current_sl = entry - 0.50
                        be_triggered = True

                # ── Comprobar SL/TP ───────────────────────────────────
                if signal == "LONG":
                    hit_sl, hit_tp = l <= current_sl, h >= tp
                else:
                    hit_sl, hit_tp = h >= current_sl, l <= tp

                if hit_tp:
                    result, exit_p = "WIN", tp; break
                elif hit_sl:
                    if be_triggered:
                        result, exit_p = "BE", current_sl
                    else:
                        result, exit_p = "LOSS", current_sl
                    break
            else:
                exit_p = float(rest["close"].iloc[-1])

        risk_usd = bal * RISK_PER_TRADE
        sl_dist = abs(entry - sl)
        qty = risk_usd / sl_dist if sl_dist > 0 else 0
        pnl = (exit_p - entry) * qty if signal == "LONG" else (entry - exit_p) * qty
        pnl_r = pnl / risk_usd if risk_usd > 0 else 0
        bal += pnl

        icons = {"WIN": "✅", "LOSS": "❌", "BE": "🛡️", "OPEN": "⏳"}
        e = icons.get(result, "⏳")
        print(f"  {day} │ {signal:5s} │ {e} {result:4s} │ E:{entry:>8.2f} │ "
              f"TP:{tp:>8.2f} │ SL:{current_sl:>8.2f} │ R:{rng:>6.2f} │ ${pnl:>+7.2f} │ {pnl_r:>+.2f}R")

        trades.append(Trade(str(day), signal, entry, sl, tp, exit_p, result,
                            round(pnl,2), round(pnl_r,2), round(rng,2), be_triggered))
    return trades, bal

def summary(trades, capital, final_bal, label):
    if not trades:
        print(f"\n⚠️  [{label}] Sin operaciones."); return
    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    bes = [t for t in trades if t.result == "BE"]
    opens = [t for t in trades if t.result == "OPEN"]
    closed = wins + losses + bes
    pnl = final_bal - capital
    wr = len(wins)/len(closed)*100 if closed else 0
    pf = abs(sum(t.pnl_usd for t in wins)/sum(t.pnl_usd for t in losses)) if losses and sum(t.pnl_usd for t in losses) != 0 else float("inf")
    
    # Max drawdown
    eq, peak, mdd = capital, capital, 0
    for t in trades:
        eq += t.pnl_usd
        peak = max(peak, eq)
        mdd = max(mdd, (peak-eq)/peak*100)

    print(f"\n{'═'*70}")
    print(f"  📊 RESUMEN [{label}]")
    print(f"{'═'*70}")
    print(f"  Capital: ${capital:,.2f} → ${final_bal:,.2f}  ({pnl:+.2f}, {pnl/capital*100:+.2f}%)")
    print(f"  Trades:  {len(trades)} total  (✅{len(wins)} │ ❌{len(losses)} │ 🛡️{len(bes)} │ ⏳{len(opens)})")
    print(f"  Win Rate: {wr:.1f}% │ Profit Factor: {pf:.2f}x │ Max DD: {mdd:.2f}%")
    if wins: print(f"  Ganancia media: ${sum(t.pnl_usd for t in wins)/len(wins):+.2f}")
    if losses: print(f"  Pérdida media:  ${sum(t.pnl_usd for t in losses)/len(losses):+.2f}")
    if bes: print(f"  Break-Evens:    {len(bes)} (pérdidas evitadas)")
    print(f"{'═'*70}\n")

    pd.DataFrame([{"date":t.date,"signal":t.signal,"entry":t.entry,"sl":t.sl,
        "tp":t.tp,"exit":t.exit_price,"result":t.result,"pnl":t.pnl_usd,
        "R":t.pnl_r,"range":t.range_size,"be":t.be_triggered} for t in trades]).to_csv(
        f"backtest_xau_{label.lower().replace(' ','_')}.csv", index=False)
    print(f"  📄 CSV: backtest_xau_{label.lower().replace(' ','_')}.csv")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", default=30, type=int)
    p.add_argument("--capital", default=1000.0, type=float)
    args = p.parse_args()

    df_15m = download(SYMBOL, "15m", args.days)
    df_1h  = download(SYMBOL, "1h",  args.days + 10)  # extra para EMA50
    if df_15m.empty: exit(1)

    # ── Run CON filtros v2 ──
    t2, b2 = run_backtest(df_15m, df_1h, args.capital, use_filters=True, use_v3=False)
    summary(t2, args.capital, b2, "CON FILTROS")

    # ── Run V3 PROP FIRM (filtros + BE + trailing + EOD) ──
    t3, b3 = run_backtest(df_15m, df_1h, args.capital, use_filters=True, use_v3=True)
    summary(t3, args.capital, b3, "V3 PROP FIRM")

    # ── Comparativa v2 vs v3 ──
    print(f"\n{'═'*70}")
    print(f"  ⚔️  COMPARATIVA v2 (FILTROS) vs v3 (PROP FIRM)")
    print(f"{'═'*70}")
    pnl2 = b2 - args.capital; pnl3 = b3 - args.capital
    w2 = [t for t in t2 if t.result=="WIN"]; l2 = [t for t in t2 if t.result=="LOSS"]
    w3 = [t for t in t3 if t.result=="WIN"]; l3 = [t for t in t3 if t.result=="LOSS"]
    be3 = [t for t in t3 if t.result=="BE"]
    c2 = w2+l2; c3 = w3+l3+be3
    wr2 = len(w2)/len(c2)*100 if c2 else 0; wr3 = len(w3)/len(c3)*100 if c3 else 0
    print(f"  {'Métrica':<20} {'v2 FILTROS':>15} {'v3 PROP FIRM':>15}")
    print(f"  {'─'*50}")
    print(f"  {'Trades':<20} {len(t2):>15} {len(t3):>15}")
    print(f"  {'Win Rate':<20} {wr2:>14.1f}% {wr3:>14.1f}%")
    print(f"  {'Break-Evens':<20} {'0':>15} {len(be3):>15}")
    print(f"  {'PnL $':<20} {pnl2:>+14.2f}$ {pnl3:>+14.2f}$")
    print(f"  {'PnL %':<20} {pnl2/args.capital*100:>+14.2f}% {pnl3/args.capital*100:>+14.2f}%")

    # Max drawdown comparison
    for label_dd, trades_dd in [("v2", t2), ("v3", t3)]:
        eq, peak, mdd = args.capital, args.capital, 0
        for t in trades_dd:
            eq += t.pnl_usd
            peak = max(peak, eq)
            mdd = max(mdd, (peak-eq)/peak*100)
        print(f"  {'Max DD ('+label_dd+')':<20} {mdd:>14.2f}%")

    mejor = "V3 PROP FIRM" if pnl3 > pnl2 else "v2 FILTROS"
    print(f"\n  🏆 GANADOR: {mejor}")
    print(f"{'═'*70}\n")
