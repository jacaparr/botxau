"""
config.py — Configuración central del bot de Binance Futures
Estrategia: EMA 9/20 + RSI 14 + ADX 14
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# API KEYS (desde .env)
# ─────────────────────────────────────────────
API_KEY    = os.getenv("BINANCE_TESTNET_API_KEY", "")
SECRET_KEY = os.getenv("BINANCE_TESTNET_SECRET_KEY", "")
USE_TESTNET = os.getenv("USE_TESTNET", "True").lower() == "true"

# ─────────────────────────────────────────────
# PARES Y TIMEFRAME
# ─────────────────────────────────────────────
SYMBOLS   = ["BTCUSDT", "ETHUSDT", "XAUUSDT", "SOLUSDT"]
TIMEFRAME = "1h"          # Timeframe principal
KLINES_LIMIT = 200        # Velas a descargar (mínimo 50 para indicadores)

# ─────────────────────────────────────────────
# PARÁMETROS DE INDICADORES
# ─────────────────────────────────────────────
EMA_FAST   = 9
EMA_SLOW   = 20
RSI_PERIOD = 14
ADX_PERIOD = 14
ATR_PERIOD = 14
VOL_MA_PERIOD = 20        # Media de volumen para filtro

# ─────────────────────────────────────────────
# CONFIGURACIÓN POR PAR
# Cada par puede tener parámetros propios.
# Si no se especifica, se usan los valores DEFAULT.
# ─────────────────────────────────────────────
DEFAULT_CONFIG = {
    "rsi_long":   55,     # RSI mínimo para Long
    "rsi_short":  45,     # RSI máximo para Short
    "adx_min":    25,     # ADX mínimo (fuerza de tendencia)
    "atr_sl":     1.5,    # Stop Loss = ATR × atr_sl
    "atr_tp":     3.0,    # Take Profit = ATR × atr_tp (ratio 1:2)
    "leverage":   3,      # Apalancamiento
}

SYMBOL_CONFIG = {
    "BTCUSDT": {
        **DEFAULT_CONFIG,
    },
    "ETHUSDT": {
        **DEFAULT_CONFIG,
        "rsi_long":  54,
        "rsi_short": 46,
    },
    "XAUUSDT": {
        # Oro: ADX más bajo (25 filtra demasiado), SL/TP más amplios
        "rsi_long":   55,
        "rsi_short":  45,
        "adx_min":    20,   # ← Más permisivo para el oro
        "atr_sl":     2.0,  # ← SL más amplio (el oro tiene más ruido intradía)
        "atr_tp":     4.0,  # ← TP más amplio (ratio 1:2)
        "leverage":   3,
    },
    "SOLUSDT": {
        **DEFAULT_CONFIG,
        "adx_min":    28,   # SOL es más volátil, exigimos tendencia más fuerte
        "atr_sl":     1.8,
        "atr_tp":     3.6,
    },
}

# ─────────────────────────────────────────────
# GESTIÓN DE RIESGO GLOBAL
# ─────────────────────────────────────────────
RISK_PER_TRADE = 0.015    # 1.5% del capital por operación (optimizado para prop firm)
MAX_OPEN_POSITIONS = 2    # Máximo de posiciones abiertas simultáneas

# ─────────────────────────────────────────────
# SESIONES HORARIAS PARA XAUUSDT (UTC)
# El oro opera mejor en sesión Londres + NY
# ─────────────────────────────────────────────
XAUUSDT_TRADE_HOURS = {
    "start": 7,   # 07:00 UTC (apertura Londres)
    "end":   21,  # 21:00 UTC (cierre NY)
}

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
LOG_FILE    = "trades_log.csv"
LOG_CONSOLE = True


def get_symbol_config(symbol: str) -> dict:
    """Retorna la configuración específica para un par."""
    return SYMBOL_CONFIG.get(symbol, DEFAULT_CONFIG)
