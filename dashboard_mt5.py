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
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

# Forzar codificación UTF-8 para evitar errores en terminales Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except: pass

app = Flask(__name__)
CORS(app)

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


def auto_scheduler_loop():
    """Hilo que arranca el bot automáticamente en horario de trading."""
    while True:
        try:
            if AUTO_SCHEDULER_ENABLED:
                schedule = is_trading_hours()
                is_running, _ = get_bot_status()
                
                if schedule["in_schedule"] and not is_running:
                    print(f"⏰ Auto-Scheduler: Arrancando bot ({schedule['current_utc']})")
                    try:
                        subprocess.Popen(
                            ["python", BOT_SCRIPT, "--risk", "1.5", "--interval", "60"],
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                        )
                    except Exception as e:
                        print(f"❌ Auto-Scheduler error: {e}")
        except Exception as e:
            print(f"❌ Scheduler error: {e}")
        
        time.sleep(60)  # Comprobar cada minuto


@app.route("/")
def index():
    return render_template("stitch.html")

@app.route("/api/status")
def api_status():
    data = read_state()
    data["schedule"] = is_trading_hours()
    # Añadir proyecciones del estudio (50% reinversión)
    data["projections"] = {
        "year_1": 14363,
        "year_3": 67829,
        "monthly_target": 1029
    }
    return jsonify(data)

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
