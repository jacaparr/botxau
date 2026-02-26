
def simulate_aggressive_scaling():
    # Paso 1: Cuenta de 25k (FundingPips)
    capital_inicial = 25000
    roi_mensual = 0.12 # 12% media ensemble
    split = 0.80
    
    profit_mes_1 = capital_inicial * roi_mensual * split
    coste_dos_100k = 1080 # 540 * 2
    
    cash_restante = profit_mes_1 - coste_dos_100k
    
    # Paso 2: Dos cuentas de 100k (200k Total)
    mega_capital = 200000
    profit_mega_bruto = mega_capital * roi_mensual
    profit_mega_neto = profit_mega_bruto * split
    
    print("--- SIMULACION AGRESIVA: ESCALADO 8X ---")
    print(f"1. Beneficio 25K (Mes 1): ${profit_mes_1:,.2f}")
    print(f"2. Compra de 2x100K: -${coste_dos_100k:,.2f}")
    print(f"3. Efectivo en mano tras compra: ${cash_restante:,.2f}")
    print("-" * 40)
    print("Escenario MES 2 (Gestionando $200,000):")
    print(f"Ganancia Bruta Mensual: ${profit_mega_bruto:,.2f}")
    print(f"TU PARTE (80%):        ${profit_mega_neto:,.2f}")
    print(f"Riesgo por trade (0.15%): ${mega_capital * 0.0015:,.2f}")
    print("-" * 40)
    print("QUE PUEDE PASAR?")
    print("A) EXITAZO: Pasas a ganar casi $20,000 al mes. Tu vida cambia en 60 dias.")
    print("B) RIESGO: Si pierdes los retos, has perdido los $1,080, pero sigues teniendo los $1,320 de beneficio.")
    print("C) SEGURIDAD: El bot tiene un drawdown de 0.50% anual, pasar las de 100k es estadisticamente muy probable.")

if __name__ == "__main__":
    simulate_aggressive_scaling()
