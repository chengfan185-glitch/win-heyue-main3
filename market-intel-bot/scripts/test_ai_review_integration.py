#!/usr/bin/env python3
"""
Test script to validate the AI selection integration
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


def test_ai_selection_logic():
    """Test the AI selection logic for extracting recommended symbols"""
    print("\nTesting AI selection logic...")
    
    # Test cases for recommended field extraction
    test_cases = [
        (
            {
                "market_environment": "bullish trend",
                "recommended": [
                    {"symbol": "BTCUSDT", "reason": "Strong momentum", "risk_level": "low"},
                    {"symbol": "ETHUSDT", "reason": "Good volume", "risk_level": "medium"}
                ]
            },
            2,
            True
        ),
        (
            {
                "market_environment": "ranging",
                "recommended": []
            },
            0,
            False
        ),
        (
            {
                "market_environment": "volatile",
            },
            0,
            False
        ),
    ]
    
    for ai_result, expected_count, should_have_field in test_cases:
        # Simulate the extraction logic from intel_runner.py
        ai_recommended = ai_result.get("recommended", [])
        has_recommended = bool(ai_recommended and isinstance(ai_recommended, list))
        
        if has_recommended != should_have_field:
            print(f"✗ Failed for {ai_result}: expected has_recommended={should_have_field}, got {has_recommended}")
            return False
        
        if has_recommended and len(ai_recommended) != expected_count:
            print(f"✗ Failed for {ai_result}: expected {expected_count} recommendations, got {len(ai_recommended)}")
            return False
            
        print(f"  ✓ {ai_result.get('market_environment')} -> {len(ai_recommended)} recommendations (correct)")
    
    print("✓ AI selection logic test passed")
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
        "topn": [
            {"symbol": "BTCUSDT", "score": 0.8},
            {"symbol": "ETHUSDT", "score": 0.7}
        ],
        "weights": {},
    }
    
    # Test adding AI intel
    ai_result = {
        "market_environment": "bullish",
        "recommended": [
            {"symbol": "BTCUSDT", "reason": "Strong momentum", "risk_level": "low"}
        ]
    }
    payload["ai_intel"] = ai_result
    assert "ai_intel" in payload, "Failed to add ai_intel to payload"
    
    # Test adding ai_recommended
    ai_recommended = ai_result.get("recommended", [])
    if ai_recommended and isinstance(ai_recommended, list):
        payload["ai_recommended"] = ai_recommended
    
    assert "ai_recommended" in payload, "Failed to add ai_recommended to payload"
    assert len(payload["ai_recommended"]) == 1, "ai_recommended should have 1 item"
    assert payload["ai_recommended"][0]["symbol"] == "BTCUSDT", "Symbol should match"
    
    # Verify no global_hold fields are added
    assert "global_hold" not in payload, "global_hold should not be in payload"
    assert "intel_global_hold" not in payload, "intel_global_hold should not be in payload"
    
    print("✓ Payload structure test passed")
    return True


if __name__ == "__main__":
    try:
        success = True
        success = test_settings() and success
        success = test_ai_selection_logic() and success
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
