
import pandas as pd

df = pd.read_csv("full_trades_log.csv")
df["time"] = pd.to_datetime(df["time"])
df["month"] = df["time"].dt.to_period("M")

# Crear reporte mensual
monthly = df.groupby("month").agg(
    trades=("pnl", "count"),
    pnl=("pnl", "sum"),
    wins=("pnl", lambda x: (x > 0).sum())
).reset_index()

monthly["wr"] = (monthly["wins"] / monthly["trades"] * 100).round(1)
monthly["pnl_pct"] = (monthly["pnl"] / 100000 * 100).round(2)

print("--- FULL ANNUAL REPORT (MONTH BY MONTH) ---")
print(monthly.to_string(index=False))

# Analisis de meses dificiles
neg_months = monthly[monthly["pnl"] < 0]
if not neg_months.empty:
    print("\n--- DIFFICULT MONTHS ANALYSIS ---")
    for _, row in neg_months.iterrows():
        print(f"Month {row['month']}: Loss ${abs(row['pnl']):.2f} ({row['pnl_pct']}%) in {row['trades']} trades.")
        
total_pnl = df["pnl"].sum()
print(f"\nFinal Balance Change: ${total_pnl:,.2f} ({(total_pnl/100000)*100:+.2f}%)")
