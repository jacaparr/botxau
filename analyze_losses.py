"""
analyze_losses.py — Estudio profundo de operaciones perdedoras con indicadores.

Este script analiza el trade_history.csv y calcula los indicadores del mercado
en el MOMENTO de cada entrada (EMA50, RSI14, ADX14, ATR14, hora, sesión) para
identificar en qué condiciones el bot falla más y qué filtros añadir.

Uso: python analyze_losses.py
(Requiere MT5 activo para obtener datos de precios históricos)
"""
import MetaTrader5 as mt5
import pandas as pd
import csv
from pathlib import Path
from datetime import datetime, timezone, timedelta

TRADE_HISTORY_FILE = "trade_history.csv"

def _ema(s, n): return s.ewm(span=n, adjust=False).mean()
def _rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).rolling(n).mean(); l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - (100 / (1 + g / l.replace(0, float('nan'))))
def _atr(h, l, c, n=14):
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()
def _adx(h, l, c, n=14):
    up = h.diff(); dn = -l.diff()
    pdm = pd.Series(0.0, index=h.index); mdm = pd.Series(0.0, index=h.index)
    pdm[(up>dn)&(up>0)] = up[(up>dn)&(up>0)]; mdm[(dn>up)&(dn>0)] = dn[(dn>up)&(dn>0)]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(n).mean()
    pdi = 100*pdm.rolling(n).mean()/atr.replace(0,float('nan'))
    mdi = 100*mdm.rolling(n).mean()/atr.replace(0,float('nan'))
    dx = 100*(pdi-mdi).abs()/(pdi+mdi).replace(0,float('nan'))
    return dx.rolling(n).mean()

def get_session(hour_utc):
    if 0 <= hour_utc < 7: return "Asiática"
    elif 7 <= hour_utc < 12: return "Londres"
    elif 12 <= hour_utc < 16: return "NY"
    else: return "Tarde/Cierre"

