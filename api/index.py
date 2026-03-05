import os
import requests
from flask import Flask, jsonify, request
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

VPS_URL   = os.environ.get("VPS_URL",   "http://37.60.247.231:5000")
LOCAL_URL = os.environ.get("LOCAL_URL", "")   # e.g. http://TU_IP:5000 or ngrok URL
TIMEOUT   = 6

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def fetch_status(url, label):
    """Fetches /api/status from a bot URL. Returns a dict with meta info."""
    if not url:
        return {"instance": label, "reachable": False, "reason": "URL no configurada"}
    try:
        r = requests.get(f"{url}/api/status", timeout=TIMEOUT)
        data = r.json()
        data["instance"]  = label
        data["reachable"] = True
        return data
    except Exception as e:
        return {"instance": label, "reachable": False, "reason": str(e)}

def proxy_get(url, path):
    try:
        r = requests.get(f"{url}{path}", timeout=TIMEOUT)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "url": url}), 502

def proxy_post(url, path):
    try:
        r = requests.post(f"{url}{path}", json=request.json, timeout=TIMEOUT)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 502

# ─────────────────────────────────────────────────────────────
# Endpoints — VPS (legacy, mantiene compatibilidad)
# ─────────────────────────────────────────────────────────────

@app.route('/api/status')
def status():
    return proxy_get(VPS_URL, '/api/status')

@app.route('/api/schedule')
def schedule():
    return proxy_get(VPS_URL, '/api/schedule')

@app.route('/api/signals')
def signals():
    return proxy_get(VPS_URL, '/api/signals')

@app.route('/api/control', methods=['POST'])
def control():
    return proxy_post(VPS_URL, '/api/control')

@app.route('/api/auto', methods=['POST'])
def auto():
    return proxy_post(VPS_URL, '/api/auto')

# ─────────────────────────────────────────────────────────────
# Endpoints — Dual Bot (NUEVO)
# ─────────────────────────────────────────────────────────────

@app.route('/api/all-status')
def all_status():
    """Consulta VPS y LOCAL en paralelo. Devuelve estado de ambos."""
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {
            ex.submit(fetch_status, VPS_URL,   "VPS"):   "vps",
            ex.submit(fetch_status, LOCAL_URL, "LOCAL"): "local",
        }
        results = {}
        for future in as_completed(futures, timeout=TIMEOUT + 1):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                results[key] = {"instance": key.upper(), "reachable": False, "reason": str(e)}
    return jsonify(results)

@app.route('/api/vps-status')
def vps_status():
    return jsonify(fetch_status(VPS_URL, "VPS"))

@app.route('/api/local-status')
def local_status():
    return jsonify(fetch_status(LOCAL_URL, "LOCAL"))

@app.route('/api/health')
def health():
    vps_ok = fetch_status(VPS_URL, "VPS").get("reachable", False)
    return jsonify({"status": "ok", "vps_reachable": vps_ok, "vps": VPS_URL,
                    "local_configured": bool(LOCAL_URL)})
