@echo off
REM ═══════════════════════════════════════════════════════════════
REM  watchdog.bat — Reinicia el bot Y el auto-updater
REM  v5: Incluye auto_update.py en segundo plano
REM ═══════════════════════════════════════════════════════════════
REM
REM  USO:
REM    1. Haz doble clic en este archivo para iniciar el bot
REM    2. El bot se reinicia solo si se cae
REM    3. El auto-updater se actualiza desde GitHub cada 30 min
REM    4. Para detener todo, cierra esta ventana
REM
REM  PARA ARRANQUE AUTOMÁTICO EN VPS:
REM    1. Presiona Win+R → escribe: shell:startup
REM    2. Crea un acceso directo a este archivo en esa carpeta
REM    → El bot arrancará cada vez que se reinicie el VPS
REM
REM ═══════════════════════════════════════════════════════════════

title BOT XAUUSD - Watchdog v5 (Auto-Update)

REM Iniciar el auto-updater en segundo plano (ventana minimizada)
echo [%date% %time%] Iniciando auto-updater en segundo plano...
start "AutoUpdater" /min python auto_update.py

echo.
echo ═══════════════════════════════════════════════
echo   Auto-Updater activo (GitHub cada 30 min)
echo ═══════════════════════════════════════════════
echo.

:loop
echo.
echo ═══════════════════════════════════════════════
echo   [%date% %time%] Iniciando bot...
echo ═══════════════════════════════════════════════
echo.

python bot_mt5.py --risk 0.45 --interval 60

echo.
echo ⚠️  Bot detenido. Reiniciando en 30 segundos...
echo     (Cierra esta ventana para detener definitivamente)
echo.

timeout /t 30 /nobreak

goto loop
