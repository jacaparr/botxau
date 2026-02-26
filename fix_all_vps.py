"""
fix_all_vps.py - Ejecuta esto en el VPS para arreglar el bot automaticamente.
Elimina la dependencia de pandas_ta (que no es compatible con Python 3.14)
y la reemplaza con calculos puros de pandas/numpy.

USO EN EL VPS:
  1. Copia este archivo a la carpeta futures-bot (Desktop\\futures-bot\\)
  2. Abre CMD como Administrador
  3. cd C:\\Users\\Administrator\\Desktop\\futures-bot
  4. python fix_all_vps.py
  5. Abre el watchdog.bat
"""

import os, re, sys

BOT_DIR = os.path.dirname(os.path.abspath(__file__))

# ─────────────────────────────────────────────────────────────────────────────
# NUEVO CONTENIDO PARA strategy_eurusd.py
# ─────────────────────────────────────────────────────────────────────────────
STRATEGY_EURUSD = '''"""
strategy_eurusd.py - Estrategia Mean Reversion para EURUSD
Sin pandas_ta - compatible con Python 3.14+
"""
import pandas as pd
import numpy as np

def _rsi(series, length=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(window=length).mean()
    loss  = (-delta.clip(upper=0)).rolling(window=length).mean()
    rs    = gain / loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))

def _atr(high, low, close, length=14):
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(window=length).mean()

def _adx(high, low, close, length=14):
    up   = high.diff()
    down = -low.diff()
    pdm  = pd.Series(0.0, index=high.index)
    mdm  = pd.Series(0.0, index=high.index)
    pdm[(up > down) & (up > 0)]   = up[(up > down) & (up > 0)]
    mdm[(down > up) & (down > 0)] = down[(down > up) & (down > 0)]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr14 = tr.rolling(length).mean()
    pdi   = 100 * pdm.rolling(length).mean() / atr14.replace(0, float("nan"))
    mdi   = 100 * mdm.rolling(length).mean() / atr14.replace(0, float("nan"))
    dx    = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, float("nan"))
    return dx.rolling(length).mean()

def _bbands(series, length=20, std=2.0):
    mid   = series.rolling(window=length).mean()
    sigma = series.rolling(window=length).std(ddof=0)
    return mid - std * sigma, mid, mid + std * sigma

def calculate_indicators(df):
    lo, mid, hi = _bbands(df["close"], 20, 2.0)
    df["bb_lower"] = lo
    df["bb_mid"]   = mid
    df["bb_upper"] = hi
    df["rsi"] = _rsi(df["close"], 14)
    df["adx"] = _adx(df["high"], df["low"], df["close"], 14)
    df["atr"] = _atr(df["high"], df["low"], df["close"], 14)
    return df

def check_signals(df_in):
    if not isinstance(df_in, pd.DataFrame) or len(df_in) < 35:
        return None
    try:
        last = df_in.iloc[-1]
    except Exception:
        return None
    req_cols = ["bb_lower", "bb_upper", "bb_mid", "rsi", "adx", "atr", "close"]
    for col in req_cols:
        if col not in last or pd.isna(last[col]):
            return None
    close, bb_lower, bb_upper, bb_mid = float(last["close"]), float(last["bb_lower"]), float(last["bb_upper"]), float(last["bb_mid"])
    rsi, adx, atr = float(last["rsi"]), float(last["adx"]), float(last["atr"])
    if close < bb_lower and rsi < 30 and adx < 20:
        return ("LONG",  close, close - atr * 1.5, bb_mid)
    if close > bb_upper and rsi > 70 and adx < 20:
        return ("SHORT", close, close + atr * 1.5, bb_mid)
    return None
'''

