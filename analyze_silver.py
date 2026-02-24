import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta, timezone

def analyze_silver_breakout():
    if not mt5.initialize():
        print("Error initializing MT5")
        return

    symbol = "XAGUSD"
    # Buscar alias
    all_symbols = [s.name for s in mt5.symbols_get()]
    actual_symbol = next((s for s in all_symbols if "XAGUSD" in s), None)
    
    if not actual_symbol:
        print("XAGUSD not found")
        return

    print(f"Analyzing {actual_symbol}...")
    
    # Descargar 180 días
    utc_to = datetime.now(timezone.utc)
    utc_from = utc_to - timedelta(days=180)
    rates = mt5.copy_rates_range(actual_symbol, mt5.TIMEFRAME_M15, utc_from, utc_to)
    
    if rates is None:
        print("No rates found")
        return

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
    df.set_index('time', inplace=True)

    # Lógica simplificada de Asian Breakout
    # ... analizando resultados ...
    
    days = sorted(set(df.index.date))
    results = []
    
    for day in days:
        day_df = df[df.index.date == day]
        asian = day_df[(day_df.index.hour >= 0) & (day_df.index.hour < 6)]
        if len(asian) < 4: continue
        
        ah = asian['high'].max()
        al = asian['low'].min()
        rng = ah - al
        
        london = day_df[(day_df.index.hour >= 7) & (day_df.index.hour < 10)]
        for ts, row in london.iterrows():
            if row['close'] > ah:
                # LONG
                sl = al
                tp = row['close'] + rng * 2.5
                # Simple exit check
                rest = day_df[day_df.index > ts]
                win = not rest[rest['high'] >= tp].empty
                loss = not rest[rest['low'] <= sl].empty
                if win: results.append(2.5)
                elif loss: results.append(-1)
                break
            elif row['close'] < al:
                # SHORT
                sl = ah
                tp = row['close'] - rng * 2.5
                rest = day_df[day_df.index > ts]
                win = not rest[rest['low'] <= tp].empty
                loss = not rest[rest['high'] >= sl].empty
                if win: results.append(2.5)
                elif loss: results.append(-1)
                break
                
    if results:
        wr = len([r for r in results if r > 0]) / len(results) * 100
        pnl = sum(results)
        print(f"Results for {actual_symbol}:")
        print(f"Trades: {len(results)}")
        print(f"Win Rate: {wr:.1f}%")
        print(f"Total R: {pnl:.1f}R")
    else:
        print("No trades found")

analyze_silver_breakout()
mt5.shutdown()
