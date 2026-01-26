#!/usr/bin/env python3
"""
Integration test that simulates the AI selection flow
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


def test_ai_selection_integration():
    """Test that AI selection integrates correctly with mock data"""
    print("Testing AI selection integration with mock...")
    
    # Create mock AI results
    mock_ai_result_with_recommendations = {
        "market_environment": "bullish trend with good volume",
        "recommended": [
            {"symbol": "BTCUSDT", "reason": "Strong breakout with volume confirmation", "risk_level": "low"},
            {"symbol": "ETHUSDT", "reason": "Following BTC momentum", "risk_level": "medium"}
        ],
        "excluded_symbols": ["XRPUSDT: too volatile", "DOGEUSDT: weak technicals"],
        "meta": {
            "model": "test",
            "generated_at": "2024-01-01T00:00:00Z"
        }
    }
    
    mock_ai_result_no_recommendations = {
        "market_environment": "high risk, choppy market",
        "recommended": [],
        "excluded_symbols": ["All symbols excluded due to poor market conditions"],
        "meta": {
            "model": "test",
            "generated_at": "2024-01-01T00:00:00Z"
        }
    }
    
    # Test 1: With recommendations
    print("\n  Test 1: AI recommends 2 symbols from Top10")
    payload = {
        "ts": time.time(),
        "time": "2024-01-01T00:00:00",
        "timeframe": "15m",
        "universe_size": 80,
        "topn": [
            {"symbol": "BTCUSDT", "score": 0.8},
            {"symbol": "ETHUSDT", "score": 0.7},
            {"symbol": "XRPUSDT", "score": 0.6},
        ],
    }
    
    # Simulate AI selection logic
    ai_result = mock_ai_result_with_recommendations
    payload["ai_intel"] = ai_result
    
    ai_recommended = ai_result.get("recommended", [])
    if ai_recommended and isinstance(ai_recommended, list):
        payload["ai_recommended"] = ai_recommended
    
    assert "ai_intel" in payload
    assert "ai_recommended" in payload
    assert len(payload["ai_recommended"]) == 2
    assert payload["ai_recommended"][0]["symbol"] == "BTCUSDT"
    assert "global_hold" not in payload, "global_hold should NOT be set (removed feature)"
    print("    ✓ Payload has ai_recommended with 2 symbols")
    
    # Test 2: No recommendations (risky market)
    print("\n  Test 2: AI recommends 0 symbols (risky conditions)")
    payload2 = {
        "ts": time.time(),
        "time": "2024-01-01T00:00:00",
        "timeframe": "15m",
        "universe_size": 80,
        "topn": [{"symbol": "BTCUSDT", "score": 0.8}],
    }
    
    ai_result2 = mock_ai_result_no_recommendations
    payload2["ai_intel"] = ai_result2
    
    ai_recommended2 = ai_result2.get("recommended", [])
    if ai_recommended2 and isinstance(ai_recommended2, list):
        payload2["ai_recommended"] = ai_recommended2
    
    assert "ai_intel" in payload2
    assert "ai_recommended" not in payload2, "ai_recommended should not be added if empty"
    print("    ✓ Payload correctly has no ai_recommended when AI returns empty list")
    
    # Test 3: File persistence
    print("\n  Test 3: AI result file persistence")
    test_output_file = "/tmp/test_ai_output.json"
    test_data = {"ts": time.time(), "ai": mock_ai_result_with_recommendations}
    
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
            assert loaded_data["ai"]["market_environment"] == "bullish trend with good volume"
            assert len(loaded_data["ai"]["recommended"]) == 2
        
        print("    ✓ AI result successfully persisted to file")
        
        # Cleanup
        os.remove(test_output_file)
    except Exception as e:
        print(f"    ✗ File persistence failed: {e}")
        return False
    
    print("\n✓ AI selection integration test passed")
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
        success = test_ai_selection_integration() and success
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
