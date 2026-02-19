"""
dashboard.py — Servidor web para visualizar el bot en tiempo real
Ejecuta: python dashboard.py
Luego abre: http://localhost:5000
"""

import json
import csv
import os
import threading
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, Response

from binance.client import Client
import config

app = Flask(__name__)

# Cliente público Binance (sin auth)
public_client = Client("", "")

# ─────────────────────────────────────────────────────────────────────────────
# ESTADO COMPARTIDO (actualizado por paper_trade.py via archivo JSON)
# ─────────────────────────────────────────────────────────────────────────────
STATE_FILE = "bot_state.json"

def read_state() -> dict:
    """Lee el estado del bot desde el archivo JSON."""
    if not os.path.exists(STATE_FILE):
        return {
            "balance": 10000.0,
            "initial_capital": 10000.0,
            "positions": {},
            "running": False,
            "last_update": "—",
        }
    with open(STATE_FILE, "r") as f:
        return json.load(f)

def read_trades() -> list[dict]:
    """Lee el historial de trades desde el CSV."""
    trades = []
    if os.path.exists("paper_trades.csv"):
        with open("paper_trades.csv", "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trades.append(row)
    return list(reversed(trades))  # Más recientes primero

def get_market_prices() -> dict:
    """Obtiene precios actuales de todos los pares (API pública)."""
    prices = {}
    for symbol in config.SYMBOLS:
        try:
            ticker = public_client.futures_symbol_ticker(symbol=symbol)
            prices[symbol] = float(ticker["price"])
        except Exception:
            prices[symbol] = 0.0
    return prices

def get_funding_rates() -> dict:
    """Obtiene el funding rate de todos los pares (API pública)."""
    rates = {}
    for symbol in config.SYMBOLS:
        try:
            data = public_client.futures_funding_rate(symbol=symbol, limit=1)
            rates[symbol] = float(data[-1]["fundingRate"]) * 100 if data else 0.0
        except Exception:
            rates[symbol] = 0.0
    return rates

def get_signal_proximity() -> list[dict]:
    """
    Para cada par, calcula los indicadores actuales y devuelve
    qué tan cerca está cada uno de generar una señal (0-100%).
    """
    import pandas as pd
    from indicators import add_indicators, get_last_signal_data
    from config import get_symbol_config

    result = []
    for symbol in config.SYMBOLS:
        try:
            raw = public_client.futures_klines(symbol=symbol, interval=config.TIMEFRAME, limit=200)
            df = pd.DataFrame(raw, columns=[
                "timestamp","open","high","low","close","volume",
                "close_time","quote_volume","trades","taker_buy_base","taker_buy_quote","ignore"
            ])
            df = df[["timestamp","open","high","low","close","volume"]].copy()
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            for col in ["open","high","low","close","volume"]:
                df[col] = df[col].astype(float)
            df.set_index("timestamp", inplace=True)

            df = add_indicators(df)
            data = get_last_signal_data(df)
            cfg  = get_symbol_config(symbol)

            rsi    = data["rsi"]
            adx    = data["adx"]
            volume = data["volume"]
            vol_ma = data["vol_ma"]
            ema_cross = data["ema_cross"]  # +1 bull, -1 bear, 0 none

            # ── Funding Rate ────────────────────────────────────────────
            try:
                fr_data = public_client.futures_funding_rate(symbol=symbol, limit=1)
                funding_rate = float(fr_data[-1]["fundingRate"]) * 100 if fr_data else 0.0
            except Exception:
                funding_rate = 0.0

            # ── Proximidad LONG (0-100 cada indicador) ──────────────────
            # RSI: qué tan cerca está de rsi_long (umbral)
            rsi_long_score  = min(100, max(0, (rsi - 40) / (cfg["rsi_long"] - 40) * 100))
            rsi_short_score = min(100, max(0, (60 - rsi) / (60 - cfg["rsi_short"]) * 100))

            # ADX: qué tan cerca está del mínimo requerido
            adx_score = min(100, max(0, adx / cfg["adx_min"] * 100))

            # Volumen: porcentaje respecto a la media
            vol_score = min(100, max(0, (volume / vol_ma) * 100)) if vol_ma > 0 else 0

            # EMA: +1 = cruce alcista, -1 = bajista, 0 = sin cruce
            ema_status = "bull" if ema_cross >= 1 else ("bear" if ema_cross <= -1 else "flat")

            # Score global LONG (todos los filtros deben cumplirse)
            long_score = (
                (rsi_long_score  * 0.30) +
                (adx_score       * 0.35) +
                (vol_score       * 0.20) +
                (50 if ema_status == "bull" else 0) * 0.15
            )
            short_score = (
                (rsi_short_score * 0.30) +
                (adx_score       * 0.35) +
                (vol_score       * 0.20) +
                (50 if ema_status == "bear" else 0) * 0.15
            )

            result.append({
                "symbol":        symbol,
                "rsi":           round(rsi, 1),
                "rsi_long_thr":  cfg["rsi_long"],
                "rsi_short_thr": cfg["rsi_short"],
                "adx":           round(adx, 1),
                "adx_min":       cfg["adx_min"],
                "vol_ratio":     round(volume / vol_ma * 100, 0) if vol_ma > 0 else 0,
                "ema_status":    ema_status,
                "funding_rate":  round(funding_rate, 4),
                "long_score":    round(long_score, 0),
                "short_score":   round(short_score, 0),
                "signal":        "LONG" if ema_cross >= 1 and rsi > cfg["rsi_long"] and adx > cfg["adx_min"]
                                 else ("SHORT" if ema_cross <= -1 and rsi < cfg["rsi_short"] and adx > cfg["adx_min"]
                                 else None),
            })
        except Exception as e:
            result.append({"symbol": symbol, "error": str(e)})
    return result

# ─────────────────────────────────────────────────────────────────────────────
# API ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", symbols=config.SYMBOLS)

@app.route("/api/status")
def api_status():
    state  = read_state()
    trades = read_trades()
    wins   = [t for t in trades if t.get("result") == "WIN"]
    losses = [t for t in trades if t.get("result") == "LOSS"]
    total_pnl = sum(float(t.get("pnl", 0)) for t in trades)
    win_rate  = (len(wins) / len(trades) * 100) if trades else 0

    return jsonify({
        "balance":         round(state.get("balance", 10000), 2),
        "initial_capital": round(state.get("initial_capital", 10000), 2),
        "pnl":             round(total_pnl, 2),
        "pnl_pct":         round((state.get("balance", 10000) / state.get("initial_capital", 10000) - 1) * 100, 2),
        "total_trades":    len(trades),
        "wins":            len(wins),
        "losses":          len(losses),
        "win_rate":        round(win_rate, 1),
        "open_positions":  state.get("positions", {}),
        "running":         state.get("running", False),
        "last_update":     state.get("last_update", "—"),
    })

@app.route("/api/trades")
def api_trades():
    return jsonify(read_trades()[:50])  # Últimos 50

@app.route("/api/market")
def api_market():
    prices = get_market_prices()
    rates  = get_funding_rates()
    result = []
    for symbol in config.SYMBOLS:
        result.append({
            "symbol":       symbol,
            "price":        prices.get(symbol, 0),
            "funding_rate": round(rates.get(symbol, 0), 4),
        })
    return jsonify(result)

@app.route("/api/equity")
def api_equity():
    """Curva de equity basada en los trades."""
    trades = list(reversed(read_trades()))  # Cronológico
    state  = read_state()
    capital = state.get("initial_capital", 10000)
    curve = [{"time": "Inicio", "equity": capital}]
    running = capital
    for t in trades:
        running += float(t.get("pnl", 0))
        curve.append({
            "time":   t.get("closed_at", ""),
            "equity": round(running, 2),
        })
    return jsonify(curve)

@app.route("/api/signals")
def api_signals():
    """Proximidad de cada par a generar una señal de trading."""
    return jsonify(get_signal_proximity())

@app.route("/api/config")
def api_config():
    """Devuelve la configuración activa del bot (timeframe, pares, etc.)."""
    return jsonify({
        "timeframe": config.TIMEFRAME,
        "symbols":   config.SYMBOLS,
        "leverage":  config.LEVERAGE,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🌐 Dashboard iniciado en: http://localhost:{port}")
    print("   Presiona Ctrl+C para detener.\n")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
