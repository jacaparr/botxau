
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import pandas_ta as ta

# --- CONFIGURACIÓN ---
CAPITAL = 50000
RISK_PCT = 0.005  # Bajamos al 0.5% por seguridad para cuenta de fondeo
DAYS = 365
SYMBOLS = ["XAUUSD", "EURUSD"]

# Parámetros XAU
ASIAN_START_H, ASIAN_END_H = 0, 6
LONDON_START_H, LONDON_END_H = 7, 10
XAU_MIN_RANGE, XAU_MAX_RANGE = 3.0, 20.0
XAU_TP_MULT = 2.0  # Bajamos un poco el TP para asegurar cierres en meses difíciles
XAU_SL_BUFFER = 0.001

def get_eurusd_signal(df):
    if len(df) < 35: return None
    bbands = ta.bbands(df['close'], length=20, std=2)
    rsi = ta.rsi(df['close'], length=14)
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    atr = ta.atr(df['high'], df['low'], df['close'], length=14)
    if bbands is None or rsi is None or adx_df is None: return None
    
    last = {"close": df['close'].iloc[-1], "bb_l": bbands.iloc[-1, 0], "bb_m": bbands.iloc[-1, 1], 
            "bb_u": bbands.iloc[-1, 2], "rsi": rsi.iloc[-1], "adx": adx_df.iloc[-1, 0], "atr": atr.iloc[-1]}
    
    if last["close"] < last["bb_l"] and last["rsi"] < 30 and last["adx"] < 25:
        return "LONG", last["close"], last["close"] - (last["atr"] * 1.5), last["bb_m"]
    if last["close"] > last["bb_u"] and last["rsi"] > 70 and last["adx"] < 25:
        return "SHORT", last["close"], last["close"] + (last["atr"] * 1.5), last["bb_m"]
    return None

def run_backtest_anual():
    if not mt5.initialize(): return "Error MT5"
    
    utc_to = datetime.now(timezone.utc)
    utc_from = utc_to - timedelta(days=DAYS)
    
    # Descargas
    r_xau_15 = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M15, utc_from, utc_to)
    r_xau_1h = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, utc_from, utc_to)
    r_eur_1h = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_H1, utc_from, utc_to)
    
    df_x15 = pd.DataFrame(r_xau_15); df_x15["time"] = pd.to_datetime(df_x15["time"], unit="s", utc=True); df_x15.set_index("time", inplace=True)
    df_x1h = pd.DataFrame(r_xau_1h); df_x1h["time"] = pd.to_datetime(df_x1h["time"], unit="s", utc=True); df_x1h.set_index("time", inplace=True)
    df_e1h = pd.DataFrame(r_eur_1h); df_e1h["time"] = pd.to_datetime(df_e1h["time"], unit="s", utc=True); df_e1h.set_index("time", inplace=True)
    
    trades = []
    
    # --- Lógica XAU ---
    ema50_series = df_x1h["close"].ewm(span=50, adjust=False).mean()
    dates = sorted(set(df_x15.index.date))
    for d in dates:
        if d.weekday() >= 5: continue
        day_df = df_x15[df_x15.index.date == d]
        asian = day_df[(day_df.index.hour >= ASIAN_START_H) & (day_df.index.hour < ASIAN_END_H)]
        if len(asian) < 4: continue
        hi, lo = float(asian["high"].max()), float(asian["low"].min())
        rng = hi - lo
        if rng < XAU_MIN_RANGE or rng > XAU_MAX_RANGE: continue
        
        ema50_today = ema50_series.loc[ema50_series.index.date <= d]
        if ema50_today.empty: continue
        ema50 = ema50_today.iloc[-1]
        
        london = day_df[(day_df.index.hour >= LONDON_START_H) & (day_df.index.hour < LONDON_END_H)]
        for t, candle in london.iterrows():
            c = float(candle["close"])
            if c > hi and c > ema50:
                s, entry, sl, tp = "LONG", c, lo - lo*XAU_SL_BUFFER, c + rng*XAU_TP_MULT; break
            elif c < lo and c < ema50:
                s, entry, sl, tp = "SHORT", c, hi + hi*XAU_SL_BUFFER, c - rng*XAU_TP_MULT; break
        else: continue
        
        rest = day_df[day_df.index > t]
        exit_p, res = entry, "OPEN"
        for _, r in rest.iterrows():
            if s == "LONG":
                if r["low"] <= sl: exit_p, res = sl, "LOSS"; break
                if r["high"] >= tp: exit_p, res = tp, "WIN"; break
            else:
                if r["high"] >= sl: exit_p, res = sl, "LOSS"; break
                if r["low"] <= tp: exit_p, res = tp, "WIN"; break
        pnl_r = (exit_p - entry)/(entry - sl) if s == "LONG" else (entry - exit_p)/(sl - entry)
        trades.append({"time": t, "sym": "XAUUSD", "pnl": CAPITAL * RISK_PCT * pnl_r})

    # --- Lógica EUR ---
    for i in range(40, len(df_e1h)-1, 4):
        window = df_e1h.iloc[:i+1]
        sig = get_eurusd_signal(window)
        if not sig: continue
        s, entry, sl, tp = sig
        next_d = df_e1h.iloc[i+1:i+25] # max 24h
        exit_p, res = entry, "OPEN"
        for t_idx, r in next_d.iterrows():
            if s == "LONG":
                if r["low"] <= sl: exit_p, res = sl, "LOSS"; break
                if r["high"] >= tp: exit_p, res = tp, "WIN"; break
            else:
                if r["high"] >= sl: exit_p, res = sl, "LOSS"; break
                if r["low"] <= tp: exit_p, res = tp, "WIN"; break
        pnl_r = (exit_p - entry)/(entry - sl) if s == "LONG" else (entry - exit_p)/(sl - entry)
        trades.append({"time": window.index[-1], "sym": "EURUSD", "pnl": CAPITAL * RISK_PCT * pnl_r})

    mt5.shutdown()
    return trades

if __name__ == "__main__":
    trades = run_backtest_anual()
    if isinstance(trades, str): print(trades); exit()
    
    df = pd.DataFrame(trades)
    df["time"] = pd.to_datetime(df["time"])
    df["month"] = df["time"].dt.to_period("M")
    
    monthly = df.groupby("month")["pnl"].sum()
    monthly_stats = df.groupby("month").agg(trades=("pnl","count"), pnl=("pnl","sum"))
    monthly_stats["pnl_pct"] = (monthly_stats["pnl"] / CAPITAL) * 100
    
    print(f"\n{'='*60}")
    print(f" REPORTES MENSUALES (365 DIAS) - CAPITAL $50,000")
    print(f"{'='*60}")
    print(monthly_stats)
    
    total_pnl = df["pnl"].sum()
    print(f"\nRESULTADO FINAL:")
    print(f"Beneficio Neto: ${total_pnl:,.2f} ({(total_pnl/CAPITAL)*100:+.2f}%)")
    print(f"Meses en Ganancia: {len(monthly[monthly > 0])}/{len(monthly)}")
    print(f"Mejor Mes: {monthly.idxmax()} (${monthly.max():,.2f})")
    print(f"Peor Mes: {monthly.idxmin()} (${monthly.min():,.2f})")
