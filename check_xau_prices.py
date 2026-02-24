from binance.client import Client
import pandas as pd
from datetime import datetime, timedelta

client = Client("", "")
symbol = "XAUUSDT"
raw = client.futures_historical_klines(symbol, "15m", "3 days ago UTC")
df = pd.DataFrame(raw, columns=["ts","open","high","low","close","volume","ct","qv","tr","tbb","tbq","ig"])
df["ts"] = pd.to_datetime(df["ts"], unit="ms")
for c in ["open","high","low","close"]: df[c] = df[c].astype(float)

print(df.tail(10))
print(f"\nPrice: {df['close'].iloc[-1]}")
print(f"Typical 6h range: {(df['high'].max() - df['low'].min())}")
