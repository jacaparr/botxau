"""
backtest_mt5.py — Backtester multi-símbolo para MetaTrader 5
=============================================================
Prueba la estrategia EMA + RSI + ADX en forex, índices y metales
usando datos históricos reales de MT5 (años de datos disponibles).

Uso:
    python backtest_mt5.py                  # Backtest todos los símbolos
    python backtest_mt5.py --days 365       # 1 año de datos
    python backtest_mt5.py --symbol EURUSD  # Solo un símbolo
"""

import MetaTrader5 as mt5
import pandas as pd
import argparse
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass

# ─────────────────────────────────────────────────────────────────────────────
# SÍMBOLOS A PROBAR
# ─────────────────────────────────────────────────────────────────────────────

SYMBOLS_TO_TEST = {
    # Forex
    "EURUSD":  {"atr_sl": 1.5, "atr_tp": 3.0, "rsi_long": 55, "rsi_short": 45, "adx_min": 25},
    "GBPUSD":  {"atr_sl": 1.5, "atr_tp": 3.0, "rsi_long": 55, "rsi_short": 45, "adx_min": 25},
    "USDJPY":  {"atr_sl": 1.5, "atr_tp": 3.0, "rsi_long": 55, "rsi_short": 45, "adx_min": 25},
    "GBPJPY":  {"atr_sl": 2.0, "atr_tp": 4.0, "rsi_long": 55, "rsi_short": 45, "adx_min": 22},
    # Plata
    "XAGUSD":  {"atr_sl": 2.0, "atr_tp": 4.0, "rsi_long": 55, "rsi_short": 45, "adx_min": 20},
}

# Parámetros globales
RISK_PER_TRADE = 0.015   # 1.5%
CAPITAL = 100000
EMA_FAST = 20
EMA_SLOW = 50
RSI_PERIOD = 14
ADX_PERIOD = 14
ATR_PERIOD = 14
TIMEFRAME = mt5.TIMEFRAME_H1  # 1 hora


# ─────────────────────────────────────────────────────────────────────────────
# INDICADORES TÉCNICOS
# ─────────────────────────────────────────────────────────────────────────────

def calc_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calc_rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))

def calc_adx(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    plus_dm = high.diff().clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    
    # Where plus_dm < minus_dm, set plus_dm to 0 and vice versa
    plus_dm[plus_dm < minus_dm] = 0
    minus_dm[minus_dm < plus_dm] = 0
    
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr.replace(0, 1e-10))
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr.replace(0, 1e-10))
    
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10)
    adx = dx.rolling(window=period).mean()
    return adx

