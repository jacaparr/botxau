import MetaTrader5 as mt5

def diagnose():
    if not mt5.initialize():
        print(f"FAILED: Connection to MT5 failed: {mt5.last_error()}")
        return

    print("--- MT5 DIAGNOSTIC ---")
    
    # Terminal Info
    t_info = mt5.terminal_info()
    if t_info:
        print(f"Terminal: {t_info.name} ({t_info.company})")
        print(f"Trade Allowed (Terminal): {t_info.trade_allowed}")
    
    # Account Info
    a_info = mt5.account_info()
    if a_info:
        print(f"\nAccount: {a_info.login} ({a_info.server})")
        print(f"Trade Allowed (Account): {a_info.trade_allowed}")
        print(f"Expert Trading Allowed: {a_info.trade_expert}")
    
    # Symbol Info (XAUUSD)
    aliases = ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "GOLD.a"]
    found_symbol = None
    for s in aliases:
        if mt5.symbol_info(s):
            found_symbol = s
            break
            
    if found_symbol:
        s_info = mt5.symbol_info(found_symbol)
        print(f"\nSymbol: {found_symbol}")
        print(f"Trade Mode: {s_info.trade_mode} (4 = FULL)")
        
        # Filling Modes Bitmask
        fm = s_info.filling_mode
        print(f"Filling Mode Bitmask: {fm}")
        modes = []
        if fm & 1: modes.append("FOK")
        if fm & 2: modes.append("IOC")
        if fm & 4: modes.append("BOC")
        print(f"Supported Modes: {', '.join(modes)}")
    else:
        print("\nSymbol XAUUSD not found.")

    mt5.shutdown()

if __name__ == "__main__":
    diagnose()
