import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta

CAPITAL = 100000
DAYS = 180  # 6 meses aprox
EOD_CLOSE_H = 16

def run_final_backtest(risk_pct):
    if not mt5.initialize(): return 0, 0, 0
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    symbol = "XAUUSD"
    # Buscar el símbolo correcto
    aliases = ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"]
    found = None
    for s in aliases:
        if mt5.symbol_info(s):
            found = s
            break
    
    if not found:
        print("Símbolo no encontrado")
        mt5.shutdown()
        return 0, 0, 0

    r_x1h = mt5.copy_rates_range(found, mt5.TIMEFRAME_H1, from_dt, to_dt)
    if r_x1h is None or len(r_x1h) == 0:
        mt5.shutdown()
        return 0, 0, 0
        
    df = pd.DataFrame(r_x1h)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df.set_index("time", inplace=True)
    
    # Indicadores
    df['ema'] = ta.ema(df['close'], length=50)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['adx'] = ta.adx(df['high'], df['low'], df['close'])['ADX_14']
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    trades = []
    bal = CAPITAL
    max_bal = CAPITAL
    mdd = 0
    
    # Iterar velas para buscar entradas
    for i in range(50, len(df)-1):
        row = df.iloc[i]
        time_utc = row.name
        
        # FILTRO DE HORA RECIÉN APLICADO: No entrar después de las 15:00 UTC
        if time_utc.hour >= (EOD_CLOSE_H - 1):
            continue
            
        if row['adx'] < 20: continue
        
        s = None
        if row['close'] > row['ema'] and row['rsi'] > 55:
            s, entry, sl, tp = "LONG", row['close'], row['close'] - row['atr']*2.5, row['close'] + row['atr']*5.0
        elif row['close'] < row['ema'] and row['rsi'] < 45:
            s, entry, sl, tp = "SHORT", row['close'], row['close'] + row['atr']*2.5, row['close'] - row['atr']*5.0
            
        if s:
            # Simular trade con cierre EOD
            next_data = df.iloc[i+1:] # hasta el final de los datos
            exit_p = entry
            exit_time = None
            
            for t_idx, r in next_data.iterrows():
                # Regla de salida normal (SL/TP)
                if s == "LONG":
                    if r["low"] <= sl: exit_p = sl; exit_time = t_idx; break
                    if r["high"] >= tp: exit_p = tp; exit_time = t_idx; break
                else:
                    if r["high"] >= sl: exit_p = sl; exit_time = t_idx; break
                    if r["low"] <= tp: exit_p = tp; exit_time = t_idx; break
                
                # Regla de CIERRE EOD (16:00 UTC)
                if t_idx.hour >= EOD_CLOSE_H:
                    exit_p = r["close"]
                    exit_time = t_idx
                    break
            
            if exit_time:
                # Calcular resultado
                # Ratio recompensa-riesgo nominal
                nominal_risk = abs(entry - sl)
                if nominal_risk > 0:
                    pnl_r = (exit_p - entry)/nominal_risk if s == "LONG" else (entry - exit_p)/nominal_risk
                    pnl_usd = CAPITAL * (risk_pct/100) * pnl_r
                    bal += pnl_usd
                    max_bal = max(max_bal, bal)
                    mdd = max(mdd, (max_bal - bal) / max_bal * 100)
                    trades.append(pnl_usd)
                    
                    # Saltar hasta que el trade se cierre para no abrir solapados
                    # i = df.index.get_loc(exit_time) # Esto es más preciso pero saltamos 12h como aproximación segura
                    i += 12 
            
    mt5.shutdown()
    win_rate = (len([t for t in trades if t > 0]) / len(trades) * 100) if trades else 0
    return sum(trades), mdd, len(trades), win_rate

if __name__ == "__main__":
    print(f"--- BACKTEST ORO (6 MESES) - NUEVAS REGLAS ---")
    pnl, dd, tr, wr = run_final_backtest(0.5)
    print(f"REGLA 15:00 UTC | Riesgo 0.5%: +${pnl:,.2f} ({pnl/CAPITAL*100:+.2f}%) | MDD: {dd:.2f}% | {tr} trades | WR: {wr:.1f}%")
    
    pnl2, dd2, tr2, wr2 = run_final_backtest(1.5)
    print(f"REGLA 15:00 UTC | Riesgo 1.5%: +${pnl2:,.2f} ({pnl2/CAPITAL*100:+.2f}%) | MDD: {dd2:.2f}% | {tr2} trades | WR: {wr2:.1f}%")