def calc_atr(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


# ─────────────────────────────────────────────────────────────────────────────
# BACKTEST
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Trade:
    date: str
    symbol: str
    signal: str
    entry: float
    sl: float
    tp: float
    exit_price: float
    result: str
    pnl_usd: float
    pnl_r: float


def run_backtest(symbol: str, config: dict, days: int) -> list[Trade]:
    """Ejecuta backtest para un símbolo."""
    # Descargar datos
    utc_to = datetime.now(timezone.utc)
    utc_from = utc_to - timedelta(days=days)
    
    rates = mt5.copy_rates_range(symbol, TIMEFRAME, utc_from, utc_to)
    if rates is None or len(rates) < 100:
        print(f"  ⚠️  {symbol}: Datos insuficientes ({len(rates) if rates else 0} velas)")
        return []
    
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    
    # Calcular indicadores
    df["ema_fast"] = calc_ema(df["close"], EMA_FAST)
    df["ema_slow"] = calc_ema(df["close"], EMA_SLOW)
    df["rsi"] = calc_rsi(df["close"], RSI_PERIOD)
    df["adx"] = calc_adx(df, ADX_PERIOD)
    df["atr"] = calc_atr(df, ATR_PERIOD)
    
    # Drop NaN
    df.dropna(inplace=True)
    if len(df) < 50:
        return []
    
    trades = []
    in_trade = False
    
    atr_sl_mult = config["atr_sl"]
    atr_tp_mult = config["atr_tp"]
    rsi_long = config["rsi_long"]
    rsi_short = config["rsi_short"]
    adx_min = config["adx_min"]
    
    for i in range(1, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        if in_trade:
            # Comprobar SL/TP
            if trade_signal == "LONG":
                if float(row["low"]) <= trade_sl:
                    trades.append(Trade(
                        str(row.name.date()), symbol, "LONG", trade_entry,
                        trade_sl, trade_tp, trade_sl, "LOSS",
                        -risk_usd, -1.0
                    ))
                    in_trade = False
                elif float(row["high"]) >= trade_tp:
                    pnl_r = atr_tp_mult / atr_sl_mult
                    trades.append(Trade(
                        str(row.name.date()), symbol, "LONG", trade_entry,
                        trade_sl, trade_tp, trade_tp, "WIN",
                        risk_usd * pnl_r, pnl_r
                    ))
                    in_trade = False
            else:  # SHORT
                if float(row["high"]) >= trade_sl:
                    trades.append(Trade(
                        str(row.name.date()), symbol, "SHORT", trade_entry,
                        trade_sl, trade_tp, trade_sl, "LOSS",
                        -risk_usd, -1.0
                    ))
                    in_trade = False
                elif float(row["low"]) <= trade_tp:
                    pnl_r = atr_tp_mult / atr_sl_mult
                    trades.append(Trade(
                        str(row.name.date()), symbol, "SHORT", trade_entry,
                        trade_sl, trade_tp, trade_tp, "WIN",
                        risk_usd * pnl_r, pnl_r
                    ))
                    in_trade = False
            continue
        
        # ── Condiciones de entrada ──
        ema_f = float(prev["ema_fast"])
        ema_s = float(prev["ema_slow"])
        rsi = float(prev["rsi"])
        adx = float(prev["adx"])
        atr = float(prev["atr"])
        close = float(prev["close"])
        
        if adx < adx_min or atr == 0:
            continue
        
        signal = None
        
        # LONG: EMA fast > EMA slow + RSI > threshold
        if ema_f > ema_s and rsi > rsi_long and close > ema_f:
            signal = "LONG"
        # SHORT: EMA fast < EMA slow + RSI < threshold
        elif ema_f < ema_s and rsi < rsi_short and close < ema_f:
            signal = "SHORT"
        
        if signal:
            trade_entry = float(row["open"])
            trade_signal = signal
            risk_usd = CAPITAL * RISK_PER_TRADE
            
            if signal == "LONG":
                trade_sl = trade_entry - atr * atr_sl_mult
                trade_tp = trade_entry + atr * atr_tp_mult
            else:
                trade_sl = trade_entry + atr * atr_sl_mult
                trade_tp = trade_entry - atr * atr_tp_mult
            
            in_trade = True
    
    return trades


def print_summary(symbol: str, trades: list[Trade], days: int):
    """Imprime resumen del backtest."""
    if not trades:
        print(f"  {symbol:<10} │ Sin trades")
        return
    
    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    total_pnl = sum(t.pnl_usd for t in trades)
    wr = len(wins) / len(trades) * 100 if trades else 0
    pf = abs(sum(t.pnl_usd for t in wins) / sum(t.pnl_usd for t in losses)) if losses and sum(t.pnl_usd for t in losses) != 0 else float("inf")
    
    # Max drawdown
    eq, peak, mdd = CAPITAL, CAPITAL, 0
    for t in trades:
        eq += t.pnl_usd
        peak = max(peak, eq)
        dd = (peak - eq) / peak * 100
        mdd = max(mdd, dd)
    
    pnl_pct = total_pnl / CAPITAL * 100
    monthly = pnl_pct / (days / 30) if days > 0 else 0
    emoji = "✅" if total_pnl > 0 else "❌"
    
    print(f"  {emoji} {symbol:<8} │ {len(trades):>3} trades │ WR: {wr:>5.1f}% │ "
          f"PnL: {pnl_pct:>+7.2f}% │ /mes: {monthly:>+5.2f}% │ "
          f"MaxDD: {mdd:>5.2f}% │ PF: {pf:>5.2f}")
    
    return {
        "symbol": symbol, "trades": len(trades), "wr": wr,
        "pnl_pct": pnl_pct, "monthly": monthly, "mdd": mdd, "pf": pf,
        "verdict": total_pnl > 0 and wr > 45 and mdd < 5
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest multi-símbolo MT5")
    parser.add_argument("--days", type=int, default=180, help="Días de datos (default: 180)")
    parser.add_argument("--symbol", type=str, default=None, help="Solo un símbolo")
    args = parser.parse_args()
    
    if not mt5.initialize():
        print("❌ No se pudo conectar a MT5. Asegúrate de que esté abierto.")
        exit(1)
    
    print(f"\n{'═'*80}")
    print(f"  📊  BACKTEST MULTI-SÍMBOLO MT5 — EMA + RSI + ADX")
    print(f"  Capital: ${CAPITAL:,} | Riesgo: {RISK_PER_TRADE*100}% | Periodo: {args.days} días")
    print(f"{'═'*80}\n")
    
    symbols = {args.symbol: SYMBOLS_TO_TEST[args.symbol]} if args.symbol else SYMBOLS_TO_TEST
    results = []
    
    for sym, config in symbols.items():
        # Verificar que el símbolo existe
        info = mt5.symbol_info(sym)
        if info is None:
            print(f"  ⚠️  {sym}: No disponible en este broker")
            continue
        if not info.visible:
            mt5.symbol_select(sym, True)
        
        trades = run_backtest(sym, config, args.days)
        result = print_summary(sym, trades, args.days)
        if result:
            results.append(result)
    
    # ── Resumen final ──
    if results:
        print(f"\n{'─'*80}")
        print(f"  🏆 VEREDICTO FINAL")
        print(f"{'─'*80}")
        
        approved = [r for r in results if r["verdict"]]
        rejected = [r for r in results if not r["verdict"]]
        
        if approved:
            print(f"\n  ✅ APROBADOS (añadir al bot):")
            for r in approved:
                print(f"     • {r['symbol']} — {r['monthly']:+.2f}%/mes, WR: {r['wr']:.0f}%, MaxDD: {r['mdd']:.2f}%")
        
        if rejected:
            print(f"\n  ❌ RECHAZADOS (no añadir):")
            for r in rejected:
                reason = []
                if r["pnl_pct"] <= 0: reason.append("pérdidas")
                if r["wr"] <= 45: reason.append(f"WR baja ({r['wr']:.0f}%)")
                if r["mdd"] >= 5: reason.append(f"DD alto ({r['mdd']:.1f}%)")
                print(f"     • {r['symbol']} — {', '.join(reason)}")
        
        total_monthly = sum(r["monthly"] for r in approved)
        print(f"\n  📈 Ganancia mensual combinada (aprobados): {total_monthly:+.2f}%")
        print(f"     Con $100K = ${total_monthly/100*CAPITAL:+,.0f}/mes extra")
    
    print(f"\n{'═'*80}\n")
    mt5.shutdown()