def load_unique_trades():
    if not Path(TRADE_HISTORY_FILE).exists():
        return []
    seen = {}
    with open(TRADE_HISTORY_FILE, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            t = str(row.get("ticket",""))
            if t and t not in seen:
                seen[t] = row
    return list(seen.values())

def get_indicators_at_entry(symbol, time_open_str):
    """Obtiene los indicadores H1 en el momento de apertura del trade."""
    try:
        dt = datetime.fromisoformat(time_open_str)
        # Pedir 120 velas antes de la entrada
        rates = mt5.copy_rates_from(symbol, mt5.TIMEFRAME_H1, dt, 120)
        if rates is None or len(rates) < 50:
            return None
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df.set_index("time", inplace=True)
        df["ema"] = _ema(df["close"], 50)
        df["rsi"] = _rsi(df["close"])
        df["adx"] = _adx(df["high"], df["low"], df["close"])
        df["atr"] = _atr(df["high"], df["low"], df["close"])
        last = df.iloc[-1]
        return {
            "ema": round(float(last["ema"]), 5),
            "rsi": round(float(last["rsi"]), 1),
            "adx": round(float(last["adx"]), 1),
            "atr": round(float(last["atr"]), 5),
            "close": round(float(last["close"]), 5),
            "above_ema": float(last["close"]) > float(last["ema"]),
        }
    except Exception as e:
        return None

def main():
    if not mt5.initialize():
        print("❌ MT5 no disponible. Ejecuta con MT5 activo.")
        return

    trades = load_unique_trades()
    if not trades:
        print("❌ No se encontraron trades en trade_history.csv")
        mt5.shutdown()
        return

    print(f"\n📊 ANÁLISIS PROFUNDO DE {len(trades)} OPERACIONES")
    print("=" * 110)
    
    results = []
    aliases = {
        "AUDUSD": ["AUDUSD", "AUDUSDm"],
        "EURUSD": ["EURUSD", "EURUSDm"],
        "GBPUSD": ["GBPUSD", "GBPUSDm"],
        "USDCAD": ["USDCAD", "USDCADm"],
        "USDCHF": ["USDCHF", "USDCHFm"],
        "USDJPY": ["USDJPY", "USDJPYm"],
        "XAUUSD": ["XAUUSD", "XAUUSDm", "GOLD"],
        "XAGUSD": ["XAGUSD", "XAGUSDm", "SILVER"],
    }

    for t in trades:
        symbol = str(t.get("symbol",""))
        time_open = str(t.get("time_open",""))
        pnl = float(t.get("pnl") or 0)
        direction = str(t.get("direction",""))
        
        if not time_open or not symbol:
            continue
        
        # Buscar el símbolo correcto en MT5
        mt5_symbol = symbol
        for base, alts in aliases.items():
            if symbol.upper().startswith(base[:4]):
                for a in alts:
                    if mt5.symbol_info(a):
                        mt5_symbol = a
                        break
                break
        
        inds = get_indicators_at_entry(mt5_symbol, time_open)
        try:
            dt = datetime.fromisoformat(time_open)
            hour_utc = dt.hour
            session = get_session(hour_utc)
        except:
            hour_utc = -1
            session = "?"
        
        result = {
            **t,
            "pnl": pnl,
            "hour_utc": hour_utc,
            "session": session,
        }
        if inds:
            result.update(inds)
        results.append(result)
    
    df = pd.DataFrame(results)
    
    print(f"\n{'Sym':<8} {'Dir':<6} {'PnL':>9}  {'Session':<12} {'H':>3}  {'RSI':>6}  {'ADX':>6}  {'AbEMA'}")
    print("-" * 75)
    for _, r in df.iterrows():
        pnl = r["pnl"]
        marker = "✅" if pnl > 0 else "❌"
        rsi = f"{r['rsi']:.1f}" if "rsi" in r and pd.notna(r.get("rsi")) else "  N/A"
        adx = f"{r['adx']:.1f}" if "adx" in r and pd.notna(r.get("adx")) else "  N/A"
        above = "Sí" if r.get("above_ema") else "No"
        print(f"{str(r['symbol']):<8} {str(r['direction']):<6} {pnl:>9.2f}  {marker}  {str(r['session']):<12} {int(r.get('hour_utc',-1)):>3}h  {rsi:>6}  {adx:>6}  {above}")
    
    print("\n" + "=" * 110)
    print("\n🔍 ESTADÍSTICAS POR CONDICIÓN:")
    
    wins = df[df["pnl"] > 0]
    losses = df[df["pnl"] <= 0]
    print(f"\n  Total trades: {len(df)} | Wins: {len(wins)} ({100*len(wins)/len(df):.0f}%) | Losses: {len(losses)}")
    print(f"  PnL Total: {df['pnl'].sum():.2f} | Avg Win: {wins['pnl'].mean():.2f} | Avg Loss: {losses['pnl'].mean():.2f}")
    
    if "session" in df.columns:
        print("\n  POR SESIÓN:")
        session_stats = df.groupby("session")["pnl"].agg(["count","sum","mean"])
        for sess, row in session_stats.iterrows():
            print(f"    {sess:<15} trades={int(row['count']):>3}  PnL={row['sum']:>9.2f}  Media={row['mean']:>7.2f}")
    
    if "adx" in df.columns:
        df_adx = df.dropna(subset=["adx"])
        if len(df_adx) > 0:
            low_adx  = df_adx[df_adx["adx"] < 20]
            med_adx  = df_adx[(df_adx["adx"] >= 20) & (df_adx["adx"] < 30)]
            high_adx = df_adx[df_adx["adx"] >= 30]
            print(f"\n  POR ADX:")
            print(f"    ADX < 20 (rango sin tendencia): trades={len(low_adx):>3}  PnL={low_adx['pnl'].sum():>9.2f}")
            print(f"    ADX 20-30 (tendencia débil):    trades={len(med_adx):>3}  PnL={med_adx['pnl'].sum():>9.2f}")
            print(f"    ADX > 30 (tendencia fuerte):    trades={len(high_adx):>3}  PnL={high_adx['pnl'].sum():>9.2f}")
    
    print("\n  PROBLEMA CORRELACIÓN USD: Trades compra vs venta USD simultáneos:")
    usd_buy  = df[df["symbol"].str.contains("USD") & (df["direction"]=="LONG")]
    usd_sell = df[df["symbol"].str.contains("USD") & (df["direction"]=="SHORT")]
    same_day_groups = df.groupby(df["time_open"].str[:10]).apply(lambda g: {
        "has_long": any(g["direction"]=="LONG"),
        "has_short": any(g["direction"]=="SHORT"),
        "pnl": g["pnl"].sum()
    })
    conflict_days = {k: v for k,v in same_day_groups.items() if v["has_long"] and v["has_short"]}
    print(f"    Días con posiciones LONG+SHORT simultáneas: {len(conflict_days)}")
    for day, info in conflict_days.items():
        print(f"    {day}  PnL del día={info['pnl']:>9.2f}")
    
    mt5.shutdown()
    print("\n✅ Análisis completado.")

if __name__ == "__main__":
    main()
