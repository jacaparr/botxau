
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
import json
import os

# --- CONFIGURACIÓN DEL BACKTEST ---
CAPITAL = 50000
RISK_PCT = 0.015  # 1.5% como el bot
DAYS = 180
SYMBOLS = ["XAUUSD", "EURUSD"]

# Parámetros Estrategia XAUUSD (Asian Breakout)
ASIAN_START_H = 0
ASIAN_END_H = 6
LONDON_START_H = 7
LONDON_END_H = 10
XAU_MIN_RANGE = 3.0
XAU_MAX_RANGE = 20.0
XAU_TP_MULT = 2.5
XAU_SL_BUFFER = 0.001

# Parámetros Estrategia EURUSD (Mean Reversion)
# Usando lógica de strategy_eurusd.py
import pandas_ta as ta

def get_eurusd_signal(df):
    if len(df) < 35: return None
    bbands = ta.bbands(df['close'], length=20, std=2)
    rsi = ta.rsi(df['close'], length=14)
    adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
    atr = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    if bbands is None or rsi is None or adx_df is None or atr is None: return None
    
    last_bb_l = bbands.iloc[-1, 0]
    last_bb_m = bbands.iloc[-1, 1]
    last_bb_u = bbands.iloc[-1, 2]
    last_rsi = rsi.iloc[-1]
    last_adx = adx_df.iloc[-1, 0]
    last_atr = atr.iloc[-1]
    last_close = df['close'].iloc[-1]
    
    if last_close < last_bb_l and last_rsi < 30 and last_adx < 25:
        return "LONG", last_close, last_close - (last_atr * 1.5), last_bb_m
    if last_close > last_bb_u and last_rsi > 70 and last_adx < 25:
        return "SHORT", last_close, last_close + (last_atr * 1.5), last_bb_m
    return None

def run_xau_backtest(df_15m, df_1h):
    trades = []
    dates = sorted(set(df_15m.index.date))
    for day in dates:
        if pd.Timestamp(day).weekday() >= 5: continue
        day_df = df_15m[df_15m.index.date == day]
        asian = day_df[(day_df.index.hour >= ASIAN_START_H) & (day_df.index.hour < ASIAN_END_H)]
        if len(asian) < 4: continue
        
        hi, lo = float(asian["high"].max()), float(asian["low"].min())
        rng = hi - lo
        if rng < XAU_MIN_RANGE or rng > XAU_MAX_RANGE: continue
        
        # EMA Filter (1h)
        ema50_series = df_1h["close"].ewm(span=50, adjust=False).mean()
        ema50 = ema50_series.loc[ema50_series.index.date <= day].iloc[-1]
        
        london = day_df[(day_df.index.hour >= LONDON_START_H) & (day_df.index.hour < LONDON_END_H)]
        signal = None
        for _, candle in london.iterrows():
            close = float(candle["close"])
            if close > hi and close > ema50:
                signal, entry, sl, tp = "LONG", close, lo - lo*XAU_SL_BUFFER, close + rng*XAU_TP_MULT
                break
            elif close < lo and close < ema50:
                signal, entry, sl, tp = "SHORT", close, hi + hi*XAU_SL_BUFFER, close - rng*XAU_TP_MULT
                break
        
        if signal:
            # Simular rest of day
            rest = day_df[day_df.index > candle.name]
            exit_p, result = entry, "OPEN"
            for _, r in rest.iterrows():
                if signal == "LONG":
                    if r["low"] <= sl: exit_p, result = sl, "LOSS"; break
                    if r["high"] >= tp: exit_p, result = tp, "WIN"; break
                else:
                    if r["high"] >= sl: exit_p, result = sl, "LOSS"; break
                    if r["low"] <= tp: exit_p, result = tp, "WIN"; break
            
            pnl_r = (exit_p - entry)/(entry - sl) if signal == "LONG" else (entry - exit_p)/(sl - entry)
            trades.append({"date": day, "type": signal, "pnl_r": pnl_r, "result": result})
    return trades

