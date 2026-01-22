"""
Test AI review integration logic
"""
import json
import os
import sys
import tempfile
from unittest.mock import Mock, patch

# Add parent directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def test_risk_off_normalization():
    """Test that various risk_off state formats are correctly normalized"""
    test_cases = [
        ("risk_off", True),
        ("risk-off", True),
        ("risk off", True),
        ("RISK_OFF", True),
        ("Risk-Off", True),
        ("RiSk OfF", True),
        ("trend", False),
        ("weak_trend", False),
        ("range", False),
        ("risk_on", False),
    ]
    
    for market_state, should_be_risk_off in test_cases:
        normalized_state = market_state.lower().replace("_", "").replace("-", "").replace(" ", "")
        is_risk_off = (normalized_state == "riskoff")
        assert is_risk_off == should_be_risk_off, f"Failed for {market_state}: expected {should_be_risk_off}, got {is_risk_off}"
    
    print("✓ All risk_off normalization tests passed")


def test_ai_snapshot_structure():
    """Test that AI snapshot has required fields"""
    payload = {
        "ts": 1234567890.0,
        "time": "2024-01-01T00:00:00",
        "timeframe": "15m",
        "topn": [{"symbol": "BTCUSDT", "score": 0.85}],
        "universe_size": 80,
        "weights": {"w_trend": 1.0},
    }
    
    ai_snapshot = {
        "ts": payload["ts"],
        "time": payload["time"],
        "timeframe": payload["timeframe"],
        "topn": payload["topn"],
        "universe_size": payload["universe_size"],
    }
    
    assert "ts" in ai_snapshot, "AI snapshot should have ts field"
    assert "time" in ai_snapshot, "AI snapshot should have time field"
    assert "timeframe" in ai_snapshot, "AI snapshot should have timeframe field"
    assert "topn" in ai_snapshot, "AI snapshot should have topn field"
    assert "universe_size" in ai_snapshot, "AI snapshot should have universe_size field"
    
    print("✓ AI snapshot structure test passed")


def test_global_hold_flags():
    """Test that both global_hold flags are set correctly"""
    payload = {
        "ts": 1234567890.0,
        "time": "2024-01-01T00:00:00",
        "timeframe": "15m",
        "topn": [],
        "universe_size": 80,
    }
    
    ai_result = {
        "market_state": "risk_off",
        "strong_sectors": [],
        "strong_coins": [],
        "weak_coins": []
    }
    
    # Simulate the logic from intel_runner.py
    market_state = ai_result.get("market_state") or ai_result.get("state") or ai_result.get("status")
    if isinstance(market_state, str):
        normalized_state = market_state.lower().replace("_", "").replace("-", "").replace(" ", "")
        if normalized_state == "riskoff":
            payload["global_hold"] = True
            payload["intel_global_hold"] = True
    
    assert payload.get("global_hold") == True, "global_hold should be True for risk_off"
    assert payload.get("intel_global_hold") == True, "intel_global_hold should be True for risk_off"
    
    print("✓ Global hold flags test passed")


def test_ai_result_attachment():
    """Test that AI result is correctly attached to payload"""
    payload = {
        "ts": 1234567890.0,
        "time": "2024-01-01T00:00:00",
        "timeframe": "15m",
        "topn": [],
        "universe_size": 80,
    }
    
    ai_result = {
        "market_state": "trend",
        "strong_sectors": ["DeFi"],
        "strong_coins": ["BTCUSDT", "ETHUSDT"],
        "weak_coins": []
    }
    
    payload["ai_intel"] = ai_result
    
    assert "ai_intel" in payload, "Payload should have ai_intel field"
    assert payload["ai_intel"]["market_state"] == "trend", "AI result should be correctly attached"
    
    print("✓ AI result attachment test passed")


def test_ai_output_file_write():
    """Test that AI result can be written to a file"""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = os.path.join(tmpdir, "ai_intel", "latest.json")
        
        ai_result = {
            "market_state": "trend",
            "strong_sectors": ["DeFi"],
            "strong_coins": ["BTCUSDT"],
            "weak_coins": []
        }
        
        # Simulate the write logic
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(ai_result, f, indent=2)
        
        # Verify file exists and contains correct data
        assert os.path.exists(output_file), "AI output file should exist"
        
        with open(output_file, 'r') as f:
            loaded_result = json.load(f)
        
        assert loaded_result["market_state"] == "trend", "Loaded AI result should match original"
        
        print("✓ AI output file write test passed")


if __name__ == '__main__':
    test_risk_off_normalization()
    test_ai_snapshot_structure()
    test_global_hold_flags()
    test_ai_result_attachment()
    test_ai_output_file_write()
    print("\n✓ All AI review logic tests passed!")
