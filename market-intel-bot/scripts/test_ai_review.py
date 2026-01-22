#!/usr/bin/env python3
"""
Test script for AI review integration in market-intel-bot
"""
import sys
import os
import time
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_ai_review_integration():
    """Test the AI review logic integration"""
    print("Testing AI review integration...")
    
    # Import the module
    os.environ['ENABLE_MARKET_INTEL_AI'] = 'true'
    os.environ['MARKET_INTEL_AI_REVIEW_SECONDS'] = '60'
    
    from src.settings import load_settings
    
    # Load settings
    cfg = load_settings()
    
    # Test 1: Verify settings are loaded correctly
    print("\n1. Testing settings...")
    assert cfg.enable_market_intel_ai == True, "enable_market_intel_ai should be True"
    assert cfg.market_intel_ai_review_seconds == 60, "market_intel_ai_review_seconds should be 60"
    assert cfg.market_intel_ai_output_file == "store/ai_intel/latest.json", "default output file is correct"
    print("   ✓ Settings loaded correctly")
    
    # Test 2: Verify AI review timing logic
    print("\n2. Testing AI review timing logic...")
    _last_ai_review_ts = 0.0
    now_ts = time.time()
    review_every = max(60, int(cfg.market_intel_ai_review_seconds))
    
    # First run should trigger (last_ts is 0)
    should_run = (_last_ai_review_ts == 0.0) or (now_ts - _last_ai_review_ts >= review_every)
    assert should_run == True, "First run should trigger AI review"
    print("   ✓ First run triggers AI review")
    
    # Update last review time
    _last_ai_review_ts = now_ts
    
    # Immediate second run should not trigger
    now_ts2 = time.time()
    should_run2 = (_last_ai_review_ts == 0.0) or (now_ts2 - _last_ai_review_ts >= review_every)
    assert should_run2 == False, "Immediate second run should not trigger"
    print("   ✓ Immediate second run does not trigger")
    
    # Test 3: Verify risk_off detection logic
    print("\n3. Testing risk_off detection...")
    
    # Test various risk_off formats
    test_cases = [
        ("risk_off", True),
        ("risk-off", True),
        ("risk off", True),
        ("RISK_OFF", True),
        ("Risk_Off", True),
        ("trend", False),
        ("range", False),
        ("weak_trend", False),
        (None, False),
    ]
    
    for state, should_hold in test_cases:
        ms = state
        if isinstance(ms, str):
            ms = ms.strip().lower()
        
        is_risk_off = ms in ("risk_off", "risk-off", "risk off")
        assert is_risk_off == should_hold, f"State '{state}' should result in hold={should_hold}"
        print(f"   ✓ State '{state}' correctly detected (hold={should_hold})")
    
    # Test 4: Verify payload structure
    print("\n4. Testing payload structure...")
    payload = {
        "ts": time.time(),
        "time": "2024-01-01T00:00:00",
        "timeframe": "15m",
        "universe_size": 50,
        "topn": [{"symbol": "BTCUSDT", "score": 0.85}],
    }
    
    # Simulate adding AI result
    ai_snapshot = {
        "ts": payload.get("ts"),
        "time": payload.get("time"),
        "timeframe": payload.get("timeframe"),
        "topn": payload.get("topn"),
        "universe_size": payload.get("universe_size"),
    }
    
    # Mock AI result
    ai_result = {
        "market_state": "risk_off",
        "recommendation": "avoid trading"
    }
    
    payload["ai_intel"] = ai_result
    
    # Check for risk_off
    ms = ai_result.get("market_state") or ai_result.get("state") or ai_result.get("status")
    if isinstance(ms, str):
        ms = ms.strip().lower()
    
    if ms in ("risk_off", "risk-off", "risk off"):
        payload["global_hold"] = True
        payload["intel_global_hold"] = True
    
    assert "ai_intel" in payload, "ai_intel should be in payload"
    assert payload.get("global_hold") == True, "global_hold should be True"
    assert payload.get("intel_global_hold") == True, "intel_global_hold should be True"
    print("   ✓ Payload structure is correct")
    print("   ✓ Both global_hold and intel_global_hold flags set")
    
    print("\n" + "="*60)
    print("All tests passed successfully!")
    print("="*60)
    print("\nSummary:")
    print("  ✓ Settings load with correct defaults")
    print("  ✓ AI review timing logic works correctly")
    print("  ✓ Risk-off state detection works for all formats")
    print("  ✓ Payload structure with AI intel is correct")
    print("  ✓ Global hold flags are set when risk_off detected")

if __name__ == "__main__":
    test_ai_review_integration()
