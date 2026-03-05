
import sys

# Try different encodings
encodings = ['utf-16le', 'utf-8', 'cp1252']

for enc in encodings:
    try:
        with open(r'C:\Users\jach1\.gemini\antigravity\scratch\futures-bot\safety_results_final.txt', 'r', encoding=enc) as f:
            for line in f:
                if any(x in line for x in ["Riesgo", "Final", "Drawdown", "OBJETIVO", "CUENTA"]):
                    print(line.strip())
    except Exception as e:
        print(f"Failed with {enc}: {e}")
