# -*- coding: utf-8 -*-
"""
scripts/import_exchange_positions_v2.py (v2.1)

Read Binance UM futures open positions via existing adapter,
append OPEN records into logs/ledger/positions.jsonl using the same schema
your ledger already uses (NO entry_features field).
"""

from __future__ import annotations

import os
import sys
import json
import time
import uuid
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _utc_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _load_open_symbols(pos_file: Path) -> set[str]:
    """
    Parse positions.jsonl and return symbols that are currently OPEN
    (based on the latest record per position_id).
    """
    if not pos_file.exists():
        return set()
    latest: Dict[str, Dict[str, Any]] = {}
    with open(pos_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            pid = obj.get("position_id")
            if not pid:
                continue
            latest[pid] = obj
    open_symbols = set()
    for obj in latest.values():
        if obj.get("status") == "OPEN":
            sym = obj.get("symbol")
            if sym:
                open_symbols.add(str(sym))
    return open_symbols


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default="logs/ledger", help="ledger base dir (default: logs/ledger)")
    parser.add_argument("--dry-run", action="store_true", help="only print exchange open positions, do not write ledger")
    parser.add_argument("--overwrite", action="store_true", help="if symbol already OPEN locally, still append a new OPEN record")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))

    # load .env if present
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(dotenv_path=str(root / ".env"))
    except Exception:
        pass

    trading_mode = os.getenv("TRADING_MODE", "live").strip().lower()
    enable_real = _truthy(os.getenv("ENABLE_REAL_TRADING")) or _truthy(os.getenv("ENABLE_REAL"))

    if trading_mode != "live" or not enable_real:
        print(f"[IMPORT_V2.1] Refuse to run: TRADING_MODE={trading_mode} ENABLE_REAL={enable_real}")
        print("[IMPORT_V2.1] Please set TRADING_MODE=live and ENABLE_REAL_TRADING=true (or ENABLE_REAL=true).")
        return 2

    from execution.adapters.binance_um_futures import BinanceUMFuturesAdapter

    adapter = BinanceUMFuturesAdapter(
        trading_mode=trading_mode,
        enable_real=True,
        base_url=os.getenv("BINANCE_FUTURES_BASE_URL") or "https://fapi.binance.com",
        api_key=os.getenv("BINANCE_API_KEY") or os.getenv("API_KEY"),
        api_secret=os.getenv("BINANCE_API_SECRET") or os.getenv("API_SECRET"),
        timeout=int(os.getenv("BINANCE_TIMEOUT", "15")),
    )

    raw_positions: List[Dict[str, Any]] = adapter.fetch_open_positions()
    raw_positions = list(raw_positions or [])

    nonzero: List[Dict[str, Any]] = []
    for p in raw_positions:
        try:
            amt = float(p.get("positionAmt", 0) or 0)
        except Exception:
            amt = 0.0
        if amt != 0:
            nonzero.append(p)

    symbols = [str(p.get("symbol", "")).strip() for p in nonzero if str(p.get("symbol", "")).strip()]
    print(f"[IMPORT_V2.1] Exchange nonzero positions: {len(nonzero)} | symbols={symbols}")

    if args.dry_run:
        print("[IMPORT_V2.1] dry-run: no ledger write (will still compute local OPEN + plan).")

    ledger_dir = (root / args.base_dir)
    ledger_dir.mkdir(parents=True, exist_ok=True)
    pos_file = ledger_dir / "positions.jsonl"
    import_dir = ledger_dir / "_imports"
    import_dir.mkdir(parents=True, exist_ok=True)

    # latest-by-symbol scan (align with TradeLedger: last record per symbol wins)
    latest_by_symbol = {}
    if pos_file.exists():
        with open(pos_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                sym0 = obj.get("symbol")
                if sym0:
                    latest_by_symbol[str(sym0)] = obj

    open_symbols_local = {s for s, o in latest_by_symbol.items() if o.get("status") == "OPEN"}

    print(f"[IMPORT_V2.1] Local OPEN symbols (from ledger): {sorted(open_symbols_local)}")

    written = 0
    now_ts = time.time()
    now_iso = _utc_iso(now_ts)

    with open(pos_file, "a", encoding="utf-8") as f:
        for p in nonzero:
            sym = str(p.get("symbol", "")).strip()
            if not sym:
                continue

            if (sym in open_symbols_local) and (not args.overwrite):
                print(f"[IMPORT_V2.1] skip {sym}: already OPEN locally (use --overwrite to force append)")
                continue

            position_amt = float(p.get("positionAmt", 0) or 0)
            side = "LONG" if position_amt > 0 else "SHORT"
            qty = abs(position_amt)

            entry_price = float(p.get("entryPrice", 0) or 0)
            leverage = int(float(p.get("leverage", 1) or 1))
            margin_type = str(p.get("marginType", "ISOLATED"))
            unreal = float(p.get("unRealizedProfit", 0) or 0)

            # basic protective defaults (you can adjust later)
            if entry_price > 0:
                if side == "LONG":
                    stop_loss = entry_price * (1 - 0.01)
                    take_profit = entry_price * (1 + 0.02)
                else:
                    stop_loss = entry_price * (1 + 0.01)
                    take_profit = entry_price * (1 - 0.02)
            else:
                stop_loss = None
                take_profit = None

            record = {
                "position_id": f"pos_external_{sym}_{uuid.uuid4().hex}",
                "symbol": sym,
                "side": side,
                "quantity": qty,
                "entry_price": entry_price,
                "current_price": entry_price,
                "leverage": leverage,
                "margin_type": margin_type,
                "unrealized_pnl": unreal,
                "realized_pnl": 0.0,
                "stop_loss_price": stop_loss,
                "take_profit_price": take_profit,
                "trailing_stop_pct": None,
                "highest_price_since_entry": None,
                "opened_at": now_ts,
                "closed_at": None,
                "status": "OPEN",
                "open_order_id": "EXTERNAL_IMPORT",
                "close_order_id": None,
                "run_id": "external_import",
                "opened_at_iso": now_iso,
            }
            if args.dry_run:
                print(f"[IMPORT_V2.1] dry-run: would append OPEN -> {sym} {side} qty={qty}")
                continue
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
            print(f"[IMPORT_V2.1] appended OPEN -> {sym} {side} qty={qty}")

    report = {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "exchange_nonzero_count": len(nonzero),
        "written": written,
        "symbols": symbols,
        "overwrite": bool(args.overwrite),
        "positions_file": str(pos_file),
    }
    report_path = import_dir / f"import_report_{int(time.time())}.json"
    with open(report_path, "w", encoding="utf-8") as rf:
        json.dump(report, rf, ensure_ascii=False, indent=2)

    print(f"[IMPORT_V2.1] DONE. written={written} report={report_path}")
    print("[IMPORT_V2.1] Next: restart runner to re-run reconciliation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
