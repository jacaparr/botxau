"""
backtest_propfirm_6m.py — Backtest 6 Meses con Configuración Real del Reto (25K)
=================================================================================
Simula la estrategia ENSEMBLE (Indicator Trend) sobre XAUUSD en los últimos 6 meses
usando:
  - Capital inicial: $25,000 (reto prop firm real)
  - Riesgo: 0.15% por operación
  - Cierre EOD: 16:00 UTC
  - Protecciones prop firm: Daily DD 4%, Total DD 8%
  - ADX > 20, EMA50, RSI 14

Muestra cada operación y si la cuenta hubiera sido descalificada.
"""

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN REAL DEL RETO
# ─────────────────────────────────────────────────────────────────────────────
CAPITAL_INICIAL  = 25_000.0   # $25,000
RISK_PCT         = 0.60       # 0.60% por trade
DAILY_DD_LIMIT   = 0.04       # 4% → parar antes del 5% de la prop firm
TOTAL_DD_LIMIT   = 0.08       # 8% → parar antes del 10% de la prop firm
EOD_CLOSE_H      = 16         # Cierre forzado a las 16:00 UTC
ADX_MIN          = 20.0
SL_ATR_MULT      = 2.5
TP_ATR_MULT      = 5.0
DAYS             = 180        # 6 meses

ALIASES = ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"]

# ─────────────────────────────────────────────────────────────────────────────
# INDICADORES MANUALES (sin pandas_ta para compatibilidad Python 3.14)
# ─────────────────────────────────────────────────────────────────────────────

def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()

def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=length).mean()
    loss = (-delta.clip(upper=0)).rolling(window=length).mean()
    rs = gain / loss.replace(0, float('nan'))
    return 100 - (100 / (1 + rs))

def atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=length).mean()

def adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    """Calcula ADX simplificado."""
    up   = high.diff()
    down = -low.diff()
    plus_dm  = pd.Series(0.0, index=high.index)
    minus_dm = pd.Series(0.0, index=high.index)
    plus_dm[(up > down) & (up > 0)]   = up[(up > down) & (up > 0)]
    minus_dm[(down > up) & (down > 0)] = down[(down > up) & (down > 0)]

    tr_val = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)

    atr14     = tr_val.rolling(length).mean()
    plus_di   = 100 * plus_dm.rolling(length).mean()  / atr14.replace(0, float('nan'))
    minus_di  = 100 * minus_dm.rolling(length).mean() / atr14.replace(0, float('nan'))
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float('nan'))
    return dx.rolling(length).mean()

# ─────────────────────────────────────────────────────────────────────────────
# MAIN BACKTEST
# ─────────────────────────────────────────────────────────────────────────────

