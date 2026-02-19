"""
logger.py — Sistema de logging con colores y guardado en CSV
"""

import csv
import os
from datetime import datetime
from colorama import Fore, Style, init

init(autoreset=True)

LOG_FILE = "trades_log.csv"
_headers_written = False


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
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{Fore.CYAN}[{ts}] ℹ️  {msg}{Style.RESET_ALL}")


def success(msg: str):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{Fore.GREEN}[{ts}] ✅ {msg}{Style.RESET_ALL}")


def warning(msg: str):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{Fore.YELLOW}[{ts}] ⚠️  {msg}{Style.RESET_ALL}")


def error(msg: str):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{Fore.RED}[{ts}] ❌ {msg}{Style.RESET_ALL}")


def signal(symbol: str, direction: str, entry: float, sl: float, tp: float):
    color = Fore.GREEN if direction == "LONG" else Fore.RED
    arrow = "📈" if direction == "LONG" else "📉"
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(
        f"{color}[{ts}] {arrow} SEÑAL {direction} | {symbol} | "
        f"Entry: {entry:.4f} | SL: {sl:.4f} | TP: {tp:.4f}{Style.RESET_ALL}"
    )


def log_trade(symbol: str, sig: str, entry: float, sl: float,
              tp: float, qty: float, pnl: float = 0.0, note: str = ""):
    _ensure_headers()
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([ts, symbol, sig, entry, sl, tp, qty, pnl, note])
