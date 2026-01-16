# ===============================
# Real Market Friction Config
# ===============================

TAKER_FEE_PCT = 0.0004      # 0.04%
MAKER_FEE_PCT = 0.0002      # 0.02%
EST_SLIPPAGE_PCT = 0.0002  # 0.02%
SAFETY_MARGIN_PCT = 0.0002 # 0.02%

MIN_NET_EDGE_PCT = (
    TAKER_FEE_PCT +
    EST_SLIPPAGE_PCT +
    SAFETY_MARGIN_PCT
)
# ~= 0.0008 (0.08%)
