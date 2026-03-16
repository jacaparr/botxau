# auto_update.ps1 — Lanzador / updater del bot en el VPS
# =========================================================
# Se auto-detecta la ruta: funciona desde cualquier directorio.
# Ejecutar:
#   powershell -ExecutionPolicy Bypass -File auto_update.ps1
# =========================================================

$ErrorActionPreference = "Continue"

# ── Ruta real del script (funciona en cualquier maquina/VPS) ─────────────────
$BotDir = if ($PSScriptRoot -ne "") { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $BotDir

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  AUTO-UPDATE + ARRANQUE BOT XAUUSD MT5" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Directorio: $BotDir" -ForegroundColor Gray
Write-Host ""

# ── 1. Git pull ──────────────────────────────────────────────────────────────
Write-Host "[1/4] Actualizando codigo desde GitHub..." -ForegroundColor Yellow
$gitResult = git pull origin main 2>&1
Write-Host "  $gitResult" -ForegroundColor Gray
if ($LASTEXITCODE -eq 0) {
    Write-Host "  OK - Codigo al dia." -ForegroundColor Green
} else {
    Write-Host "  AVISO: git pull con advertencias. Continuando..." -ForegroundColor Yellow
}

# ── 2. Matar procesos Python anteriores ─────────────────────────────────────
Write-Host "`n[2/4] Deteniendo procesos Python anteriores..." -ForegroundColor Yellow
$killed = 0
Get-Process python -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    $killed++
}
if ($killed -gt 0) {
    Write-Host "  $killed proceso(s) detenido(s)." -ForegroundColor Red
} else {
    Write-Host "  Ningun proceso Python activo." -ForegroundColor Gray
}
Start-Sleep 2

# ── 3. Instalar/actualizar dependencias ─────────────────────────────────────
Write-Host "`n[3/4] Verificando dependencias..." -ForegroundColor Yellow
python -m pip install -r requirements.txt -q 2>&1 | Out-Null
Write-Host "  OK - Dependencias al dia." -ForegroundColor Green

# ── 4. Arrancar dashboard + bot + auto_update.py ────────────────────────────
Write-Host "`n[4/4] Iniciando procesos..." -ForegroundColor Yellow

Start-Process -FilePath "python" -ArgumentList "dashboard_mt5.py" `
    -WorkingDirectory $BotDir -WindowStyle Minimized -PassThru | Out-Null
Start-Sleep 3

Start-Process -FilePath "python" -ArgumentList "bot_mt5.py" `
    -WorkingDirectory $BotDir -WindowStyle Minimized -PassThru | Out-Null
Start-Sleep 2

Start-Process -FilePath "python" -ArgumentList "auto_update.py" `
    -WorkingDirectory $BotDir -WindowStyle Minimized -PassThru | Out-Null
Start-Sleep 1

# ── Verificar ────────────────────────────────────────────────────────────────
$procs = Get-Process python -ErrorAction SilentlyContinue
Write-Host ""
if ($procs.Count -ge 2) {
    Write-Host "================================================" -ForegroundColor Green
    Write-Host "  BOT ACTIVO - $($procs.Count) procesos Python corriendo" -ForegroundColor Green
    Write-Host "  Dashboard: http://localhost:5000" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Green
} else {
    Write-Host "  ATENCION: Menos procesos de lo esperado ($($procs.Count))" -ForegroundColor Red
}
