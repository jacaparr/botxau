"""Quick results script"""
import MetaTrader5 as mt5
mt5.initialize()
from backtest_mt5 import SYMBOLS_TO_TEST, run_backtest, CAPITAL

days = 180
print("SYMBOL     | TRADES | WR%  | PnL%    | /MES   | MaxDD  | PF   | ADD?")
print("-" * 75)

for s, c in SYMBOLS_TO_TEST.items():
    info = mt5.symbol_info(s)
    if not info:
        print(f"{s:10} | NOT AVAILABLE")
        continue
    if not info.visible:
        mt5.symbol_select(s, True)

    trades = run_backtest(s, c, days)
    if not trades:
        print(f"{s:10} | NO TRADES")
        continue

    wins = [t for t in trades if t.result == "WIN"]
    losses = [t for t in trades if t.result == "LOSS"]
    pnl = sum(t.pnl_usd for t in trades)
    wr = len(wins) / len(trades) * 100
    loss_sum = sum(t.pnl_usd for t in losses)
    pf = abs(sum(t.pnl_usd for t in wins) / loss_sum) if loss_sum != 0 else 999
    pp = pnl / CAPITAL * 100
    mo = pp / (days / 30)

    eq, pk, mdd = CAPITAL, CAPITAL, 0
    for t in trades:
        eq += t.pnl_usd
        pk = max(pk, eq)
        mdd = max(mdd, (pk - eq) / pk * 100)

    verdict = "YES" if pnl > 0 and wr > 45 and mdd < 5 else "NO"
    print(f"{s:10} | {len(trades):>6} | {wr:>4.0f} | {pp:>+7.1f} | {mo:>+5.1f}% | {mdd:>5.1f}% | {pf:>4.1f} | {verdict}")

mt5.shutdown()
