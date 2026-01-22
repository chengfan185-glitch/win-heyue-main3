

"""
EdgeGate v2 - PROBE Position Mechanism

Implements a 3-state gating system (BLOCK/PROBE/FULL) to allow weak positive expectation
trades with small positions while maintaining the Edge baseline.

States:
- BLOCK: No trade allowed (position_multiplier = 0)
- PROBE: Small position allowed (position_multiplier = 0.10 or 0.25)
- FULL: Full position allowed (position_multiplier = 1.0)

Key Thresholds:
- net_edge <= 0 → BLOCK
- confidence < 0.55 → BLOCK
- edge_percentile < 0.60 → BLOCK
- edge_percentile [0.60, 0.75) → PROBE 0.10
- edge_percentile [0.75, 0.90) → PROBE 0.25
- edge_percentile >= 0.90 → FULL 1.00
"""

from __future__ import annotations
print("🔥 LOADED EdgeGate V2 (policy) FROM:", __file__)
from typing import Dict, Any, Literal, Optional
from dataclasses import dataclass
import os


@dataclass
class EdgeGateV2Result:
    """Result from EdgeGate v2 decision"""
    state: Literal["BLOCK", "PROBE", "FULL"]
    position_multiplier: float
    reason: str
    details: Dict[str, Any]


