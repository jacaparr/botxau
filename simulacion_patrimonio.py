
import pandas as pd
import numpy as np

# Parámetros del Fondeo (100k)
FONDEO_CAPITAL = 100000
FONDEO_AVG_ROI_MONTHLY = 1.02 # Basado en los ~$1,000/mes (aprox 1%)

# Parámetros Capital Privado
PRIVADO_INICIAL = 0
RISK_PCT_PRIVADO = 1.0 # Riesgo agresivo en cuenta privada
PRIVADO_AVG_ROI_MONTHLY = 5.0 # Estimación agresiva para estrategia potente (~5% mes)

def simulate_hybrid_growth():
    months = 36
    privado_balance = PRIVADO_INICIAL
    fondeo_accumulated = 0
    
    print(f"{'Mes':<5} | {'Sueldo Acum.':<15} | {'Balance Privado':<15} | {'Total Patrimonio':<15}")
    print("-" * 65)
    
    for month in range(1, months + 1):
        profit_fondeo = 1029.00 
        reinvest = profit_fondeo * 0.5
        ahorro = profit_fondeo * 0.5
        
        yield_privado = privado_balance * (PRIVADO_AVG_ROI_MONTHLY / 100)
        privado_balance += reinvest + yield_privado
        fondeo_accumulated += ahorro
        
        if month % 6 == 0 or month == 1:
            print(f"{month:<5} | ${fondeo_accumulated:<14,.2f} | ${privado_balance:<14,.2f} | ${fondeo_accumulated + privado_balance:<14,.2f}")

    print("-" * 65)
    print(f"RESUMEN TRAS {months/12:.0f} AÑOS:")
    print(f"💰 Ahorro Líquido (Sueldo): ${fondeo_accumulated:,.2f}")
    print(f"📈 Cuenta Privada: ${privado_balance:,.2f}")
    print(f"👑 PATRIMONIO TOTAL: ${fondeo_accumulated + privado_balance:,.2f}")

    print("-" * 60)
    print(f"RESUMEN TRAS 1 AÑO:")
    print(f"💰 Ahorro en Mano (50% Fondeo): ${fondeo_accumulated:,.2f}")
    print(f"📈 Valor Cuenta Privada: ${privado_balance:,.2f}")
    print(f"🚀 TOTAL PATRIMONIO: ${fondeo_accumulated + privado_balance:,.2f}")

if __name__ == "__main__":
    simulate_hybrid_growth()
