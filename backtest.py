"""
backtest.py — Motor de backtesting con datos históricos de Binance
Simula la estrategia EMA + RSI + ADX barra a barra
"""

import argparse
import pandas as pd
from tabulate import tabulate
from binance.client import Client

import config
from indicators import add_indicators
from risk_manager import calc_sl_tp
import logger


def download_historical_data(symbol: str, interval: str, limit: int = 1000) -> pd.DataFrame:
    """
    Descarga datos históricos de Binance Futures (sin API key, datos públicos).
    Usa el endpoint de Futuros para soportar pares como XAUUSDT que no están en Spot.
    """
    client = Client("", "")  # Sin auth para datos públicos
    # Usar futures_klines para soportar XAUUSDT y otros pares solo disponibles en Futuros
    try:
        raw = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    except Exception:
        # Fallback a spot si el par no está en futuros
        raw = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(raw, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    df.set_index("timestamp", inplace=True)
    return df


def run_backtest(symbol: str, interval: str = "1h", limit: int = 1000,
                 initial_capital: float = 10000.0) -> dict:
    """
    Ejecuta el backtest para un par y retorna las métricas.

    Args:
        symbol:          Par de trading
        interval:        Timeframe
        limit:           Número de velas históricas
        initial_capital: Capital inicial en USDT

    Returns:
        Diccionario con métricas del backtest
    """
    cfg = config.get_symbol_config(symbol)
    logger.info(f"📊 Iniciando backtest: {symbol} | {interval} | {limit} velas")

    # Descargar datos
    df = download_historical_data(symbol, interval, limit)
    if df.empty:
        logger.error(f"No se pudieron descargar datos para {symbol}")
        return {}

    # Calcular indicadores
    df = add_indicators(df)
    logger.info(f"  Velas disponibles tras indicadores: {len(df)}")

    # ── Simulación barra a barra ──────────────────────────────────────────
    capital    = initial_capital
    trades     = []
    in_trade   = False
    entry_price = 0.0
    sl_price   = 0.0
    tp_price   = 0.0
    trade_side = ""
    qty        = 0.0

    for i in range(1, len(df) - 1):
        row      = df.iloc[i]      # Vela cerrada (señal)
        next_row = df.iloc[i + 1]  # Vela siguiente (ejecución)

        # ── Gestión de posición abierta ───────────────────────────────────
        if in_trade:
            high = next_row["high"]
            low  = next_row["low"]

            hit_sl = (trade_side == "LONG" and low  <= sl_price) or \
                     (trade_side == "SHORT" and high >= sl_price)
            hit_tp = (trade_side == "LONG" and high >= tp_price) or \
                     (trade_side == "SHORT" and low  <= tp_price)

            if hit_sl or hit_tp:
                exit_price = sl_price if hit_sl else tp_price
                result     = "WIN" if hit_tp else "LOSS"

                if trade_side == "LONG":
                    pnl = (exit_price - entry_price) * qty
                else:
                    pnl = (entry_price - exit_price) * qty

                capital += pnl
                trades.append({
                    "timestamp": next_row.name,
                    "symbol":    symbol,
                    "side":      trade_side,
                    "entry":     entry_price,
                    "exit":      exit_price,
                    "sl":        sl_price,
                    "tp":        tp_price,
                    "qty":       qty,
                    "pnl":       round(pnl, 2),
                    "result":    result,
                    "capital":   round(capital, 2),
                })
                in_trade = False
            continue  # No abrir nueva posición mientras hay una abierta

        # ── Detección de señal ────────────────────────────────────────────
        ema_cross = row["ema_cross"]
        rsi       = row["rsi"]
        adx       = row["adx"]
        volume    = row["volume"]
        vol_ma    = row["vol_ma"]
        atr       = row["atr"]

        # Filtros
        if adx < cfg["adx_min"]:
            continue
        if volume < vol_ma * 0.8:
            continue

        signal = None
        if ema_cross == 1 and rsi > cfg["rsi_long"]:
            signal = "LONG"
        elif ema_cross == -1 and rsi < cfg["rsi_short"]:
            signal = "SHORT"

        if signal is None:
            continue

        # ── Abrir posición ────────────────────────────────────────────────
        entry_price = next_row["open"]  # Entrada al open de la siguiente vela
        sl_price, tp_price = calc_sl_tp(entry_price, atr, signal, symbol)

        # Tamaño de posición: 2% del capital en riesgo
        risk_amount = capital * config.RISK_PER_TRADE
        sl_distance = abs(entry_price - sl_price)
        qty = risk_amount / sl_distance if sl_distance > 0 else 0.001

        in_trade   = True
        trade_side = signal

    # ── Métricas ──────────────────────────────────────────────────────────
    if not trades:
        logger.warning(f"{symbol}: Sin operaciones en el backtest.")
        return {"symbol": symbol, "trades": 0}

    trades_df = pd.DataFrame(trades)
    wins      = trades_df[trades_df["result"] == "WIN"]
    losses    = trades_df[trades_df["result"] == "LOSS"]
    total_pnl = trades_df["pnl"].sum()
    win_rate  = len(wins) / len(trades_df) * 100
    avg_win   = wins["pnl"].mean() if len(wins) > 0 else 0
    avg_loss  = losses["pnl"].mean() if len(losses) > 0 else 0
    profit_factor = (wins["pnl"].sum() / abs(losses["pnl"].sum())
                     if len(losses) > 0 and losses["pnl"].sum() != 0 else float("inf"))

    # Max Drawdown
    capital_curve = trades_df["capital"]
    rolling_max   = capital_curve.cummax()
    drawdown      = (capital_curve - rolling_max) / rolling_max * 100
    max_drawdown  = drawdown.min()

    metrics = {
        "symbol":        symbol,
        "trades":        len(trades_df),
        "wins":          len(wins),
        "losses":        len(losses),
        "win_rate":      round(win_rate, 1),
        "total_pnl":     round(total_pnl, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_win":       round(avg_win, 2),
        "avg_loss":      round(avg_loss, 2),
        "max_drawdown":  round(max_drawdown, 2),
        "final_capital": round(capital, 2),
    }

    # Guardar trades a CSV
    output_file = f"backtest_{symbol}_{interval}.csv"
    trades_df.to_csv(output_file, index=False)
    logger.info(f"  Trades guardados en: {output_file}")

    return metrics


def print_results(results: list[dict]):
    """Imprime tabla de resultados del backtest."""
    if not results:
        return

    headers = ["Par", "Trades", "Win Rate", "PnL Total", "Profit Factor",
               "Max DD", "Capital Final"]
    rows = []
    for r in results:
        if r.get("trades", 0) == 0:
            rows.append([r["symbol"], 0, "-", "-", "-", "-", "-"])
            continue
        rows.append([
            r["symbol"],
            r["trades"],
            f"{r['win_rate']}%",
            f"${r['total_pnl']:+.2f}",
            r["profit_factor"],
            f"{r['max_drawdown']:.1f}%",
            f"${r['final_capital']:.2f}",
        ])

    print("\n" + "=" * 70)
    print("📊 RESULTADOS DEL BACKTEST")
    print("=" * 70)
    print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))
    print("=" * 70 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtesting EMA+RSI+ADX Strategy")
    parser.add_argument("--symbol",   default=None,    help="Par específico (ej: BTCUSDT). Si no se indica, prueba todos.")
    parser.add_argument("--interval", default="1h",    help="Timeframe (default: 1h)")
    parser.add_argument("--limit",    default=1000, type=int, help="Número de velas (default: 1000)")
    parser.add_argument("--capital",  default=10000.0, type=float, help="Capital inicial USDT (default: 10000)")
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else config.SYMBOLS
    all_results = []

    for sym in symbols:
        result = run_backtest(sym, args.interval, args.limit, args.capital)
        all_results.append(result)

    print_results(all_results)
