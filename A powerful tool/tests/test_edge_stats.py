"""
Unit tests for EdgeStats percentile calculation
"""

import unittest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from risk.edge_stats import EdgeStats, EdgeRecord


class TestEdgeStats(unittest.TestCase):
    """Test EdgeStats percentile calculation"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.stats = EdgeStats(max_window=100, min_sample=2)
    
    def test_empty_stats(self):
        """Test behavior with no history"""
        percentile = self.stats.get_edge_percentile(0.001, "BTCUSDT", "LONG", "15m")
        self.assertIsNone(percentile)  # Returns None when insufficient samples
        
        summary = self.stats.get_statistics()
        self.assertEqual(summary["count"], 0)
    
    def test_single_record(self):
        """Test with single historical record"""
        # Use stats with min_sample=1 for this test
        stats = EdgeStats(max_window=100, min_sample=1)
        stats.record_edge(net_edge=0.001, symbol="BTCUSDT", direction="LONG", timeframe="15m")
        
        # Same value should be at 0 percentile (no values below it)
        percentile = stats.get_edge_percentile(0.001, "BTCUSDT", "LONG", "15m")
        self.assertEqual(percentile, 0.0)
        
        # Higher value should be at 100th percentile
        percentile = stats.get_edge_percentile(0.002, "BTCUSDT", "LONG", "15m")
        self.assertEqual(percentile, 1.0)
    
    def test_percentile_calculation(self):
        """Test percentile calculation with multiple records"""
        # Add 10 records with edge values 0.001 to 0.010
        for i in range(10):
            edge = 0.001 * (i + 1)
            self.stats.record_edge(net_edge=edge, symbol="BTCUSDT", direction="LONG", timeframe="15m")
        
        # Test specific percentiles
        # Value 0.001 should be at 0 percentile (0/10)
        self.assertEqual(self.stats.get_edge_percentile(0.001, "BTCUSDT", "LONG", "15m"), 0.0)
        
        # Value 0.005 should be at 0.4 percentile (4/10)
        self.assertEqual(self.stats.get_edge_percentile(0.005, "BTCUSDT", "LONG", "15m"), 0.4)
        
        # Value 0.010 should be at 0.9 percentile (9/10)
        self.assertEqual(self.stats.get_edge_percentile(0.010, "BTCUSDT", "LONG", "15m"), 0.9)
        
        # Value 0.011 (above all) should be at 1.0 percentile
        self.assertEqual(self.stats.get_edge_percentile(0.011, "BTCUSDT", "LONG", "15m"), 1.0)
    
    def test_max_history_limit(self):
        """Test that max_window limit is enforced"""
        stats = EdgeStats(max_window=5, min_sample=2)
        
        # Add 10 records
        for i in range(10):
            stats.record_edge(net_edge=0.001 * (i + 1), symbol="BTCUSDT", direction="LONG", timeframe="15m")
        
        # Should only keep last 5
        key_str = "BTCUSDT:LONG:15m"
        self.assertEqual(len(stats._history[key_str]), 5)
        self.assertEqual(len(stats._sorted_edges[key_str]), 5)
        
        # First record (0.001) should have been removed
        # Last 5 should be 0.006 to 0.010
        edges = sorted(stats._sorted_edges[key_str])
        self.assertAlmostEqual(edges[0], 0.006, places=6)
        self.assertAlmostEqual(edges[-1], 0.010, places=6)
    
    def test_statistics_summary(self):
        """Test statistical summary calculation"""
        # Add records with known distribution
        values = [0.001, 0.002, 0.003, 0.004, 0.005, 0.006, 0.007, 0.008, 0.009, 0.010]
        for val in values:
            self.stats.record_edge(net_edge=val, symbol="BTCUSDT", direction="LONG", timeframe="15m")
        
        summary = self.stats.get_statistics(symbol="BTCUSDT", direction="LONG", timeframe="15m")
        
        self.assertEqual(summary["count"], 10)
        self.assertAlmostEqual(summary["min"], 0.001, places=6)
        self.assertAlmostEqual(summary["max"], 0.010, places=6)
        self.assertAlmostEqual(summary["mean"], 0.0055, places=6)
        # Median for 10 items is at index int(10 * 0.5) = 5, which is 0.006
        self.assertAlmostEqual(summary["median"], 0.006, places=6)
    
    def test_recent_records(self):
        """Test retrieval of recent records"""
        # Add records with timestamps
        now = datetime.now(timezone.utc)
        for i in range(5):
            timestamp = now + timedelta(minutes=i)
            self.stats.record_edge(
                net_edge=0.001 * (i + 1),
                symbol="BTCUSDT",
                direction="LONG",
                timeframe="15m",
                signal_type="ml_long",
                timestamp=timestamp,
            )
        
        recent = self.stats.get_recent_records(symbol="BTCUSDT", direction="LONG", timeframe="15m", limit=3)
        self.assertEqual(len(recent), 3)
        
        # Should return last 3 records (most recent)
        self.assertAlmostEqual(recent[0].net_edge, 0.003, places=6)
        self.assertAlmostEqual(recent[-1].net_edge, 0.005, places=6)
    
    def test_persistence(self):
        """Test saving and loading from file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            persistence_path = Path(tmpdir) / "edge_stats.json"
            
            # Create stats and add records
            stats1 = EdgeStats(max_window=10, min_sample=2, persistence_path=str(persistence_path))
            stats1.record_edge(net_edge=0.001, symbol="BTCUSDT", direction="LONG", timeframe="15m")
            stats1.record_edge(net_edge=0.002, symbol="ETHUSDT", direction="SHORT", timeframe="15m")
            stats1.record_edge(net_edge=0.003, symbol="BTCUSDT", direction="LONG", timeframe="15m")
            
            # Verify file was created
            self.assertTrue(persistence_path.exists())
            
            # Load into new instance
            stats2 = EdgeStats(persistence_path=str(persistence_path))
            
            # Verify data was loaded
            self.assertEqual(len(stats2._history["BTCUSDT:LONG:15m"]), 2)
            self.assertEqual(len(stats2._history["ETHUSDT:SHORT:15m"]), 1)
            
            # Verify percentile calculation works with loaded data
            percentile = stats2.get_edge_percentile(0.002, "BTCUSDT", "LONG", "15m")
            self.assertAlmostEqual(percentile, 0.5, places=2)
    
    def test_clear(self):
        """Test clearing all history"""
        self.stats.record_edge(net_edge=0.001, symbol="BTCUSDT", direction="LONG", timeframe="15m")
        self.stats.record_edge(net_edge=0.002, symbol="ETHUSDT", direction="SHORT", timeframe="15m")
        
        self.assertEqual(len(self.stats._history), 2)
        
        self.stats.clear()
        
        self.assertEqual(len(self.stats._history), 0)
        self.assertEqual(len(self.stats._sorted_edges), 0)
    
    def test_duplicate_values(self):
        """Test handling of duplicate edge values"""
        # Add multiple records with same edge value
        for i in range(5):
            self.stats.record_edge(net_edge=0.005, symbol="BTCUSDT", direction="LONG", timeframe="15m")
        
        # Add some different values
        self.stats.record_edge(net_edge=0.001, symbol="BTCUSDT", direction="LONG", timeframe="15m")
        self.stats.record_edge(net_edge=0.010, symbol="BTCUSDT", direction="LONG", timeframe="15m")
        
        # Should handle duplicates correctly
        key_str = "BTCUSDT:LONG:15m"
        self.assertEqual(len(self.stats._history[key_str]), 7)
        self.assertEqual(len(self.stats._sorted_edges[key_str]), 7)
        
        # Percentile of 0.005 should be around 14% (1/7)
        percentile = self.stats.get_edge_percentile(0.005, "BTCUSDT", "LONG", "15m")
        self.assertAlmostEqual(percentile, 1/7, places=2)
    
    def test_negative_edges(self):
        """Test handling of negative edge values"""
        # Add mix of negative and positive edges
        values = [-0.002, -0.001, 0.000, 0.001, 0.002]
        for val in values:
            self.stats.record_edge(net_edge=val, symbol="BTCUSDT", direction="LONG", timeframe="15m")
        
        # Test percentiles
        self.assertEqual(self.stats.get_edge_percentile(-0.002, "BTCUSDT", "LONG", "15m"), 0.0)
        self.assertEqual(self.stats.get_edge_percentile(0.000, "BTCUSDT", "LONG", "15m"), 0.4)
        self.assertEqual(self.stats.get_edge_percentile(0.002, "BTCUSDT", "LONG", "15m"), 0.8)
    
    def test_percentile_range(self):
        """Test that percentiles are always in [0, 1]"""
        # Add some records
        for i in range(10):
            self.stats.record_edge(net_edge=0.001 * (i + 1), symbol="BTCUSDT", direction="LONG", timeframe="15m")
        
        # Test extreme values
        percentile_min = self.stats.get_edge_percentile(-999.0, "BTCUSDT", "LONG", "15m")
        self.assertGreaterEqual(percentile_min, 0.0)
        self.assertLessEqual(percentile_min, 1.0)
        
        percentile_max = self.stats.get_edge_percentile(999.0, "BTCUSDT", "LONG", "15m")
        self.assertGreaterEqual(percentile_max, 0.0)
        self.assertLessEqual(percentile_max, 1.0)
    
    def test_symbol_direction_separation(self):
        """Test that different symbols/directions are tracked separately"""
        # Add records for different keys
        self.stats.record_edge(0.001, "BTCUSDT", "LONG", "15m")
        self.stats.record_edge(0.002, "BTCUSDT", "LONG", "15m")
        self.stats.record_edge(0.005, "BTCUSDT", "SHORT", "15m")
        self.stats.record_edge(0.010, "ETHUSDT", "LONG", "15m")
        
        # Check separate tracking
        self.assertEqual(len(self.stats._history), 3)  # 3 unique keys
        self.assertEqual(len(self.stats._history["BTCUSDT:LONG:15m"]), 2)
        self.assertEqual(len(self.stats._history["BTCUSDT:SHORT:15m"]), 1)
        self.assertEqual(len(self.stats._history["ETHUSDT:LONG:15m"]), 1)
        
        # Percentiles should be calculated independently
        # BTCUSDT LONG: 0.001, 0.002 -> 0.0015 would be at 0.5
        p1 = self.stats.get_edge_percentile(0.0015, "BTCUSDT", "LONG", "15m")
        self.assertAlmostEqual(p1, 0.5, places=2)
        
        # BTCUSDT SHORT: only 0.005 -> insufficient samples
        p2 = self.stats.get_edge_percentile(0.005, "BTCUSDT", "SHORT", "15m")
        self.assertIsNone(p2)
    
    def test_minimum_samples_enforcement(self):
        """Test that percentile returns None when samples < min_sample"""
        stats = EdgeStats(max_window=100, min_sample=20)
        
        # Add only 10 records (< 50 minimum)
        for i in range(10):
            stats.record_edge(0.001 * (i + 1), "BTCUSDT", "LONG", "15m")
        
        # Should return None (insufficient samples)
        percentile = stats.get_edge_percentile(0.005, "BTCUSDT", "LONG", "15m")
        self.assertIsNone(percentile)
        
        # Add more records to reach minimum
        for i in range(40):
            stats.record_edge(0.001 * (i + 11), "BTCUSDT", "LONG", "15m")
        
        # Now should return valid percentile
        percentile = stats.get_edge_percentile(0.005, "BTCUSDT", "LONG", "15m")
        self.assertIsNotNone(percentile)
        self.assertGreaterEqual(percentile, 0.0)
        self.assertLessEqual(percentile, 1.0)


if __name__ == "__main__":
    unittest.main()
