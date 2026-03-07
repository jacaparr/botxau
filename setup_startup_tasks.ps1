#!/usr/bin/env pwsh
# setup_startup_tasks.ps1
# Ejecutar en el VPS como Administrador UNA SOLA VEZ
# Registra bot_mt5.py, dashboard_mt5.py y auto_update.py como tareas
# programadas que arrancan automaticamente al iniciar Windows.

$BOT_DIR  = "C:\bot"
$PYTHON   = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PYTHON) { $PYTHON = "python" }

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  CONFIGURANDO INICIO AUTOMATICO EN VPS" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Python : $PYTHON"
Write-Host "  Bot dir: $BOT_DIR"
Write-Host ""

# ── Helper ────────────────────────────────────────────────────────────────────
function Register-BotTask {
    param(
        [string]$TaskName,
        [string]$Script,
        [int]   $DelaySeconds
    )

    # Borrar si ya existe
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    $action  = New-ScheduledTaskAction `
                   -Execute $PYTHON `
                   -Argument "$BOT_DIR\$Script" `
                   -WorkingDirectory $BOT_DIR

    # Trigger: al arrancar Windows + delay para que la red esté lista
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $settings = New-ScheduledTaskSettingsSet `
                    -ExecutionTimeLimit (New-TimeSpan -Hours 0) `
                    -RestartCount 3 `
                    -RestartInterval (New-TimeSpan -Minutes 1) `
                    -StartWhenAvailable `
                    -RunOnlyIfNetworkAvailable

    # Añadir delay al trigger
    $trigger.Delay = "PT${DelaySeconds}S"

    # Correr como SYSTEM para que no dependa de login interactivo
    $principal = New-ScheduledTaskPrincipal `
                     -UserId "SYSTEM" `
                     -LogonType ServiceAccount `
                     -RunLevel Highest

    Register-ScheduledTask `
        -TaskName  $TaskName `
        -Action    $action `
        -Trigger   $trigger `
        -Settings  $settings `
        -Principal $principal `
        -Force | Out-Null

    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) {
        Write-Host "  [OK] $TaskName registrado (delay ${DelaySeconds}s)" -ForegroundColor Green
    } else {
        Write-Host "  [ERROR] $TaskName no se pudo registrar" -ForegroundColor Red
    }
}

# ── Registrar las 3 tareas ─────────────────────────────────────────────────────
Write-Host "[1/3] dashboard_mt5.py  (delay 20s)..." -ForegroundColor Yellow
Register-BotTask -TaskName "BotDashboard"   -Script "dashboard_mt5.py"  -DelaySeconds 20

Write-Host "[2/3] bot_mt5.py        (delay 35s)..." -ForegroundColor Yellow
Register-BotTask -TaskName "BotMT5"         -Script "bot_mt5.py"         -DelaySeconds 35

Write-Host "[3/3] auto_update.py    (delay 50s)..." -ForegroundColor Yellow
Register-BotTask -TaskName "BotAutoUpdate"  -Script "auto_update.py"     -DelaySeconds 50

# ── Abrir puerto 5000 en firewall (por si acaso) ──────────────────────────────
Write-Host "`n[+] Asegurando regla firewall puerto 5000..." -ForegroundColor Yellow
$rule = Get-NetFirewallRule -DisplayName "Bot Dashboard 5000" -ErrorAction SilentlyContinue
if ($rule) {
    Set-NetFirewallRule -DisplayName "Bot Dashboard 5000" -Enabled True
} else {
    New-NetFirewallRule `
        -DisplayName "Bot Dashboard 5000" `
        -Direction   Inbound `
        -Protocol    TCP `
        -LocalPort   5000 `
        -Action      Allow `
        -Profile     Any | Out-Null
}
Write-Host "  [OK] Firewall puerto 5000 abierto" -ForegroundColor Green

# ── Resumen final ──────────────────────────────────────────────────────────────
Write-Host "`n=========================================" -ForegroundColor Cyan
Write-Host "  RESUMEN" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
$tasks = @("BotDashboard", "BotMT5", "BotAutoUpdate")
foreach ($t in $tasks) {
    $task = Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue
    $estado = if ($task) { "REGISTRADO ✓" } else { "ERROR ✗" }
    $color  = if ($task) { "Green" } else { "Red" }
    Write-Host "  $t : $estado" -ForegroundColor $color
}

Write-Host "`n  Ahora al reiniciar el VPS arrancan solos." -ForegroundColor Cyan
Write-Host "  Para arrancar manualmente ahora sin reiniciar:" -ForegroundColor Gray
Write-Host "    Start-ScheduledTask -TaskName BotDashboard" -ForegroundColor Gray
Write-Host "    Start-ScheduledTask -TaskName BotMT5" -ForegroundColor Gray
Write-Host "    Start-ScheduledTask -TaskName BotAutoUpdate" -ForegroundColor Gray
Write-Host "=========================================`n" -ForegroundColor Cyan

Pause
