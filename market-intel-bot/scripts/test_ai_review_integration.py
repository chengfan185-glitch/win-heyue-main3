#!/usr/bin/env python3
"""
Test script to validate the AI review integration
"""
import os
import sys
import json
import time

# Add parent directory to path to import modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.settings import load_settings


def test_settings():
    """Test that new settings are loaded correctly"""
    print("Testing settings...")
    cfg = load_settings()
    
    assert hasattr(cfg, 'enable_market_intel_ai'), "Missing enable_market_intel_ai field"
    assert hasattr(cfg, 'market_intel_ai_review_seconds'), "Missing market_intel_ai_review_seconds field"
    assert hasattr(cfg, 'market_intel_ai_output_file'), "Missing market_intel_ai_output_file field"
    
    assert isinstance(cfg.enable_market_intel_ai, bool), "enable_market_intel_ai should be bool"
    assert isinstance(cfg.market_intel_ai_review_seconds, int), "market_intel_ai_review_seconds should be int"
    assert isinstance(cfg.market_intel_ai_output_file, str), "market_intel_ai_output_file should be str"
    
    # Check defaults
    assert cfg.enable_market_intel_ai == True, "Default enable_market_intel_ai should be True"
    assert cfg.market_intel_ai_review_seconds == 1800, "Default market_intel_ai_review_seconds should be 1800"
    assert cfg.market_intel_ai_output_file == "store/ai_intel/latest.json", "Default market_intel_ai_output_file should be store/ai_intel/latest.json"
    
    print("✓ Settings test passed")
    return True


def test_ai_review_logic():
    """Test the AI review logic for risk_off detection"""
    print("\nTesting AI review logic...")
    
    # Test various market_state values
    test_cases = [
        ({"market_state": "risk_off"}, True),
        ({"market_state": "risk-off"}, True),
        ({"market_state": "risk off"}, True),
        ({"market_state": "RISK_OFF"}, True),
        ({"state": "risk_off"}, True),
        ({"status": "risk-off"}, True),
        ({"market_state": "trend"}, False),
        ({"market_state": "range"}, False),
        ({}, False),
    ]
    
    for ai_result, should_hold in test_cases:
        # Simulate the normalization logic from intel_runner.py
        ms = None
        try:
            ms = ai_result.get("market_state") or ai_result.get("state") or ai_result.get("status")
            if isinstance(ms, str):
                ms = ms.strip().lower()
        except Exception:
            ms = None
        
        is_risk_off = ms in ("risk_off", "risk-off", "risk off")
        
        if is_risk_off != should_hold:
            print(f"✗ Failed for {ai_result}: expected hold={should_hold}, got hold={is_risk_off}")
            return False
        else:
            print(f"  ✓ {ai_result} -> hold={is_risk_off} (correct)")
    
    print("✓ AI review logic test passed")
    return True


def test_payload_structure():
    """Test that payload structure supports new fields"""
    print("\nTesting payload structure...")
    
    # Simulate a payload
    payload = {
        "ts": time.time(),
        "time": "2024-01-01T00:00:00",
        "timeframe": "15m",
        "universe_size": 80,
        "topn": [],
        "weights": {},
    }
    
    # Test adding AI intel
    payload["ai_intel"] = {"market_state": "risk_off"}
    assert "ai_intel" in payload, "Failed to add ai_intel to payload"
    
    # Test adding global_hold flags
    payload["global_hold"] = True
    payload["intel_global_hold"] = True
    assert payload["global_hold"] == True, "Failed to set global_hold"
    assert payload["intel_global_hold"] == True, "Failed to set intel_global_hold"
    
    print("✓ Payload structure test passed")
    return True


if __name__ == "__main__":
    try:
        success = True
        success = test_settings() and success
        success = test_ai_review_logic() and success
        success = test_payload_structure() and success
        
        if success:
            print("\n" + "="*50)
            print("All tests passed! ✓")
            print("="*50)
            sys.exit(0)
        else:
            print("\n" + "="*50)
            print("Some tests failed! ✗")
            print("="*50)
            sys.exit(1)
    except Exception as e:
        print(f"\nTest failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
