import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timezone, timedelta

CAPITAL = 100000
DAYS = 365
EOD_CLOSE_H = 16
DAILY_DD_LIMIT = 0.04 # 4%
MAX_DD_LIMIT = 0.08   # 8%

def run_safety_audit(risk_pct):
    if not mt5.initialize(): return
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=DAYS)
    
    symbol = "XAUUSD"
    aliases = ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"]
    found = None
    for s in aliases:
        if mt5.symbol_info(s): found = s; break
    if not found: return

    r = mt5.copy_rates_range(found, mt5.TIMEFRAME_H1, from_dt, to_dt)
    df = pd.DataFrame(r); df["time"] = pd.to_datetime(df["time"], unit="s", utc=True); df.set_index("time", inplace=True)
    
    df['ema'] = ta.ema(df['close'], length=50)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['adx'] = ta.adx(df['high'], df['low'], df['close'])['ADX_14']
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    
    bal = CAPITAL
    peak_bal = CAPITAL
    day_start_bal = CAPITAL
    current_day = None
    
    violations_daily = 0
    violations_total = 0
    max_daily_dd = 0
    hit_10_flag = False
    days_to_10 = 0
    
    trades = []
    
    for i in range(50, len(df)-1):
        row = df.iloc[i]
        t = row.name
        
        # Reset diario
        if current_day != t.date():
            current_day = t.date()
            day_start_bal = bal
            
        # Monitorear Drawdown Diario (Estimado por velas, no es perfecto pero da una idea)
        # En un backtest de H1 no vemos el drawdown flotante exacto intra-vela, pero usaremos el SL.
        
        if row.name.hour >= (EOD_CLOSE_H - 1): continue
        if row['adx'] < 20: continue
        
        s = None
        if row['close'] > row['ema'] and row['rsi'] > 55:
            s, entry, sl, tp = "LONG", row['close'], row['close'] - row['atr']*2.5, row['close'] + row['atr']*5.0
        elif row['close'] < row['ema'] and row['rsi'] < 45:
            s, entry, sl, tp = "SHORT", row['close'], row['close'] + row['atr']*2.5, row['close'] - row['atr']*5.0
            
        if s:
            next_data = df.iloc[i+1:]
            exit_p = entry
            exit_time = None
            
            # Verificación de riesgo
            risk_amount = bal * (risk_pct/100)
            
            for t_idx, r in next_data.iterrows():
                # Simular DD flotante (peor caso es el SL)
                # Si el SL > que el margen diario que queda, es una violación potencial
                # Aunque el trade no se cierre, el DD flotante cuenta para el broker.
                
                # Para simplificar: si el SL impacta >4% del balance inicial del día, avisar.
                
                if s == "LONG":
                    if r["low"] <= sl: exit_p = sl; exit_time = t_idx; break
                    if r["high"] >= tp: exit_p = tp; exit_time = t_idx; break
                else:
                    if r["high"] >= sl: exit_p = sl; exit_time = t_idx; break
                    if r["low"] <= tp: exit_p = tp; exit_time = t_idx; break
                
                if t_idx.hour >= EOD_CLOSE_H:
                    exit_p = r["close"]; exit_time = t_idx; break
            
            if exit_time:
                # Resultado
                # PnL real vs riesgo nominal
                pnl_r = (exit_p - entry)/abs(entry - sl) if s == "LONG" else (entry - exit_p)/abs(entry - sl)
                pnl_usd = risk_amount * pnl_r
                
                # Check Daily DD violation during this trade
                # If loss > (day_start_bal * DAILY_DD_LIMIT), violation.
                if pnl_usd < 0 and abs(pnl_usd) > (day_start_bal * DAILY_DD_LIMIT):
                    violations_daily += 1
                
                bal += pnl_usd
                peak_bal = max(peak_bal, bal)
                
                # Max Daily DD tracking
                current_daily_dd = (day_start_bal - bal) / day_start_bal
                max_daily_dd = max(max_daily_dd, current_daily_dd)
                
                if (peak_bal - bal) / peak_bal > MAX_DD_LIMIT:
                    violations_total += 1
                
                # Check if 10% target hit
                if bal >= (CAPITAL * 1.10) and not hit_10_flag:
                    days_to_10 = (exit_time - from_dt).days
                    hit_10_flag = True

                i += 12
                
    mt5.shutdown()
    print(f"--- AUDITORÍA CHALLENGE (Riesgo {risk_pct}%) ---")
    print(f"Resultado Final: ${bal:,.2f} ({((bal-CAPITAL)/CAPITAL*100):+.2f}%)")
    print(f"Max Daily Drawdown: {max_daily_dd*100:.2f}% (Límite 4%)")
    if hit_10_flag:
        print(f"✅ OBJETIVO 10% ALCANZADO en {days_to_10} días")
    else:
        print(f"❌ OBJETIVO 10% NO ALCANZADO en {DAYS} días")
    
    if violations_daily > 0 or max_daily_dd > DAILY_DD_LIMIT:
        print("❌ CUENTA PERDIDA (Violación DD Diario)")
    elif violations_total > 0:
        print("❌ CUENTA PERDIDA (Violación DD Total)")
    else:
        print("✅ CUENTA SOBREVIVIENTE")

if __name__ == "__main__":
    import sys
    # Forzar codificación UTF-8 para evitar errores en terminales Windows
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except: pass

    run_safety_audit(0.15)
    print("\n")
    run_safety_audit(0.12)
