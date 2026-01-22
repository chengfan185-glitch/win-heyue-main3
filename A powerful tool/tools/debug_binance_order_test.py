#!/usr/bin/env python3
"""
Debug helper: validate a Binance USDT-M market order parameters using the
/order/test endpoint (does NOT create a real order).

Usage:
  - Ensure your .env is in project root with BINANCE_API_KEY and BINANCE_API_SECRET.
  - Recommended: install python-dotenv:
      py -m pip install python-dotenv
  - Run:
      python tools/debug_binance_order_test.py
  - Optional args:
      --symbol SYMBOL (default ETHUSDT)
      --side SIDE (BUY/SELL) (default BUY)
      --quantity QTY (base asset quantity, e.g. 0.007)
      --quote_quote QUOTE (quoteOrderQty, e.g. 50)
      --use-server-time (force server time when signing for this test)
      --debug (enable adapter debug logging)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import traceback

# Load .env automatically
try:
    from dotenv import load_dotenv

    load_dotenv()  # loads .env from cwd
except Exception:
    # dotenv not installed; ok if env already set in shell
    pass

# Ensure project root on sys.path so execution package can be imported
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests

# Import adapter
try:
    from execution.adapters.binance_um_futures import BinanceUMFuturesAdapter
except Exception as e:
    print("Failed to import BinanceUMFuturesAdapter:", e)
    traceback.print_exc()
    raise

def mask(s: str, head: int = 4, tail: int = 4) -> str:
    if not s:
        return "<empty>"
    if len(s) <= head + tail + 2:
        return s[:head] + "..." + s[-tail:]
    return s[:head] + "..." + s[-tail:]

def print_exchange_info(symbol: str):
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        r = requests.get(url, params={"symbol": symbol}, timeout=10)
        r.raise_for_status()
        j = r.json()
        print(f"\n=== exchangeInfo for {symbol} ===")
        print(json.dumps(j, indent=2)[:4000])  # cap output
        # Helpful quick filters
        try:
            s = j.get("symbols", [])[0]
            print("\n--- Relevant filters ---")
            for f in s.get("filters", []):
                if f.get("filterType") in ("LOT_SIZE", "MIN_NOTIONAL", "MARKET_LOT_SIZE"):
                    print(json.dumps(f, indent=2))
        except Exception:
            pass
    except Exception as e:
        print("Failed to fetch exchangeInfo:", repr(e))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="ETHUSDT")
    parser.add_argument("--side", default="BUY", choices=["BUY", "SELL"])
    parser.add_argument("--quantity", type=float, default=0.007)
    parser.add_argument("--quote_quantity", type=float, default=None)
    parser.add_argument("--use-server-time", action="store_true", help="Use serverTime for signing in this test")
    parser.add_argument("--debug", action="store_true", help="Enable adapter debug prints")
    args = parser.parse_args()

    print(f"Project root: {ROOT}")
    print(f"Symbol={args.symbol} side={args.side} quantity={args.quantity} quote_quantity={args.quote_quantity}")

    # Instantiate adapter
    a = BinanceUMFuturesAdapter(trading_mode="live", enable_real=True)
    # Toggle adapter debug if requested and adapter exposes _debug
    try:
        if args.debug:
            setattr(a, "_debug", True)
        print("adapter api_key:", mask(getattr(a, "api_key", None)))
    except Exception:
        pass

    # Print connection / time sync info
    try:
        ok = a.test_connection()
        print("test_connection:", ok)
        if hasattr(a, "_ts"):
            print("adapter _ts():", a._ts())
        # Force refresh dual-side detection
        try:
            dual = a.is_dual_side_enabled(refresh=True)
            print("is_dual_side_enabled:", dual)
        except Exception as ex:
            print("is_dual_side_enabled() failed:", ex)
    except Exception as e:
        print("test_connection failed:", e)
        traceback.print_exc()

    # Print exchange info (local public query)
    print_exchange_info(args.symbol)

    # Prepare order/test params
    params = {
        "symbol": args.symbol,
        "side": args.side,
        "type": "MARKET",
        "reduceOnly": "false",
    }
    if args.quote_quantity is not None:
        params["quoteOrderQty"] = str(args.quote_quantity)
    else:
        params["quantity"] = str(args.quantity)

    print("\nPrepared params (for /fapi/v1/order/test):")
    print(json.dumps(params, indent=2))

    # Optionally, show qs/signature that will be sent (masked)
    try:
        # Prefer adapter helper if available
        if hasattr(a, "_build_qs_and_signature"):
            qs, sig = a._build_qs_and_signature(params, use_server_time=args.use_server_time)
            print("\nBuilt QS preview (first 400 chars):")
            print(qs[:400])
            print("Signature (masked):", mask(sig, 6, 6))
        else:
            print("\nAdapter has no _build_qs_and_signature helper; proceeding to call _request directly.")
    except Exception as e:
        print("Failed to build qs/signature:", e)

    # Call order test (safe)
    print("\nCalling /fapi/v1/order/test ... (this will NOT place a real order)")
    try:
        res = a._request("POST", "/fapi/v1/order/test", params)
        print("Order test succeeded. Response:")
        print(json.dumps(res, indent=2) if isinstance(res, (dict, list)) else str(res))
    except Exception as e:
        print("Order test failed with exception:", repr(e))
        # Try to extract response body if available
        try:
            resp = getattr(e, "response", None)
            if resp is not None:
                print("HTTP response status:", getattr(resp, "status_code", None))
                try:
                    text = resp.text
                    print("HTTP response text (full):")
                    print(text)
                except Exception:
                    print("Could not read response.text")
        except Exception:
            pass

        # As last resort, show stack
        traceback.print_exc()

if __name__ == "__main__":
    main()