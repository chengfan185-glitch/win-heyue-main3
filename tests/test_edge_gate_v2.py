"""
Unit tests for EdgeGate v2 PROBE position mechanism
"""

import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from risk.edge_gate_v2 import EdgeGateV2, EdgeGateV2Result


class TestEdgeGateV2(unittest.TestCase):
    """Test EdgeGate v2 decision logic"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.gate = EdgeGateV2(
            min_confidence=0.55,
            probe_small_multiplier=0.10,
            probe_medium_multiplier=0.25,
            full_multiplier=1.0,
            percentile_probe_small=0.60,
            percentile_probe_medium=0.75,
            percentile_full=0.90,
        )
    
    def test_block_negative_edge(self):
        """Test BLOCK when net_edge <= 0"""
        # Negative edge
        result = self.gate.evaluate(
            net_edge=-0.001,
            confidence=0.80,
            edge_percentile=0.95,
        )
        self.assertEqual(result.state, "BLOCK")
        self.assertEqual(result.position_multiplier, 0.0)
        self.assertIn("net_edge_non_positive", result.reason)
        
        # Zero edge
        result = self.gate.evaluate(
            net_edge=0.0,
            confidence=0.80,
            edge_percentile=0.95,
        )
        self.assertEqual(result.state, "BLOCK")
        self.assertEqual(result.position_multiplier, 0.0)
    
    def test_block_low_confidence(self):
        """Test BLOCK when confidence < min_confidence"""
        result = self.gate.evaluate(
            net_edge=0.001,
            confidence=0.54,  # Below 0.55 threshold
            edge_percentile=0.95,
        )
        self.assertEqual(result.state, "BLOCK")
        self.assertEqual(result.position_multiplier, 0.0)
        self.assertIn("confidence_too_low", result.reason)
    
    def test_block_low_percentile(self):
        """Test BLOCK when edge_percentile < percentile_probe_small"""
        result = self.gate.evaluate(
            net_edge=0.001,
            confidence=0.80,
            edge_percentile=0.59,  # Below 0.60 threshold
        )
        self.assertEqual(result.state, "BLOCK")
        self.assertEqual(result.position_multiplier, 0.0)
        self.assertIn("edge_percentile_too_low", result.reason)
    
    def test_probe_small_boundary(self):
        """Test PROBE small at lower boundary"""
        # At 0.60 percentile (exact threshold)
        result = self.gate.evaluate(
            net_edge=0.001,
            confidence=0.80,
            edge_percentile=0.60,
        )
        self.assertEqual(result.state, "PROBE")
        self.assertEqual(result.position_multiplier, 0.10)
        self.assertIn("probe_small", result.reason)
        
        # Just above threshold
        result = self.gate.evaluate(
            net_edge=0.001,
            confidence=0.80,
            edge_percentile=0.65,
        )
        self.assertEqual(result.state, "PROBE")
        self.assertEqual(result.position_multiplier, 0.10)
    
    def test_probe_medium_boundary(self):
        """Test PROBE medium at boundaries"""
        # At 0.75 percentile (exact threshold)
        result = self.gate.evaluate(
            net_edge=0.001,
            confidence=0.80,
            edge_percentile=0.75,
        )
        self.assertEqual(result.state, "PROBE")
        self.assertEqual(result.position_multiplier, 0.25)
        self.assertIn("probe_medium", result.reason)
        
        # Just below full threshold
        result = self.gate.evaluate(
            net_edge=0.001,
            confidence=0.80,
            edge_percentile=0.89,
        )
        self.assertEqual(result.state, "PROBE")
        self.assertEqual(result.position_multiplier, 0.25)
    
    def test_full_position(self):
        """Test FULL position at boundary and above"""
        # At 0.90 percentile (exact threshold)
        result = self.gate.evaluate(
            net_edge=0.001,
            confidence=0.80,
            edge_percentile=0.90,
        )
        self.assertEqual(result.state, "FULL")
        self.assertEqual(result.position_multiplier, 1.0)
        self.assertIn("full_position", result.reason)
        
        # Above threshold
        result = self.gate.evaluate(
            net_edge=0.001,
            confidence=0.80,
            edge_percentile=0.99,
        )
        self.assertEqual(result.state, "FULL")
        self.assertEqual(result.position_multiplier, 1.0)
    
    def test_details_populated(self):
        """Test that details are properly populated"""
        result = self.gate.evaluate(
            net_edge=0.002,
            confidence=0.75,
            edge_percentile=0.85,
            fee_estimate=0.0004,
            slippage_estimate=0.0002,
            volatility=0.015,
        )
        
        self.assertEqual(result.details["net_edge"], 0.002)
        self.assertEqual(result.details["confidence"], 0.75)
        self.assertEqual(result.details["edge_percentile"], 0.85)
        self.assertEqual(result.details["fee_estimate"], 0.0004)
        self.assertEqual(result.details["slippage_estimate"], 0.0002)
        self.assertEqual(result.details["volatility"], 0.015)
    
    def test_multiple_blocking_conditions(self):
        """Test that first blocking condition is reported"""
        # Multiple failures - should report net_edge first
        result = self.gate.evaluate(
            net_edge=-0.001,
            confidence=0.30,
            edge_percentile=0.40,
        )
        self.assertEqual(result.state, "BLOCK")
        self.assertIn("net_edge_non_positive", result.reason)
    
    def test_get_thresholds(self):
        """Test threshold retrieval"""
        thresholds = self.gate.get_thresholds()
        self.assertEqual(thresholds["min_confidence"], 0.55)
        self.assertEqual(thresholds["percentile_probe_small"], 0.60)
        self.assertEqual(thresholds["percentile_probe_medium"], 0.75)
        self.assertEqual(thresholds["percentile_full"], 0.90)
        self.assertEqual(thresholds["probe_small_multiplier"], 0.10)
        self.assertEqual(thresholds["probe_medium_multiplier"], 0.25)
        self.assertEqual(thresholds["full_multiplier"], 1.0)


class TestEdgeGateV2EdgeCases(unittest.TestCase):
    """Test edge cases for EdgeGate v2"""
    
    def test_extreme_values(self):
        """Test with extreme input values"""
        gate = EdgeGateV2()
        
        # Very high confidence and percentile
        result = gate.evaluate(
            net_edge=0.05,
            confidence=0.99,
            edge_percentile=1.0,
        )
        self.assertEqual(result.state, "FULL")
        
        # Barely positive edge
        result = gate.evaluate(
            net_edge=0.0001,
            confidence=0.80,
            edge_percentile=0.95,
        )
        self.assertEqual(result.state, "FULL")
    
    def test_boundary_precision(self):
        """Test precision at exact boundaries"""
        gate = EdgeGateV2()
        
        # Exact confidence boundary (0.55)
        result_below = gate.evaluate(net_edge=0.001, confidence=0.549999, edge_percentile=0.95)
        self.assertEqual(result_below.state, "BLOCK")
        
        result_at = gate.evaluate(net_edge=0.001, confidence=0.55, edge_percentile=0.95)
        self.assertEqual(result_at.state, "FULL")
        
        result_above = gate.evaluate(net_edge=0.001, confidence=0.550001, edge_percentile=0.95)
        self.assertEqual(result_above.state, "FULL")


if __name__ == "__main__":
    unittest.main()
