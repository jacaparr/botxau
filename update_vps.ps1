#!/usr/bin/env pwsh
# update_vps.ps1 — Sube la versión local del bot al VPS y la reinicia
# Uso: .\update_vps.ps1
# Requisito: tener scp/ssh disponibles (instalados con OpenSSH en Windows)

$VPS_IP = "37.60.247.231"
$VPS_USER = "Administrator"   # Cambia si tu usuario es distinto
$VPS_DIR = "C:\bot"          # Directorio del bot en el VPS
$ZIP = "bot_vps_update_v5.zip"

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "  ACTUALIZANDO BOT EN VPS $VPS_IP" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

# 1. Subir ZIP al VPS
Write-Host "`n[1/4] Subiendo archivos al VPS..." -ForegroundColor Yellow
scp $ZIP "${VPS_USER}@${VPS_IP}:C:\bot\"
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: No se pudo subir el ZIP" -ForegroundColor Red; exit 1 }

# 2. Detener el bot actual en el VPS
Write-Host "[2/4] Deteniendo bot actual en VPS..." -ForegroundColor Yellow
ssh "${VPS_USER}@${VPS_IP}" "taskkill /F /IM python.exe /T 2>nul; echo Bot detenido"

# 3. Descomprimir y sobrescribir archivos
Write-Host "[3/4] Instalando nueva version..." -ForegroundColor Yellow
ssh "${VPS_USER}@${VPS_IP}" "cd C:\bot && powershell Expand-Archive -Force -Path bot_vps_update_v5.zip -DestinationPath .\"

# 4. Reiniciar el bot via watchdog
Write-Host "[4/4] Reiniciando bot con watchdog..." -ForegroundColor Yellow
ssh "${VPS_USER}@${VPS_IP}" "cd C:\bot && start /min cmd /c watchdog.bat"

Write-Host "`n✅ VPS actualizado correctamente!" -ForegroundColor Green
Write-Host "   Bot arrancando con: riesgo 0.60%, estrategia Ensemble" -ForegroundColor Green
Write-Host "   Dashboard en: http://${VPS_IP}:5000" -ForegroundColor Cyan
