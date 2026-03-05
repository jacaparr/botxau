import os
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

VPS_URL = os.environ.get("VPS_URL", "http://37.60.247.231:5000")
TIMEOUT = 6

def proxy_get(path):
    try:
        r = requests.get(f"{VPS_URL}{path}", timeout=TIMEOUT)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e), "vps": VPS_URL}), 502

def proxy_post(path):
    try:
        r = requests.post(f"{VPS_URL}{path}", json=request.json, timeout=TIMEOUT)
        return jsonify(r.json())
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 502

@app.route('/api/status')
def status():
    return proxy_get('/api/status')

@app.route('/api/schedule')
def schedule():
    return proxy_get('/api/schedule')

@app.route('/api/signals')
def signals():
    return proxy_get('/api/signals')

@app.route('/api/control', methods=['POST'])
def control():
    return proxy_post('/api/control')

@app.route('/api/auto', methods=['POST'])
def auto():
    return proxy_post('/api/auto')

@app.route('/api/health')
def health():
    try:
        r = requests.get(f"{VPS_URL}/api/status", timeout=3)
        vps_ok = r.status_code == 200
    except:
        vps_ok = False
    return jsonify({"status": "ok", "vps_reachable": vps_ok, "vps": VPS_URL})
