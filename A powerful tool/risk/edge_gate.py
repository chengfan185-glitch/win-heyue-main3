# risk/edge_gate.py
# Small focused edge_cost_gate with cost breakdown logging
# - Computes gross_edge_pct, fee_estimate, net_expected_edge
# - Returns a dict used by runner; when net_expected_edge <= 0:
#   prints a clear cost decomposition to help immediate triage.
#
# Wide entry option:
# - Allow small negative net edge to go through as PROBE (small size),
#   so we can collect real samples; strict exit is handled by TP/SL/timeout.

from __future__ import annotations

from typing import Dict, Any
import os

print("🔥 LOADED EdgeGate V1 (cost model) FROM:", __file__)

# Example fees (adjust to your exchange account/tiers)
DEFAULT_TAKER_FEE_PCT = float(os.getenv("TAKER_FEE_PCT", "0.0004"))   # 0.04%
DEFAULT_MAKER_FEE_PCT = float(os.getenv("MAKER_FEE_PCT", "0.0002"))   # 0.02%
DEFAULT_SLIPPAGE_PCT = float(os.getenv("SLIPPAGE_PCT", "0.0005"))     # 0.05% estimated slippage


def edge_cost_gate(predicted_edge_pct: float, use_taker: bool = True) -> Dict[str, Any]:
    """
    Given predicted edge (decimal fraction, e.g. 0.01 for 1%),
    compute gross_edge_pct, fee_estimate, net_expected_edge and return details.

    Return dict keys (runner-friendly):
    - ok: bool
    - probe: bool
    - decision_hint: str
    - predicted_edge_pct / fee_pct / fee_estimate / net_expected_edge: float
    """
    # gross edge is prediction before costs
    gross_edge_pct = float(predicted_edge_pct)

    fee_pct = DEFAULT_TAKER_FEE_PCT if use_taker else DEFAULT_MAKER_FEE_PCT
    # total trading cost (entry + exit) roughly 2*fee + expected slippage
    fee_estimate = 2.0 * fee_pct + DEFAULT_SLIPPAGE_PCT

    # net expected edge after subtracting fees/slippage
    net_expected_edge = gross_edge_pct - fee_estimate

    # Wide entry: allow small negative net edge to go through as PROBE (small size)
    ALLOW_NEG_EDGE_PROBE = os.getenv("ALLOW_NEG_EDGE_PROBE", "true").lower() == "true"
    NEG_EDGE_PROBE = float(os.getenv("NEG_EDGE_PROBE", "-0.0008"))  # -0.08% default trial threshold

    result: Dict[str, Any] = {
        "ok": False,
        "probe": False,
        "predicted_edge_pct": gross_edge_pct,
        "fee_pct": fee_pct,
        "fee_estimate": fee_estimate,
        "net_expected_edge": net_expected_edge,
        "decision_hint": None,
    }

    # Decision + logging
    if net_expected_edge <= 0:
        result["decision_hint"] = "NON_POSITIVE_NET_EDGE"

        # print cost decomposition for diagnostics
        print("=== EdgeGate Cost Breakdown ===")
        print(f"predicted_edge_pct: {gross_edge_pct:.6f}")
        print(f"fee_pct (per side): {fee_pct:.6f}")
        print(f"fee_estimate (entry+exit+slippage): {fee_estimate:.6f}")
        print(f"net_expected_edge: {net_expected_edge:.6f}  --> NON-POSITIVE")

        # If only slightly negative, allow PROBE to proceed (wide entry)
        if ALLOW_NEG_EDGE_PROBE and net_expected_edge >= NEG_EDGE_PROBE:
            result["ok"] = True
            result["probe"] = True
            result["decision_hint"] = "NEG_EDGE_PROBE_ALLOWED"
            print(f"--> PROBE allowed (net_edge={net_expected_edge:.6f} >= {NEG_EDGE_PROBE:.6f})")
        else:
            # Too negative: block
            result["ok"] = False
            result["probe"] = False
            result["decision_hint"] = "BLOCK_BY_COST_TOO_NEGATIVE"
            print("--> BLOCK by cost (too negative)")

        print("================================")
    else:
        # Positive net edge: allow
        result["ok"] = True
        result["probe"] = False
        result["decision_hint"] = "POSITIVE_NET_EDGE"
        # print lightweight diagnostics for visibility
        print(f"[EdgeGate] predicted={gross_edge_pct:.6f} fee_est={fee_estimate:.6f} net={net_expected_edge:.6f}")

    return result
