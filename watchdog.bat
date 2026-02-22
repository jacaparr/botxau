@echo off
REM ═══════════════════════════════════════════════════════════════
REM  watchdog.bat — Reinicia el bot automáticamente si se cierra
REM ═══════════════════════════════════════════════════════════════
REM
REM  USO:
REM    1. Haz doble clic en este archivo para iniciar el bot
REM    2. Si el bot se cierra por error, se reinicia en 30 segundos
REM    3. Para detener definitivamente, cierra esta ventana
REM
REM  PARA ARRANQUE AUTOMÁTICO EN VPS:
REM    1. Presiona Win+R → escribe: shell:startup
REM    2. Crea un acceso directo a este archivo en esa carpeta
REM    → El bot arrancará cada vez que se reinicie el VPS
REM
REM ═══════════════════════════════════════════════════════════════

title BOT XAUUSD - Watchdog v4

:loop
echo.
echo ═══════════════════════════════════════════════
echo   [%date% %time%] Iniciando bot...
echo ═══════════════════════════════════════════════
echo.

python bot_mt5.py --risk 1.5 --interval 60

echo.
echo ⚠️  Bot detenido. Reiniciando en 30 segundos...
echo     (Cierra esta ventana para detener definitivamente)
echo.

timeout /t 30 /nobreak

goto loop
