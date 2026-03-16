#!/usr/bin/env pwsh
# vps_init_git.ps1 — Inicializa git en el VPS y sincroniza con GitHub
# Ejecutar en el VPS (PowerShell como Admin)
# UNA SOLA VEZ — después el auto_update.py lo mantiene sincronizado

$BOT_DIR  = if ($PSScriptRoot -ne "") { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$REPO_URL = "https://github.com/jacaparr/botxau.git"
$BRANCH   = "main"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  INICIALIZANDO GIT EN VPS" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# Ir al directorio del bot
if (-not (Test-Path $BOT_DIR)) {
    New-Item -ItemType Directory -Path $BOT_DIR | Out-Null
    Write-Host "  Directorio $BOT_DIR creado" -ForegroundColor Green
}
Set-Location $BOT_DIR

# Verificar si git está instalado
$gitVersion = git --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ERROR: Git no está instalado en el VPS" -ForegroundColor Red
    Write-Host "  Descarga git desde: https://git-scm.com/download/win" -ForegroundColor Yellow
    Pause; exit 1
}
Write-Host "  Git instalado: $gitVersion" -ForegroundColor Green

# ── Opción A: Ya hay archivos pero no .git ────────────────────────────────────
$isGitRepo = Test-Path "$BOT_DIR\.git"
if (-not $isGitRepo) {
    Write-Host "`n[1/3] Inicializando repositorio git..." -ForegroundColor Yellow
    git init
    git remote add origin $REPO_URL
    git fetch origin $BRANCH

    # Hacer checkout preservando archivos locales importantes (.env, state JSON)
    git checkout -f $BRANCH
    # Sobreescribir solo con los archivos del repo (preserva .env y JSONs de estado)
    git reset --hard "origin/$BRANCH"
    Write-Host "  Repositorio inicializado y sincronizado" -ForegroundColor Green
} else {
    Write-Host "`n[1/3] Repositorio git ya existe, haciendo pull..." -ForegroundColor Yellow
    git remote set-url origin $REPO_URL
    git fetch origin $BRANCH
    git reset --hard "origin/$BRANCH"
    Write-Host "  Pull completado" -ForegroundColor Green
}

# ── Verificar archivos clave ──────────────────────────────────────────────────
Write-Host "`n[2/3] Verificando archivos clave..." -ForegroundColor Yellow
$files = @("bot_mt5.py", "dashboard_mt5.py", "index.html", "auto_update.py", "watchdog.bat")
foreach ($f in $files) {
    if (Test-Path "$BOT_DIR\$f") {
        Write-Host "  ✓ $f" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $f (falta)" -ForegroundColor Red
    }
}

# ── Reiniciar dashboard ───────────────────────────────────────────────────────
Write-Host "`n[3/3] Reiniciando dashboard..." -ForegroundColor Yellow
taskkill /F /IM python.exe /T 2>$null | Out-Null
Start-Sleep -Seconds 2
Start-Process python -ArgumentList "dashboard_mt5.py" -WorkingDirectory $BOT_DIR -WindowStyle Minimized
Start-Sleep -Seconds 3
$listening = netstat -ano | findstr ":5000" | findstr LISTENING
if ($listening) {
    Write-Host "  Dashboard corriendo en puerto 5000 ✓" -ForegroundColor Green
} else {
    Write-Host "  ERROR: Dashboard no arrancó" -ForegroundColor Red
}

Write-Host "`n=========================================" -ForegroundColor Cyan
Write-Host "  LISTO — Git inicializado en $BOT_DIR" -ForegroundColor Green
Write-Host "  Desde ahora auto_update.py sincroniza" -ForegroundColor Green
Write-Host "  GitHub cada 30 minutos automaticamente" -ForegroundColor Green
Write-Host "=========================================`n" -ForegroundColor Cyan
Pause
