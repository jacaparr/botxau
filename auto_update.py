"""
auto_update.py — Auto-actualizador del bot desde GitHub.
==========================================================
Corre en segundo plano en el VPS.
Cada 30 minutos comprueba si hay nuevos commits en GitHub.
Si los hay, descarga los archivos actualizados y reinicia el bot.

CONFIGURACIÓN (una sola vez):
  Añadir al .env del VPS:
    GITHUB_TOKEN=ghp_XXXXXXXXXXXXXXXXXXXX
    GITHUB_REPO=jacaparr/botxau
    GITHUB_BRANCH=main
"""

import os, ssl, json, subprocess, time, sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ------------------------------------------------------------------
# Configuración
# ------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPO   = os.getenv("GITHUB_REPO", "jacaparr/botxau")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
BOT_DIR       = Path(__file__).parent
STATE_FILE    = BOT_DIR / "autoupdate_state.json"
CHECK_INTERVAL = 30 * 60  # 30 minutos

# Archivos que se actualizan automáticamente (los más críticos)
FILES_TO_UPDATE = [
    # Bot core
    "bot_mt5.py",
    "config.py",
    "strategy_eurusd.py",
    "telegram_notify.py",
    "indicators.py",
    "logger.py",
    "analyze_losses.py",
    # Dashboard
    "dashboard_mt5.py",
    "index.html",
    "requirements.txt",
    "templates/index_mt5.html",
]

# SSL sin verificación (necesario en algunos VPS Windows)
_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"[AutoUpdate {ts}] {msg}", flush=True)


def _api_request(url):
    """Hace una petición a la GitHub API con autenticación."""
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "User-Agent": "BotAutoUpdater/1.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL) as r:
            return json.loads(r.read())
    except Exception as e:
        log(f"❌ Error API: {e}")
        return None


def get_latest_commit_sha():
    """Obtiene el SHA del último commit en GitHub."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/{GITHUB_BRANCH}"
    data = _api_request(url)
    if data and "sha" in data:
        return data["sha"]
    return None


def download_file(filename):
    """Descarga un archivo desde GitHub usando el token."""
    url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{filename}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}", "User-Agent": "BotAutoUpdater/1.0"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
            content = r.read()
            target = BOT_DIR / filename
            target.write_bytes(content)
            log(f"   ✅ {filename} actualizado ({len(content):,} bytes)")
            return True
    except Exception as e:
        log(f"   ❌ Error descargando {filename}: {e}")
        return False


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_sha": None}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def restart_bot():
    """Mata todos los procesos python y relanza el dashboard actualizado."""
    log("🔄 Reiniciando bot y dashboard...")
    try:
        # Matar todos los procesos Python (bot + dashboard)
        subprocess.run(
            ["taskkill", "/F", "/IM", "python.exe"],
            capture_output=True, text=True
        )
        log("   ✅ Procesos Python detenidos")
        time.sleep(2)

        # Relanzar dashboard_mt5.py en background
        dashboard = BOT_DIR / "dashboard_mt5.py"
        if dashboard.exists():
            subprocess.Popen(
                ["python", str(dashboard)],
                cwd=str(BOT_DIR),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            log("   ✅ Dashboard relanzado en puerto 5000")
        else:
            log("   ⚠️ dashboard_mt5.py no encontrado")

        log("   ✅ watchdog reiniciará bot_mt5.py automáticamente")
    except Exception as e:
        log(f"   ⚠️ Error al reiniciar: {e}")


def check_and_update():
    """Comprueba si hay actualizaciones y las aplica."""
    if not GITHUB_TOKEN:
        log("⚠️ GITHUB_TOKEN no configurado. Saltando comprobación.")
        return False

    state = load_state()
    latest_sha = get_latest_commit_sha()

    if not latest_sha:
        log("⚠️ No se pudo obtener el SHA de GitHub.")
        return False

    if latest_sha == state.get("last_sha"):
        log(f"✔️ Sin cambios (SHA: {latest_sha[:8]}...)")
        return False

    log(f"🆕 Nuevo commit detectado: {latest_sha[:8]}...")
    log(f"   Anterior SHA: {(state.get('last_sha') or 'ninguno')[:8]}...")
    log("   Descargando archivos actualizados...")

    updated = 0
    for fname in FILES_TO_UPDATE:
        if download_file(fname):
            updated += 1

    log(f"\n   📦 {updated}/{len(FILES_TO_UPDATE)} archivos actualizados.")

    if updated > 0:
        state["last_sha"] = latest_sha
        state["last_update"] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        restart_bot()

    return updated > 0


def main():
    log("🚀 Auto-updater iniciado.")
    log(f"   Repo: {GITHUB_REPO} | Branch: {GITHUB_BRANCH}")
    log(f"   Intervalo de comprobación: {CHECK_INTERVAL // 60} minutos")
    log(f"   Archivos monitorizados: {', '.join(FILES_TO_UPDATE)}")

    # Comprobación inicial al arrancar
    log("\n⏩ Comprobación inicial al arranque...")
    check_and_update()

    while True:
        log(f"\n⏳ Esperando {CHECK_INTERVAL // 60} min. para el siguiente check...")
        time.sleep(CHECK_INTERVAL)
        check_and_update()


if __name__ == "__main__":
    main()
