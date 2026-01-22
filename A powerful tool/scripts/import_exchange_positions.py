# -*- coding: utf-8 -*-
"""
scripts/import_exchange_positions_v2.py

One-click: read current Binance UM futures open positions via existing adapter
-> adopt into local ledger (positions.jsonl) as OPEN
-> mark entry_features.source = external_import (or custom source)

Why:
- If exchange has open positions but local ledger doesn't recognize them,
  reconciliation will enter CLOSE_ONLY forever.
- This script makes local ledger "recognize" those positions so matches can happen.

Usage:
  python scripts/import_exchange_positions_v2.py
  python scripts/import_exchange_positions_v2.py --dry-run
  python scripts/import_exchange_positions_v2.py --overwrite
  python scripts/import_exchange_positions_v2.py --source external_import

Notes:
- Requires TRADING_MODE=live and ENABLE_REAL_TRADING=true (or ENABLE_REAL=true)
- Requires BINANCE_API_KEY / BINANCE_API_SECRET configured (same as runner)
"""

from __future__ import annotations

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default="logs/ledger", help="ledger base dir (default: logs/ledger)")
    parser.add_argument("--source", default="external_import", help="entry_features.source value")
    parser.add_argument("--overwrite", action="store_true", help="overwrite existing local OPEN positions for same symbol")
    parser.add_argument("--dry-run", action="store_true", help="only print exchange open positions, do not write ledger")
    args = parser.parse_args()

    # Ensure repo root on sys.path (so imports work when executed from scripts/)
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    # Load .env if present
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(dotenv_path=str(root / ".env"))
    except Exception:
        # dotenv is optional; env vars may already exist
        pass

    trading_mode = os.getenv("TRADING_MODE", "live").strip().lower()
    enable_real = _truthy(os.getenv("ENABLE_REAL_TRADING")) or _truthy(os.getenv("ENABLE_REAL"))

    if trading_mode != "live" or not enable_real:
        print(f"[IMPORT_V2] Refuse to run: TRADING_MODE={trading_mode} ENABLE_REAL={enable_real}")
        print("[IMPORT_V2] Please set TRADING_MODE=live and ENABLE_REAL_TRADING=true (or ENABLE_REAL=true) in .env")
        return 2

    # Import project modules
    from execution.adapters.binance_um_futures import BinanceUMFuturesAdapter
    from core.ledger.trade_ledger import TradeLedger

    # Init adapter (same env keys as runner)
    adapter = BinanceUMFuturesAdapter(
        trading_mode=trading_mode,
        enable_real=True,
        base_url=os.getenv("BINANCE_FUTURES_BASE_URL") or "https://fapi.binance.com",
        api_key=os.getenv("BINANCE_API_KEY") or os.getenv("API_KEY"),
        api_secret=os.getenv("BINANCE_API_SECRET") or os.getenv("API_SECRET"),
        timeout=int(os.getenv("BINANCE_TIMEOUT", "15")),
    )

    # Fetch exchange open positions (raw positionRisk dicts)
    try:
        raw_positions: List[Dict[str, Any]] = adapter.fetch_open_positions()
    except Exception as e:
        print(f"[IMPORT_V2] Fetch exchange positions failed: {e}")
        return 3

    # Normalize list
    raw_positions = list(raw_positions or [])
    nonzero = []
    for p in raw_positions:
        try:
            amt = float(p.get("positionAmt", 0) or 0)
        except Exception:
            amt = 0.0
        if amt != 0:
            nonzero.append(p)

    symbols = [str(p.get("symbol", "")).strip() for p in nonzero if str(p.get("symbol", "")).strip()]
    print(f"[IMPORT_V2] Exchange nonzero positions: {len(nonzero)} | symbols={symbols}")

    if args.dry_run:
        print("[IMPORT_V2] dry-run: no ledger write.")
        return 0

    # Init ledger and adopt
    ledger = TradeLedger(base_dir=args.base_dir)
    adopted = ledger.adopt_exchange_positions_raw(
        nonzero,
        source=args.source,
        overwrite=bool(args.overwrite),
    )

    # Write report
    report_dir = Path(args.base_dir) / "_imports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "ledger_run_id": getattr(ledger, "run_id", None),
        "source": args.source,
        "overwrite": bool(args.overwrite),
        "exchange_nonzero_count": len(nonzero),
        "adopted_count": adopted,
        "symbols": symbols,
    }
    report_path = report_dir / f"import_report_{int(time.time())}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[IMPORT_V2] Adopted into ledger: {adopted}")
    print(f"[IMPORT_V2] Report: {report_path}")
    print("[IMPORT_V2] Next: restart runner to re-run reconciliation (should exit CLOSE_ONLY if matches).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
