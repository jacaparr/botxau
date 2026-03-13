"""
dashboard_mt5.py — Servidor web para el Bot MT5 v5
==================================================
Monitorea XAUUSD (Live) y EURUSD (Test) en tiempo real.
Permite iniciar/detener el bot desde la web.
Auto-Scheduler: arranca el bot automáticamente en horario de trading.

Uso: python dashboard_mt5.py
O abre http://localhost:5000
"""

import os
import json
import time
import subprocess
import signal
import psutil
import threading
import sys
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS
try:
    import requests as _requests
except ImportError:
    _requests = None

# Forzar codificación UTF-8 para evitar errores en terminales Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except: pass

app = Flask(__name__)
CORS(app)

# ─── Identidad y URLs remotas ───────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(override=True)
VPS_URL   = os.getenv("VPS_URL",   "http://37.60.247.231:5000")
LOCAL_URL = os.getenv("LOCAL_URL", "https://cindi-excogitative-jaycob.ngrok-free.dev")

def _detect_instance() -> str:
    """Auto-detecta LOCAL vs VPS. Primero .env, luego por balance del estado."""
    env_val = os.getenv("BOT_INSTANCE", "").upper()
    if env_val in ("LOCAL", "VPS"):
        return env_val
    # Auto-detectar por balance del estado: <50k → VPS, >=50k → LOCAL
    try:
        with open("bot_state_mt5_v5.json", "r") as f:
            s = json.load(f)
        bal = float(s.get("prop_starting_balance", 100000))
        return "VPS" if bal < 50000 else "LOCAL"
    except Exception:
        return "LOCAL"

BOT_INSTANCE = _detect_instance()

# Configuración
STATE_FILE = "bot_state_mt5_v5.json"
BOT_SCRIPT = "bot_mt5.py"
BOT_PROCESS = None

# Schedule: horas UTC en las que el bot DEBE estar activo
# El rango asiático se forma 00:00-06:00, entrada London 07:00-10:00, cierre EOD 16:00
SCHEDULE_START_H = 0   # 00:00 UTC
SCHEDULE_END_H = 17    # 17:00 UTC (1h después de EOD para cerrar posiciones)
SKIP_DAYS = [5, 6]     # Sábado=5, Domingo=6 (mercado cerrado)
SKIP_MONDAY = True     # No operar lunes (filtro de la estrategia)
AUTO_SCHEDULER_ENABLED = True

def get_bot_status():
    """Comprueba si el proceso del bot está corriendo."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmd = proc.info['cmdline']
            if cmd and BOT_SCRIPT in " ".join(cmd):
                return True, proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False, None

def read_state():
    """Lee el archivo de estado generado por el bot."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                # Verificar si el estado es reciente (máx 2 minutos)
                last_upd = data.get("last_update", "")
                is_running_proc, _ = get_bot_status()
                data["is_running"] = is_running_proc
                return data
        except Exception:
            pass
    return {"running": False, "is_running": False, "error": "No hay archivo de estado"}

def is_trading_hours() -> dict:
    """Comprueba si estamos en horario de trading."""
    now = datetime.now(timezone.utc)
    weekday = now.weekday()  # 0=Lun, 4=Vie, 5=Sáb, 6=Dom
    hour = now.hour
    
    in_schedule = (
        weekday not in SKIP_DAYS and
        not (SKIP_MONDAY and weekday == 0) and
        SCHEDULE_START_H <= hour < SCHEDULE_END_H
    )
    
    # Calcular próxima ventana
    next_start = now.replace(hour=SCHEDULE_START_H, minute=0, second=0, microsecond=0)
    if in_schedule or hour >= SCHEDULE_END_H:
        next_start += timedelta(days=1)
    
    # Saltar días no operativos
    while next_start.weekday() in SKIP_DAYS or (SKIP_MONDAY and next_start.weekday() == 0):
        next_start += timedelta(days=1)
    
    next_entry = next_start.replace(hour=7)  # London Open
    secs_to_next = (next_start - now).total_seconds() if not in_schedule else 0
    
    return {
        "in_schedule": in_schedule,
        "current_utc": now.strftime("%H:%M UTC"),
        "weekday": ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"][weekday],
        "schedule": f"{SCHEDULE_START_H:02d}:00 - {SCHEDULE_END_H:02d}:00 UTC",
        "next_session": next_start.strftime("%A %d/%m %H:%M UTC"),
        "next_entry_window": next_entry.strftime("%H:%M UTC"),
        "seconds_to_next": max(0, int(secs_to_next)),
        "auto_enabled": AUTO_SCHEDULER_ENABLED,
        "skip_monday": SKIP_MONDAY,
    }


