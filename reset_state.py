"""
reset_state.py — Resetea el estado del bot para que empiece en 0.

USAR cuando:
  - El bot dice "TRADING BLOQUEADO" por Drawdown falso
  - Cambias de cuenta (demo -> real)
  - Quieres empezar un nuevo reto

USO: python reset_state.py
"""
import json, os

STATE_FILE = "bot_state_mt5_v5.json"
STARTING_BALANCE = 25000.0  # Tu balance inicial del reto

fresh_state = {
    "last_ranges": {},
    "trades_today": 0,
    "pnl_today": 0.0,
    "virtual_trades_today": 0,
    "virtual_pnl_today": 0.0,
    "last_trade_date": "",
    "daily_summary_sent": "",
    "consecutive_losses": 0,
    "dd_alert_sent_today": False,
    "prop_starting_balance": STARTING_BALANCE,
    "prop_peak_balance": STARTING_BALANCE,
    "prop_day": "",
    "prop_day_start_balance": STARTING_BALANCE,
    "virtual_positions": [],
    "live_positions": [],
    "running": False
}

with open(STATE_FILE, "w") as f:
    json.dump(fresh_state, f, indent=2)

print(f"\n[OK] Estado reseteado. Balance inicial: ${STARTING_BALANCE:,.0f}")
print("     Ahora abre el watchdog.bat\n")
