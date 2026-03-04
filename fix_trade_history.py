"""
fix_trade_history.py — Limpia duplicados del trade_history.csv corrupto.
Uso: python fix_trade_history.py
"""
import csv
from pathlib import Path

TRADE_HISTORY_FILE = "trade_history.csv"
OUTPUT_FILE = "trade_history_clean.csv"

fieldnames = [
    "ticket", "symbol", "direction", "volume",
    "time_open", "price_open", "sl", "tp",
    "time_close", "price_close", "pnl", "balance_after"
]

if not Path(TRADE_HISTORY_FILE).exists():
    print("❌ No se encontró trade_history.csv")
    exit(1)

print(f"📂 Leyendo {TRADE_HISTORY_FILE}...")
with open(TRADE_HISTORY_FILE, "r", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

total_rows = len(rows)
print(f"   Filas totales (con duplicados): {total_rows:,}")

# Deduplicar por ticket (el primer registro gana)
seen = {}
for row in rows:
    ticket = str(row.get("ticket", ""))
    if ticket and ticket not in seen:
        seen[ticket] = row

unique_rows = list(seen.values())
# Ordenar por time_open
unique_rows.sort(key=lambda r: r.get("time_open") or "")

print(f"   Trades únicos encontrados:      {len(unique_rows):,}")
print(f"   Duplicados eliminados:          {total_rows - len(unique_rows):,}")

# Guardar CSV limpio
with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(unique_rows)

print(f"\n✅ CSV limpio guardado en: {OUTPUT_FILE}")
print("\n📊 RESUMEN DE TRADES:")
print(f"{'#':<4} {'Ticket':<16} {'Symbol':<8} {'Dir':<6} {'PnL':>10}  {'Abierto':<22} {'Cerrado'}")
print("-" * 90)
total_pnl = 0
wins = 0
for i, r in enumerate(unique_rows, 1):
    pnl = float(r.get("pnl") or 0)
    total_pnl += pnl
    wins += 1 if pnl > 0 else 0
    marker = "✅" if pnl > 0 else "❌"
    t_open = (r.get("time_open") or "")[:19]
    t_close = (r.get("time_close") or "")[:19]
    sym = str(r.get("symbol") or "")
    direc = str(r.get("direction") or "")
    tick = str(r.get("ticket") or "")
    print(f"{i:<4} {tick:<16} {sym:<8} {direc:<6} {pnl:>10.2f}  {marker}  {t_open:<22} {t_close}")

print("-" * 90)
print(f"\n{'Total PnL:':<40} {total_pnl:>10.2f}")
print(f"{'Win Rate:':<40} {wins}/{len(unique_rows)} = {wins/len(unique_rows)*100:.0f}%" if unique_rows else "")
print(f"\n⚠️  Para reemplazar el original, ejecuta:")
print(f"   copy trade_history_clean.csv trade_history.csv")