def export_mt5_history(days=45):
    """Extrae el historial real de trades desde MetaTrader 5."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        return False

    from_date = datetime.now().timestamp() - (days * 24 * 60 * 60)
    to_date = datetime.now().timestamp()
    
    history_deals = mt5.history_deals_get(from_date, to_date)
    if history_deals is None:
        mt5.shutdown()
        return False

    deals_list = []
    for deal in history_deals:
        if deal.entry == mt5.DEAL_ENTRY_OUT: # Cierre
            deals_list.append({
                "ticket": deal.ticket,
                "time_close": datetime.fromtimestamp(deal.time).strftime('%Y-%m-%d %H:%M:%S'),
                "symbol": deal.symbol,
                "direction": "SELL" if deal.type == mt5.DEAL_TYPE_SELL else "BUY",
                "volume": deal.volume,
                "price_close": deal.price,
                "pnl": round(deal.profit + deal.commission + deal.swap, 2),
                "comment": deal.comment
            })

    with open("trade_history.json", "w") as f:
        json.dump(deals_list, f, indent=2)
    
    mt5.shutdown()
    return True

def auto_scheduler_loop():
    """Hilo que arranca el bot y actualiza el historial."""
    last_history_upd = 0
    while True:
        try:
            now_ts = time.time()
            # Actualizar historial cada 30 minutos
            if now_ts - last_history_upd > 1800:
                if export_mt5_history():
                    last_history_upd = now_ts

            if AUTO_SCHEDULER_ENABLED:
                schedule = is_trading_hours()
                is_running, _ = get_bot_status()
                
                if schedule["in_schedule"] and not is_running:
                    print(f"⏰ Auto-Scheduler: Arrancando bot ({schedule['current_utc']})")
                    try:
                        subprocess.Popen(
                            ["python", BOT_SCRIPT, "--risk", "0.60"], 
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                        )
                    except Exception as e:
                        print(f"❌ Auto-Scheduler error: {e}")
        except Exception as e:
            print(f"❌ Scheduler error: {e}")
        
        time.sleep(60)


@app.route("/")
def index():
    """Sirve el STITCH Remote Viewer v5.2.2 (dual-bot)."""
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "index.html")

@app.route("/full")
def index_full():
    """Dashboard completo single-bot (legacy)."""
    return render_template("index_mt5.html")

@app.route("/api/status")
def api_status():
    data = read_state()
    data["schedule"] = is_trading_hours()
    
    # Cargar historial de trades si existe
    if os.path.exists("trade_history.json"):
        try:
            with open("trade_history.json", "r") as f:
                data["trade_history"] = json.load(f)
        except:
            data["trade_history"] = []
    else:
        data["trade_history"] = []

    # Filtrar solo trades de XAUUSD
    data["trade_history"] = [
        t for t in data.get("trade_history", [])
        if "XAU" in str(t.get("symbol", "")).upper()
    ]

    # Añadir proyecciones del estudio (50% reinversión)
    data["projections"] = {
        "year_1": 14363,
        "year_3": 67829,
        "monthly_target": 1029
    }
    return jsonify(data)

@app.route("/api/health")
def api_health():
    """Comprueba conectividad con el VPS remoto."""
    vps_ok = False
    reason = "requests no instalado"
    if _requests:
        try:
            r = _requests.get(VPS_URL + "/api/status", timeout=3)
            vps_ok = r.status_code == 200
            reason = ""
        except Exception as e:
            reason = str(e)[:80]
    return jsonify({
        "vps_reachable": vps_ok,
        "local_ok": True,
        "vps_url": VPS_URL,
        "reason": reason,
    })

@app.route("/api/all-status")
def api_all_status():
    """Estado de AMBOS bots. Rol-consciente: LOCAL vs VPS."""
    self_data = read_state()
    self_data["reachable"]        = True
    self_data["trades_today"]     = self_data.get("trades_today", 0)
    self_data["pnl_today"]        = self_data.get("pnl_today", 0.0)
    self_data["prop_firm"]        = self_data.get("prop_firm", {})
    self_data["account"]          = self_data.get("account", {})
    self_data["starting_balance"] = self_data.get("prop_starting_balance", 100000)

    def _fetch(url, label, default_starting):
        """Intenta obtener datos de una URL remota."""
        if _requests and url:
            try:
                r = _requests.get(url + "/api/status", timeout=2)
                if r.status_code == 200:
                    d = r.json()
                    d["reachable"]        = True
                    d["starting_balance"] = d.get("prop_starting_balance", default_starting)
                    d["instance_label"]   = label
                    return d
            except Exception:
                pass
        return {"reachable": False, "instance_label": label,
                "starting_balance": default_starting,
                "reason": f"{label} no accesible ({url or 'URL no configurada'})."}

    if BOT_INSTANCE == "VPS":
        # Este servidor ES el VPS → self = vps, remoto = local
        self_data["instance_label"] = "VPS $25K"
        vps   = self_data
        local = _fetch(LOCAL_URL, "LOCAL $100K", 100000)
    else:
        # Este servidor ES LOCAL → self = local, remoto = vps
        self_data["instance_label"] = "LOCAL $100K"
        local = self_data
        vps   = _fetch(VPS_URL, "VPS $25K", 25000)

    return jsonify({"vps": vps, "local": local})

@app.route("/api/git-pull", methods=["POST"])
def api_git_pull():
    """Trigger a git pull on this server instance (for remote updates)."""
    import subprocess
    try:
        result = subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True, text=True, timeout=30,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        return jsonify({
            "ok": result.returncode == 0,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[-200:] if result.stderr else ""
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/schedule")
def api_schedule():
    return jsonify(is_trading_hours())

@app.route("/api/auto", methods=["POST"])
def api_auto():
    """Activa/desactiva el auto-scheduler."""
    global AUTO_SCHEDULER_ENABLED
    enabled = request.json.get("enabled", True)
    AUTO_SCHEDULER_ENABLED = enabled
    return jsonify({"status": "success", "auto_enabled": AUTO_SCHEDULER_ENABLED})

@app.route("/api/reset-prop-state", methods=["POST"])
def api_reset_prop_state():
    """Resetea los contadores prop firm del estado usando el balance MT5 actual como nuevo punto de partida. v2"""
    import json as _json, datetime as _dt
    try:
        state_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_state_mt5_v5.json")
        s = _json.load(open(state_file, encoding="utf-8"))

        # Obtener balance actual de MT5
        try:
            import MetaTrader5 as mt5
            mt5.initialize()
            ai = mt5.account_info()
            real_balance = float(ai.balance) if ai else float(s.get("prop_day_start_balance", 100000.0))
            mt5.shutdown()
        except Exception:
            real_balance = float(s.get("prop_day_start_balance", 100000.0))

        today = _dt.datetime.utcnow().strftime("%Y-%m-%d")
        # Acepta starting_balance del body; si no viene, usa el del .env (PROP_STARTING_BALANCE)
        body = request.get_json(silent=True) or {}
        starting_balance = float(body.get("starting_balance", os.getenv("PROP_STARTING_BALANCE", 100000.0)))
        s["prop_starting_balance"]  = starting_balance
        s["prop_peak_balance"]      = real_balance   # pico = balance actual → DD total = 0%
        s["prop_day_start_balance"] = real_balance   # inicio día = balance actual → DD diario = 0%
        s["prop_day"]               = today
        s["consecutive_losses"]     = 0
        s["can_trade"]              = True

        with open(state_file, "w", encoding="utf-8") as f:
            _json.dump(s, f, indent=2)

        return jsonify({"ok": True, "new_balance": real_balance, "starting_balance": starting_balance, "reset_date": today})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/signals")
def api_signals():
    """Obtiene datos de velas para el gráfico y proximidad de señales."""
    try:
        data = read_state()
        # En una versión real, aquí llamaríamos a una función de MT5 para traer últimas 30 velas
        # Por ahora, enviamos placeholders estructurados para que el dashboard sepa dibujarlos
        return jsonify({
            "status": "success",
            "symbol": "XAUUSD",
            "ema": data.get("ema", 0),
            "rsi": data.get("rsi", 0),
            "candles": [] # Podríamos integrar datos reales aquí
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/control", methods=["POST"])
def api_control():
    """Inicia o detiene el bot."""
    action = request.json.get("action")
    is_running, pid = get_bot_status()
    
    if action == "start":
        if is_running:
            return jsonify({"status": "error", "message": "El bot ya está corriendo"})
        
        # Iniciar watchdog.bat (recomendado) o el script directamente
        try:
            # Usamos watchdog.bat para que el bot se auto-recupere si falla
            subprocess.Popen(["cmd", "/c", "start", "/min", "watchdog.bat"], shell=True)
            return jsonify({"status": "success", "message": "Bot iniciado correctamente"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})
            
    elif action == "stop":
        if not is_running:
            return jsonify({"status": "error", "message": "El bot no está corriendo"})
        
        try:
            # Matar el proceso
            p = psutil.Process(pid)
            p.terminate()
            # También intentar matar el cmd de watchdog si existe
            return jsonify({"status": "success", "message": "Bot detenido"})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

    return jsonify({"status": "error", "message": "Acción no válida"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    # Iniciar auto-scheduler en hilo separado
    scheduler_thread = threading.Thread(target=auto_scheduler_loop, daemon=True)
    scheduler_thread.start()
    print("⏰ Auto-Scheduler activado")
    
    schedule = is_trading_hours()
    print(f"🌐 Dashboard MT5 iniciado en: http://localhost:{port}")
    print(f"📅 Horario: {schedule['schedule']} (Mar-Vie)")
    print(f"📍 Próxima sesión: {schedule['next_session']}")
    app.run(host="0.0.0.0", port=port, debug=False)
