#!/usr/bin/env python3
"""
快速校验 TP/SL 计算是否符合预期，不依赖完整 runner。
"""

import os

def calc_tp_sl(entry_price: float, side: str, sl_pct: float, tp_pct: float):
    side = side.upper()
    if side == "LONG":
        sl = entry_price * (1 - sl_pct)
        tp = entry_price * (1 + tp_pct)
    elif side == "SHORT":
        sl = entry_price * (1 + sl_pct)
        tp = entry_price * (1 - tp_pct)
    else:
        raise ValueError("side must be LONG or SHORT")
    return sl, tp

def main():
    sl_pct = float(os.getenv("STOP_LOSS_PCT", "0.006"))
    tp_pct = float(os.getenv("TAKE_PROFIT_PCT", "0.010"))
    print(f"Using STOP_LOSS_PCT={sl_pct}, TAKE_PROFIT_PCT={tp_pct}")

    for entry in (50000.0, 2000.0):
        for side in ("LONG", "SHORT"):
            sl, tp = calc_tp_sl(entry, side, sl_pct, tp_pct)
            print(f"{side} entry={entry:.2f} -> SL={sl:.2f}, TP={tp:.2f}")

if __name__ == "__main__":
    main()
