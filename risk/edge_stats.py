"""
EdgeStats - Historical Edge Percentile Tracking

Tracks historical net_edge values BY symbol/direction/timeframe to calculate 
percentile rankings for new signals. This ensures "apples-to-apples" comparison
for percentile-based position sizing.

Production Requirements:
- Track edges by (symbol, direction, timeframe) separately
- Rolling window to avoid stale data pollution
- Minimum sample size enforcement
- No dependency on trade outcomes (avoid future function bias)
"""

from __future__ import annotations
from typing import List, Optional, Dict, Any, Literal
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import bisect


@dataclass
class EdgeStatsKey:
    """Key for edge statistics tracking"""
    symbol: str
    direction: Literal["LONG", "SHORT"]
    timeframe: str  # e.g., "5m", "15m", "1h"
    
    def to_str(self) -> str:
        return f"{self.symbol}:{self.direction}:{self.timeframe}"
    
    @staticmethod
    def from_str(key_str: str) -> EdgeStatsKey:
        parts = key_str.split(":")
        return EdgeStatsKey(
            symbol=parts[0],
            direction=parts[1],
            timeframe=parts[2],
        )


@dataclass
class EdgeRecord:
    """Record of a signal's edge value"""
    timestamp: datetime
    net_edge: float
    symbol: str
    direction: Literal["LONG", "SHORT"]
    timeframe: str
    signal_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class EdgeStats:
    """
    Historical edge statistics tracker with symbol/direction/timeframe separation
    
    Maintains rolling windows of historical net_edge values and provides
    percentile calculations for new signals of the same type.
    
    Philosophy:
    - Only compare apples-to-apples (same symbol/direction/timeframe)
    - Enforce minimum sample size for statistical validity
    - Use rolling windows to avoid stale data
    - Independent of trade outcomes (no future function)
    """
    
    def __init__(
        self,
        max_window: int = 1000,
        min_sample: int = 50,
        persistence_path: Optional[str] = None,
    ):
        """
        Initialize EdgeStats
        
        Args:
            max_window: Maximum number of historical records per key (default 1000)
            min_sample: Minimum samples required for valid percentile (default 50)
            persistence_path: Optional path to persist statistics (JSON file)
        """
        self.max_window = max_window
        self.min_sample = min_sample
        self.persistence_path = Path(persistence_path) if persistence_path else None
        
        # Sorted edge lists by key for fast percentile lookup
        # key -> sorted list of net_edge values
        self._sorted_edges: Dict[str, List[float]] = {}
        
        # Full history with metadata by key
        self._history: Dict[str, List[EdgeRecord]] = {}
        
        # Load from persistence if available
        if self.persistence_path and self.persistence_path.exists():
            self._load_from_file()
    
    def record_edge(
        self,
        net_edge: float,
        symbol: str,
        direction: Literal["LONG", "SHORT"],
        timeframe: str = "15m",
        signal_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> None:
        """
        Record a new edge value for a specific symbol/direction/timeframe
        
        CRITICAL: Must be called AFTER decision is made but BEFORE trade outcome is known
        to avoid future function bias.
        
        Args:
            net_edge: Net edge value (after fees/slippage)
            symbol: Trading symbol (e.g., "BTCUSDT")
            direction: Signal direction ("LONG" or "SHORT")
            timeframe: Timeframe (e.g., "5m", "15m", "1h")
            signal_type: Optional signal type classifier
            metadata: Additional metadata
            timestamp: Record timestamp (defaults to now)
        """
        timestamp = timestamp or datetime.now(timezone.utc)
        metadata = metadata or {}
        
        key = EdgeStatsKey(symbol=symbol, direction=direction, timeframe=timeframe)
        key_str = key.to_str()
        
        record = EdgeRecord(
            timestamp=timestamp,
            net_edge=net_edge,
            symbol=symbol,
            direction=direction,
            timeframe=timeframe,
            signal_type=signal_type,
            metadata=metadata,
        )
        
        # Initialize lists if needed
        if key_str not in self._history:
            self._history[key_str] = []
            self._sorted_edges[key_str] = []
        
        # Add to history
        self._history[key_str].append(record)
        
        # Add to sorted edges for percentile calculation
        bisect.insort(self._sorted_edges[key_str], net_edge)
        
        # Trim if exceeds max_window (rolling window)
        if len(self._history[key_str]) > self.max_window:
            # Remove oldest record
            removed = self._history[key_str].pop(0)
            # Remove from sorted list
            sorted_list = self._sorted_edges[key_str]
            idx = bisect.bisect_left(sorted_list, removed.net_edge)
            if idx < len(sorted_list) and sorted_list[idx] == removed.net_edge:
                sorted_list.pop(idx)
        
        # Persist if configured
        if self.persistence_path:
            self._save_to_file()
    
    def get_edge_percentile(
        self,
        net_edge: float,
        symbol: str,
        direction: Literal["LONG", "SHORT"],
        timeframe: str = "15m",
    ) -> Optional[float]:
        """
        Calculate percentile rank of a net_edge value for specific symbol/direction/timeframe
        
        Returns None if insufficient samples (< min_sample).
        
        Args:
            net_edge: Net edge value to rank
            symbol: Trading symbol
            direction: Signal direction
            timeframe: Timeframe
            
        Returns:
            Percentile in [0, 1] or None if insufficient samples
        """
        key = EdgeStatsKey(symbol=symbol, direction=direction, timeframe=timeframe)
        key_str = key.to_str()
        
        sorted_list = self._sorted_edges.get(key_str, [])
        
        # Enforce minimum sample size
        if len(sorted_list) < self.min_sample:
            return None
        
        # Find position in sorted list
        idx = bisect.bisect_left(sorted_list, net_edge)
        
        # Calculate percentile
        percentile = idx / len(sorted_list)
        
        return percentile
    
    def get_statistics(
        self,
        symbol: Optional[str] = None,
        direction: Optional[Literal["LONG", "SHORT"]] = None,
        timeframe: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get summary statistics of edge distribution
        
        If symbol/direction/timeframe specified, returns stats for that key.
        Otherwise returns aggregate stats across all keys.
        
        Returns:
            Dictionary with min, max, mean, median, percentiles, sample counts
        """
        if symbol and direction and timeframe:
            # Stats for specific key
            key = EdgeStatsKey(symbol=symbol, direction=direction, timeframe=timeframe)
            key_str = key.to_str()
            sorted_list = self._sorted_edges.get(key_str, [])
            
            if not sorted_list:
                return {
                    "key": key_str,
                    "count": 0,
                    "sufficient_samples": False,
                }
            
            n = len(sorted_list)
            
            def percentile_value(p: float) -> float:
                idx = int(n * p)
                idx = min(idx, n - 1)
                return sorted_list[idx]
            
            return {
                "key": key_str,
                "count": n,
                "sufficient_samples": n >= self.min_sample,
                "min": sorted_list[0],
                "max": sorted_list[-1],
                "mean": sum(sorted_list) / n,
                "median": percentile_value(0.5),
                "p25": percentile_value(0.25),
                "p50": percentile_value(0.50),
                "p75": percentile_value(0.75),
                "p90": percentile_value(0.90),
            }
        else:
            # Aggregate stats across all keys
            all_edges = []
            for sorted_list in self._sorted_edges.values():
                all_edges.extend(sorted_list)
            
            if not all_edges:
                return {
                    "count": 0,
                    "keys": 0,
                    "min": None,
                    "max": None,
                    "mean": None,
                }
            
            all_edges.sort()
            n = len(all_edges)
            
            def percentile_value(p: float) -> float:
                idx = int(n * p)
                idx = min(idx, n - 1)
                return all_edges[idx]
            
            return {
                "count": n,
                "keys": len(self._sorted_edges),
                "min": all_edges[0],
                "max": all_edges[-1],
                "mean": sum(all_edges) / n,
                "median": percentile_value(0.5),
                "p25": percentile_value(0.25),
                "p50": percentile_value(0.50),
                "p75": percentile_value(0.75),
                "p90": percentile_value(0.90),
            }
    
    def get_recent_records(
        self,
        symbol: Optional[str] = None,
        direction: Optional[Literal["LONG", "SHORT"]] = None,
        timeframe: Optional[str] = None,
        limit: int = 10,
    ) -> List[EdgeRecord]:
        """
        Get most recent edge records
        
        Args:
            symbol: Optional filter by symbol
            direction: Optional filter by direction
            timeframe: Optional filter by timeframe
            limit: Maximum number of records to return
            
        Returns:
            List of recent EdgeRecord objects
        """
        if symbol and direction and timeframe:
            key = EdgeStatsKey(symbol=symbol, direction=direction, timeframe=timeframe)
            key_str = key.to_str()
            history = self._history.get(key_str, [])
            return history[-limit:] if history else []
        else:
            # Aggregate recent records across all keys
            all_records = []
            for history in self._history.values():
                all_records.extend(history)
            # Sort by timestamp
            all_records.sort(key=lambda r: r.timestamp)
            return all_records[-limit:] if all_records else []
    
    def clear(
        self,
        symbol: Optional[str] = None,
        direction: Optional[Literal["LONG", "SHORT"]] = None,
        timeframe: Optional[str] = None,
    ) -> None:
        """
        Clear history
        
        If symbol/direction/timeframe specified, clears only that key.
        Otherwise clears all history.
        """
        if symbol and direction and timeframe:
            key = EdgeStatsKey(symbol=symbol, direction=direction, timeframe=timeframe)
            key_str = key.to_str()
            if key_str in self._sorted_edges:
                del self._sorted_edges[key_str]
            if key_str in self._history:
                del self._history[key_str]
        else:
            self._sorted_edges.clear()
            self._history.clear()
            if self.persistence_path and self.persistence_path.exists():
                self.persistence_path.unlink()
    
    def _save_to_file(self) -> None:
        """Save statistics to persistence file"""
        if not self.persistence_path:
            return
        
        # Ensure directory exists
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "max_window": self.max_window,
            "min_sample": self.min_sample,
            "history": {},
        }
        
        for key_str, history in self._history.items():
            data["history"][key_str] = [
                {
                    "timestamp": rec.timestamp.isoformat(),
                    "net_edge": rec.net_edge,
                    "symbol": rec.symbol,
                    "direction": rec.direction,
                    "timeframe": rec.timeframe,
                    "signal_type": rec.signal_type,
                    "metadata": rec.metadata,
                }
                for rec in history
            ]
        
        # Write atomically
        temp_path = self.persistence_path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(data, f, indent=2)
        temp_path.replace(self.persistence_path)
    
    def _load_from_file(self) -> None:
        """Load statistics from persistence file"""
        if not self.persistence_path or not self.persistence_path.exists():
            return
        
        try:
            with open(self.persistence_path, "r") as f:
                data = json.load(f)
            
            self.max_window = data.get("max_window", self.max_window)
            self.min_sample = data.get("min_sample", self.min_sample)
            
            # Rebuild history and sorted edges
            self._history.clear()
            self._sorted_edges.clear()
            
            for key_str, records in data.get("history", {}).items():
                self._history[key_str] = []
                self._sorted_edges[key_str] = []
                
                for rec_data in records:
                    record = EdgeRecord(
                        timestamp=datetime.fromisoformat(rec_data["timestamp"]),
                        net_edge=rec_data["net_edge"],
                        symbol=rec_data["symbol"],
                        direction=rec_data["direction"],
                        timeframe=rec_data["timeframe"],
                        signal_type=rec_data.get("signal_type"),
                        metadata=rec_data.get("metadata", {}),
                    )
                    self._history[key_str].append(record)
                    bisect.insort(self._sorted_edges[key_str], record.net_edge)
            
            total_records = sum(len(h) for h in self._history.values())
            print(f"[EdgeStats] Loaded {total_records} records across {len(self._history)} keys from {self.persistence_path}")
        except Exception as e:
            print(f"[EdgeStats] Error loading from {self.persistence_path}: {e}")


def create_default_edge_stats() -> EdgeStats:
    """Create EdgeStats with default configuration"""
    return EdgeStats(
        max_window=1000,
        min_sample=50,
        persistence_path="logs/edge_stats/edge_history.json",
    )