def run_eur_backtest(df_h1):
    trades = []
    # Usar una ventana deslizante para simular trades H1
    for i in range(35, len(df_h1)-1):
        window = df_h1.iloc[:i+1]
        res = get_eurusd_signal(window)
        if res:
            sig, entry, sl, tp = res
            # Simular siguiente vela o velas
            next_data = df_h1.iloc[i+1:]
            exit_p, result = entry, "OPEN"
            for _, r in next_data.iterrows():
                if sig == "LONG":
                    if r["low"] <= sl: exit_p, result = sl, "LOSS"; break
                    if r["high"] >= tp: exit_p, result = tp, "WIN"; break
                else:
                    if r["high"] >= sl: exit_p, result = sl, "LOSS"; break
                    if r["low"] <= tp: exit_p, result = tp, "WIN"; break
                # Cierre al final de 24h si no toca
                if (r.name - window.index[-1]).total_seconds() > 86400: break

            pnl_r = (exit_p - entry)/(entry - sl) if sig == "LONG" else (entry - exit_p)/(sl - entry)
            trades.append({"date": window.index[-1].date(), "type": sig, "pnl_r": pnl_r, "result": result})
            # Saltar velas para no duplicar trades en el mismo movimiento
            i += 10 
    return trades

if __name__ == "__main__":
    if not mt5.initialize():
        print("Error MT5")
        exit()
        
    print(f"Iniciando Backtest: 50k Capital, {DAYS} días...")
    utc_to = datetime.now(timezone.utc)
    utc_from = utc_to - timedelta(days=DAYS)
    
    # XAUUSD Data
    r_xau_15 = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_M15, utc_from, utc_to)
    r_xau_1h = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1, utc_from, utc_to)
    df_x_15 = pd.DataFrame(r_xau_15); df_x_15["time"] = pd.to_datetime(df_x_15["time"], unit="s", utc=True); df_x_15.set_index("time", inplace=True)
    df_x_1h = pd.DataFrame(r_xau_1h); df_x_1h["time"] = pd.to_datetime(df_x_1h["time"], unit="s", utc=True); df_x_1h.set_index("time", inplace=True)
    
    # EURUSD Data
    r_eur_1h = mt5.copy_rates_range("EURUSD", mt5.TIMEFRAME_H1, utc_from, utc_to)
    df_e_1h = pd.DataFrame(r_eur_1h); df_e_1h["time"] = pd.to_datetime(df_e_1h["time"], unit="s", utc=True); df_e_1h.set_index("time", inplace=True)
    
    trades_xau = run_xau_backtest(df_x_15, df_x_1h)
    trades_eur = run_eur_backtest(df_e_1h)
    
    def calc_stats(trades, label):
        if not trades: return
        b, w = CAPITAL, 0
        for t in trades:
            b += CAPITAL * RISK_PCT * t["pnl_r"]
            if t["pnl_r"] > 0: w += 1
        print(f"  > {label}: {len(trades)} trades | WR: {w/len(trades)*100:.1f}% | PnL: {(b-CAPITAL)/CAPITAL*100:+.2f}%")

    print("\nDESGLOSE POR SÍMBOLO:")
    calc_stats(trades_xau, "XAUUSD (Asian Breakout)")
    calc_stats(trades_eur, "EURUSD (Mean Reversion)")

    all_trades = trades_xau + trades_eur
    all_trades.sort(key=lambda x: x["date"])
    
    bal = CAPITAL
    max_bal = CAPITAL
    mdd = 0
    wins = 0
    for t in all_trades:
        pnl = CAPITAL * RISK_PCT * t["pnl_r"]
        bal += pnl
        max_bal = max(max_bal, bal)
        dd = (max_bal - bal) / max_bal * 100
        mdd = max(mdd, dd)
        if t["pnl_r"] > 0: wins += 1
        
    print(f"\nRESULTADOS FINALES (6 MESES):")
    print(f"Capital Inicial: ${CAPITAL}")
    print(f"Balance Final: ${bal:.2f}")
    print(f"Profit Total: {(bal-CAPITAL)/CAPITAL*100:+.2f}% (${bal-CAPITAL:,.2f})")
    print(f"Max Drawdown: {mdd:.2f}%")
    print(f"Win Rate: {wins/len(all_trades)*100:.1f}% ({len(all_trades)} trades)")
    
    mt5.shutdown()
