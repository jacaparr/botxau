"""
paper_trade.py — Paper Trading con API pública de Binance (SIN API KEYS)
=========================================================================
Usa datos reales de mercado de Binance Futures (gratis, sin autenticación)
y simula las órdenes localmente con un balance virtual.

No necesitas crear cuenta ni API keys.

Uso:
    python paper_trade.py                    # Paper trade todos los pares
    python paper_trade.py --symbol BTCUSDT   # Solo un par
    python paper_trade.py --capital 5000     # Capital inicial distinto
    python paper_trade.py --interval 15m     # Timeframe diferente
"""

import argparse
import time
import csv
import json
import os
from datetime import datetime, timezone
from dataclasses import dataclass, field

import pandas as pd
from binance.client import Client

import config
from indicators import add_indicators, get_last_signal_data
from strategy import check_signal, FUNDING_RATE_THRESHOLD
from strategy_xau import check_signal_xau
from risk_manager import calc_sl_tp, calc_position_size
import logger

XAU_SYMBOL   = "XAUUSDT"   # Par que usa la estrategia Asian Breakout
XAU_INTERVAL = "15m"        # XAU siempre en 15m para resolución de sesión


# ─────────────────────────────────────────────────────────────────────────────
# CLIENTE PÚBLICO (sin API keys, solo datos de mercado)
# ─────────────────────────────────────────────────────────────────────────────
public_client = Client("", "")   # ← Sin autenticación, 100% gratuito


# ─────────────────────────────────────────────────────────────────────────────
# ESTRUCTURAS DE DATOS
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SimulatedPosition:
    symbol:      str
    side:        str          # "LONG" o "SHORT"
    entry_price: float
    qty:         float
    stop_loss:   float
    take_profit: float
    opened_at:   str = field(default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))


@dataclass
class TradeResult:
    symbol:      str
    side:        str
    entry_price: float
    exit_price:  float
    qty:         float
    pnl:         float
    result:      str          # "WIN" o "LOSS"
    opened_at:   str
    closed_at:   str