def run():
    print("\n" + "="*90)
    print("  [BACKTEST] PROP FIRM 6 MESES -- XAUUSD ENSEMBLE (Indicator Trend)")
    print(f"  Capital: ${CAPITAL_INICIAL:,.0f} | Riesgo: {RISK_PCT}%/trade | "
          f"DD Limites: {DAILY_DD_LIMIT*100:.0f}%/{TOTAL_DD_LIMIT*100:.0f}%")
    print("="*90 + "\n")

    if not mt5.initialize():
        print("[ERROR] No se pudo conectar a MT5. Asegurate de que MT5 esta abierto.")
        return

    # Buscar símbolo
    symbol = None
    for alias in ALIASES:
        if mt5.symbol_info(alias):
            symbol = alias
            break

    if not symbol:
        print("[ERROR] Simbolo XAUUSD no encontrado en MT5.")
        mt5.shutdown()
        return

    print(f"[OK] Simbolo encontrado: {symbol}")

    to_dt   = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    rates   = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, from_dt, to_dt)

    if rates is None or len(rates) == 0:
        print("[ERROR] Sin datos historicos. Revisa que el simbolo tiene historial H1.")
        mt5.shutdown()
        return

    mt5.shutdown()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)

    # Calcular indicadores
    df['ema50'] = ema(df['close'], 50)
    df['rsi14'] = rsi(df['close'], 14)
    df['adx14'] = adx(df['high'], df['low'], df['close'], 14)
    df['atr14'] = atr(df['high'], df['low'], df['close'], 14)
    df.dropna(inplace=True)

    # ─── Estado del backtest ───────────────────────────────────────────────
    balance      = CAPITAL_INICIAL
    peak_balance = CAPITAL_INICIAL
    day_start_bal = {df.index[0].date(): CAPITAL_INICIAL}
    trades       = []
    account_blown= False
    blow_reason  = ""
    in_trade     = False
    trade_end_idx= 0

    # Cabecera tabla
    print(f"{'#':<4} {'Fecha':^20} {'Señal':^6} {'Entrada':>10} {'SL':>10} {'TP':>10} "
          f"{'Salida':>10} {'PnL $':>9} {'Balance':>11} {'DD Día':>7} {'DD Tot':>7} {'Estado':^12}")
    print("-"*115)

    for idx, (ts, row) in enumerate(df.iterrows()):
        if in_trade and idx < trade_end_idx:
            continue

        # Filtro EOD: no entrar después de las 15:00 UTC (cierre a las 16:00)
        if ts.hour >= (EOD_CLOSE_H - 1):
            continue

        adx_val = float(row['adx14'])
        if adx_val < ADX_MIN:
            continue

        # Señal ENSEMBLE (Indicator Trend)
        signal = None
        if row['close'] > row['ema50'] and row['rsi14'] > 55:
            signal = "LONG"
        elif row['close'] < row['ema50'] and row['rsi14'] < 45:
            signal = "SHORT"

        if not signal:
            continue

        entry     = float(row['close'])
        atr_val   = float(row['atr14'])
        sl        = entry - atr_val * SL_ATR_MULT if signal == "LONG" else entry + atr_val * SL_ATR_MULT
        tp        = entry + atr_val * TP_ATR_MULT if signal == "LONG" else entry - atr_val * TP_ATR_MULT
        sl_dist   = abs(entry - sl)
        risk_amt  = balance * (RISK_PCT / 100)
        today     = ts.date()

        # ── Verificar protecciones prop firm ANTES de entrar ──────────────
        day_start = day_start_bal.get(today, balance)
        daily_dd  = (day_start - balance) / day_start if day_start > 0 else 0
        total_dd  = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0

        if daily_dd >= DAILY_DD_LIMIT or total_dd >= TOTAL_DD_LIMIT:
            continue  # El guard no hubiera dejado entrar

        # ── Simular el trade ───────────────────────────────────────────────
        future = df.iloc[idx+1:]
        exit_price = entry
        exit_time  = None
        exit_idx   = idx + 1

        for f_idx, (f_ts, f_row) in enumerate(future.iterrows()):
            if signal == "LONG":
                if f_row['low'] <= sl:  exit_price = sl; exit_time = f_ts; exit_idx = idx+1+f_idx; break
                if f_row['high'] >= tp: exit_price = tp; exit_time = f_ts; exit_idx = idx+1+f_idx; break
            else:
                if f_row['high'] >= sl: exit_price = sl; exit_time = f_ts; exit_idx = idx+1+f_idx; break
                if f_row['low'] <= tp:  exit_price = tp; exit_time = f_ts; exit_idx = idx+1+f_idx; break
            # EOD close
            if f_ts.hour >= EOD_CLOSE_H:
                exit_price = float(f_row['close']); exit_time = f_ts; exit_idx = idx+1+f_idx; break

        if exit_time is None:
            continue

        # Calcular PnL
        pnl_r   = (exit_price - entry) / sl_dist if signal == "LONG" else (entry - exit_price) / sl_dist
        pnl_usd = risk_amt * pnl_r

        # Actualizar balance y tracking
        prev_bal      = balance
        balance      += pnl_usd
        peak_balance  = max(peak_balance, balance)
        in_trade      = True
        trade_end_idx = exit_idx + 12  # Skip ~12 velas para evitar solapados

        # Actualizar día de inicio si cambió
        exit_date = exit_time.date()
        if exit_date not in day_start_bal:
            day_start_bal[exit_date] = balance - pnl_usd  # balance al inicio del día de salida

        # Calcular drawdowns POST-trade
        day_dd_post  = max(0, (day_start_bal.get(today, prev_bal) - balance) / day_start_bal.get(today, prev_bal)) * 100
        total_dd_post = max(0, (peak_balance - balance) / peak_balance) * 100

        # Estado
        if balance <= CAPITAL_INICIAL * (1 - TOTAL_DD_LIMIT):
            account_blown = True
            blow_reason   = f"Total DD > {TOTAL_DD_LIMIT*100:.0f}%"
            status = "🔴 BLOWN"
        elif day_dd_post >= DAILY_DD_LIMIT * 100:
            status = "🟡 STOP DÍA"
        elif total_dd_post >= TOTAL_DD_LIMIT * 50:
            status = "🟡 CUIDADO"
        else:
            status = "🟢 OK"

        win  = "✅" if pnl_usd > 0 else "❌"
        num  = len(trades) + 1
        print(f"{num:<4} {str(ts)[:19]:^20} {signal+' '+win:^8} {entry:>10.2f} {sl:>10.2f} "
              f"{tp:>10.2f} {exit_price:>10.2f} {pnl_usd:>+9.2f} "
              f"${balance:>10,.2f} {day_dd_post:>6.2f}% {total_dd_post:>6.2f}% {status:^12}")

        trades.append({
            "date": str(ts)[:10],
            "signal": signal,
            "pnl_usd": pnl_usd,
            "balance": balance,
            "daily_dd": day_dd_post,
            "total_dd": total_dd_post,
        })

        if account_blown:
            print(f"\n[!!!] CUENTA DESCALIFICADA: {blow_reason}")
            print(f"      Ocurrio en trade #{num} -- {str(ts)[:10]}")
            break

    # ─── RESUMEN FINAL ───────────────────────────────────────────────────────
    print("\n" + "="*90)
    print("  RESUMEN FINAL DEL BACKTEST")
    print("="*90)

    if not trades:
        print("  [!] Sin trades generados. Revisa la conexion MT5 o el historial del simbolo.")
        return

    wins      = [t for t in trades if t['pnl_usd'] > 0]
    losses    = [t for t in trades if t['pnl_usd'] <= 0]
    pnl_total = sum(t['pnl_usd'] for t in trades)
    wr        = len(wins) / len(trades) * 100
    max_dd    = max(t['total_dd'] for t in trades)
    avg_win   = sum(t['pnl_usd'] for t in wins) / len(wins) if wins else 0
    avg_loss  = sum(t['pnl_usd'] for t in losses) / len(losses) if losses else 0
    profit_factor = abs(sum(t['pnl_usd'] for t in wins) / sum(t['pnl_usd'] for t in losses)) if losses and sum(t['pnl_usd'] for t in losses) != 0 else float('inf')

    print(f"\n  Período:          {trades[0]['date']}  →  {trades[-1]['date']}")
    print(f"  Capital inicial:  ${CAPITAL_INICIAL:>12,.2f}")
    print(f"  Balance final:    ${balance:>12,.2f}")
    print(f"  PnL Total:        ${pnl_total:>+12,.2f}  ({pnl_total/CAPITAL_INICIAL*100:+.2f}%)")
    print(f"\n  Total Trades:     {len(trades)}")
    print(f"  Ganadores:        {len(wins)}  ({wr:.1f}%)")
    print(f"  Perdedores:       {len(losses)}  ({100-wr:.1f}%)")
    print(f"  Ganancia media:   ${avg_win:>+.2f}")
    print(f"  Pérdida media:    ${avg_loss:>+.2f}")
    print(f"  Profit Factor:    {profit_factor:.2f}")
    print(f"\n  Max Drawdown:     {max_dd:.2f}%  (límite: {TOTAL_DD_LIMIT*100:.0f}%)")

    print("\n  --- VEREDICTO PROP FIRM ---")
    if account_blown:
        print(f"  [FAIL] HUBIERAS PERDIDO LA CUENTA:")
        print(f"         Razon: {blow_reason}")
        print(f"         >> Reducir riesgo a 0.05% y activar 'reduced_risk' antes.")
    else:
        target_pct    = 10.0  # El reto requiere ganar un 10%
        target_amount = CAPITAL_INICIAL * (target_pct / 100)
        pnl_pct       = pnl_total / CAPITAL_INICIAL * 100
        print(f"  [OK] LA CUENTA HABRIA SOBREVIVIDO LOS 6 MESES")
        if pnl_total >= target_amount:
            print(f"  [PASS] RETO SUPERADO: +{pnl_pct:.2f}% vs objetivo +{target_pct:.0f}%")
        else:
            print(f"  [INFO] Reto NO superado: Solo +{pnl_pct:.2f}% vs objetivo +{target_pct:.0f}%")
            print(f"         >> Considera aumentar riesgo a 0.20% con caucion.")

    print("\n" + "="*90 + "\n")

if __name__ == "__main__":
    run()
