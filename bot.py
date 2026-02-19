"""
bot.py — Loop principal del bot de trading
Ejecuta la estrategia en tiempo real sobre Binance Futures Testnet
"""

import argparse
import time
from datetime import datetime, timezone

import config
import logger
from exchange import BinanceFuturesExchange
from strategy import check_signal, get_entry_price, get_atr
from risk_manager import calc_sl_tp, calc_position_size, apply_leverage, validate_risk

# Intervalo en segundos entre ciclos del bot
# 1h = 3600s, pero chequeamos cada 60s para no perdernos el cierre de vela
CHECK_INTERVAL_SECONDS = 60


def run_cycle(exchange: BinanceFuturesExchange, dry_run: bool = False):
    """
    Ejecuta un ciclo completo del bot:
    1. Para cada par, descarga velas
    2. Calcula señal
    3. Si hay señal y no hay posición abierta → coloca orden
    """
    logger.info(f"─── Ciclo {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC ───")

    # Contar posiciones abiertas
    open_positions = exchange.get_open_positions()
    open_symbols   = {p["symbol"] for p in open_positions}
    n_open         = len(open_symbols)

    if n_open >= config.MAX_OPEN_POSITIONS:
        logger.info(f"Máximo de posiciones abiertas alcanzado ({n_open}/{config.MAX_OPEN_POSITIONS}). Esperando...")
        return

    # Obtener balance
    balance = exchange.get_balance()
    logger.info(f"💰 Balance disponible: {balance:.2f} USDT")

    for symbol in config.SYMBOLS:
        # Saltar si ya hay posición abierta en este par
        if symbol in open_symbols:
            logger.info(f"{symbol}: Posición ya abierta. Saltando.")
            continue

        # Descargar velas
        df = exchange.get_klines(symbol, config.TIMEFRAME, limit=config.KLINES_LIMIT)
        if df.empty:
            logger.warning(f"{symbol}: No se pudieron obtener datos. Saltando.")
            continue

        # Calcular señal (pasamos exchange para el filtro de Funding Rate)
        signal = check_signal(df, symbol, exchange=exchange)

        if signal is None:
            continue

        # Calcular precios de entrada, SL y TP
        entry_price = get_entry_price(df)
        atr         = get_atr(df)
        sl_price, tp_price = calc_sl_tp(entry_price, atr, signal, symbol)

        # Calcular tamaño de posición
        qty, leverage = apply_leverage(
            calc_position_size(balance, entry_price, sl_price, symbol),
            symbol
        )

        # Validar riesgo
        if not validate_risk(balance, qty, entry_price, sl_price):
            continue

        # Log de la señal
        logger.signal(symbol, signal, entry_price, sl_price, tp_price)

        if dry_run:
            logger.warning(f"[DRY-RUN] {symbol}: Orden {signal} NO colocada (modo simulación).")
            continue

        # 🔒 ISOLATED MARGIN: asegurar modo aislado ANTES de cualquier orden
        try:
            exchange.set_isolated_margin(symbol)
        except Exception:
            logger.error(f"{symbol}: No se pudo configurar ISOLATED MARGIN. Saltando orden.")
            continue

        # Configurar leverage
        exchange.set_leverage(symbol, leverage)

        # Colocar orden
        side = "BUY" if signal == "LONG" else "SELL"
        order = exchange.place_market_order(symbol, side, qty, sl_price, tp_price)

        if order:
            logger.log_trade(symbol, signal, entry_price, sl_price, tp_price, qty)
            # Actualizar posiciones abiertas
            open_symbols.add(symbol)
            n_open += 1

            if n_open >= config.MAX_OPEN_POSITIONS:
                logger.info("Máximo de posiciones alcanzado. Deteniendo búsqueda de señales.")
                break

        # Pequeña pausa entre pares para no saturar la API
        time.sleep(0.5)


def main():
    parser = argparse.ArgumentParser(description="Binance Futures Bot — EMA+RSI+ADX")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Modo simulación: calcula señales pero NO coloca órdenes reales"
    )
    args = parser.parse_args()

    mode = "DRY-RUN (simulación)" if args.dry_run else "LIVE (Testnet)"
    logger.info(f"🤖 Bot iniciado en modo: {mode}")
    logger.info(f"   Pares: {', '.join(config.SYMBOLS)}")
    logger.info(f"   Timeframe: {config.TIMEFRAME}")
    logger.info(f"   Testnet: {config.USE_TESTNET}")

    if not config.API_KEY or not config.SECRET_KEY:
        logger.error(
            "❌ API keys no configuradas. "
            "Copia .env.example a .env y añade tus claves del Testnet."
        )
        return

    exchange = BinanceFuturesExchange()

    logger.info(f"⏱️  Ciclo cada {CHECK_INTERVAL_SECONDS}s. Presiona Ctrl+C para detener.\n")

    try:
        while True:
            try:
                run_cycle(exchange, dry_run=args.dry_run)
            except Exception as e:
                logger.error(f"Error en ciclo: {e}")

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        logger.info("🛑 Bot detenido por el usuario.")


if __name__ == "__main__":
    main()
