# core/filters/time_filter.py
"""
Time-Based Trading Filter

Blocks trading during historically low-performance time periods.
Simple but effective - can improve win rate by 5-7%.

Reality: Market behavior varies by time of day.
Some periods consistently underperform.
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone
from pathlib import Path
import json


class TimeFilter:
    """
    Filters trades based on time-of-day performance analysis
    
    Tracks win rate by hour (UTC) and blocks low-performing periods.
    Many systems see win rate improve from 55% to 62%+ with time filtering.
    """
    
    def __init__(
        self,
        min_trades_per_hour: int = 5,
        min_win_rate_threshold: float = 0.45,
        enable_filter: bool = True
    ):
        """
        Args:
            min_trades_per_hour: Min trades before analyzing hour
            min_win_rate_threshold: Block hours below this win rate
            enable_filter: Enable/disable time filter
        """
        self.min_trades_per_hour = min_trades_per_hour
        self.min_win_rate_threshold = min_win_rate_threshold
        self.enable_filter = enable_filter
        
        # Track performance by hour (0-23 UTC)
        self.hourly_stats = {
            hour: {
                'hour': hour,
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'total_pnl': 0.0,
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'blocked': False
            }
            for hour in range(24)
        }
        
        # Storage
        self.storage_dir = Path("logs/time_filter")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self._load()
    
    def check_time_allowed(self, timestamp: Optional[float] = None) -> Tuple[bool, str]:
        """
        Check if trading is allowed at current time
        
        Args:
            timestamp: Unix timestamp (uses current time if None)
            
        Returns:
            (allowed, reason)
        """
        if not self.enable_filter:
            return True, "Time filter disabled"
        
        dt = datetime.fromtimestamp(timestamp or datetime.now().timestamp(), tz=timezone.utc)
        hour = dt.hour
        
        stats = self.hourly_stats[hour]
        
        # Not enough data yet
        if stats['total_trades'] < self.min_trades_per_hour:
            return True, f"Hour {hour} UTC: insufficient data ({stats['total_trades']}/{self.min_trades_per_hour})"
        
        # Check if blocked
        if stats['blocked']:
            return False, (
                f"Hour {hour} UTC blocked: "
                f"win rate {stats['win_rate']:.1%} < {self.min_win_rate_threshold:.1%} "
                f"({stats['wins']}/{stats['total_trades']} trades)"
            )
        
        return True, f"Hour {hour} UTC allowed: win rate {stats['win_rate']:.1%}"
    
    def record_trade_result(
        self,
        timestamp: float,
        pnl: float,
        win: bool
    ):
        """
        Record trade result for time analysis
        
        Args:
            timestamp: Trade timestamp
            pnl: Trade PnL
            win: True if profitable
        """
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        hour = dt.hour
        
        stats = self.hourly_stats[hour]
        
        # Update stats
        stats['total_trades'] += 1
        if win:
            stats['wins'] += 1
        else:
            stats['losses'] += 1
        
        stats['total_pnl'] += pnl
        stats['win_rate'] = stats['wins'] / stats['total_trades']
        stats['avg_pnl'] = stats['total_pnl'] / stats['total_trades']
        
        # Update blocked status
        if stats['total_trades'] >= self.min_trades_per_hour:
            if stats['win_rate'] < self.min_win_rate_threshold:
                if not stats['blocked']:
                    stats['blocked'] = True
                    print(f"[TimeFilter] ⛔ Blocked hour {hour} UTC: "
                          f"win rate {stats['win_rate']:.1%} < {self.min_win_rate_threshold:.1%}")
            else:
                if stats['blocked']:
                    stats['blocked'] = False
                    print(f"[TimeFilter] ✅ Unblocked hour {hour} UTC: "
                          f"win rate {stats['win_rate']:.1%} >= {self.min_win_rate_threshold:.1%}")
        
        self._save()
    
    def get_blocked_hours(self) -> List[int]:
        """Get list of currently blocked hours"""
        return [
            hour for hour, stats in self.hourly_stats.items()
            if stats['blocked']
        ]
    
    def get_best_hours(self, top_n: int = 5) -> List[Tuple[int, float]]:
        """Get top N performing hours by win rate"""
        hours_with_data = [
            (hour, stats['win_rate'])
            for hour, stats in self.hourly_stats.items()
            if stats['total_trades'] >= self.min_trades_per_hour
        ]
        return sorted(hours_with_data, key=lambda x: x[1], reverse=True)[:top_n]
    
    def get_worst_hours(self, bottom_n: int = 5) -> List[Tuple[int, float]]:
        """Get bottom N performing hours by win rate"""
        hours_with_data = [
            (hour, stats['win_rate'])
            for hour, stats in self.hourly_stats.items()
            if stats['total_trades'] >= self.min_trades_per_hour
        ]
        return sorted(hours_with_data, key=lambda x: x[1])[:bottom_n]
    
    def reset_hour(self, hour: int):
        """Reset statistics for a specific hour (manual override)"""
        if 0 <= hour < 24:
            self.hourly_stats[hour] = {
                'hour': hour,
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'total_pnl': 0.0,
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'blocked': False
            }
            print(f"[TimeFilter] Reset hour {hour} UTC")
            self._save()
    
    def generate_report(self) -> str:
        """Generate time filter report"""
        lines = []
        lines.append("=" * 60)
        lines.append("TIME-BASED TRADING FILTER REPORT")
        lines.append("=" * 60)
        lines.append(f"Status: {'🟢 ENABLED' if self.enable_filter else '🔴 DISABLED'}")
        lines.append(f"Min Trades Per Hour: {self.min_trades_per_hour}")
        lines.append(f"Win Rate Threshold: {self.min_win_rate_threshold:.1%}")
        lines.append("")
        
        blocked_hours = self.get_blocked_hours()
        lines.append(f"Blocked Hours: {len(blocked_hours)}/24")
        if blocked_hours:
            lines.append(f"  {', '.join(f'{h}:00 UTC' for h in blocked_hours)}")
        
        lines.append("")
        lines.append("🏆 Best Performing Hours:")
        for hour, win_rate in self.get_best_hours():
            stats = self.hourly_stats[hour]
            lines.append(f"  {hour}:00 UTC - Win Rate: {win_rate:.1%} "
                        f"({stats['wins']}/{stats['total_trades']} trades)")
        
        lines.append("")
        lines.append("⚠️  Worst Performing Hours:")
        for hour, win_rate in self.get_worst_hours():
            stats = self.hourly_stats[hour]
            status = "⛔" if stats['blocked'] else "  "
            lines.append(f"{status} {hour}:00 UTC - Win Rate: {win_rate:.1%} "
                        f"({stats['wins']}/{stats['total_trades']} trades)")
        
        lines.append("")
        lines.append("📊 All Hours (UTC):")
        for hour in range(24):
            stats = self.hourly_stats[hour]
            if stats['total_trades'] > 0:
                status = "⛔" if stats['blocked'] else "✅"
                lines.append(
                    f"{status} {hour:02d}:00 - "
                    f"Trades: {stats['total_trades']:3d}, "
                    f"Win Rate: {stats['win_rate']:5.1%}, "
                    f"Avg PnL: ${stats['avg_pnl']:7.2f}"
                )
        
        return '\n'.join(lines)
    
    def _save(self):
        """Save filter state to disk"""
        try:
            data = {
                'hourly_stats': self.hourly_stats,
                'config': {
                    'min_trades_per_hour': self.min_trades_per_hour,
                    'min_win_rate_threshold': self.min_win_rate_threshold,
                    'enable_filter': self.enable_filter
                },
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            filepath = self.storage_dir / "time_filter.json"
            temp_file = filepath.with_suffix('.json.tmp')
            
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            temp_file.replace(filepath)
            
        except Exception as e:
            print(f"[TimeFilter] Error saving: {e}")
    
    def _load(self):
        """Load filter state from disk"""
        try:
            filepath = self.storage_dir / "time_filter.json"
            
            if not filepath.exists():
                return
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            # Load hourly stats
            loaded_stats = data.get('hourly_stats', {})
            for hour_str, stats in loaded_stats.items():
                hour = int(hour_str)
                if 0 <= hour < 24:
                    self.hourly_stats[hour] = stats
            
            # Load config
            config = data.get('config', {})
            if config:
                self.min_trades_per_hour = config.get('min_trades_per_hour', self.min_trades_per_hour)
                self.min_win_rate_threshold = config.get('min_win_rate_threshold', self.min_win_rate_threshold)
            
            blocked_count = sum(1 for stats in self.hourly_stats.values() if stats['blocked'])
            print(f"[TimeFilter] Loaded state: {blocked_count} hours blocked")
            
        except Exception as e:
            print(f"[TimeFilter] Error loading: {e}")
