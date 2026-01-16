# risk/edge_gate.py

import os

TAKER_FEE_PCT = float(os.getenv("TAKER_FEE_PCT", "0.0004"))
EST_SLIPPAGE_PCT = float(os.getenv("EST_SLIPPAGE_PCT", "0.0002"))
SAFETY_MARGIN_PCT = float(os.getenv("SAFETY_MARGIN_PCT", "0.0002"))

MIN_NET_EDGE_PCT = (
    TAKER_FEE_PCT
    + EST_SLIPPAGE_PCT
    + SAFETY_MARGIN_PCT
)

def edge_cost_gate(predicted_edge_pct: float):
    """
    判断预测 edge 是否覆盖真实交易成本
    """
    gross_edge = predicted_edge_pct
    fee_pct = TAKER_FEE_PCT
    slippage_pct = EST_SLIPPAGE_PCT

    net_expected_edge = gross_edge - fee_pct - slippage_pct
    passed = net_expected_edge >= MIN_NET_EDGE_PCT

    return {
        "passed": passed,
        "gross_edge_pct": gross_edge,
        "net_expected_edge": net_expected_edge,
        "min_required": MIN_NET_EDGE_PCT,
    }
