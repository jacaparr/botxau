import os

files = ['bot_mt5.py', 'auto_update.py', 'telegram_notify.py', 'analyze_losses.py', 'config.py', 'indicators.py', 'logger.py', 'strategy_eurusd.py']
print('VERIFICACION DE ARCHIVOS CLAVE')
print('=' * 50)
for f in files:
    exists = os.path.exists(f)
    size = os.path.getsize(f) if exists else 0
    status = 'OK' if exists and size > 0 else 'FALTA'
    print(f'  {f:<30} {status:>6}  ({size:,} bytes)')

code = open('bot_mt5.py').read()
checks = {
    'Filtro USD correlacion': 'would_conflict_usd' in code,
    'Reporte semanal auto':   'generate_weekly_report' in code,
    'Dedup trade history':    'existing_tickets' in code,
    'Riesgo 0.45%':          '0.45' in code,
    'Import analyze_losses':  'from analyze_losses import' in code,
}
print('\nVERIFICACION FUNCIONES BOT')
print('=' * 50)
for name, ok in checks.items():
    print(f'  {name:<35} {"OK" if ok else "FALTA"}')

code_au = open('auto_update.py').read()
checks_au = {
    'GitHub API check':  'get_latest_commit_sha' in code_au,
    'Descarga archivos': 'download_file' in code_au,
    'Restart bot':       'restart_bot' in code_au,
    'Intervalo 30 min':  '30 * 60' in code_au,
}
print('\nVERIFICACION AUTO-UPDATER')
print('=' * 50)
for name, ok in checks_au.items():
    print(f'  {name:<35} {"OK" if ok else "FALTA"}')

wd = open('watchdog.bat').read()
print('\nVERIFICACION WATCHDOG BAT')
print('=' * 50)
print(f'  Lanza auto_update.py: {"OK" if "auto_update.py" in wd else "FALTA"}')
print(f'  Modo minimizado:      {"OK" if "/min" in wd else "FALTA"}')

vercel = open('vercel.json').read()
print('\nVERIFICACION VERCEL')
print('=' * 50)
print(f'  api/index.py route:  {"OK" if "api/index.py" in vercel else "FALTA"}')
print(f'  Static HTML route:   {"OK" if "index.html" in vercel else "FALTA"}')
print(f'  VPS_URL env:         {"OK" if "VPS_URL" in vercel else "FALTA"}')
