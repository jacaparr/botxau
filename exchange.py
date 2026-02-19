"""
exchange.py — Wrapper para Binance Futures Testnet API
Gestiona conexión, datos de mercado y órdenes
"""

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException

import config
import logger


class BinanceFuturesExchange:
    """Wrapper para Binance Futures (Testnet o Real)."""

    TESTNET_URL = "https://testnet.binancefuture.com"

    def __init__(self):
        self.client = Client(
            api_key=config.API_KEY,
            api_secret=config.SECRET_KEY,
            testnet=config.USE_TESTNET,
        )
        if config.USE_TESTNET:
            # Apuntar al endpoint del Testnet de Futuros
            self.client.FUTURES_URL = self.TESTNET_URL + "/fapi"
            logger.info("🧪 Conectado a Binance Futures TESTNET")
        else:
            logger.warning("⚠️ Conectado a Binance Futures REAL — ¡Cuidado con el dinero!")

    # ─────────────────────────────────────────────────────────────────────
    # DATOS DE MERCADO
    # ─────────────────────────────────────────────────────────────────────

    def get_funding_rate(self, symbol: str) -> float:
        """
        🔄 FEATURE: Funding Rate
        Retorna la tasa de financiación actual (cada 8h en perpetuos).

        Lógica de uso:
          - Funding Rate > 0  → Los Longs pagan a los Shorts → Sesgo SHORT
          - Funding Rate < 0  → Los Shorts pagan a los Longs → Sesgo LONG
          - |Rate| > 0.01%   → La tasa es significativa (1 USD por cada 10,000)

        Returns:
            float: tasa en decimal (ej: 0.0001 = 0.01%)
        """
        try:
            data = self.client.futures_funding_rate(symbol=symbol, limit=1)
            if data:
                rate = float(data[-1]["fundingRate"])
                direction = "→ Short bias" if rate > 0 else "→ Long bias"
                logger.info(f"{symbol}: Funding Rate: {rate*100:.4f}% {direction}")
                return rate
            return 0.0
        except BinanceAPIException as e:
            logger.error(f"Error obteniendo funding rate de {symbol}: {e}")
            return 0.0

    def get_klines(self, symbol: str, interval: str, limit: int = 200) -> pd.DataFrame:
        """
        Descarga velas OHLCV de Binance Futures.

        Returns:
            DataFrame con columnas: open, high, low, close, volume
        """
        try:
            raw = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=limit,
            )
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
        except BinanceAPIException as e:
            logger.error(f"Error obteniendo klines de {symbol}: {e}")
            return pd.DataFrame()

    def get_balance(self) -> float:
        """Retorna el balance disponible en USDT."""
        try:
            balances = self.client.futures_account_balance()
            for b in balances:
                if b["asset"] == "USDT":
                    return float(b["availableBalance"])
            return 0.0
        except BinanceAPIException as e:
            logger.error(f"Error obteniendo balance: {e}")
            return 0.0

    def get_open_positions(self) -> list[dict]:
        """Retorna lista de posiciones abiertas con cantidad != 0."""
        try:
            positions = self.client.futures_position_information()
            open_pos = [
                p for p in positions
                if float(p["positionAmt"]) != 0
            ]
            return open_pos
        except BinanceAPIException as e:
            logger.error(f"Error obteniendo posiciones: {e}")
            return []

    def has_open_position(self, symbol: str) -> bool:
        """Verifica si hay una posición abierta para el par dado."""
        positions = self.get_open_positions()
        return any(p["symbol"] == symbol for p in positions)

    # ─────────────────────────────────────────────────────────────────────
    # CONFIGURACIÓN DE LEVERAGE Y MARGEN
    # ─────────────────────────────────────────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int):
        """Configura el apalancamiento para un par."""
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            logger.info(f"{symbol}: Leverage configurado a {leverage}x")
        except BinanceAPIException as e:
            logger.error(f"Error configurando leverage para {symbol}: {e}")

    def set_isolated_margin(self, symbol: str):
        """
        🔒 FEATURE: Isolated Margin
        Asegura que el par opere en modo ISOLATED (no CROSS) antes de abrir
        cualquier posición. En ISOLATED, solo el margen asignado a esa posición
        está en riesgo — el resto del capital queda protegido.

        Diferencia ISOLATED vs CROSS:
          - CROSS:    Todas las posiciones comparten el balance → una pérdida grande
                      puede liquidar todo el wallet.
          - ISOLATED: Cada posición tiene su propio margen → pérdida máxima limitada
                      al margen asignado a esa posición.
        """
        try:
            self.client.futures_change_margin_type(
                symbol=symbol,
                marginType="ISOLATED",
            )
            logger.info(f"{symbol}: ✅ Modo ISOLATED MARGIN activado")
        except BinanceAPIException as e:
            # Código -4046: ya está en ISOLATED → no es un error real
            if "-4046" in str(e) or "No need to change" in str(e):
                logger.info(f"{symbol}: Ya estaba en ISOLATED MARGIN")
            else:
                logger.error(f"Error configurando ISOLATED MARGIN en {symbol}: {e}")
                raise  # Propagar el error para detener la operación

    # ─────────────────────────────────────────────────────────────────────
    # ÓRDENES
    # ─────────────────────────────────────────────────────────────────────

    def place_market_order(self, symbol: str, side: str, qty: float,
                           stop_loss: float, take_profit: float) -> dict | None:
        """
        Coloca una orden de mercado con SL y TP.

        🚨 KILL SWITCH: Si el Stop Loss falla al enviarse al servidor,
        la orden de entrada se cancela automáticamente para evitar
        quedarse en una posición sin protección.

        Args:
            symbol:      Par de trading (ej: "BTCUSDT")
            side:        "BUY" para Long, "SELL" para Short
            qty:         Cantidad de contratos
            stop_loss:   Precio de Stop Loss
            take_profit: Precio de Take Profit

        Returns:
            Respuesta de la API o None si hay error
        """
        # Redondear qty según las reglas del par
        qty = self._round_qty(symbol, qty)
        if qty <= 0:
            logger.error(f"{symbol}: Cantidad inválida ({qty})")
            return None

        price_precision = self._get_price_precision(symbol)
        sl_side = "SELL" if side == "BUY" else "BUY"
        order = None

        try:
            # ── Paso 1: Orden principal de mercado ────────────────────────
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type="MARKET",
                quantity=qty,
            )
            logger.success(
                f"{symbol}: Orden {side} colocada | Qty: {qty} | ID: {order['orderId']}"
            )

            # ── Paso 2: Stop Loss (KILL SWITCH) ───────────────────────────
            # Si esta orden falla, CANCELAMOS la posición inmediatamente.
            try:
                self.client.futures_create_order(
                    symbol=symbol,
                    side=sl_side,
                    type="STOP_MARKET",
                    stopPrice=round(stop_loss, price_precision),
                    closePosition=True,
                )
                logger.info(f"{symbol}: 🛡️ Stop Loss colocado en {stop_loss:.4f}")
            except BinanceAPIException as sl_error:
                # 🚨 KILL SWITCH ACTIVADO: cerrar posición inmediatamente
                logger.error(
                    f"{symbol}: ❌ KILL SWITCH — Fallo al colocar SL ({sl_error}). "
                    f"Cerrando posición para evitar exposición sin protección!"
                )
                self.close_position(symbol)
                return None

            # ── Paso 3: Take Profit ───────────────────────────────────────
            try:
                self.client.futures_create_order(
                    symbol=symbol,
                    side=sl_side,
                    type="TAKE_PROFIT_MARKET",
                    stopPrice=round(take_profit, price_precision),
                    closePosition=True,
                )
                logger.info(f"{symbol}: 🎯 Take Profit colocado en {take_profit:.4f}")
            except BinanceAPIException as tp_error:
                # TP falla → continuar, el SL ya protege la posición
                logger.warning(
                    f"{symbol}: ⚠️ Fallo al colocar TP ({tp_error}). "
                    f"La posición sigue activa con SL en {stop_loss:.4f}."
                )

            return order

        except BinanceAPIException as e:
            logger.error(f"Error colocando orden en {symbol}: {e}")
            return None

    def close_position(self, symbol: str):
        """Cierra la posición abierta para el par dado."""
        try:
            positions = self.get_open_positions()
            for p in positions:
                if p["symbol"] == symbol:
                    amt = float(p["positionAmt"])
                    side = "SELL" if amt > 0 else "BUY"
                    self.client.futures_create_order(
                        symbol=symbol,
                        side=side,
                        type="MARKET",
                        quantity=abs(amt),
                        reduceOnly=True,
                    )
                    logger.info(f"{symbol}: Posición cerrada.")
        except BinanceAPIException as e:
            logger.error(f"Error cerrando posición en {symbol}: {e}")

    # ─────────────────────────────────────────────────────────────────────
    # UTILIDADES
    # ─────────────────────────────────────────────────────────────────────

    def _round_qty(self, symbol: str, qty: float) -> float:
        """Redondea la cantidad según las reglas del par."""
        try:
            info = self.client.futures_exchange_info()
            for s in info["symbols"]:
                if s["symbol"] == symbol:
                    for f in s["filters"]:
                        if f["filterType"] == "LOT_SIZE":
                            step = float(f["stepSize"])
                            precision = len(str(step).rstrip("0").split(".")[-1])
                            return round(qty - (qty % step), precision)
        except Exception:
            pass
        return round(qty, 3)

    def _get_price_precision(self, symbol: str) -> int:
        """Retorna la precisión de precio para un par."""
        try:
            info = self.client.futures_exchange_info()
            for s in info["symbols"]:
                if s["symbol"] == symbol:
                    return s.get("pricePrecision", 2)
        except Exception:
            pass
        return 2


if __name__ == "__main__":
    print("🔌 Probando conexión con Binance Futures Testnet...")
    exchange = BinanceFuturesExchange()
    balance = exchange.get_balance()
    print(f"💰 Balance USDT disponible: {balance:.2f} USDT")

    print("\n📊 Descargando últimas 5 velas de BTCUSDT 1h...")
    df = exchange.get_klines("BTCUSDT", "1h", limit=5)
    print(df.to_string())

    print("\n📋 Posiciones abiertas:")
    positions = exchange.get_open_positions()
    if positions:
        for p in positions:
            print(f"  {p['symbol']}: {p['positionAmt']} @ {p['entryPrice']}")
    else:
        print("  Sin posiciones abiertas.")
