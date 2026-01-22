# core/filters/failure_blacklist.py
"""
Failure Mode Blacklist

Tracks and blocks losing combinations of (strategy_id, market_state, conditions).
This is a professional quant essential that 90% of traders don't implement.

Key benefit: Eliminates known losing scenarios automatically
Typical improvement: Clean, fast win rate boost by avoiding bad setups
"""

from __future__ import annotations
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from pathlib import Path
import json


class FailureModeBlacklist:
    """
    Tracks performance of strategy+market_state combinations and blocks losers
    
    Example blacklisted combinations:
    - (strategy_X, VOLATILE market, high_volatility) with win_rate < 40%
    - (strategy_Y, RANGING market, low_volume) with negative EV
    
    This is the fastest, cleanest way to improve win rate.
    """
    
    def __init__(
        self,
        min_trades_for_analysis: int = 10,
        blacklist_win_rate_threshold: float = 0.40,
        blacklist_ev_threshold: float = -50.0,
        enable_blacklist: bool = True
    ):
        """
        Args:
            min_trades_for_analysis: Minimum trades before blacklisting a combination
            blacklist_win_rate_threshold: Blacklist if win rate < threshold (default 40%)
            blacklist_ev_threshold: Blacklist if EV < threshold (default -$50)
            enable_blacklist: Enable/disable blacklist enforcement
        """
        self.min_trades_for_analysis = min_trades_for_analysis
        self.blacklist_win_rate_threshold = blacklist_win_rate_threshold
        self.blacklist_ev_threshold = blacklist_ev_threshold
        self.enable_blacklist = enable_blacklist
        
        # Track performance by combination
        # Key: (strategy_id, market_regime, volatility_bucket)
        self.combination_stats: Dict[str, Dict[str, Any]] = {}
        
        # Blacklisted combinations
        self.blacklisted: Dict[str, Dict[str, Any]] = {}
        
        # Storage
        self.storage_dir = Path("logs/failure_blacklist")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self._load()
    
    def _make_key(
        self,
        strategy_id: str,
        market_regime: str,
        volatility_level: Optional[str] = None
    ) -> str:
        """Create combination key"""
        parts = [strategy_id, market_regime]
        if volatility_level:
            parts.append(volatility_level)
        return "|".join(parts)
    
    def _classify_volatility(self, volatility: float) -> str:
        """Classify volatility into buckets"""
        if volatility < 0.01:
            return "LOW"
        elif volatility < 0.03:
            return "MEDIUM"
        else:
            return "HIGH"
    
    def check_combination(
        self,
        strategy_id: str,
        market_regime: str,
        volatility: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        Check if a combination is blacklisted
        
        Args:
            strategy_id: Strategy identifier
            market_regime: Current market regime (TRENDING_UP, VOLATILE, etc.)
            volatility: Current volatility level
            
        Returns:
            (allowed, reason) - False if blacklisted
        """
        if not self.enable_blacklist:
            return True, "Blacklist disabled"
        
        # Build key with increasing specificity
        volatility_level = self._classify_volatility(volatility) if volatility is not None else None
        
        # Check most specific first
        if volatility_level:
            key_specific = self._make_key(strategy_id, market_regime, volatility_level)
            if key_specific in self.blacklisted:
                reason = self.blacklisted[key_specific]['reason']
                return False, f"Blacklisted: {reason}"
        
        # Check less specific
        key_general = self._make_key(strategy_id, market_regime)
        if key_general in self.blacklisted:
            reason = self.blacklisted[key_general]['reason']
            return False, f"Blacklisted: {reason}"
        
        return True, "Not blacklisted"
    
    def record_trade_result(
        self,
        strategy_id: str,
        market_regime: str,
        volatility: Optional[float],
        pnl: float,
        win: bool
    ):
        """
        Record trade result for a combination
        
        Args:
            strategy_id: Strategy identifier
            market_regime: Market regime during trade
            volatility: Volatility during trade
            pnl: Trade PnL
            win: True if profitable trade
        """
        volatility_level = self._classify_volatility(volatility) if volatility is not None else None
        key = self._make_key(strategy_id, market_regime, volatility_level)
        
        # Initialize if new
        if key not in self.combination_stats:
            self.combination_stats[key] = {
                'strategy_id': strategy_id,
                'market_regime': market_regime,
                'volatility_level': volatility_level,
                'trades': [],
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'total_pnl': 0.0,
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'expected_value': 0.0,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
        
        stats = self.combination_stats[key]
        
        # Record trade
        stats['trades'].append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'pnl': pnl,
            'win': win
        })
        
        # Update statistics
        stats['total_trades'] += 1
        if win:
            stats['wins'] += 1
        else:
            stats['losses'] += 1
        
        stats['total_pnl'] += pnl
        stats['win_rate'] = stats['wins'] / stats['total_trades']
        stats['avg_pnl'] = stats['total_pnl'] / stats['total_trades']
        stats['expected_value'] = stats['avg_pnl']
        stats['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        # Check if should be blacklisted
        if stats['total_trades'] >= self.min_trades_for_analysis:
            should_blacklist = (
                stats['win_rate'] < self.blacklist_win_rate_threshold or
                stats['expected_value'] < self.blacklist_ev_threshold
            )
            
            if should_blacklist and key not in self.blacklisted:
                self._add_to_blacklist(key, stats)
        
        self._save()
    
    def _add_to_blacklist(self, key: str, stats: Dict[str, Any]):
        """Add combination to blacklist"""
        self.blacklisted[key] = {
            'key': key,
            'strategy_id': stats['strategy_id'],
            'market_regime': stats['market_regime'],
            'volatility_level': stats['volatility_level'],
            'total_trades': stats['total_trades'],
            'win_rate': stats['win_rate'],
            'expected_value': stats['expected_value'],
            'reason': (
                f"{stats['strategy_id']} in {stats['market_regime']} "
                f"({stats['volatility_level'] or 'ANY'} vol): "
                f"Win rate {stats['win_rate']:.1%}, EV ${stats['expected_value']:.2f}"
            ),
            'blacklisted_at': datetime.now(timezone.utc).isoformat()
        }
        
        print(f"[FailureBlacklist] ⛔ Blacklisted: {self.blacklisted[key]['reason']}")
    
    def remove_from_blacklist(self, key: str):
        """Remove combination from blacklist (manual override)"""
        if key in self.blacklisted:
            del self.blacklisted[key]
            print(f"[FailureBlacklist] ✅ Removed from blacklist: {key}")
            self._save()
    
    def get_blacklist_report(self) -> str:
        """Generate blacklist report"""
        lines = []
        lines.append("=" * 60)
        lines.append("FAILURE MODE BLACKLIST REPORT")
        lines.append("=" * 60)
        lines.append(f"Status: {'🟢 ENABLED' if self.enable_blacklist else '🔴 DISABLED'}")
        lines.append(f"Blacklisted Combinations: {len(self.blacklisted)}")
        lines.append(f"Tracked Combinations: {len(self.combination_stats)}")
        lines.append("")
        
        if self.blacklisted:
            lines.append("⛔ BLACKLISTED COMBINATIONS:")
            for key, info in self.blacklisted.items():
                lines.append(f"\n  {key}")
                lines.append(f"    Win Rate: {info['win_rate']:.1%} (threshold: {self.blacklist_win_rate_threshold:.1%})")
                lines.append(f"    EV: ${info['expected_value']:.2f} (threshold: ${self.blacklist_ev_threshold:.2f})")
                lines.append(f"    Trades: {info['total_trades']}")
                lines.append(f"    Reason: {info['reason']}")
        
        lines.append("")
        lines.append("📊 ALL COMBINATION STATS:")
        for key, stats in sorted(
            self.combination_stats.items(),
            key=lambda x: x[1]['expected_value'],
            reverse=True
        ):
            status = "⛔" if key in self.blacklisted else "✅"
            lines.append(f"\n  {status} {key}")
            lines.append(f"    Trades: {stats['total_trades']}, Win Rate: {stats['win_rate']:.1%}, EV: ${stats['expected_value']:.2f}")
        
        return '\n'.join(lines)
    
    def _save(self):
        """Save blacklist and stats to disk"""
        try:
            data = {
                'blacklisted': self.blacklisted,
                'combination_stats': self.combination_stats,
                'config': {
                    'min_trades_for_analysis': self.min_trades_for_analysis,
                    'blacklist_win_rate_threshold': self.blacklist_win_rate_threshold,
                    'blacklist_ev_threshold': self.blacklist_ev_threshold,
                    'enable_blacklist': self.enable_blacklist
                },
                'updated_at': datetime.now(timezone.utc).isoformat()
            }
            
            filepath = self.storage_dir / "blacklist.json"
            temp_file = filepath.with_suffix('.json.tmp')
            
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            temp_file.replace(filepath)
            
        except Exception as e:
            print(f"[FailureBlacklist] Error saving: {e}")
    
    def _load(self):
        """Load blacklist and stats from disk"""
        try:
            filepath = self.storage_dir / "blacklist.json"
            
            if not filepath.exists():
                return
            
            with open(filepath, 'r') as f:
                data = json.load(f)
            
            self.blacklisted = data.get('blacklisted', {})
            self.combination_stats = data.get('combination_stats', {})
            
            config = data.get('config', {})
            if config:
                self.min_trades_for_analysis = config.get('min_trades_for_analysis', self.min_trades_for_analysis)
                self.blacklist_win_rate_threshold = config.get('blacklist_win_rate_threshold', self.blacklist_win_rate_threshold)
                self.blacklist_ev_threshold = config.get('blacklist_ev_threshold', self.blacklist_ev_threshold)
            
            print(f"[FailureBlacklist] Loaded {len(self.blacklisted)} blacklisted combinations")
            
        except Exception as e:
            print(f"[FailureBlacklist] Error loading: {e}")
