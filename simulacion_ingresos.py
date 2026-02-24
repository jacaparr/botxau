
# Parámetros del Fondeo (100k)
FONDEO_MONTHLY_PROFIT = 1029.00  # Fijo al 0.05% de riesgo

# Parámetros Capital Privado
PRIVADO_INICIAL = 0
PRIVADO_AVG_ROI_MONTHLY = 5.0  # Estrategia potente al 0.5% de riesgo

def simulate_income_evolution():
    months = 36
    privado_balance = PRIVADO_INICIAL
    
    print(f"{'Mes':<5} | {'Ingreso Fondeo':<15} | {'Ingreso Privado':<16} | {'INGRESO TOTAL MES'}")
    print("-" * 70)
    
    for month in range(1, months + 1):
        # 1. Ganancia fija del fondeo
        ingreso_fondeo = FONDEO_MONTHLY_PROFIT
        
        # 2. Ganancia de la cuenta privada (5% del balance actual)
        ingreso_privado = privado_balance * (PRIVADO_AVG_ROI_MONTHLY / 100)
        
        # 3. Reinversión para el mes siguiente (50% de la ganancia del fondeo + 100% ganancia privada)
        # Nota: Estamos asumiendo que el usuario REINVIERTE todo el beneficio privado para crecer rapido 
        # y saca el 50% del fondeo como sueldo.
        reinvest_fondeo = ingreso_fondeo * 0.5
        privado_balance += reinvest_fondeo + ingreso_privado
        
        # Hitos de flujo de caja
        if month in [1, 12, 24, 36]:
            total_mes = ingreso_fondeo + ingreso_privado
            print(f"{month:<5} | ${ingreso_fondeo:<14,.2f} | ${ingreso_privado:<15,.2f} | ${total_mes:<14,.2f}")

    print("-" * 70)
    print(f"RESUMEN DE INGRESOS MENSUALES:")
    print(f"💰 Al inicio: Ganabas $1,029/mes.")
    print(f"🚀 Al Año 3: Estarás ganando ${FONDEO_MONTHLY_PROFIT + (privado_balance * 0.05):,.2f} al mes.")

if __name__ == "__main__":
    simulate_income_evolution()
