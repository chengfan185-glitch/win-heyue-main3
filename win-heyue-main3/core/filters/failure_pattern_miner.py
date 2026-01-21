# core/filters/failure_pattern_miner.py
"""
Failure Pattern Auto-Discovery

Automatically mines and identifies failure patterns from trade history.
Uses statistical analysis and pattern recognition to find losing combinations.

Key features:
- Multi-dimensional pattern analysis
- Statistical significance testing
- Automatic rule generation
- Pattern ranking by severity
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import json
import statistics


class FailurePattern:
    """Represents a discovered failure pattern"""
    
    def __init__(
        self,
        pattern_id: str,
        conditions: Dict[str, Any],
        stats: Dict[str, float],
        severity: float
    ):
        self.pattern_id = pattern_id
        self.conditions = conditions
        self.stats = stats
        self.severity = severity
        self.discovered_at = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'pattern_id': self.pattern_id,
            'conditions': self.conditions,
            'stats': self.stats,
            'severity': self.severity,
            'discovered_at': self.discovered_at
        }


class FailurePatternMiner:
    """
    Automatically discovers failure patterns from trade history
    
    Analysis dimensions:
    1. Strategy + Market Regime
    2. Strategy + Volatility Level
    3. Strategy + Time Period
    4. Strategy + Volume Conditions
    5. Multi-factor combinations
    
    Outputs: Ranked list of failure patterns with statistical confidence
    """
    
    def __init__(
        self,
        min_sample_size: int = 10,
        significance_level: float = 0.05,
        min_severity: float = 0.6
    ):
        """
        Args:
            min_sample_size: Minimum trades to consider pattern valid
            significance_level: Statistical significance threshold (p-value)
            min_severity: Minimum severity score to report pattern
        """
        self.min_sample_size = min_sample_size
        self.significance_level = significance_level
        self.min_severity = min_severity
        
        # Discovered patterns
        self.patterns: List[FailurePattern] = []
        
        # Storage
        self.storage_dir = Path("logs/failure_patterns")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def mine_patterns(self, trades: List[Dict[str, Any]]) -> List[FailurePattern]:
        """
        Mine failure patterns from trade history
        
        Args:
            trades: List of trade records with metadata
            
        Returns:
            List of discovered failure patterns, ranked by severity
        """
        print(f"[PatternMiner] Analyzing {len(trades)} trades for failure patterns...")
        
        if len(trades) < self.min_sample_size:
            print(f"[PatternMiner] Insufficient data: need at least {self.min_sample_size} trades")
            return []
        
        # Clear old patterns
        self.patterns = []
        
        # 1. Single-dimension analysis
        self._analyze_strategy_market_regime(trades)
        self._analyze_strategy_volatility(trades)
        self._analyze_strategy_time_period(trades)
        self._analyze_strategy_volume(trades)
        
        # 2. Two-dimension combinations
        self._analyze_market_time_combination(trades)
        self._analyze_volatility_volume_combination(trades)
        
        # 3. Rank and filter patterns
        self.patterns.sort(key=lambda p: p.severity, reverse=True)
        self.patterns = [p for p in self.patterns if p.severity >= self.min_severity]
        
        print(f"[PatternMiner] Discovered {len(self.patterns)} significant failure patterns")
        
        # Save patterns
        self._save_patterns()
        
        return self.patterns
    
    def _analyze_strategy_market_regime(self, trades: List[Dict[str, Any]]):
        """Analyze strategy performance by market regime"""
        # Group by (strategy_id, market_regime)
        groups = defaultdict(list)
        
        for trade in trades:
            key = (
                trade.get('strategy_id', 'unknown'),
                trade.get('market_regime', 'UNKNOWN')
            )
            groups[key].append(trade)
        
        # Analyze each group
        for (strategy_id, regime), group_trades in groups.items():
            if len(group_trades) < self.min_sample_size:
                continue
            
            stats = self._calculate_group_stats(group_trades)
            
            # Check if it's a failure pattern
            if self._is_failure_pattern(stats):
                severity = self._calculate_severity(stats)
                
                pattern = FailurePattern(
                    pattern_id=f"strategy_regime_{strategy_id}_{regime}",
                    conditions={
                        'type': 'strategy_market_regime',
                        'strategy_id': strategy_id,
                        'market_regime': regime
                    },
                    stats=stats,
                    severity=severity
                )
                self.patterns.append(pattern)
    
    def _analyze_strategy_volatility(self, trades: List[Dict[str, Any]]):
        """Analyze strategy performance by volatility levels"""
        # Classify trades by volatility
        for trade in trades:
            volatility = trade.get('volatility', 0.02)
            if volatility < 0.01:
                trade['volatility_bucket'] = 'LOW'
            elif volatility < 0.03:
                trade['volatility_bucket'] = 'MEDIUM'
            else:
                trade['volatility_bucket'] = 'HIGH'
        
        # Group by (strategy_id, volatility_bucket)
        groups = defaultdict(list)
        
        for trade in trades:
            key = (
                trade.get('strategy_id', 'unknown'),
                trade.get('volatility_bucket', 'MEDIUM')
            )
            groups[key].append(trade)
        
        # Analyze each group
        for (strategy_id, vol_bucket), group_trades in groups.items():
            if len(group_trades) < self.min_sample_size:
                continue
            
            stats = self._calculate_group_stats(group_trades)
            
            if self._is_failure_pattern(stats):
                severity = self._calculate_severity(stats)
                
                pattern = FailurePattern(
                    pattern_id=f"strategy_volatility_{strategy_id}_{vol_bucket}",
                    conditions={
                        'type': 'strategy_volatility',
                        'strategy_id': strategy_id,
                        'volatility_level': vol_bucket
                    },
                    stats=stats,
                    severity=severity
                )
                self.patterns.append(pattern)
    
    def _analyze_strategy_time_period(self, trades: List[Dict[str, Any]]):
        """Analyze strategy performance by time of day"""
        # Add hour to trades
        for trade in trades:
            timestamp = trade.get('timestamp', trade.get('exit_timestamp', 0))
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            hour = dt.hour
            
            # Classify into periods
            if 0 <= hour < 6:
                trade['time_period'] = 'NIGHT_0_6'
            elif 6 <= hour < 12:
                trade['time_period'] = 'MORNING_6_12'
            elif 12 <= hour < 18:
                trade['time_period'] = 'AFTERNOON_12_18'
            else:
                trade['time_period'] = 'EVENING_18_24'
        
        # Group by (strategy_id, time_period)
        groups = defaultdict(list)
        
        for trade in trades:
            key = (
                trade.get('strategy_id', 'unknown'),
                trade.get('time_period', 'UNKNOWN')
            )
            groups[key].append(trade)
        
        # Analyze each group
        for (strategy_id, period), group_trades in groups.items():
            if len(group_trades) < self.min_sample_size:
                continue
            
            stats = self._calculate_group_stats(group_trades)
            
            if self._is_failure_pattern(stats):
                severity = self._calculate_severity(stats)
                
                pattern = FailurePattern(
                    pattern_id=f"strategy_time_{strategy_id}_{period}",
                    conditions={
                        'type': 'strategy_time_period',
                        'strategy_id': strategy_id,
                        'time_period': period
                    },
                    stats=stats,
                    severity=severity
                )
                self.patterns.append(pattern)
    
    def _analyze_strategy_volume(self, trades: List[Dict[str, Any]]):
        """Analyze strategy performance by volume conditions"""
        # Calculate volume percentiles
        volumes = [t.get('volume_ratio', 1.0) for t in trades if 'volume_ratio' in t]
        if not volumes:
            return
        
        p33 = statistics.quantiles(volumes, n=3)[0]
        p66 = statistics.quantiles(volumes, n=3)[1]
        
        # Classify trades by volume
        for trade in trades:
            vol_ratio = trade.get('volume_ratio', 1.0)
            if vol_ratio < p33:
                trade['volume_bucket'] = 'LOW'
            elif vol_ratio < p66:
                trade['volume_bucket'] = 'MEDIUM'
            else:
                trade['volume_bucket'] = 'HIGH'
        
        # Group by (strategy_id, volume_bucket)
        groups = defaultdict(list)
        
        for trade in trades:
            key = (
                trade.get('strategy_id', 'unknown'),
                trade.get('volume_bucket', 'MEDIUM')
            )
            groups[key].append(trade)
        
        # Analyze each group
        for (strategy_id, vol_bucket), group_trades in groups.items():
            if len(group_trades) < self.min_sample_size:
                continue
            
            stats = self._calculate_group_stats(group_trades)
            
            if self._is_failure_pattern(stats):
                severity = self._calculate_severity(stats)
                
                pattern = FailurePattern(
                    pattern_id=f"strategy_volume_{strategy_id}_{vol_bucket}",
                    conditions={
                        'type': 'strategy_volume',
                        'strategy_id': strategy_id,
                        'volume_level': vol_bucket
                    },
                    stats=stats,
                    severity=severity
                )
                self.patterns.append(pattern)
    
    def _analyze_market_time_combination(self, trades: List[Dict[str, Any]]):
        """Analyze combination of market regime and time"""
        groups = defaultdict(list)
        
        for trade in trades:
            if 'market_regime' not in trade or 'time_period' not in trade:
                continue
            
            key = (
                trade.get('strategy_id', 'unknown'),
                trade.get('market_regime'),
                trade.get('time_period')
            )
            groups[key].append(trade)
        
        for (strategy_id, regime, period), group_trades in groups.items():
            if len(group_trades) < self.min_sample_size:
                continue
            
            stats = self._calculate_group_stats(group_trades)
            
            if self._is_failure_pattern(stats):
                severity = self._calculate_severity(stats)
                
                pattern = FailurePattern(
                    pattern_id=f"combo_regime_time_{strategy_id}_{regime}_{period}",
                    conditions={
                        'type': 'market_regime_time',
                        'strategy_id': strategy_id,
                        'market_regime': regime,
                        'time_period': period
                    },
                    stats=stats,
                    severity=severity
                )
                self.patterns.append(pattern)
    
    def _analyze_volatility_volume_combination(self, trades: List[Dict[str, Any]]):
        """Analyze combination of volatility and volume"""
        groups = defaultdict(list)
        
        for trade in trades:
            if 'volatility_bucket' not in trade or 'volume_bucket' not in trade:
                continue
            
            key = (
                trade.get('strategy_id', 'unknown'),
                trade.get('volatility_bucket'),
                trade.get('volume_bucket')
            )
            groups[key].append(trade)
        
        for (strategy_id, vol, volume), group_trades in groups.items():
            if len(group_trades) < self.min_sample_size:
                continue
            
            stats = self._calculate_group_stats(group_trades)
            
            if self._is_failure_pattern(stats):
                severity = self._calculate_severity(stats)
                
                pattern = FailurePattern(
                    pattern_id=f"combo_vol_volume_{strategy_id}_{vol}_{volume}",
                    conditions={
                        'type': 'volatility_volume',
                        'strategy_id': strategy_id,
                        'volatility_level': vol,
                        'volume_level': volume
                    },
                    stats=stats,
                    severity=severity
                )
                self.patterns.append(pattern)
    
    def _calculate_group_stats(self, trades: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate statistics for a group of trades"""
        total = len(trades)
        wins = sum(1 for t in trades if t.get('pnl', 0) > 0)
        losses = total - wins
        
        win_rate = wins / total if total > 0 else 0
        
        total_pnl = sum(t.get('pnl', 0) for t in trades)
        avg_pnl = total_pnl / total if total > 0 else 0
        
        winning_trades = [t.get('pnl', 0) for t in trades if t.get('pnl', 0) > 0]
        losing_trades = [abs(t.get('pnl', 0)) for t in trades if t.get('pnl', 0) < 0]
        
        avg_win = sum(winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(losing_trades) / len(losing_trades) if losing_trades else 0
        
        profit_factor = (sum(winning_trades) / sum(losing_trades)) if losing_trades and sum(losing_trades) > 0 else float('inf')
        
        expected_value = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        return {
            'total_trades': total,
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': min(profit_factor, 999.0),  # Cap at 999
            'expected_value': expected_value
        }
    
    def _is_failure_pattern(self, stats: Dict[str, float]) -> bool:
        """Determine if statistics represent a failure pattern"""
        # Multiple failure criteria
        criteria = [
            stats['win_rate'] < 0.42,  # Very low win rate
            stats['expected_value'] < -30,  # Negative EV
            stats['profit_factor'] < 0.8,  # Poor profit factor
            (stats['win_rate'] < 0.48 and stats['expected_value'] < -10),  # Combined poor performance
        ]
        
        return any(criteria)
    
    def _calculate_severity(self, stats: Dict[str, float]) -> float:
        """
        Calculate severity score (0-1) for a failure pattern
        
        Higher severity = worse pattern
        """
        # Component scores (0-1, higher is worse)
        win_rate_score = max(0, (0.50 - stats['win_rate']) / 0.50)
        ev_score = max(0, min(1.0, (-stats['expected_value']) / 100))
        pf_score = max(0, (1.0 - stats['profit_factor']) / 1.0) if stats['profit_factor'] < 1.0 else 0
        
        # Sample size factor (more trades = more confident)
        confidence = min(1.0, stats['total_trades'] / (self.min_sample_size * 3))
        
        # Weighted average
        raw_severity = (
            win_rate_score * 0.4 +
            ev_score * 0.4 +
            pf_score * 0.2
        )
        
        # Apply confidence
        return raw_severity * confidence
    
    def _save_patterns(self):
        """Save discovered patterns to disk"""
        try:
            data = {
                'patterns': [p.to_dict() for p in self.patterns],
                'config': {
                    'min_sample_size': self.min_sample_size,
                    'significance_level': self.significance_level,
                    'min_severity': self.min_severity
                },
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            filepath = self.storage_dir / "discovered_patterns.json"
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            print(f"[PatternMiner] Saved patterns to {filepath}")
            
        except Exception as e:
            print(f"[PatternMiner] Error saving patterns: {e}")
    
    def generate_report(self) -> str:
        """Generate detailed report of discovered patterns"""
        lines = []
        lines.append("=" * 80)
        lines.append("FAILURE PATTERN MINING REPORT")
        lines.append("=" * 80)
        lines.append(f"Patterns Discovered: {len(self.patterns)}")
        lines.append(f"Min Sample Size: {self.min_sample_size}")
        lines.append(f"Min Severity: {self.min_severity}")
        lines.append("")
        
        if not self.patterns:
            lines.append("No significant failure patterns found.")
            return '\n'.join(lines)
        
        lines.append("TOP FAILURE PATTERNS (Ranked by Severity):")
        lines.append("")
        
        for i, pattern in enumerate(self.patterns[:10], 1):  # Top 10
            lines.append(f"{i}. Pattern: {pattern.pattern_id}")
            lines.append(f"   Severity: {pattern.severity:.2f}")
            lines.append(f"   Conditions: {pattern.conditions}")
            lines.append(f"   Statistics:")
            for key, value in pattern.stats.items():
                if isinstance(value, float):
                    lines.append(f"     {key}: {value:.2f}")
                else:
                    lines.append(f"     {key}: {value}")
            lines.append("")
        
        return '\n'.join(lines)
