"""
Test settings loading for market intel AI configuration
"""
import os
import sys

# Add parent directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.settings import load_settings


def test_settings_defaults():
    """Test that AI settings load with correct defaults"""
    # Clear any existing env vars that might interfere
    for key in ['ENABLE_MARKET_INTEL_AI', 'MARKET_INTEL_AI_REVIEW_SECONDS', 'MARKET_INTEL_AI_OUTPUT_FILE']:
        if key in os.environ:
            del os.environ[key]
    
    cfg = load_settings()
    
    # Check defaults
    assert cfg.enable_market_intel_ai == True, "enable_market_intel_ai should default to True"
    assert cfg.market_intel_ai_review_seconds == 1800, f"market_intel_ai_review_seconds should default to 1800, got {cfg.market_intel_ai_review_seconds}"
    assert cfg.market_intel_ai_output_file == "store/ai_intel/latest.json", f"market_intel_ai_output_file should default to 'store/ai_intel/latest.json', got {cfg.market_intel_ai_output_file}"
    
    print("✓ All default settings loaded correctly")


def test_settings_from_env():
    """Test that AI settings can be overridden via environment variables"""
    os.environ['ENABLE_MARKET_INTEL_AI'] = 'false'
    os.environ['MARKET_INTEL_AI_REVIEW_SECONDS'] = '3600'
    os.environ['MARKET_INTEL_AI_OUTPUT_FILE'] = 'custom/path/ai_output.json'
    
    cfg = load_settings()
    
    assert cfg.enable_market_intel_ai == False, "enable_market_intel_ai should be False"
    assert cfg.market_intel_ai_review_seconds == 3600, f"market_intel_ai_review_seconds should be 3600, got {cfg.market_intel_ai_review_seconds}"
    assert cfg.market_intel_ai_output_file == "custom/path/ai_output.json", f"market_intel_ai_output_file should be 'custom/path/ai_output.json', got {cfg.market_intel_ai_output_file}"
    
    # Clean up
    del os.environ['ENABLE_MARKET_INTEL_AI']
    del os.environ['MARKET_INTEL_AI_REVIEW_SECONDS']
    del os.environ['MARKET_INTEL_AI_OUTPUT_FILE']
    
    print("✓ Environment variable overrides work correctly")


if __name__ == '__main__':
    test_settings_defaults()
    test_settings_from_env()
    print("\n✓ All settings tests passed!")
