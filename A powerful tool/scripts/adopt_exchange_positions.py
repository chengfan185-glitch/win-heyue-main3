"""Adopt Binance exchange open positions into local ledger.

Why:
- If the bot was stopped (Ctrl+C) or logs were cleaned, the exchange may still have real open positions.
- Reconciliation will switch to CLOSE_ONLY until local ledger and exchange are aligned.

This script writes a single OPEN snapshot per symbol into logs/ledger/positions.jsonl,
so the bot can resume and manage/exit these positions deterministically.

Usage:
  python scripts/adopt_exchange_positions.py
  python -m scripts.adopt_exchange_positions

Environment:
  TRADING_MODE=live
  ENABLE_REAL_TRADING=true
  (Your usual Binance API env vars must be present.)

Optional:
  AUTO_ADOPT_OVERWRITE=true   # overwrite existing local OPEN record for same symbol
"""

import os
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path when run as a file.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.ledger import Ledger  # alias to TradeLedger
from execution.adapters.binance_um_futures import BinanceUMFuturesAdapter


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def main() -> None:
    print("\n🔧 Adopt exchange positions → local ledger")

    trading_mode = os.environ.get("TRADING_MODE", "paper")
    enable_real = _truthy(os.environ.get("ENABLE_REAL_TRADING", "false"))

    if trading_mode != "live" or not enable_real:
        print(
            "⚠️  Warning: TRADING_MODE!=live or ENABLE_REAL_TRADING!=true. "
            "You may be reading PAPER mode positions (likely empty)."
        )

    overwrite = _truthy(os.environ.get("AUTO_ADOPT_OVERWRITE", "false"))

    adapter = BinanceUMFuturesAdapter()
    ledger = Ledger(run_id=f"adopt_{int(time.time())}")

    print("🔍 Fetching exchange open positions...")
    raw_positions = adapter.fetch_open_positions()

    if not raw_positions:
        print("✅ No open positions on exchange (or adapter in paper mode).")
        return

    res = ledger.adopt_exchange_positions_raw(raw_positions, source="manual_adopt", overwrite=overwrite)

    print("\n🎯 Adopt completed")
    print(f"- adopted: {res['adopted']}")
    print(f"- skipped: {res['skipped']}")
    print(f"- positions_path: {ledger.positions_path}")


if __name__ == "__main__":
    main()
