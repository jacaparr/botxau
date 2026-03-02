import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import json
import os

def export_mt5_history(days=30):
    if not mt5.initialize():
        print("Error al inicializar MT5")
        return

    # Obtener historial de los últimos X días
    from_date = datetime.now().timestamp() - (days * 24 * 60 * 60)
    to_date = datetime.now().timestamp()
    
    history_deals = mt5.history_deals_get(from_date, to_date)
    if history_deals is None:
        print("No se encontraron trades en el historial")
        mt5.shutdown()
        return

    deals_list = []
    for deal in history_deals:
        # Solo trades cerrados o con PnL real (Entry/Exit)
        if deal.entry == mt5.DEAL_ENTRY_OUT: # Cierre de posición
            deals_list.append({
                "ticket": deal.ticket,
                "order": deal.order,
                "time": datetime.fromtimestamp(deal.time).strftime('%Y-%m-%d %H:%M:%S'),
                "symbol": deal.symbol,
                "type": "SELL" if deal.type == mt5.DEAL_TYPE_SELL else "BUY",
                "volume": deal.volume,
                "price": deal.price,
                "pnl": deal.profit + deal.commission + deal.swap,
                "comment": deal.comment
            })

    # Guardar en JSON para el dashboard
    with open("trade_history.json", "w") as f:
        json.dump(deals_list, f, indent=2)
    
    print(f"✅ Historial de {len(deals_list)} trades exportado a trade_history.json")
    mt5.shutdown()

if __name__ == "__main__":
    export_mt5_history()
