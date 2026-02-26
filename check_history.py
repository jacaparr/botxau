import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta

def find_symbol():
    syms = ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"]
    for s in syms:
        if mt5.symbol_info(s):
            return s
    return None

if __name__ == "__main__":
    if not mt5.initialize():
        print("MT5 Init Failed")
        exit()
        
    symbol = find_symbol()
    if not symbol:
        print("No XAU symbol found")
    else:
        # Check M5
        r_m5 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 200000)
        depth_m5 = len(r_m5) if r_m5 is not None else 0
        
        # Check H1
        r_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 20000)
        depth_h1 = len(r_h1) if r_h1 is not None else 0
        
        print(f"Symbol: {symbol}")
        print(f"M5 Candles: {depth_m5}")
        print(f"H1 Candles: {depth_h1}")
        
        if r_m5 is not None and len(r_m5) > 0:
            first = datetime.fromtimestamp(r_m5[0].time)
            last = datetime.fromtimestamp(r_m5[-1].time)
            print(f"M5 Range: {first} to {last} ({(last-first).days} days)")
            
    mt5.shutdown()
