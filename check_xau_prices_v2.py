from binance.client import Client
import pandas as pd
from datetime import datetime, timedelta

client = Client("", "")
symbol = "XAUUSDT"
raw = client.futures_historical_klines(symbol, "1h", "24 hours ago UTC")
df = pd.DataFrame(raw, columns=["ts","open","high","low","close","volume","ct","qv","tr","tbb","tbq","ig"])
for c in ["open","high","low","close"]: df[c] = df[c].astype(float)

price = df['close'].iloc[-1]
range_val = df['high'].max() - df['low'].min()

with open("price_check.txt", "w") as f:
    f.write(f"Symbol: {symbol}\n")
    f.write(f"Current Price: {price}\n")
    f.write(f"24h Range: {range_val}\n")
    f.write(f"Sample data:\n{df.tail(5).to_string()}\n")