class PaperPortfolio:
    """Gestiona el balance virtual y las posiciones simuladas."""

    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.balance         = initial_capital
        self.positions: dict[str, SimulatedPosition] = {}
        self.trade_history: list[TradeResult] = []

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def open_position(self, symbol: str, side: str, entry_price: float,
                      qty: float, stop_loss: float, take_profit: float):
        """Abre una posición simulada."""
        self.positions[symbol] = SimulatedPosition(
            symbol=symbol, side=side, entry_price=entry_price,
            qty=qty, stop_loss=stop_loss, take_profit=take_profit,
        )
        arrow = "📈" if side == "LONG" else "📉"
        logger.success(
            f"[PAPER] {arrow} {side} abierto en {symbol} | "
            f"Precio: {entry_price:.4f} | Qty: {qty:.6f} | "
            f"SL: {stop_loss:.4f} | TP: {take_profit:.4f}"
        )

    def check_and_close(self, symbol: str, current_high: float,
                        current_low: float) -> TradeResult | None:
        """
        Verifica si el SL o TP fue alcanzado con los precios actuales.
        Retorna el resultado si se cerró, None si sigue abierta.
        """
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]
        hit_sl = (pos.side == "LONG"  and current_low  <= pos.stop_loss)  or \
                 (pos.side == "SHORT" and current_high >= pos.stop_loss)
        hit_tp = (pos.side == "LONG"  and current_high >= pos.take_profit) or \
                 (pos.side == "SHORT" and current_low  <= pos.take_profit)

        if not hit_sl and not hit_tp:
            return None

        exit_price = pos.stop_loss if hit_sl else pos.take_profit
        result_str = "LOSS" if hit_sl else "WIN"

        if pos.side == "LONG":
            pnl = (exit_price - pos.entry_price) * pos.qty
        else:
            pnl = (pos.entry_price - exit_price) * pos.qty

        self.balance += pnl
        del self.positions[symbol]

        trade = TradeResult(
            symbol=symbol, side=pos.side,
            entry_price=pos.entry_price, exit_price=exit_price,
            qty=pos.qty, pnl=round(pnl, 4),
            result=result_str,
            opened_at=pos.opened_at,
            closed_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )
        self.trade_history.append(trade)

        emoji = "✅" if result_str == "WIN" else "❌"
        logger.info(
            f"[PAPER] {emoji} {result_str} | {symbol} | "
            f"PnL: {pnl:+.4f} USDT | Balance: {self.balance:.2f} USDT"
        )
        return trade

    def print_summary(self):
        """Imprime el resumen del portfolio actual."""
        wins   = [t for t in self.trade_history if t.result == "WIN"]
        losses = [t for t in self.trade_history if t.result == "LOSS"]
        total  = len(self.trade_history)
        total_pnl = sum(t.pnl for t in self.trade_history)
        win_rate  = (len(wins) / total * 100) if total > 0 else 0

        print("\n" + "═" * 60)
        print("📊  RESUMEN PAPER TRADING")
        print("═" * 60)
        print(f"  Capital inicial : ${self.initial_capital:,.2f} USDT")
        print(f"  Capital actual  : ${self.balance:,.2f} USDT")
        print(f"  PnL Total       : ${total_pnl:+,.2f} USDT  ({(self.balance/self.initial_capital-1)*100:+.2f}%)")
        print(f"  Trades totales  : {total}  (✅ {len(wins)} wins | ❌ {len(losses)} losses)")
        print(f"  Win Rate        : {win_rate:.1f}%")
        if self.positions:
            print(f"  Posiciones abiertas: {list(self.positions.keys())}")
        print("═" * 60 + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE DATOS DE MERCADO (API PÚBLICA, SIN AUTH)
# ─────────────────────────────────────────────────────────────────────────────

def get_klines_public(symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
    """Descarga velas de Binance Futures usando la API pública (sin auth)."""
    try:
        raw = public_client.futures_klines(symbol=symbol, interval=interval, limit=limit)
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
    except Exception as e:
        logger.error(f"Error descargando {symbol}: {e}")
        return pd.DataFrame()


def get_funding_rate_public(symbol: str) -> float:
    """Obtiene el funding rate actual usando la API pública (sin auth)."""
    try:
        data = public_client.futures_funding_rate(symbol=symbol, limit=1)
        if data:
            return float(data[-1]["fundingRate"])
        return 0.0
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# MOCK DE EXCHANGE para strategy.py (usa API pública)
# ─────────────────────────────────────────────────────────────────────────────

class PublicExchangeMock:
    """
    Mock del exchange que usa la API pública de Binance (sin auth).
    Solo implementa get_funding_rate() para el filtro de strategy.py.
    """
    def get_funding_rate(self, symbol: str) -> float:
        rate = get_funding_rate_public(symbol)
        direction = "→ Short bias" if rate > 0 else "→ Long bias"
        if abs(rate) >= FUNDING_RATE_THRESHOLD:
            logger.info(f"{symbol}: Funding Rate: {rate*100:.4f}% {direction}")
        return rate


# ─────────────────────────────────────────────────────────────────────────────
# LOGGER CSV DE TRADES
# ─────────────────────────────────────────────────────────────────────────────

PAPER_LOG_FILE = "paper_trades.csv"
STATE_FILE     = "bot_state.json"

def _save_trade_csv(trade: TradeResult):
    file_exists = os.path.exists(PAPER_LOG_FILE)
    with open(PAPER_LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["opened_at", "closed_at", "symbol", "side",
                             "entry", "exit", "qty", "pnl", "result"])
        writer.writerow([
            trade.opened_at, trade.closed_at, trade.symbol, trade.side,
            trade.entry_price, trade.exit_price, trade.qty, trade.pnl, trade.result
        ])

def _save_state_json(portfolio: PaperPortfolio):
    """Escribe el estado del bot en JSON para que el dashboard lo lea."""
    positions_data = {
        sym: {
            "side":        pos.side,
            "entry_price": pos.entry_price,
            "qty":         pos.qty,
            "stop_loss":   pos.stop_loss,
            "take_profit": pos.take_profit,
            "opened_at":   pos.opened_at,
        }
        for sym, pos in portfolio.positions.items()
    }
    state = {
        "balance":         round(portfolio.balance, 4),
        "initial_capital": round(portfolio.initial_capital, 4),
        "positions":       positions_data,
        "running":         True,
        "last_update":     datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# LOOP PRINCIPAL DE PAPER TRADING
# ─────────────────────────────────────────────────────────────────────────────

def run_paper_trading(symbols: list[str], interval: str,
                      initial_capital: float, check_seconds: int = 60):
    """
    Loop principal del paper trading.
    Usa datos reales de Binance pero ejecuta órdenes localmente.

    Args:
        symbols:        Lista de pares a operar
        interval:       Timeframe (ej: "1h", "15m")
        initial_capital: Capital virtual inicial en USDT
        check_seconds:  Segundos entre cada ciclo
    """
    portfolio    = PaperPortfolio(initial_capital)
    mock_exchange = PublicExchangeMock()

    logger.info("🤖 PAPER TRADING INICIADO (API pública, sin auth)")
    logger.info(f"   Pares:           {', '.join(symbols)}")
    logger.info(f"   Timeframe:       {interval}")
    logger.info(f"   Capital virtual: ${initial_capital:,.2f} USDT")
    logger.info(f"   Ciclo cada:      {check_seconds}s")
    logger.info(f"   Trades → CSV:    {PAPER_LOG_FILE}")
    logger.info("   Presiona Ctrl+C para detener y ver resumen.\n")

    try:
        while True:
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"─── Ciclo {ts} UTC | Balance: ${portfolio.balance:.2f} USDT ───")

            for symbol in symbols:
                # ── 1. Descargar velas ────────────────────────────────────
                df = get_klines_public(symbol, interval, limit=config.KLINES_LIMIT)
                if df.empty:
                    continue

                # ── 2. Verificar si SL/TP fue alcanzado ───────────────────
                if portfolio.has_position(symbol) and len(df) >= 2:
                    last_row = df.iloc[-2]  # Última vela cerrada
                    trade = portfolio.check_and_close(
                        symbol,
                        current_high=float(last_row["high"]),
                        current_low=float(last_row["low"]),
                    )
                    if trade:
                        _save_trade_csv(trade)
                    continue  # No buscar nueva señal si había posición

                # ── 3. Detectar señal (estrategia según el par) ───────────────
                if portfolio.has_position(symbol):
                    continue  # Ya tiene posición, no abrir otra

                if symbol == XAU_SYMBOL:
                    # ═══════════════════════════════════════════════════════
                    # XAUUSDT → ASIAN RANGE BREAKOUT (82% win rate backtest)
                    # Siempre usa 15m para tener resolución de sesión
                    # ═══════════════════════════════════════════════════════
                    df_xau = get_klines_public(symbol, XAU_INTERVAL, limit=50)
                    if df_xau.empty:
                        continue
                    signal, sl_price, tp_price = check_signal_xau(df_xau, symbol)
                    
                    if signal:
                        # 📈 Estrategia 1: ASIAN BREAKOUT (Mañana London)
                        entry_price = float(df_xau["close"].iloc[-1])
                        qty = calc_position_size(portfolio.balance, entry_price, sl_price, symbol)
                        if qty > 0 and sl_price > 0:
                            portfolio.open_position(symbol, signal, entry_price, qty, sl_price, tp_price)
                            logger.log_trade(symbol, signal, entry_price, sl_price, tp_price, qty, note="PAPER-XAU-ARB")
                            continue

                    # 📉 Estrategia 2: EMA/RSI Fallback (Si no hay rotura o es otra hora)
                    # Usamos el dataframe estándar (df) que puede ser 5m, 15m, etc.
                    signal = check_signal(df, symbol, exchange=mock_exchange)
                    if signal:
                        df_ind = add_indicators(df)
                        data   = get_last_signal_data(df_ind)
                        entry_price = data["close"]
                        atr         = data["atr"]
                        sl_price, tp_price = calc_sl_tp(entry_price, atr, signal, symbol)
                        qty = calc_position_size(portfolio.balance, entry_price, sl_price, symbol)
                        
                        if qty > 0:
                            portfolio.open_position(symbol, signal, entry_price, qty, sl_price, tp_price)
                            logger.log_trade(symbol, signal, entry_price, sl_price, tp_price, qty, note="PAPER-XAU-EMA")

                else:
                    # ═══════════════════════════════════════════════════════
                    # Resto de pares → EMA 9/20 + RSI + ADX + Funding Rate
                    # ═══════════════════════════════════════════════════════
                    signal = check_signal(df, symbol, exchange=mock_exchange)
                    if signal is None:
                        continue

                    df_ind = add_indicators(df)
                    data   = get_last_signal_data(df_ind)
                    entry_price = data["close"]
                    atr         = data["atr"]

                    sl_price, tp_price = calc_sl_tp(entry_price, atr, signal, symbol)
                    qty = calc_position_size(portfolio.balance, entry_price, sl_price, symbol)

                    if qty <= 0:
                        logger.warning(f"{symbol}: Cantidad calculada inválida. Saltando.")
                        continue

                    portfolio.open_position(symbol, signal, entry_price, qty, sl_price, tp_price)
                    logger.log_trade(symbol, signal, entry_price, sl_price, tp_price, qty, note="PAPER")

                time.sleep(0.3)  # Pausa entre pares

            # ── Guardar estado para el dashboard ──────────────────────
            _save_state_json(portfolio)

            time.sleep(check_seconds)

    except KeyboardInterrupt:
        logger.info("\n🛑 Paper trading detenido por el usuario.")
        portfolio.print_summary()
        print(f"\n📄 Trades guardados en: {PAPER_LOG_FILE}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Paper Trading con API pública de Binance (sin API keys)"
    )
    parser.add_argument(
        "--symbol", default=None,
        help="Par específico (ej: BTCUSDT). Si no se indica, usa todos los de config."
    )
    parser.add_argument(
        "--interval", default=config.TIMEFRAME,
        help=f"Timeframe (default: {config.TIMEFRAME})"
    )
    parser.add_argument(
        "--capital", default=10000.0, type=float,
        help="Capital virtual inicial en USDT (default: 10000)"
    )
    parser.add_argument(
        "--interval-seconds", default=60, type=int,
        help="Segundos entre ciclos (default: 60)"
    )
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else config.SYMBOLS
    run_paper_trading(
        symbols=symbols,
        interval=args.interval,
        initial_capital=args.capital,
        check_seconds=args.interval_seconds,
    )
