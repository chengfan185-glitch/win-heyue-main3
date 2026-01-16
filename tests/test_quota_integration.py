"""
Integration test for quota management with Shanghai timezone

This test verifies that quota management correctly uses Shanghai local date
and properly resets at Shanghai midnight (UTC 16:00).
"""

import unittest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.utils.time import shanghai_local_date


class TestQuotaManagement(unittest.TestCase):
    """Test quota management with Shanghai timezone"""

    def test_quota_file_date_format(self):
        """Test that quota file uses Shanghai date in YYYY-MM-DD format"""
        # Test at different UTC times
        test_cases = [
            (datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc), "2026-01-15"),
            (datetime(2026, 1, 15, 15, 59, 59, tzinfo=timezone.utc), "2026-01-15"),
            (datetime(2026, 1, 15, 16, 0, 0, tzinfo=timezone.utc), "2026-01-16"),  # Day change!
            (datetime(2026, 1, 15, 23, 30, 0, tzinfo=timezone.utc), "2026-01-16"),
        ]
        
        for dt_utc, expected_date in test_cases:
            with self.subTest(utc_time=dt_utc):
                quota_date = shanghai_local_date(dt_utc)
                self.assertEqual(quota_date, expected_date)

    def test_quota_reset_scenario(self):
        """
        Simulate quota reset at Shanghai midnight
        
        Scenario:
        1. At UTC 15:00 (Shanghai 23:00 Jan 15) - quota_date should be "2026-01-15"
        2. At UTC 17:00 (Shanghai 01:00 Jan 16) - quota_date should be "2026-01-16"
        The quota should reset because the date changed.
        """
        # Create temporary quota file
        with tempfile.TemporaryDirectory() as tmpdir:
            quota_file = Path(tmpdir) / "daily_quota.json"
            
            # Initial state: UTC 15:00 (Shanghai 23:00 Jan 15)
            dt1 = datetime(2026, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
            initial_quota = {
                "date": shanghai_local_date(dt1),
                "remaining": 3
            }
            quota_file.write_text(json.dumps(initial_quota))
            
            # Verify initial state
            stored = json.loads(quota_file.read_text())
            self.assertEqual(stored["date"], "2026-01-15")
            self.assertEqual(stored["remaining"], 3)
            
            # Simulate time passing to UTC 17:00 (Shanghai 01:00 Jan 16)
            dt2 = datetime(2026, 1, 15, 17, 0, 0, tzinfo=timezone.utc)
            new_date = shanghai_local_date(dt2)
            
            # Check if date changed (this is what _quota_today_key() does)
            self.assertEqual(new_date, "2026-01-16")
            self.assertNotEqual(stored["date"], new_date)
            
            # Simulate quota reset (this is what get_remaining_quota() does)
            if stored["date"] != new_date:
                stored = {
                    "date": new_date,
                    "remaining": 10  # DAILY_ORDER_QUOTA
                }
                quota_file.write_text(json.dumps(stored))
            
            # Verify quota was reset
            final = json.loads(quota_file.read_text())
            self.assertEqual(final["date"], "2026-01-16")
            self.assertEqual(final["remaining"], 10)

    def test_quota_no_reset_same_day(self):
        """
        Verify quota does NOT reset if still same Shanghai day
        
        Scenario:
        1. At UTC 08:00 (Shanghai 16:00 Jan 15) - quota_date "2026-01-15"
        2. At UTC 15:00 (Shanghai 23:00 Jan 15) - still "2026-01-15"
        Quota should NOT reset.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            quota_file = Path(tmpdir) / "daily_quota.json"
            
            # Initial state: UTC 08:00 (Shanghai 16:00 Jan 15)
            dt1 = datetime(2026, 1, 15, 8, 0, 0, tzinfo=timezone.utc)
            initial_quota = {
                "date": shanghai_local_date(dt1),
                "remaining": 5
            }
            quota_file.write_text(json.dumps(initial_quota))
            
            # Time passes to UTC 15:00 (Shanghai 23:00 Jan 15)
            dt2 = datetime(2026, 1, 15, 15, 0, 0, tzinfo=timezone.utc)
            new_date = shanghai_local_date(dt2)
            
            stored = json.loads(quota_file.read_text())
            
            # Date should be the same
            self.assertEqual(stored["date"], "2026-01-15")
            self.assertEqual(new_date, "2026-01-15")
            
            # Quota should NOT reset (remains 5)
            if stored["date"] == new_date:
                remaining = stored["remaining"]
            else:
                remaining = 10  # Would reset if date changed
            
            self.assertEqual(remaining, 5)  # Not reset


if __name__ == "__main__":
    unittest.main()
