"""
backtest_eurusd_v2.py — Validador de Estrategia Mean Reversion
=============================================================
Descarga datos reales de MT5 y prueba la nueva estrategia de EURUSD.
"""

import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
import strategy_eurusd as strategy
import logger

# Configuración
SYMBOL = "EURUSD"
TIMEFRAME = mt5.TIMEFRAME_H1  # 1 Hora para Mean Reversion
CAPITAL = 100000
RISK_PCT = 1.0
DAYS_BACK = 365

import traceback

def run_backtest():
    try:
        if not mt5.initialize():
            print("[ERROR] MT5 debe estar abierto")
            return

        print(f"Descargando {DAYS_BACK} dias de {SYMBOL} ({TIMEFRAME})...")
        rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 24 * DAYS_BACK)
        if rates is None or len(rates) == 0:
            print("[ERROR] No se pudieron descargar datos")
            return

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        
        # Calcular indicadores
        df = strategy.calculate_indicators(df)
        
        # Limpiar NaNs iniciales generados por indicadores
        df.dropna(inplace=True)
        
        trades = []
        in_position = False
        
        print(f"Ejecutando simulacion en {len(df)} velas...")
        
        for i in range(len(df)):
            current_data = df.iloc[:i+1]
            row = df.iloc[i]
            
            if not in_position:
                # Buscar señal
                try:
                    res = strategy.check_signals(current_data)
                    if res:
                        # DEBUG
                        if not isinstance(res, tuple):
                            print(f"[DEBUG] res is NOT tuple: {type(res)} -> {res}")
                        
                        sig, entry, sl, tp = res
                        in_position = {
                            'side': sig,
                            'entry': entry,
                            'sl': sl,
                            'tp': tp,
                            'entry_time': df.index[i]
                        }
                except Exception as e:
                    print(f"[DEBUG] Error checking signals at i={i}: {e}")
                    raise e
            else:
                # Gestionar posición
                try:
                    pos = in_position
                    if not isinstance(pos, dict):
                        print(f"[DEBUG] pos is NOT dict: {type(pos)} -> {pos}")
                        
                    high = row['high']
                    low = row['low']
                    
                    # Verificar SL/TP
                    hit_sl = (pos['side'] == 'LONG' and low <= pos['sl']) or (pos['side'] == 'SHORT' and high >= pos['sl'])
                    hit_tp = (pos['side'] == 'LONG' and high >= pos['tp']) or (pos['side'] == 'SHORT' and low <= pos['tp'])
                    
                    if hit_sl or hit_tp:
                        result = "WIN" if hit_tp else "LOSS"
                        pnl = (RISK_PCT if result == "WIN" else -1.0) # Simplificado a R:R
                        trades.append({
                            'entry_time': pos['entry_time'],
                            'exit_time': df.index[i],
                            'side': pos['side'],
                            'result': result,
                            'pnl_r': pnl
                        })
                        in_position = False
                except Exception as e:
                    print(f"[DEBUG] Error managing position at i={i}: {e}")
                    raise e

        # Resultados
        if not trades:
            print("⚠️ No se generaron trades.")
            return

        df_trades = pd.DataFrame(trades)
        wins = len(df_trades[df_trades['result'] == "WIN"])
        losses = len(df_trades[df_trades['result'] == "LOSS"])
        wr = (wins / len(trades)) * 100
        total_r = df_trades['pnl_r'].sum()
        
        pnl_usd = total_r * (CAPITAL * RISK_PCT / 100)
        
        print("\n" + "="*50)
        print(f"RESULTADOS EURUSD (MEAN REVERSION)")
        print("="*50)
        print(f"Periodo:      {DAYS_BACK} días")
        print(f"Total Trades: {len(trades)}")
        print(f"Win Rate:     {wr:.1f}%")
        print(f"Total R:      {total_r:+.2f}R")
        print(f"PnL Est ($):  ${pnl_usd:+,.2f}")
        print("="*50)

    except Exception as e:
        print(f"[ERROR] Error en backtest: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    run_backtest()
    mt5.shutdown()
