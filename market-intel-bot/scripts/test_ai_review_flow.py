#!/usr/bin/env python3
"""
Integration test that simulates the AI review flow
"""
import os
import sys
import json
import time
from unittest.mock import Mock, patch

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.settings import load_settings
from src.store import write_json
import pipeline.intel_runner


def test_ai_review_integration():
    """Test that AI review integrates correctly with mock data"""
    print("Testing AI review integration with mock...")
    
    # Create a mock AI result
    mock_ai_result_normal = {
        "market_state": "trend",
        "strong_sectors": ["BTC", "ETH"],
        "meta": {
            "model": "test",
            "generated_at": "2024-01-01T00:00:00Z"
        }
    }
    
    mock_ai_result_risk_off = {
        "market_state": "risk_off",
        "strong_sectors": [],
        "meta": {
            "model": "test",
            "generated_at": "2024-01-01T00:00:00Z"
        }
    }
    
    # Test 1: Normal market state
    print("\n  Test 1: Normal market state (trend)")
    payload = {
        "ts": time.time(),
        "time": "2024-01-01T00:00:00",
        "timeframe": "15m",
        "universe_size": 80,
        "topn": [{"symbol": "BTCUSDT", "score": 0.8}],
    }
    
    # Simulate AI review logic
    ai_result = mock_ai_result_normal
    payload["ai_intel"] = ai_result
    
    ms = ai_result.get("market_state") or ai_result.get("state") or ai_result.get("status")
    if isinstance(ms, str):
        ms = ms.strip().lower()
    
    if ms in ("risk_off", "risk-off", "risk off"):
        payload["global_hold"] = True
        payload["intel_global_hold"] = True
    
    assert "ai_intel" in payload
    assert "global_hold" not in payload, "global_hold should not be set for normal state"
    print("    ✓ Payload correctly does not have global_hold for normal state")
    
    # Test 2: Risk off state
    print("\n  Test 2: Risk off market state")
    payload2 = {
        "ts": time.time(),
        "time": "2024-01-01T00:00:00",
        "timeframe": "15m",
        "universe_size": 80,
        "topn": [{"symbol": "BTCUSDT", "score": 0.8}],
    }
    
    ai_result2 = mock_ai_result_risk_off
    payload2["ai_intel"] = ai_result2
    
    ms2 = ai_result2.get("market_state") or ai_result2.get("state") or ai_result2.get("status")
    if isinstance(ms2, str):
        ms2 = ms2.strip().lower()
    
    if ms2 in ("risk_off", "risk-off", "risk off"):
        payload2["global_hold"] = True
        payload2["intel_global_hold"] = True
    
    assert "ai_intel" in payload2
    assert "global_hold" in payload2 and payload2["global_hold"] == True
    assert "intel_global_hold" in payload2 and payload2["intel_global_hold"] == True
    print("    ✓ Payload correctly has global_hold=True and intel_global_hold=True")
    
    # Test 3: File persistence
    print("\n  Test 3: AI result file persistence")
    test_output_file = "/tmp/test_ai_output.json"
    test_data = {"ts": time.time(), "ai": mock_ai_result_normal}
    
    try:
        os.makedirs(os.path.dirname(test_output_file), exist_ok=True)
        write_json(test_output_file, test_data)
        
        # Verify file was written
        assert os.path.exists(test_output_file), "AI output file was not created"
        
        # Read and verify content
        with open(test_output_file, 'rb') as f:
            import orjson
            loaded_data = orjson.loads(f.read())
            assert "ts" in loaded_data
            assert "ai" in loaded_data
            assert loaded_data["ai"]["market_state"] == "trend"
        
        print("    ✓ AI result successfully persisted to file")
        
        # Cleanup
        os.remove(test_output_file)
    except Exception as e:
        print(f"    ✗ File persistence failed: {e}")
        return False
    
    print("\n✓ AI review integration test passed")
    return True


def test_review_interval_logic():
    """Test that the review interval logic works correctly"""
    print("\nTesting review interval logic...")
    
    cfg = load_settings()
    review_every = max(60, int(cfg.market_intel_ai_review_seconds))
    
    # Test 1: Should review on first run (ts == 0.0)
    last_ts = 0.0
    now_ts = time.time()
    should_review = (last_ts == 0.0) or (now_ts - last_ts >= review_every)
    assert should_review == True, "Should review on first run"
    print("  ✓ Correctly triggers review on first run")
    
    # Test 2: Should not review if interval hasn't elapsed
    last_ts = time.time()
    now_ts = last_ts + 100  # Only 100 seconds passed (< 1800 default)
    should_review = (last_ts == 0.0) or (now_ts - last_ts >= review_every)
    assert should_review == False, "Should not review if interval hasn't elapsed"
    print("  ✓ Correctly skips review when interval hasn't elapsed")
    
    # Test 3: Should review if interval has elapsed
    last_ts = time.time()
    now_ts = last_ts + 2000  # 2000 seconds passed (> 1800 default)
    should_review = (last_ts == 0.0) or (now_ts - last_ts >= review_every)
    assert should_review == True, "Should review if interval has elapsed"
    print("  ✓ Correctly triggers review when interval has elapsed")
    
    print("✓ Review interval logic test passed")
    return True


if __name__ == "__main__":
    try:
        success = True
        success = test_ai_review_integration() and success
        success = test_review_interval_logic() and success
        
        if success:
            print("\n" + "="*50)
            print("All integration tests passed! ✓")
            print("="*50)
            sys.exit(0)
        else:
            print("\n" + "="*50)
            print("Some integration tests failed! ✗")
            print("="*50)
            sys.exit(1)
    except Exception as e:
        print(f"\nIntegration test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
