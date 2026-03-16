# reset_vps_25k.ps1
# Ejecutar en el VPS via RDP: powershell -File <ruta>\reset_vps_25k.ps1
# Resetea el estado del bot a $25K limpio (DD = 0%)

$BotDir = if ($PSScriptRoot -ne "") { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
Set-Location $BotDir

Write-Host "Deteniendo bot..." -ForegroundColor Yellow
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

Write-Host "Leyendo balance actual del estado..." -ForegroundColor Cyan
python -c @"
import json, datetime, os

state_file = 'bot_state_mt5_v5.json'
today = datetime.datetime.utcnow().strftime('%Y-%m-%d')
now_iso = datetime.datetime.utcnow().isoformat() + '+00:00'

# Leer estado existente si hay, para preservar radar y otros datos
if os.path.exists(state_file):
    s = json.load(open(state_file))
else:
    s = {}

# Balance de referencia del VPS = 25000
VPS_BALANCE = 25000.0

# Leer balance real de MT5 si esta disponible en el estado
real_balance = s.get('prop_day_start_balance', VPS_BALANCE)
# Si el balance guardado es mayor que 25K, usarlo como pico; si es menor, usar 25K
anchor = max(real_balance, VPS_BALANCE)

s['prop_starting_balance']  = VPS_BALANCE
s['prop_peak_balance']       = anchor
s['prop_day_start_balance']  = anchor
s['prop_day']                = today
s['consecutive_losses']      = 0
s['dd_alert_sent_today']     = False
s['trades_today']            = 0
s['pnl_today']               = 0.0
s['last_update']             = now_iso
s['prop_firm'] = {
    'daily_dd':          0.0,
    'daily_dd_limit':    4.0,
    'total_dd':          0.0,
    'total_dd_limit':    8.0,
    'current_risk':      0.5,
    'consecutive_losses': 0,
    'peak_balance':      anchor,
    'day_start_balance': anchor,
    'can_trade':         True,
    'status_msg':        'OK'
}

json.dump(s, open(state_file, 'w'), indent=2, default=str)
print('Estado VPS reseteado OK')
print('prop_starting_balance : 25000')
print('prop_peak_balance     :', anchor)
print('Total DD              : 0%')
print('Daily DD              : 0%')
print('Risk                  : 0.5% (completo)')
"@

Write-Host ""
Write-Host "Arrancando bot v7..." -ForegroundColor Green
Start-Process python -ArgumentList "bot_mt5.py" -WorkingDirectory $BotDir -WindowStyle Minimized
Start-Sleep -Seconds 3
Start-Process python -ArgumentList "dashboard_mt5.py" -WorkingDirectory $BotDir -WindowStyle Minimized
Start-Sleep -Seconds 2

$procs = (Get-Process python -ErrorAction SilentlyContinue).Count
Write-Host "Procesos Python activos: $procs" -ForegroundColor Cyan
Write-Host "Dashboard VPS: http://37.60.247.231:5000" -ForegroundColor Green
Write-Host "Reset completo." -ForegroundColor Green
