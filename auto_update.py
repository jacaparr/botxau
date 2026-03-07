"""
auto_update.py — Auto-actualizador del bot desde GitHub.
==========================================================
Corre en segundo plano en el VPS.
Cada 30 minutos comprueba si hay nuevos commits en GitHub.
Si los hay, hace git pull y reinicia el bot.

No necesita GITHUB_TOKEN — usa git pull directamente.
"""

import os, ssl, json, subprocess, time, sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GITHUB_REPO   = os.getenv("GITHUB_REPO", "jacaparr/botxau")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
BOT_DIR       = Path(__file__).parent
STATE_FILE    = BOT_DIR / "autoupdate_state.json"
CHECK_INTERVAL = 10 * 60  # 10 minutos

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"[AutoUpdate {ts}] {msg}", flush=True)


def get_remote_sha() -> str:
    """Obtiene el SHA del ultimo commit remoto via GitHub API (sin token, repo publico)."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/{GITHUB_BRANCH}"
    headers = {"User-Agent": "BotAutoUpdater/1.0", "Accept": "application/vnd.github.v3+json"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15, context=_SSL) as r:
            data = json.loads(r.read())
            return data.get("sha", "")
    except Exception as e:
        log(f"⚠️ Error al consultar GitHub API: {e}")
        return ""


def get_local_sha() -> str:
    """Obtiene el SHA del commit local actual."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=str(BOT_DIR)
        )
        return r.stdout.strip()
    except Exception:
        return ""


def git_pull() -> bool:
    """Ejecuta git pull en el directorio del bot."""
    try:
        # Descartar cambios en archivos de runtime para evitar conflictos
        for runtime_file in ["trade_history.csv", "autoupdate_state.json", "bot_state_mt5_v5.json"]:
            subprocess.run(
                ["git", "checkout", "--", runtime_file],
                capture_output=True, cwd=str(BOT_DIR)
            )
        r = subprocess.run(
            ["git", "pull", "origin", GITHUB_BRANCH],
            capture_output=True, text=True, timeout=30, cwd=str(BOT_DIR)
        )
        if r.returncode == 0:
            log(f"✅ git pull OK: {r.stdout.strip()[:120]}")
            return True
        else:
            log(f"❌ git pull error: {r.stderr.strip()[:120]}")
            return False
    except Exception as e:
        log(f"❌ git pull exception: {e}")
        return False


def restart_bot():
    """Reinicia bot, dashboard y auto_update."""
    log("🔄 Reiniciando procesos...")
    try:
        subprocess.run(["taskkill", "/F", "/IM", "python.exe"], capture_output=True)
        time.sleep(2)
        log("   ✅ Procesos Python detenidos")

        for script in ["dashboard_mt5.py", "bot_mt5.py", "auto_update.py"]:
            if (BOT_DIR / script).exists():
                subprocess.Popen(
                    ["python", str(BOT_DIR / script)],
                    cwd=str(BOT_DIR),
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
                log(f"   ✅ {script} relanzado")
                time.sleep(2)

        # Este proceso se va a matar y relanzar, salir limpiamente
        sys.exit(0)
    except Exception as e:
        log(f"   ⚠️ Error al reiniciar: {e}")


def is_bot_running() -> bool:
    """Comprueba si bot_mt5.py está corriendo via localhost:5000/api/status."""
    try:
        import urllib.request as _ur
        req = _ur.Request("http://localhost:5000/api/status",
                          headers={"User-Agent": "AutoUpdate-Watchdog/1.0"})
        with _ur.urlopen(req, timeout=5) as r:
            data = json.loads(r.read())
            # is_running=True + last_update reciente (< 5 min)
            if not data.get("is_running", False):
                return False
            last_upd = data.get("last_update", "")
            if last_upd:
                try:
                    from datetime import timezone
                    ts = datetime.fromisoformat(last_upd.replace("Z", "+00:00"))
                    age = (datetime.now(timezone.utc) - ts).total_seconds()
                    if age > 300:  # más de 5 minutos sin actualizar → bot colgado
                        log(f"⚠️ Bot lleva {int(age)}s sin actualizar (posible cuelgue)")
                        return False
                except Exception:
                    pass
            return True
    except Exception:
        return False


def watchdog_restart():
    """Reinicia solo bot_mt5.py sin matar el resto de procesos."""
    log("🐕 Watchdog: bot_mt5.py caído — reiniciando solo el bot...")
    try:
        # Matar solo bot_mt5.py
        r = subprocess.run(
            ["wmic", "process", "where", "CommandLine like '%bot_mt5.py%'", "delete"],
            capture_output=True, text=True
        )
        time.sleep(3)
        if (BOT_DIR / "bot_mt5.py").exists():
            subprocess.Popen(
                ["python", str(BOT_DIR / "bot_mt5.py")],
                cwd=str(BOT_DIR),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            log("   ✅ bot_mt5.py relanzado por watchdog")
        else:
            log("   ❌ bot_mt5.py no encontrado en disco")
    except Exception as e:
        log(f"   ⚠️ Error en watchdog_restart: {e}")


def check_and_update():
    """Comprueba si hay actualizaciones y las aplica."""
    remote_sha = get_remote_sha()
    if not remote_sha:
        return False

    local_sha = get_local_sha()
    if not local_sha:
        # git fallo (no en PATH, permisos, etc.) — no reiniciar en bucle
        log("⚠️ git rev-parse HEAD fallo — saltando comprobacion (evita reinicio en bucle)")
        return False

    if remote_sha == local_sha:
        log(f"✔️ Sin cambios (SHA: {local_sha[:8]}...)")
        return False

    log(f"🆕 Nuevo commit: {remote_sha[:8]}... (local: {local_sha[:8]})")
    if git_pull():
        log("📦 Codigo actualizado. Reiniciando...")
        restart_bot()
        return True
    return False


def main():
    log("🚀 Auto-updater iniciado.")
    log(f"   Repo: {GITHUB_REPO} | Branch: {GITHUB_BRANCH}")
    log(f"   Intervalo: {CHECK_INTERVAL // 60} minutos")

    log("\n⏩ Comprobacion inicial...")
    check_and_update()

    while True:
        log(f"\n⏳ Esperando {CHECK_INTERVAL // 60} min...")
        time.sleep(CHECK_INTERVAL)

        # — Watchdog: reiniciar bot si se cayó (independiente de git) —
        if not is_bot_running():
            log("🔴 Watchdog: bot_mt5.py NO está corriendo")
            watchdog_restart()
            time.sleep(15)  # dar tiempo a que arranque antes del check de git

        check_and_update()


if __name__ == "__main__":
    main()
