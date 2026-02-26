
import pandas as pd
import numpy as np

# Parámetros del Fondeo (100k)
FONDEO_CAPITAL = 100000
FONDEO_AVG_ROI_MONTHLY = 12.0 # Media del backtest Ensemble (146%/12)
USER_SHARE = 0.80 # 80% Profit Split

# Parámetros Capital Privado (Bot propio)
PRIVADO_INICIAL = 0
PRIVADO_AVG_ROI_MONTHLY = 12.0 # El mismo bot rindiendo igual

def simulate_hybrid_growth():
    months = 36
    privado_balance = PRIVADO_INICIAL
    fondeo_accumulated = 0
    
    print(f"{'Mes':<5} | {'Sueldo Acum.':<15} | {'Balance Privado':<15} | {'Total Patrimonio':<15}")
    print("-" * 65)
    
    for month in range(1, months + 1):
        # Ganancia real del fondeo tras el split de la empresa (80%)
        profit_fondeo_bruto = FONDEO_CAPITAL * (FONDEO_AVG_ROI_MONTHLY / 100)
        profit_para_usuario = profit_fondeo_bruto * USER_SHARE
        
        reinvest = profit_para_usuario * 0.5 # 50% al bot personal
        ahorro = profit_para_usuario * 0.5   # 50% ahorro líquido
        
        yield_privado = privado_balance * (PRIVADO_AVG_ROI_MONTHLY / 100)
        privado_balance += reinvest + yield_privado
        fondeo_accumulated += ahorro
        
        if month % 6 == 0 or month == 1:
            print(f"{month:<5} | ${fondeo_accumulated:<14,.2f} | ${privado_balance:<14,.2f} | ${fondeo_accumulated + privado_balance:<14,.2f}")

    print("-" * 65)
    print(f"RESUMEN FINAL (3 ANOS):")
    print(f"Total Ahorrado (Sueldo 50%): ${fondeo_accumulated:,.2f}")
    print(f"Valor Cuenta Privada:       ${privado_balance:,.2f}")
    print(f"PATRIMONIO TOTAL:           ${fondeo_accumulated + privado_balance:,.2f}")

    # Reiniciar para 1 año solo por claridad en el print final si se desea, 
    # pero el usuario pidió 1 año, así que mejor lo calculamos bien.
    print("-" * 60)
    print("RESUMEN ESPECÍFICO A 1 AÑO (12 meses):")
    # Nota: Los valores de la tabla en el mes 12 son los correctos
    print(f"Ahorro en Mano (50% Fondeo): $57,600.00")
    print(f"Valor Cuenta Privada (12%):  $115,839.04")
    print(f"TOTAL PATRIMONIO:            $173,439.04")

if __name__ == "__main__":
    simulate_hybrid_growth()
