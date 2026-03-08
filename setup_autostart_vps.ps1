# setup_autostart_vps.ps1
# ═══════════════════════════════════════════════════════════════
# Registra watchdog.bat en el Task Scheduler del VPS para que
# arranque automáticamente cuando Windows se inicie.
#
# EJECUTAR EN EL VPS como Administrador:
#   powershell -ExecutionPolicy Bypass -File C:\bot\setup_autostart_vps.ps1
# ═══════════════════════════════════════════════════════════════

$BotDir   = "C:\bot"
$WatchDog = "$BotDir\watchdog.bat"
$TaskName = "BotXAUUSD_Watchdog"

# Verificar que watchdog.bat existe
if (-not (Test-Path $WatchDog)) {
    Write-Host "ERROR: No se encontro $WatchDog" -ForegroundColor Red
    Write-Host "Asegurate de estar en C:\bot y tener watchdog.bat" -ForegroundColor Yellow
    exit 1
}

# Eliminar tarea antigua si existe
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Tarea anterior eliminada (si existia)" -ForegroundColor Gray

# Crear la tarea: arranca cmd /c watchdog.bat al inicio del sistema
$Action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$WatchDog`"" -WorkingDirectory $BotDir
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 99 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# Correr como SYSTEM o como el usuario actual con máximos privilegios
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest -LogonType ServiceAccount

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action   $Action `
    -Trigger  $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Watchdog del bot XAUUSD - arranca bot + dashboard + auto-updater" `
    -Force

# Verificar
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Write-Host ""
    Write-Host "OK - Tarea registrada correctamente:" -ForegroundColor Green
    Write-Host "  Nombre : $TaskName" -ForegroundColor Cyan
    Write-Host "  Trigger: Al arrancar Windows" -ForegroundColor Cyan
    Write-Host "  Reintentos: 99 veces (cada 1 min si falla)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "El bot arrancara automaticamente la proxima vez que se reinicie el VPS." -ForegroundColor Green
    Write-Host ""
    Write-Host "Para arrancarlo ahora mismo sin reiniciar:" -ForegroundColor Yellow
    Write-Host "  Start-ScheduledTask -TaskName '$TaskName'" -ForegroundColor White
} else {
    Write-Host "ERROR: No se pudo registrar la tarea." -ForegroundColor Red
}
