#!/usr/bin/env python3
"""
Test script for AlertManager validation.

This script tests AlertManager behavior with different configurations:
1. With enabled=False (no Telegram credentials required)
2. With enabled=True and dummy token (tests error handling)

Usage:
    python scripts/test_alerts.py

No actual Telegram credentials are required when enabled=False.
"""

import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.alerts.alert_manager import AlertManager, AlertLevel


def test_disabled_alert_manager():
    """Test AlertManager with disabled mode (no Telegram)"""
    print("\n" + "=" * 60)
    print("TEST 1: AlertManager with enabled=False")
    print("=" * 60)
    
    try:
        # Create AlertManager with disabled mode
        alerts = AlertManager(enabled=False, bot_token=None, chat_id=None)
        
        # Check attributes
        print(f"✓ AlertManager created: {type(alerts)}")
        print(f"✓ Has send_alert: {hasattr(alerts, 'send_alert')}")
        print(f"✓ Has info: {hasattr(alerts, 'info')}")
        print(f"✓ Has warning: {hasattr(alerts, 'warning')}")
        print(f"✓ Has error: {hasattr(alerts, 'error')}")
        print(f"✓ Has debug: {hasattr(alerts, 'debug')}")
        
        # Test basic methods (should not crash)
        print("\nTesting basic methods (should not send, but not crash):")
        alerts.info("Test info message")
        print("✓ info() called successfully")
        
        alerts.warning("Test warning message")
        print("✓ warning() called successfully")
        
        alerts.error("Test error message")
        print("✓ error() called successfully")
        
        alerts.debug("Test debug message")
        print("✓ debug() called successfully")
        
        # Test send_alert method
        print("\nTesting send_alert() method:")
        alerts.send_alert(AlertLevel.INFO, "Test Title", "Test message")
        print("✓ send_alert() with AlertLevel enum called successfully")
        
        alerts.send_alert("WARNING", "Test Title", "Test message with string level")
        print("✓ send_alert() with string level called successfully")
        
        alerts.send_alert("INFO", "Test", "Test with extra", extra={"key": "value"})
        print("✓ send_alert() with extra dict called successfully")
        
        # Test semantic helpers
        print("\nTesting semantic helper methods:")
        alerts.alert_system_startup("paper", "test-run-123")
        print("✓ alert_system_startup() called successfully")
        
        alerts.alert_quota_exhausted("BTCUSDT", 0)
        print("✓ alert_quota_exhausted() called successfully")
        
        alerts.alert_order_placed("BTCUSDT", "LONG", 100.0, 50000.0, "paper")
        print("✓ alert_order_placed() called successfully")
        
        alerts.alert_fatal_error("Test fatal error")
        print("✓ alert_fatal_error() called successfully")
        
        alerts.alert_order_failed("BTCUSDT", "Test error message")
        print("✓ alert_order_failed() called successfully")
        
        alerts.alert_reconciliation_failed("Test reconciliation report")
        print("✓ alert_reconciliation_failed() called successfully")
        
        alerts.alert_system_shutdown("Test shutdown")
        print("✓ alert_system_shutdown() called successfully")
        
        print("\n✅ TEST 1 PASSED: AlertManager works correctly when disabled")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 1 FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_enabled_with_dummy_token():
    """Test AlertManager with enabled=True but dummy token (error handling)"""
    print("\n" + "=" * 60)
    print("TEST 2: AlertManager with enabled=True and dummy token")
    print("=" * 60)
    
    try:
        # Create AlertManager with enabled mode but dummy credentials
        alerts = AlertManager(
            enabled=True,
            bot_token="dummy_token_123",
            chat_id="123456789"
        )
        
        print(f"✓ AlertManager created with dummy credentials: {type(alerts)}")
        print(f"✓ Config enabled: {alerts.config.enabled}")
        
        # Test methods (should handle errors gracefully)
        print("\nTesting methods (should handle errors gracefully):")
        
        alerts.info("Test info with dummy token")
        print("✓ info() handled gracefully (error logged internally)")
        
        alerts.send_alert(AlertLevel.WARNING, "Test", "Test message")
        print("✓ send_alert() handled gracefully (error logged internally)")
        
        alerts.alert_system_startup("paper", "test-123")
        print("✓ alert_system_startup() handled gracefully")
        
        print("\n✅ TEST 2 PASSED: AlertManager handles errors gracefully")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 2 FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_env_based_initialization():
    """Test AlertManager initialization from environment"""
    print("\n" + "=" * 60)
    print("TEST 3: AlertManager with env-based initialization")
    print("=" * 60)
    
    try:
        # Create AlertManager without explicit params (loads from env)
        alerts = AlertManager()
        
        print(f"✓ AlertManager created from env: {type(alerts)}")
        print(f"✓ Config enabled: {alerts.config.enabled}")
        print(f"✓ Has send_alert: {hasattr(alerts, 'send_alert')}")
        
        # Test basic functionality
        alerts.info("Test from env-based initialization")
        print("✓ info() called successfully")
        
        alerts.send_alert("INFO", "Test", "Test message")
        print("✓ send_alert() called successfully")
        
        print("\n✅ TEST 3 PASSED: AlertManager env-based initialization works")
        return True
        
    except Exception as e:
        print(f"\n❌ TEST 3 FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("AlertManager Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(("Disabled AlertManager", test_disabled_alert_manager()))
    results.append(("Enabled with dummy token", test_enabled_with_dummy_token()))
    results.append(("Env-based initialization", test_env_based_initialization()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
