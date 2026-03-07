# update_vps.ps1 — Actualizar VPS al bot MT5 v7 (HYBRID_D1_ICT)
# =============================================================
# EJECUTAR ESTE SCRIPT EN EL VPS via RDP
# Boton derecho -> Run with PowerShell  (o desde PowerShell admin)
# =============================================================

$ErrorActionPreference = "Continue"
$BotDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  ACTUALIZACION BOT XAUUSD MT5 v7" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "Directorio: $BotDir" -ForegroundColor Gray

# ── 1. Matar procesos Python viejos ──────────────────────────
Write-Host "`n[1/5] Deteniendo procesos Python anteriores..." -ForegroundColor Yellow
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "  Matando PID $($_.Id)" -ForegroundColor Red
    Stop-Process -Id $_.Id -Force
}
Start-Sleep 2
Write-Host "  OK - Procesos detenidos." -ForegroundColor Green

# ── 2. Git pull ───────────────────────────────────────────────
Write-Host "`n[2/5] Descargando ultima version del codigo (git pull)..." -ForegroundColor Yellow
Set-Location $BotDir
$gitResult = git pull origin main 2>&1
Write-Host $gitResult -ForegroundColor Gray
if ($LASTEXITCODE -eq 0) {
    Write-Host "  OK - Codigo actualizado." -ForegroundColor Green
} else {
    Write-Host "  AVISO: git pull tuvo problemas. Continuando de todos modos..." -ForegroundColor Yellow
}

# ── 3. Instalar dependencias nuevas (si hay) ─────────────────
Write-Host "`n[3/5] Verificando dependencias (pip install)..." -ForegroundColor Yellow
python -m pip install -r requirements.txt -q
Write-Host "  OK - Dependencias al dia." -ForegroundColor Green

# ── 3b. Actualizar .env del VPS ──────────────────────────────
Write-Host "`n[3b] Actualizando .env del VPS..." -ForegroundColor Yellow
$envFile = Join-Path $BotDir ".env"
$envContent = @"
# Binance Futures TESTNET API Keys
BINANCE_TESTNET_API_KEY=
BINANCE_TESTNET_SECRET_KEY=
USE_TESTNET=True

# Telegram
TELEGRAM_BOT_TOKEN=8208547121:AAH5CFnVHt2mjwK55UyXHFsTyWEt4wxf5N8
TELEGRAM_CHAT_ID=5230399966

# Prop Firm - VPS
BOT_INSTANCE=VPS
PROP_STARTING_BALANCE=23767.96
PROP_BASE_RISK=0.50
PROP_DAILY_DD_LIMIT=0.04
PROP_MAX_DD_LIMIT=0.08

# URL del bot LOCAL (ngrok)
LOCAL_URL=https://cindi-excogitative-jaycob.ngrok-free.dev
"@
$envContent | Out-File -FilePath $envFile -Encoding UTF8 -Force
Write-Host "  OK - .env VPS actualizado (BOT_INSTANCE=VPS, LOCAL_URL configurada)." -ForegroundColor Green

# ── 4. Crear watchdog_mt5.bat y actualizar inicio automatico ─
Write-Host "`n[4/5] Creando watchdog_mt5.bat..." -ForegroundColor Yellow

$watchdogContent = @"
@echo off
title BOT XAUUSD MT5 v7 - Watchdog
cd /d "$BotDir"

:LOOP_BOT
echo [%date% %time%] Iniciando bot_mt5.py y dashboard_mt5.py...
start "DASHBOARD MT5" /min python dashboard_mt5.py
timeout /t 3 /nobreak >nul
python bot_mt5.py
echo [%date% %time%] Bot terminado. Reiniciando en 10s...
taskkill /f /fi "WINDOWTITLE eq DASHBOARD MT5" >nul 2>&1
timeout /t 10 /nobreak >nul
goto LOOP_BOT
"@

$watchdogPath = Join-Path $BotDir "watchdog_mt5.bat"
$watchdogContent | Out-File -FilePath $watchdogPath -Encoding ASCII -Force
Write-Host "  OK - watchdog_mt5.bat creado en $watchdogPath" -ForegroundColor Green

