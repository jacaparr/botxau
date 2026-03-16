#!/usr/bin/env pwsh
# fix_vps_firewall.ps1
# Ejecutar en el VPS con PowerShell como Administrador
# Abre el puerto 5000, instala dependencias y arranca el dashboard

$BOT_DIR = if ($PSScriptRoot -ne "") { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
$PORT    = 5000

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  ARREGLANDO PUERTO Y DASHBOARD EN VPS" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# ── 1. Abrir puerto 5000 en Windows Firewall ─────────────────────────────────
Write-Host "`n[1/4] Abriendo puerto $PORT en Windows Firewall..." -ForegroundColor Yellow
$existingRule = Get-NetFirewallRule -DisplayName "Bot Dashboard $PORT" -ErrorAction SilentlyContinue
if ($existingRule) {
    Write-Host "  Regla ya existe, actualizando..." -ForegroundColor Gray
    Set-NetFirewallRule -DisplayName "Bot Dashboard $PORT" -Enabled True
} else {
    New-NetFirewallRule `
        -DisplayName "Bot Dashboard $PORT" `
        -Direction   Inbound `
        -Protocol    TCP `
        -LocalPort   $PORT `
        -Action      Allow `
        -Profile     Any | Out-Null
    Write-Host "  Regla creada OK" -ForegroundColor Green
}

# ── 2. Instalar requests si falta ────────────────────────────────────────────
Write-Host "`n[2/4] Verificando dependencias Python..." -ForegroundColor Yellow
try {
    $check = python -c "import requests; print('OK')" 2>&1
    if ($check -eq "OK") {
        Write-Host "  requests ya instalado" -ForegroundColor Green
    } else {
        pip install requests flask flask-cors psutil | Out-Null
        Write-Host "  Dependencias instaladas" -ForegroundColor Green
    }
} catch {
    Write-Host "  Error verificando Python: $_" -ForegroundColor Red
}

# ── 3. Matar proceso antiguo si existe ───────────────────────────────────────
Write-Host "`n[3/4] Reiniciando dashboard..." -ForegroundColor Yellow
$old = Get-WmiObject Win32_Process | Where-Object { $_.CommandLine -like "*dashboard_mt5*" }
if ($old) {
    $old | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
    Write-Host "  Proceso anterior detenido" -ForegroundColor Gray
}

# Matar cualquier python en puerto 5000
$pid5000 = (netstat -ano | findstr ":5000" | findstr LISTENING) -replace '.*\s+(\d+)$', '$1'
if ($pid5000) {
    taskkill /PID $pid5000 /F 2>&1 | Out-Null
    Start-Sleep -Seconds 1
}

# ── 4. Arrancar dashboard en background ──────────────────────────────────────
Write-Host "`n[4/4] Arrancando dashboard..." -ForegroundColor Yellow
if (Test-Path "$BOT_DIR\dashboard_mt5.py") {
    Start-Process -FilePath "python" `
        -ArgumentList "dashboard_mt5.py" `
        -WorkingDirectory $BOT_DIR `
        -WindowStyle Minimized
    Start-Sleep -Seconds 4

    # Verificar que arrancó
    $running = netstat -ano | findstr ":5000" | findstr LISTENING
    if ($running) {
        Write-Host "  Dashboard corriendo en puerto $PORT" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: No se pudo arrancar el dashboard" -ForegroundColor Red
        Write-Host "  Intenta manualmente: cd $BOT_DIR && python dashboard_mt5.py" -ForegroundColor Yellow
    }
} else {
    Write-Host "  ERROR: No se encontro $BOT_DIR\dashboard_mt5.py" -ForegroundColor Red
    Write-Host "  Sube el archivo al VPS primero" -ForegroundColor Yellow
}

# ── Resultado final ───────────────────────────────────────────────────────────
Write-Host "`n=========================================" -ForegroundColor Cyan
Write-Host "  RESUMEN" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
$rule = Get-NetFirewallRule -DisplayName "Bot Dashboard $PORT" -ErrorAction SilentlyContinue
Write-Host "  Firewall puerto $PORT : $(if($rule -and $rule.Enabled -eq 'True'){'ABIERTO ✓'}else{'ERROR ✗'})" -ForegroundColor $(if($rule){'Green'}else{'Red'})
$proc = netstat -ano | findstr ":$PORT" | findstr LISTENING
Write-Host "  Dashboard corriendo  : $(if($proc){'SI ✓'}else{'NO ✗'})" -ForegroundColor $(if($proc){'Green'}else{'Red'})
Write-Host "`n  URL dashboard VPS: http://37.60.247.231:$PORT" -ForegroundColor Cyan
Write-Host "=========================================`n" -ForegroundColor Cyan

Pause