class EdgeGateV2:
    """
    EdgeGate v2 - PROBE Position Mechanism
    
    Provides risk-adjusted position sizing based on:
    - net_edge: Expected edge after costs
    - confidence: ML model confidence or signal strength
    - edge_percentile: Historical percentile ranking of this signal's edge
    """
    
    def __init__(
        self,
        min_confidence: float = None,
        probe_small_multiplier: float = None,
        probe_medium_multiplier: float = None,
        full_multiplier: float = None,
        percentile_probe_small: float = None,
        percentile_probe_medium: float = None,
        percentile_full: float = None,
    ):
        """
        Initialize EdgeGate v2 with configurable thresholds
        
        Args:
            min_confidence: Minimum confidence threshold (default 0.55)
            probe_small_multiplier: Position multiplier for small probe (default 0.10)
            probe_medium_multiplier: Position multiplier for medium probe (default 0.25)
            full_multiplier: Position multiplier for full position (default 1.0)
            percentile_probe_small: Percentile threshold for small probe (default 0.60)
            percentile_probe_medium: Percentile threshold for medium probe (default 0.75)
            percentile_full: Percentile threshold for full position (default 0.90)
        """
        # Load from environment or use defaults
        self.min_confidence = float(
            min_confidence if min_confidence is not None 
            else os.getenv("EDGE_GATE_V2_MIN_CONFIDENCE", "0.55")
        )
        
        self.probe_small_multiplier = float(
            probe_small_multiplier if probe_small_multiplier is not None
            else os.getenv("EDGE_GATE_V2_PROBE_SMALL_MULT", "0.10")
        )
        
        self.probe_medium_multiplier = float(
            probe_medium_multiplier if probe_medium_multiplier is not None
            else os.getenv("EDGE_GATE_V2_PROBE_MEDIUM_MULT", "0.25")
        )
        
        self.full_multiplier = float(
            full_multiplier if full_multiplier is not None
            else os.getenv("EDGE_GATE_V2_FULL_MULT", "1.0")
        )
        
        self.percentile_probe_small = float(
            percentile_probe_small if percentile_probe_small is not None
            else os.getenv("EDGE_GATE_V2_PERCENTILE_PROBE_SMALL", "0.60")
        )
        
        self.percentile_probe_medium = float(
            percentile_probe_medium if percentile_probe_medium is not None
            else os.getenv("EDGE_GATE_V2_PERCENTILE_PROBE_MEDIUM", "0.75")
        )
        
        self.percentile_full = float(
            percentile_full if percentile_full is not None
            else os.getenv("EDGE_GATE_V2_PERCENTILE_FULL", "0.90")
        )
        
        print(f"[EdgeGateV2] Initialized with thresholds:")
        print(f"  min_confidence={self.min_confidence}")
        print(f"  percentile_thresholds=[{self.percentile_probe_small}, {self.percentile_probe_medium}, {self.percentile_full}]")
        print(f"  position_multipliers=[{self.probe_small_multiplier}, {self.probe_medium_multiplier}, {self.full_multiplier}]")
    
    def evaluate(
        self,
        net_edge: float,
        confidence: float,
        edge_percentile: float,
        fee_estimate: Optional[float] = None,
        slippage_estimate: Optional[float] = None,
        volatility: Optional[float] = None,
    ) -> EdgeGateV2Result:
        """
        Evaluate trading signal and determine gate state
        
        Args:
            net_edge: Net edge after costs (gross_edge - fees - slippage)
            confidence: Signal confidence [0, 1]
            edge_percentile: Percentile rank of this edge in historical distribution [0, 1]
            fee_estimate: Optional fee estimate (for info only, net_edge should already account for this)
            slippage_estimate: Optional slippage estimate (for info)
            volatility: Optional volatility measure (for info)
            
        Returns:
            EdgeGateV2Result with state, position_multiplier, and reason
        """
        details = {
            "net_edge": net_edge,
            "confidence": confidence,
            "edge_percentile": edge_percentile,
            "fee_estimate": fee_estimate,
            "slippage_estimate": slippage_estimate,
            "volatility": volatility,
        }
        
        # Rule 1: Block if net_edge <= 0 (negative expectation)
        if net_edge <= 0:
            return EdgeGateV2Result(
                state="BLOCK",
                position_multiplier=0.0,
                reason=f"net_edge_non_positive (net_edge={net_edge:.6f} <= 0)",
                details=details
            )
        
        # Rule 2: Block if confidence < min_confidence
        if confidence < self.min_confidence:
            return EdgeGateV2Result(
                state="BLOCK",
                position_multiplier=0.0,
                reason=f"confidence_too_low (confidence={confidence:.3f} < {self.min_confidence:.3f})",
                details=details
            )
        
        # Rule 3: Block if edge_percentile < percentile_probe_small
        if edge_percentile < self.percentile_probe_small:
            return EdgeGateV2Result(
                state="BLOCK",
                position_multiplier=0.0,
                reason=f"edge_percentile_too_low (percentile={edge_percentile:.3f} < {self.percentile_probe_small:.3f})",
                details=details
            )
        
        # Rule 4: PROBE small if edge_percentile in [probe_small, probe_medium)
        if edge_percentile < self.percentile_probe_medium:
            return EdgeGateV2Result(
                state="PROBE",
                position_multiplier=self.probe_small_multiplier,
                reason=f"probe_small (percentile={edge_percentile:.3f} in [{self.percentile_probe_small:.2f}, {self.percentile_probe_medium:.2f}))",
                details=details
            )
        
        # Rule 5: PROBE medium if edge_percentile in [probe_medium, full)
        if edge_percentile < self.percentile_full:
            return EdgeGateV2Result(
                state="PROBE",
                position_multiplier=self.probe_medium_multiplier,
                reason=f"probe_medium (percentile={edge_percentile:.3f} in [{self.percentile_probe_medium:.2f}, {self.percentile_full:.2f}))",
                details=details
            )
        
        # Rule 6: FULL if edge_percentile >= full
        return EdgeGateV2Result(
            state="FULL",
            position_multiplier=self.full_multiplier,
            reason=f"full_position (percentile={edge_percentile:.3f} >= {self.percentile_full:.2f})",
            details=details
        )
    
    def get_thresholds(self) -> Dict[str, float]:
        """Get current threshold configuration"""
        return {
            "min_confidence": self.min_confidence,
            "probe_small_multiplier": self.probe_small_multiplier,
            "probe_medium_multiplier": self.probe_medium_multiplier,
            "full_multiplier": self.full_multiplier,
            "percentile_probe_small": self.percentile_probe_small,
            "percentile_probe_medium": self.percentile_probe_medium,
            "percentile_full": self.percentile_full,
        }


def create_default_edge_gate_v2() -> EdgeGateV2:
    """Create EdgeGate v2 with default configuration"""
    return EdgeGateV2()
