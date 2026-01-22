# -*- coding: utf-8 -*-
"""
scripts/guard_close_once.py

One-shot position guard: close position when TP/SL/timeout hit.

Usage (PowerShell examples):

# 1) Dry-run (only prints decision, no close)
$env:DRY_RUN="1"
python scripts/guard_close_once.py --symbol SOLUSDT --side SHORT

# 2) Real close when triggered
Remove-Item Env:DRY_RUN -ErrorAction SilentlyContinue
$env:TAKE_PROFIT_PCT="0.0045"
$env:STOP_LOSS_PCT="0.0025"
$env:MAX_HOLD_MINUTES="45"
python scripts/guard_close_once.py --symbol SOLUSDT --side SHORT

# 3) If you want it to always close immediately for testing:
$env:FORCE_CLOSE="1"
python scripts/guard_close_once.py --symbol SOLUSDT --side SHORT
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

# Your adapter
from execution.adapters.binance_um_futures import BinanceUMFuturesAdapter


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return float(v)
    except Exception:
        return default


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(float(v))
    except Exception:
        return default


def _pick_position_row(pr: List[Dict[str, Any]], side: str) -> Optional[Dict[str, Any]]:
    """
    Binance futures hedge mode returns two rows: LONG + SHORT.
    One-way mode usually returns BOTH (or may still show LONG/SHORT with 0).

    We choose the row matching requested side and non-zero positionAmt.
    """
    side_u = side.upper().strip()
    candidates = []
    for row in pr or []:
        if str(row.get("positionSide", "")).upper() != side_u:
            continue
        try:
            amt = float(row.get("positionAmt", 0) or 0)
        except Exception:
            amt = 0.0
        if amt != 0.0:
            candidates.append(row)

    if candidates:
        return candidates[0]

    # fallback: if user asked BOTH or if hedge info isn't present, try any non-zero
    if side_u == "BOTH":
        for row in pr or []:
            try:
                amt = float(row.get("positionAmt", 0) or 0)
            except Exception:
                amt = 0.0
            if amt != 0.0:
                return row

    return None


def _calc_pnl_pct(position_side: str, entry: float, mark: float) -> float:
    """
    PNL% based on mark vs entry.
    LONG: (mark-entry)/entry
    SHORT: (entry-mark)/entry
    """
    if entry <= 0:
        return 0.0
    ps = position_side.upper().strip()
    if ps == "SHORT":
        return (entry - mark) / entry
    # default LONG
    return (mark - entry) / entry


def _minutes_since_ms(ts_ms: int) -> float:
    if ts_ms <= 0:
        return 0.0
    return (time.time() * 1000 - ts_ms) / 60000.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True, help="e.g. SOLUSDT")
    ap.add_argument("--side", default="SHORT", help="LONG or SHORT (hedge mode). Default SHORT.")
    args = ap.parse_args()

    symbol = str(args.symbol).upper().strip()
    side = str(args.side).upper().strip()

    trading_mode = str(os.getenv("TRADING_MODE", "paper")).lower().strip()
    enable_real = _env_bool("ENABLE_REAL_TRADING", False) or _env_bool("ENABLE_REAL", False)

    take_profit_pct = _env_float("TAKE_PROFIT_PCT", 0.0045)
    stop_loss_pct = _env_float("STOP_LOSS_PCT", 0.0025)
    max_hold_minutes = _env_int("MAX_HOLD_MINUTES", 45)

    dry_run = _env_bool("DRY_RUN", False)
    force_close = _env_bool("FORCE_CLOSE", False)

    print("============================================================")
    print("GuardCloseOnce")
    print("============================================================")
    print(f"symbol={symbol} side={side}")
    print(f"TRADING_MODE={trading_mode} enable_real={enable_real}")
    print(f"TP={take_profit_pct:.6f} SL={stop_loss_pct:.6f} MAX_HOLD_MIN={max_hold_minutes}")
    print(f"DRY_RUN={dry_run} FORCE_CLOSE={force_close}")

    a = BinanceUMFuturesAdapter(trading_mode=trading_mode, enable_real=enable_real)

    # Pull position risk rows
    try:
        pr = a.get_position_risk(symbol)
    except Exception as e:
        print(f"[ERROR] get_position_risk failed: {e}")
        return 2

    row = _pick_position_row(pr, side)
    if not row:
        print("[OK] No non-zero position found for requested side. Nothing to do.")
        return 0

    try:
        position_amt = float(row.get("positionAmt", 0) or 0)
    except Exception:
        position_amt = 0.0

    position_side = str(row.get("positionSide", side)).upper().strip()
    try:
        entry = float(row.get("entryPrice", 0) or 0)
    except Exception:
        entry = 0.0
    try:
        mark = float(row.get("markPrice", 0) or 0)
    except Exception:
        mark = 0.0
    try:
        u_pnl = float(row.get("unRealizedProfit", 0) or 0)
    except Exception:
        u_pnl = 0.0

    update_ms = 0
    try:
        update_ms = int(row.get("updateTime", 0) or 0)
    except Exception:
        update_ms = 0

    pnl_pct = _calc_pnl_pct(position_side, entry, mark)
    hold_min = _minutes_since_ms(update_ms)

    print("------------------------------------------------------------")
    print(f"positionSide={position_side} positionAmt={position_amt}")
    print(f"entryPrice={entry} markPrice={mark}")
    print(f"unRealizedProfit={u_pnl}  pnl_pct={pnl_pct:.6f}  hold_min~={hold_min:.2f}")
    print("------------------------------------------------------------")

    # Decide
    reason = None
    if force_close:
        reason = "force_close"
    elif pnl_pct >= take_profit_pct:
        reason = f"take_profit_hit (pnl_pct={pnl_pct:.6f} >= {take_profit_pct:.6f})"
    elif pnl_pct <= -abs(stop_loss_pct):
        reason = f"stop_loss_hit (pnl_pct={pnl_pct:.6f} <= {-abs(stop_loss_pct):.6f})"
    elif max_hold_minutes > 0 and hold_min >= float(max_hold_minutes):
        reason = f"timeout_hit (hold_min~={hold_min:.2f} >= {max_hold_minutes})"

    if not reason:
        print("[OK] Guard condition not triggered. No close executed.")
        return 0

    print(f"[TRIGGER] {reason}")

    if dry_run:
        print("[DRY_RUN] Would close position now. Exiting.")
        return 0

    # Execute close
    try:
        res = a.close_position(symbol, position_side=position_side)  # position_side must be LONG/SHORT in hedge
    except Exception as e:
        print(f"[ERROR] close_position failed: {e}")
        return 3

    # Print receipt
    try:
        print("[CLOSE_RESULT]", asdict(res))
    except Exception:
        print("[CLOSE_RESULT]", res)

    # Confirm closed (poll a few times)
    for i in range(10):
        try:
            pos = [p for p in a.get_positions() if str(p.symbol).upper() == symbol]
        except Exception:
            pos = []
        if not pos:
            print("[CONFIRMED] Position closed (get_positions empty).")
            return 0
        time.sleep(0.5)

    print("[WARN] Position still appears open after polling. Please check manually:")
    try:
        print(a.get_position_risk(symbol))
    except Exception:
        pass
    return 1


if __name__ == "__main__":
    sys.exit(main())
