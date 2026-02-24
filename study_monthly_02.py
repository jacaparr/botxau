
import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta

CAPITAL = 100000
RISK_PCT = 0.2  # El riesgo solicitado para la cuenta de fondeo
DAYS = 365

def run_indicator_monthly_detail():
    if not mt5.initialize(): 
        print("Error inicializando MT5")
        return
    
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    symbol = "XAUUSD" # O alias si es necesario
    for s in ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"]:
        if mt5.symbol_info(s):
            symbol = s
            break
            
    print(f"Descargando datos para {symbol}...")
    r_x1h = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, from_dt, to_dt)
    if r_x1h is None or len(r_x1h) == 0:
        print("No se pudieron descargar datos.")
        mt5.shutdown()
        return
        
    df = pd.DataFrame(r_x1h)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_localize(None)
    df.set_index("time", inplace=True)
    
    # Indicadores
    df['ema'] = ta.ema(df['close'], length=50)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['adx'] = ta.adx(df['high'], df['low'], df['close'])['ADX_14']
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    trades = []
    current_balance = CAPITAL
    
    for i in range(50, len(df)-1):
        row = df.iloc[i]
        if row['adx'] < 20: continue
        
        s_type = None
        if row['close'] > row['ema'] and row['rsi'] > 55:
            s_type, entry, sl, tp = "LONG", row['close'], row['close'] - row['atr']*2.5, row['close'] + row['atr']*5.0
        elif row['close'] < row['ema'] and row['rsi'] < 45:
            s_type, entry, sl, tp = "SHORT", row['close'], row['close'] + row['atr']*2.5, row['close'] - row['atr']*5.0
            
        if s_type:
            # Simular trade (max 48h)
            next_data = df.iloc[i+1:min(i+49, len(df))]
            exit_p = entry
            result = "TP"
            for _, r in next_data.iterrows():
                if s_type == "LONG":
                    if r["low"] <= sl: 
                        exit_p = sl
                        result = "SL"
                        break
                    if r["high"] >= tp: 
                        exit_p = tp
                        result = "TP"
                        break
                else:
                    if r["high"] >= sl: 
                        exit_p = sl
                        result = "SL"
                        break
                    if r["low"] <= tp: 
                        exit_p = tp
                        result = "TP"
                        break
            
            pnl_r = (exit_p - entry)/(entry - sl) if s_type == "LONG" else (entry - exit_p)/(sl - entry)
            pnl_usd = CAPITAL * (RISK_PCT/100) * pnl_r
            trades.append({
                "date": row.name,
                "month": row.name.strftime("%Y-%m"),
                "pnl": pnl_usd,
                "result": result
            })
            # Saltar velas para no solapar señales en el mismo movimiento
            i += 12
    
    if not trades:
        print("No se encontraron trades.")
        mt5.shutdown()
        return

    df_res = pd.DataFrame(trades)
    
    # Agrupar por mes
    monthly = df_res.groupby("month").agg(
        Profit_USD=('pnl', 'sum'),
        Trades=('pnl', 'count'),
        Wins=('result', lambda x: (x == 'TP').sum()),
        Losses=('result', lambda x: (x == 'SL').sum())
    )
    
    monthly["Win_Rate"] = (monthly["Wins"] / monthly["Trades"] * 100).round(1).astype(str) + "%"
    monthly["ROI_%"] = (monthly["Profit_USD"] / CAPITAL * 100).round(2).astype(str) + "%"
    
    print("\n" + "="*70)
    print(f"ESTUDIO MENSUAL: ESTRATEGIA POTENTE (ORO) - RIESGO {RISK_PCT}%")
    print("="*70)
    print(monthly.to_string())
    print("="*70)
    print(f"BENEIFICO TOTAL ANUAL: ${monthly['Profit_USD'].sum():,.2f} ({(monthly['Profit_USD'].sum()/CAPITAL*100):.2f}%)")
    print(f"PROMEDIO MENSUAL: ${monthly['Profit_USD'].mean():,.2f}")
    
    mt5.shutdown()

if __name__ == "__main__":
    run_indicator_monthly_detail()
