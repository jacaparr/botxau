"""
risk_manager.py — Gestión de riesgo y cálculo de posiciones
Stop Loss y Take Profit basados en ATR
"""

from config import get_symbol_config, RISK_PER_TRADE
import logger


def calc_sl_tp(entry_price: float, atr: float, signal: str, symbol: str) -> tuple[float, float]:
    """
    Calcula los precios de Stop Loss y Take Profit basados en ATR.

    Args:
        entry_price: Precio de entrada
        atr:         Average True Range actual
        signal:      "LONG" o "SHORT"
        symbol:      Par de trading (para usar config específica)

    Returns:
        (stop_loss_price, take_profit_price)
    """
    cfg = get_symbol_config(symbol)
    sl_mult = cfg["atr_sl"]
    tp_mult = cfg["atr_tp"]

    if signal == "LONG":
        stop_loss   = entry_price - (atr * sl_mult)
        take_profit = entry_price + (atr * tp_mult)
    else:  # SHORT
        stop_loss   = entry_price + (atr * sl_mult)
        take_profit = entry_price - (atr * tp_mult)

    ratio = tp_mult / sl_mult
    logger.info(
        f"{symbol} | SL: {stop_loss:.4f} (ATR×{sl_mult}) | "
        f"TP: {take_profit:.4f} (ATR×{tp_mult}) | Ratio 1:{ratio:.1f}"
    )
    return stop_loss, take_profit


def calc_position_size(balance_usdt: float, entry_price: float,
                       stop_loss: float, symbol: str) -> float:
    """
    Calcula el tamaño de la posición en función del riesgo por operación.

    Fórmula: qty = (balance × risk_pct) / |entry - stop_loss|

    Args:
        balance_usdt: Capital disponible en USDT
        entry_price:  Precio de entrada
        stop_loss:    Precio de Stop Loss
        symbol:       Par de trading

    Returns:
        Cantidad de contratos/monedas a comprar
    """
    cfg = get_symbol_config(symbol)
    risk_amount = balance_usdt * RISK_PER_TRADE  # USDT en riesgo
    sl_distance = abs(entry_price - stop_loss)

    if sl_distance == 0:
        logger.warning(f"{symbol}: SL distance = 0, usando tamaño mínimo.")
        return 0.001

    qty = risk_amount / sl_distance

    logger.info(
        f"{symbol} | Balance: {balance_usdt:.2f} USDT | "
        f"Riesgo: {risk_amount:.2f} USDT ({RISK_PER_TRADE*100:.0f}%) | "
        f"Qty: {qty:.6f}"
    )
    return qty


def apply_leverage(qty: float, symbol: str) -> tuple[float, int]:
    """
    Retorna la cantidad ajustada con apalancamiento y el leverage a usar.

    Returns:
        (qty_with_leverage, leverage)
    """
    cfg = get_symbol_config(symbol)
    leverage = cfg["leverage"]
    # En futuros, el qty ya incluye el leverage implícitamente al calcular el margen.
    # Aquí simplemente retornamos el leverage para configurarlo en la exchange.
    return qty, leverage


def validate_risk(balance_usdt: float, qty: float, entry_price: float,
                  stop_loss: float) -> bool:
    """
    Valida que la operación no supere el riesgo máximo permitido.

    Returns:
        True si la operación es válida
    """
    potential_loss = qty * abs(entry_price - stop_loss)
    max_loss = balance_usdt * RISK_PER_TRADE * 3  # Máximo 3× el riesgo normal

    if potential_loss > max_loss:
        logger.warning(
            f"⚠️ Riesgo excesivo: pérdida potencial {potential_loss:.2f} USDT "
            f"> máximo {max_loss:.2f} USDT. Operación rechazada."
        )
        return False
    return True
