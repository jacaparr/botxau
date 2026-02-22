"""
logger.py — Sistema de logging con colores + archivo
=====================================================
Escribe logs tanto a consola (con colores) como a archivo (bot.log).
Ideal para VPS donde necesitas revisar logs después.
"""

import csv
import os
import logging
from datetime import datetime, timezone
from colorama import Fore, Style, init
from logging.handlers import RotatingFileHandler

init(autoreset=True)

LOG_FILE = "trades_log.csv"
BOT_LOG_FILE = "bot.log"
_headers_written = False

# ─────────────────────────────────────────────────────────────────────────────
# FILE LOGGER (para VPS)
# ─────────────────────────────────────────────────────────────────────────────

_file_logger = logging.getLogger("bot_mt5")
_file_logger.setLevel(logging.DEBUG)

# Rotación: max 5MB por archivo, mantener 3 archivos
_handler = RotatingFileHandler(
    BOT_LOG_FILE, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
)
_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s",
                      datefmt="%Y-%m-%d %H:%M:%S")
)
_file_logger.addHandler(_handler)


# ─────────────────────────────────────────────────────────────────────────────
# FUNCIONES DE LOG
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_headers():
    global _headers_written
    if not _headers_written and not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "symbol", "signal", "entry_price",
                "stop_loss", "take_profit", "qty", "pnl", "note"
            ])
    _headers_written = True


def info(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{Fore.CYAN}[{ts}] ℹ️  {msg}{Style.RESET_ALL}")
    _file_logger.info(msg)


def success(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{Fore.GREEN}[{ts}] ✅ {msg}{Style.RESET_ALL}")
    _file_logger.info(msg)


def warning(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{Fore.YELLOW}[{ts}] ⚠️  {msg}{Style.RESET_ALL}")
    _file_logger.warning(msg)


def error(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"{Fore.RED}[{ts}] ❌ {msg}{Style.RESET_ALL}")
    _file_logger.error(msg)


def signal(symbol: str, direction: str, entry: float, sl: float, tp: float):
    color = Fore.GREEN if direction == "LONG" else Fore.RED
    arrow = "📈" if direction == "LONG" else "📉"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    msg = (f"SEÑAL {direction} | {symbol} | "
           f"Entry: {entry:.4f} | SL: {sl:.4f} | TP: {tp:.4f}")
    print(f"{color}[{ts}] {arrow} {msg}{Style.RESET_ALL}")
    _file_logger.info(msg)


def log_trade(symbol: str, sig: str, entry: float, sl: float,
              tp: float, qty: float, pnl: float = 0.0, note: str = ""):
    _ensure_headers()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([ts, symbol, sig, entry, sl, tp, qty, pnl, note])
    _file_logger.info(
        f"TRADE | {symbol} {sig} | E:{entry:.2f} SL:{sl:.2f} "
        f"TP:{tp:.2f} | Qty:{qty} PnL:{pnl}"
    )