# ─────────────────────────────────────────────────────────────────────────────
# PARCHE PARA bot_mt5.py: sustituye "import pandas_ta as ta" y todas las
# llamadas a ta.ema / ta.rsi / ta.adx / ta.atr por funciones puras
# ─────────────────────────────────────────────────────────────────────────────
INDICATOR_BLOCK = '''import numpy as np

# --- INDICADORES PUROS (sin pandas_ta) ----------------------------------
def _ema(s, n):     return s.ewm(span=n, adjust=False).mean()
def _rsi(s, n=14):
    d = s.diff(); g = d.clip(lower=0).rolling(n).mean(); l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100/(1 + g/l.replace(0, float("nan")))
def _atr(h, l, c, n=14):
    tr = __import__("pandas").concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()
def _adx(h, l, c, n=14):
    up=h.diff(); dn=-l.diff()
    import pandas as _pd; import numpy as _np
    pdm=_pd.Series(0.0,index=h.index); mdm=_pd.Series(0.0,index=h.index)
    pdm[(up>dn)&(up>0)]=up[(up>dn)&(up>0)]; mdm[(dn>up)&(dn>0)]=dn[(dn>up)&(dn>0)]
    tr=_pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    a=tr.rolling(n).mean(); pi=100*pdm.rolling(n).mean()/a.replace(0,_np.nan); mi=100*mdm.rolling(n).mean()/a.replace(0,_np.nan)
    return (100*(pi-mi).abs()/(pi+mi).replace(0,_np.nan)).rolling(n).mean()
# -------------------------------------------------------------------------
'''

# ─────────────────────────────────────────────────────────────────────────────
def patch_bot_mt5(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Reemplazar la línea de import
    if "import pandas_ta as ta" in content:
        content = content.replace("import pandas_ta as ta", INDICATOR_BLOCK.strip())
        print("  [OK] Eliminado 'import pandas_ta as ta'")
    else:
        print("  [INFO] pandas_ta ya no estaba en el import principal")

    # 2. Reemplazar todas las llamadas a ta.ema / ta.rsi / ta.adx / ta.atr
    replacements = {
        r"ta\.ema\(([^,]+),\s*length=(\d+)\)":
            lambda m: f"_ema({m.group(1)}, {m.group(2)})",
        r"ta\.rsi\(([^,]+),\s*length=(\d+)\)":
            lambda m: f"_rsi({m.group(1)}, {m.group(2)})",
        r"ta\.atr\(([^,]+),\s*([^,]+),\s*([^,]+),\s*length=(\d+)\)":
            lambda m: f"_atr({m.group(1)}, {m.group(2)}, {m.group(3)}, {m.group(4)})",
        r"ta\.adx\(([^,]+),\s*([^,]+),\s*([^\)]+)\)\[.ADX_14.\]":
            lambda m: f"_adx({m.group(1)}, {m.group(2)}, {m.group(3)})",
        r"ta\.adx\(([^,]+),\s*([^,]+),\s*([^\)]+)\)":
            lambda m: f"_adx({m.group(1)}, {m.group(2)}, {m.group(3)})",
    }

    count = 0
    for pattern, repl in replacements.items():
        new_content, n = re.subn(pattern, repl, content)
        if n > 0:
            count += n
            content = new_content

    if count:
        print(f"  [OK] Reemplazadas {count} llamadas ta.xxx por funciones puras")
    else:
        print("  [INFO] No quedan llamadas a ta.xxx (ya estaba limpio)")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  FIX BOT VPS - Eliminando dependencia de pandas_ta")
    print("="*60 + "\n")

    # 1. strategy_eurusd.py
    path_eur = os.path.join(BOT_DIR, "strategy_eurusd.py")
    if os.path.exists(path_eur):
        with open(path_eur, "w", encoding="utf-8") as f:
            f.write(STRATEGY_EURUSD)
        print("[OK] strategy_eurusd.py reescrito sin pandas_ta")
    else:
        print(f"[WARN] No encontrado: {path_eur}")

    # 2. bot_mt5.py
    path_bot = os.path.join(BOT_DIR, "bot_mt5.py")
    if os.path.exists(path_bot):
        print("[...] Parcheando bot_mt5.py ...")
        patch_bot_mt5(path_bot)
        print("[OK] bot_mt5.py actualizado")
    else:
        print(f"[ERROR] No encontrado: {path_bot}")
        print(f"        Asegurate de ejecutar este script DENTRO de la carpeta futures-bot")
        sys.exit(1)

    print("\n" + "="*60)
    print("  TODO LISTO. Ahora abre el watchdog.bat")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
