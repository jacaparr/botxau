# setup_vps.ps1 — Instalación Automática para VPS Windows
# =======================================================
# Este script prepara el VPS para correr el bot 24/7.
# Ejecución: Botón derecho -> Run with PowerShell

$ErrorActionPreference = "Stop"

Write-Host "===============================================" -ForegroundColor Cyan
Write-Host "🥇 INSTALADOR AUTOMÁTICO - BOT XAUUSD v4" -ForegroundColor Cyan
Write-Host "===============================================" -ForegroundColor Cyan

# 1. Verificar Python
Write-Host "`n[1/4] Verificando Python..." -ForegroundColor Yellow
try {
    python --version
    Write-Host "✅ Python detectado." -ForegroundColor Green
} catch {
    Write-Host "❌ Python no encontrado. Descargando instalador..." -ForegroundColor Red
    $url = "https://www.python.org/ftp/python/3.11.5/python-3.11.5-amd64.exe"
    $out = "$env:TEMP\python_install.exe"
    Invoke-WebRequest -Uri $url -OutFile $out
    Write-Host "Ejecutando instalador... Sigue los pasos y marca 'Add Python to PATH'" -ForegroundColor Cyan
    Start-Process $out -Wait
    Write-Host "Reicia este script después de instalar Python." -ForegroundColor Yellow
    exit
}

# 2. Instalar dependencias
Write-Host "`n[2/4] Instalando librerías necesarias..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Write-Host "✅ Dependencias instaladas." -ForegroundColor Green

# 3. Verificar MetaTrader 5
Write-Host "`n[3/4] Verificando MetaTrader 5..." -ForegroundColor Yellow
Write-Host "IMPORTANTE: MT5 debe estar instalado y abierto en el VPS." -ForegroundColor Cyan
$mt5_check = python -c "import MetaTrader5 as mt5; print('OK' if mt5.initialize() else 'ERROR')"
if ($mt5_check -eq "OK") {
    Write-Host "✅ Conexión con MT5 exitosa." -ForegroundColor Green
} else {
    Write-Host "⚠️ No se pudo conectar con MT5. Asegúrate de que esté ABIERTO." -ForegroundColor Yellow
}

# 4. Configurar arranque automático (Watchdog)
Write-Host "`n[4/4] Configurando arranque automático..." -ForegroundColor Yellow
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c cd /d $PSScriptRoot && watchdog.bat"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName "BotScalingGold" -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force

Write-Host "`n===============================================" -ForegroundColor Green
Write-Host "✅ INSTALACIÓN COMPLETADA" -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
Write-Host "1. Asegúrate de haber configurado el archivo .env con tu Token y Chat ID."
Write-Host "2. Mantén MT5 abierto con tu cuenta de fondeo logueada."
Write-Host "3. El bot se iniciará solo cada vez que el VPS se reinicie."
Write-Host "`nPara iniciar el bot ahora, ejecuta: watchdog.bat"
Write-Host "===============================================" -ForegroundColor Green

pause
