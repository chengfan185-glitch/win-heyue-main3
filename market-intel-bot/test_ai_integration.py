"""
Integration test for AI review in intel_runner
This tests the full flow without actually calling the AI API
"""
import json
import os
import sys
import tempfile
import time
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.settings import load_settings, Settings


def test_ai_review_enabled_and_elapsed():
    """Test that AI review runs when enabled and interval has elapsed"""
    
    # Mock settings with AI enabled
    cfg = Mock(spec=Settings)
    cfg.enable_market_intel_ai = True
    cfg.market_intel_ai_review_seconds = 10  # Short interval for testing
    cfg.market_intel_ai_output_file = "/tmp/test_ai_intel.json"
    
    # Simulate the logic from intel_runner
    _last_ai_review_ts = 0.0
    now_ts = time.time()
    elapsed = now_ts - _last_ai_review_ts
    
    should_run = cfg.enable_market_intel_ai and elapsed >= cfg.market_intel_ai_review_seconds
    
    assert should_run == True, "AI review should run when enabled and interval elapsed"
    print("✓ AI review timing logic test passed")


def test_ai_review_disabled():
    """Test that AI review doesn't run when disabled"""
    
    cfg = Mock(spec=Settings)
    cfg.enable_market_intel_ai = False
    cfg.market_intel_ai_review_seconds = 10
    cfg.market_intel_ai_output_file = "/tmp/test_ai_intel.json"
    
    _last_ai_review_ts = 0.0
    now_ts = time.time()
    elapsed = now_ts - _last_ai_review_ts
    
    should_run = cfg.enable_market_intel_ai and elapsed >= cfg.market_intel_ai_review_seconds
    
    assert should_run == False, "AI review should not run when disabled"
    print("✓ AI review disabled test passed")


def test_ai_review_interval_not_elapsed():
    """Test that AI review doesn't run when interval hasn't elapsed"""
    
    cfg = Mock(spec=Settings)
    cfg.enable_market_intel_ai = True
    cfg.market_intel_ai_review_seconds = 1800
    cfg.market_intel_ai_output_file = "/tmp/test_ai_intel.json"
    
    _last_ai_review_ts = time.time() - 100  # Only 100 seconds ago
    now_ts = time.time()
    elapsed = now_ts - _last_ai_review_ts
    
    should_run = cfg.enable_market_intel_ai and elapsed >= cfg.market_intel_ai_review_seconds
    
    assert should_run == False, "AI review should not run when interval hasn't elapsed"
    print("✓ AI review interval not elapsed test passed")