# Actualizar acceso directo de inicio automatico
$StartupFolder = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$ShortcutPath = "$StartupFolder\BotWatchdog.lnk"
try {
    $WShell = New-Object -ComObject WScript.Shell
    $SC = $WShell.CreateShortcut($ShortcutPath)
    $SC.TargetPath = $watchdogPath
    $SC.WorkingDirectory = $BotDir
    $SC.Save()
    Write-Host "  OK - Inicio automatico actualizado a watchdog_mt5.bat." -ForegroundColor Green
} catch {
    Write-Host "  AVISO: No se pudo actualizar el acceso directo: $_" -ForegroundColor Yellow
}

# Matar watchdog.bat viejo si sigue corriendo
Get-Process cmd -ErrorAction SilentlyContinue | ForEach-Object {
    $cmdline = (Get-WmiObject Win32_Process -Filter "ProcessId=$($_.Id)" -ErrorAction SilentlyContinue).CommandLine
    if ($cmdline -like "*watchdog.bat*" -and $cmdline -notlike "*watchdog_mt5*") {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  Watchdog viejo (PID $($_.Id)) detenido." -ForegroundColor Red
    }
}

# ── 5. Lanzar bot nuevo ───────────────────────────────────────
Write-Host "`n[5/5] Iniciando bot_mt5.py + dashboard_mt5.py..." -ForegroundColor Yellow

Start-Process -FilePath "python" -ArgumentList "dashboard_mt5.py" `
    -WorkingDirectory $BotDir -WindowStyle Minimized
Start-Sleep 3

Start-Process -FilePath "python" -ArgumentList "bot_mt5.py" `
    -WorkingDirectory $BotDir -WindowStyle Minimized
Start-Sleep 3

Start-Process -FilePath "python" -ArgumentList "auto_update.py" `
    -WorkingDirectory $BotDir -WindowStyle Minimized
Write-Host "  Auto-updater lanzado (git pull cada 30 min)" -ForegroundColor Cyan
Start-Sleep 2

# Verificar procesos activos
$pProcs = Get-Process python -ErrorAction SilentlyContinue
if ($pProcs.Count -ge 2) {
    Write-Host "  OK - $($pProcs.Count) procesos Python activos." -ForegroundColor Green
} elseif ($pProcs.Count -eq 1) {
    Write-Host "  AVISO - Solo 1 proceso Python. Revisa si hay errores en los logs." -ForegroundColor Yellow
} else {
    Write-Host "  ERROR - 0 procesos Python activos. Asegurate de que MT5 este abierto." -ForegroundColor Red
}

# Test rapido del dashboard
Start-Sleep 3
try {
    $resp = Invoke-WebRequest -Uri "http://localhost:5000" -TimeoutSec 6 -UseBasicParsing
    Write-Host "  Dashboard HTTP $($resp.StatusCode) - ACTIVO en http://localhost:5000" -ForegroundColor Green
} catch {
    Write-Host "  AVISO: Dashboard no responde aun. Espera 10-15s y abre http://localhost:5000" -ForegroundColor Yellow
}

Write-Host "`n================================================" -ForegroundColor Green
Write-Host "  ACTUALIZACION COMPLETADA" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Bot activo:  bot_mt5.py  (HYBRID_D1_ICT, XAUUSD)" -ForegroundColor White
Write-Host "Dashboard:   http://localhost:5000" -ForegroundColor White
Write-Host "Watchdog:    watchdog_mt5.bat  (auto-reinicio en crash)" -ForegroundColor White
Write-Host "Auto-inicio: Configurado para arrancar con el VPS" -ForegroundColor White
Write-Host ""
Write-Host "IMPORTANTE:" -ForegroundColor Yellow
Write-Host "  * MT5 debe estar abierto con la cuenta de fondeo activa" -ForegroundColor Yellow
Write-Host "  * El dashboard nuevo muestra XAUUSD/MT5, no EURUSD/viejo" -ForegroundColor Yellow
Write-Host ""
pause

Write-Host "`n✅ VPS actualizado correctamente!" -ForegroundColor Green
Write-Host "   Bot arrancando con: riesgo 0.45%, estrategia Ensemble" -ForegroundColor Green
Write-Host "   Dashboard en: http://${VPS_IP}:5000" -ForegroundColor Cyan
