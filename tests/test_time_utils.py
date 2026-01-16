"""
Unit tests for Shanghai timezone utilities

These tests ensure correct timezone handling across critical boundaries,
particularly the UTC 16:00 -> Shanghai 00:00 transition.
"""

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Import the time utilities
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.utils.time import (
    now_shanghai,
    format_dt_shanghai,
    shanghai_local_date,
    utc_to_shanghai,
    SHANGHAI_TZ,
)


class TestShanghaiTimeUtils(unittest.TestCase):
    """Test Shanghai timezone utilities"""

    def test_shanghai_timezone_offset(self):
        """Test that Shanghai timezone is UTC+8"""
        # Create a datetime in Shanghai
        dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=SHANGHAI_TZ)
        # Convert to UTC
        dt_utc = dt.astimezone(timezone.utc)
        # Should be 8 hours earlier
        self.assertEqual(dt_utc.hour, 4)

    def test_utc_midnight_boundary(self):
        """Test the critical UTC 16:00 = Shanghai 00:00 boundary"""
        # UTC 16:00:00 on Jan 15 should be Shanghai 00:00:00 on Jan 16
        dt_utc = datetime(2026, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        dt_sh = utc_to_shanghai(dt_utc)
        
        self.assertEqual(dt_sh.year, 2026)
        self.assertEqual(dt_sh.month, 1)
        self.assertEqual(dt_sh.day, 16)  # Next day
        self.assertEqual(dt_sh.hour, 0)
        self.assertEqual(dt_sh.minute, 0)
        self.assertEqual(dt_sh.second, 0)

    def test_shanghai_local_date_boundary_before_midnight(self):
        """Test date calculation just before Shanghai midnight"""
        # UTC 15:59:59 on Jan 15 = Shanghai 23:59:59 on Jan 15
        dt_utc = datetime(2026, 1, 15, 15, 59, 59, tzinfo=timezone.utc)
        date_str = shanghai_local_date(dt_utc)
        
        self.assertEqual(date_str, "2026-01-15")

    def test_shanghai_local_date_boundary_at_midnight(self):
        """Test date calculation at Shanghai midnight"""
        # UTC 16:00:00 on Jan 15 = Shanghai 00:00:00 on Jan 16
        dt_utc = datetime(2026, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        date_str = shanghai_local_date(dt_utc)
        
        self.assertEqual(date_str, "2026-01-16")

    def test_shanghai_local_date_boundary_after_midnight(self):
        """Test date calculation just after Shanghai midnight"""
        # UTC 16:00:01 on Jan 15 = Shanghai 00:00:01 on Jan 16
        dt_utc = datetime(2026, 1, 15, 16, 0, 1, tzinfo=timezone.utc)
        date_str = shanghai_local_date(dt_utc)
        
        self.assertEqual(date_str, "2026-01-16")

    def test_shanghai_local_date_late_evening_utc(self):
        """Test date calculation in late UTC evening"""
        # UTC 23:30:00 on Jan 15 = Shanghai 07:30:00 on Jan 16
        dt_utc = datetime(2026, 1, 15, 23, 30, 0, tzinfo=timezone.utc)
        date_str = shanghai_local_date(dt_utc)
        
        self.assertEqual(date_str, "2026-01-16")

    def test_format_dt_shanghai_with_timezone(self):
        """Test formatting datetime with timezone info"""
        dt_utc = datetime(2026, 1, 15, 16, 30, 45, tzinfo=timezone.utc)
        formatted = format_dt_shanghai(dt_utc)
        
        # Should contain +08:00 and be next day
        self.assertIn("+08:00", formatted)
        self.assertIn("2026-01-16", formatted)
        self.assertIn("00:30:45", formatted)

    def test_format_dt_shanghai_naive_datetime(self):
        """Test formatting naive datetime (assumed UTC)"""
        dt_naive = datetime(2026, 1, 15, 16, 0, 0)
        formatted = format_dt_shanghai(dt_naive)
        
        # Should assume UTC and convert to Shanghai
        self.assertIn("+08:00", formatted)
        self.assertIn("2026-01-16", formatted)
        self.assertIn("00:00:00", formatted)

    def test_shanghai_local_date_with_none(self):
        """Test shanghai_local_date with None (uses current time)"""
        # This will use current time, just ensure it returns valid format
        date_str = shanghai_local_date(None)
        
        # Should be YYYY-MM-DD format
        self.assertRegex(date_str, r'^\d{4}-\d{2}-\d{2}$')

    def test_shanghai_local_date_naive_datetime(self):
        """Test shanghai_local_date with naive datetime (assumed UTC)"""
        dt_naive = datetime(2026, 1, 15, 23, 30, 0)
        date_str = shanghai_local_date(dt_naive)
        
        # Naive datetime assumed UTC, so UTC 23:30 = Shanghai next day
        self.assertEqual(date_str, "2026-01-16")

    def test_now_shanghai_returns_tz_aware(self):
        """Test that now_shanghai returns timezone-aware datetime"""
        dt = now_shanghai()
        
        self.assertIsNotNone(dt.tzinfo)
        # Check it's Shanghai timezone
        self.assertEqual(dt.tzinfo.key, "Asia/Shanghai")

    def test_utc_to_shanghai_naive_datetime(self):
        """Test UTC to Shanghai conversion with naive datetime"""
        dt_naive = datetime(2026, 1, 15, 8, 0, 0)
        dt_sh = utc_to_shanghai(dt_naive)
        
        # Should assume UTC and convert (UTC 08:00 -> Shanghai 16:00)
        self.assertEqual(dt_sh.hour, 16)
        self.assertEqual(dt_sh.day, 15)

    def test_quota_date_scenario_1(self):
        """
        Real-world scenario: Runner checks quota at UTC 2026-01-15 23:30
        Should use quota_date = 2026-01-16 (Shanghai date)
        """
        dt_utc = datetime(2026, 1, 15, 23, 30, 0, tzinfo=timezone.utc)
        quota_date = shanghai_local_date(dt_utc)
        
        self.assertEqual(quota_date, "2026-01-16")

    def test_quota_date_scenario_2(self):
        """
        Real-world scenario: Runner checks quota at UTC 2026-01-15 15:59:59
        Should use quota_date = 2026-01-15 (still same Shanghai date)
        """
        dt_utc = datetime(2026, 1, 15, 15, 59, 59, tzinfo=timezone.utc)
        quota_date = shanghai_local_date(dt_utc)
        
        self.assertEqual(quota_date, "2026-01-15")

    def test_quota_date_scenario_3(self):
        """
        Real-world scenario: Runner checks quota at UTC 2026-01-15 16:00:00
        Should use quota_date = 2026-01-16 (new Shanghai day starts)
        """
        dt_utc = datetime(2026, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        quota_date = shanghai_local_date(dt_utc)
        
        self.assertEqual(quota_date, "2026-01-16")

    def test_month_boundary(self):
        """Test date calculation across month boundary"""
        # Last second of January in Shanghai
        # UTC 2026-01-31 15:59:59 = Shanghai 2026-01-31 23:59:59
        dt_utc = datetime(2026, 1, 31, 15, 59, 59, tzinfo=timezone.utc)
        date_str = shanghai_local_date(dt_utc)
        self.assertEqual(date_str, "2026-01-31")
        
        # First second of February in Shanghai
        # UTC 2026-01-31 16:00:00 = Shanghai 2026-02-01 00:00:00
        dt_utc = datetime(2026, 1, 31, 16, 0, 0, tzinfo=timezone.utc)
        date_str = shanghai_local_date(dt_utc)
        self.assertEqual(date_str, "2026-02-01")

    def test_year_boundary(self):
        """Test date calculation across year boundary"""
        # Last second of year in Shanghai
        # UTC 2025-12-31 15:59:59 = Shanghai 2025-12-31 23:59:59
        dt_utc = datetime(2025, 12, 31, 15, 59, 59, tzinfo=timezone.utc)
        date_str = shanghai_local_date(dt_utc)
        self.assertEqual(date_str, "2025-12-31")
        
        # First second of new year in Shanghai
        # UTC 2025-12-31 16:00:00 = Shanghai 2026-01-01 00:00:00
        dt_utc = datetime(2025, 12, 31, 16, 0, 0, tzinfo=timezone.utc)
        date_str = shanghai_local_date(dt_utc)
        self.assertEqual(date_str, "2026-01-01")


if __name__ == "__main__":
    unittest.main()