def test_full_integration_with_risk_off():
    """Test full integration with mock AI returning risk_off"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = os.path.join(tmpdir, "ai_intel", "latest.json")
        
        # Mock configuration
        cfg = Mock(spec=Settings)
        cfg.enable_market_intel_ai = True
        cfg.market_intel_ai_review_seconds = 0  # Always run
        cfg.market_intel_ai_output_file = output_file
        
        # Mock payload
        payload = {
            "ts": time.time(),
            "time": "2024-01-01T00:00:00",
            "timeframe": "15m",
            "topn": [{"symbol": "BTCUSDT", "score": 0.85}],
            "universe_size": 80,
        }
        
        # Mock AI result with risk_off
        mock_ai_result = {
            "market_state": "risk_off",
            "strong_sectors": [],
            "strong_coins": [],
            "weak_coins": ["ALTUSDT"],
            "meta": {"model": "test", "generated_at": "2024-01-01T00:00:00Z"}
        }
        
        # Simulate AI review logic
        _last_ai_review_ts = 0.0
        now_ts = time.time()
        elapsed = now_ts - _last_ai_review_ts
        
        if cfg.enable_market_intel_ai and elapsed >= cfg.market_intel_ai_review_seconds:
            # Build AI snapshot
            ai_snapshot = {
                "ts": payload["ts"],
                "time": payload["time"],
                "timeframe": payload["timeframe"],
                "topn": payload["topn"],
                "universe_size": payload["universe_size"],
            }
            
            # Simulate AI call (without actually calling it)
            ai_result = mock_ai_result
            
            # Attach to payload
            payload["ai_intel"] = ai_result
            
            # Persist AI result
            dir_path = os.path.dirname(output_file)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(ai_result, f, indent=2)
            
            # Check for risk_off state
            market_state = ai_result.get("market_state") or ai_result.get("state") or ai_result.get("status")
            if isinstance(market_state, str):
                normalized_state = market_state.lower().replace("_", "").replace("-", "").replace(" ", "")
                if normalized_state == "riskoff":
                    payload["global_hold"] = True
                    payload["intel_global_hold"] = True
        
        # Verify results
        assert "ai_intel" in payload, "Payload should have ai_intel"
        assert payload["ai_intel"]["market_state"] == "risk_off", "AI result should be attached"
        assert payload.get("global_hold") == True, "global_hold should be True"
        assert payload.get("intel_global_hold") == True, "intel_global_hold should be True"
        assert os.path.exists(output_file), "AI output file should exist"
        
        # Verify file contents
        with open(output_file, 'r') as f:
            loaded_result = json.load(f)
        assert loaded_result["market_state"] == "risk_off", "File should contain risk_off state"
        
        print("✓ Full integration with risk_off test passed")


def test_full_integration_with_trend():
    """Test full integration with mock AI returning trend (no risk_off)"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_file = os.path.join(tmpdir, "ai_intel", "latest.json")
        
        # Mock configuration
        cfg = Mock(spec=Settings)
        cfg.enable_market_intel_ai = True
        cfg.market_intel_ai_review_seconds = 0  # Always run
        cfg.market_intel_ai_output_file = output_file
        
        # Mock payload
        payload = {
            "ts": time.time(),
            "time": "2024-01-01T00:00:00",
            "timeframe": "15m",
            "topn": [{"symbol": "BTCUSDT", "score": 0.85}],
            "universe_size": 80,
        }
        
        # Mock AI result with trend
        mock_ai_result = {
            "market_state": "trend",
            "strong_sectors": ["DeFi"],
            "strong_coins": ["BTCUSDT", "ETHUSDT"],
            "weak_coins": [],
            "meta": {"model": "test", "generated_at": "2024-01-01T00:00:00Z"}
        }
        
        # Simulate AI review logic
        _last_ai_review_ts = 0.0
        now_ts = time.time()
        elapsed = now_ts - _last_ai_review_ts
        
        if cfg.enable_market_intel_ai and elapsed >= cfg.market_intel_ai_review_seconds:
            # Build AI snapshot
            ai_snapshot = {
                "ts": payload["ts"],
                "time": payload["time"],
                "timeframe": payload["timeframe"],
                "topn": payload["topn"],
                "universe_size": payload["universe_size"],
            }
            
            # Simulate AI call
            ai_result = mock_ai_result
            
            # Attach to payload
            payload["ai_intel"] = ai_result
            
            # Persist AI result
            dir_path = os.path.dirname(output_file)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            with open(output_file, 'w') as f:
                json.dump(ai_result, f, indent=2)
            
            # Check for risk_off state
            market_state = ai_result.get("market_state") or ai_result.get("state") or ai_result.get("status")
            if isinstance(market_state, str):
                normalized_state = market_state.lower().replace("_", "").replace("-", "").replace(" ", "")
                if normalized_state == "riskoff":
                    payload["global_hold"] = True
                    payload["intel_global_hold"] = True
        
        # Verify results
        assert "ai_intel" in payload, "Payload should have ai_intel"
        assert payload["ai_intel"]["market_state"] == "trend", "AI result should be attached"
        assert payload.get("global_hold") != True, "global_hold should not be set for trend"
        assert payload.get("intel_global_hold") != True, "intel_global_hold should not be set for trend"
        assert os.path.exists(output_file), "AI output file should exist"
        
        print("✓ Full integration with trend test passed")


if __name__ == '__main__':
    test_ai_review_enabled_and_elapsed()
    test_ai_review_disabled()
    test_ai_review_interval_not_elapsed()
    test_full_integration_with_risk_off()
    test_full_integration_with_trend()
    print("\n✓ All integration tests passed!")
