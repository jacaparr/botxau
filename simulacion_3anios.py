
# Parámetros del Fondeo (100k)
FONDEO_MONTHLY_PROFIT = 1029.00  # Objetivo $1,000/mes

# Parámetros Capital Privado
PRIVADO_INICIAL = 0
PRIVADO_AVG_ROI_MONTHLY = 5.0  # Crecimiento esperado con estrategia potente

def simulate_3_years():
    months = 36
    privado_balance = PRIVADO_INICIAL
    sueldo_acumulado = 0
    
    print(f"{'Mes':<5} | {'Sueldo Acum.':<15} | {'Cuenta Privada':<15} | {'Patrimonio Total':<15}")
    print("-" * 70)
    
    for month in range(1, months + 1):
        # Ganancia del Fondeo
        reinvest = FONDEO_MONTHLY_PROFIT * 0.5
        sueldo = FONDEO_MONTHLY_PROFIT * 0.5
        
        # Rendimiento compuesto en cuenta privada
        yield_privado = privado_balance * (PRIVADO_AVG_ROI_MONTHLY / 100)
        privado_balance += reinvest + yield_privado
        sueldo_acumulado += sueldo
        
        # Hitos temporales notables
        if month in [1, 6, 12, 18, 24, 30, 36]:
            print(f"{month:<5} | ${sueldo_acumulado:<14,.2f} | ${privado_balance:<14,.2f} | ${sueldo_acumulado + privado_balance:<14,.2f}")

    print("-" * 70)
    print(f"RESUMEN FINAL (3 AÑOS):")
    print(f"💰 Sueldo Total Ahorrado: ${sueldo_acumulado:,.2f}")
    print(f"📈 Valor Cuenta Privada: ${privado_balance:,.2f}")
    print(f"👑 PATRIMONIO TOTAL:     ${sueldo_acumulado + privado_balance:,.2f}")

if __name__ == "__main__":
    simulate_3_years()
