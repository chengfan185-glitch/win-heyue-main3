# core/filters/ev_admission_policy.py
"""
Expected Value (EV) Based Admission Policy

Win Rate vs EV decision framework for live trading admission.

Key principle: EV > 0 and stable is the ultimate criterion, not just win rate.
"""

from __future__ import annotations
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
import math


@dataclass
class EVMetrics:
    """Expected Value metrics for a strategy"""
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    expected_value: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'win_rate': self.win_rate,
            'avg_win': self.avg_win,
            'avg_loss': self.avg_loss,
            'profit_factor': self.profit_factor,
            'expected_value': self.expected_value,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'total_trades': self.total_trades
        }


class EVAdmissionPolicy:
    """
    Expected Value based admission decision framework
    
    Philosophy:
    - Win rate alone is misleading
    - 55% WR + 1.8 R:R = excellent strategy
    - 70% WR but low capacity = unsustainable
    - 55-62% WR is healthy for mid-freq futures
    - >65% often indicates overfitting
    
    Decision Matrix:
    - EV > threshold AND stable
    - Win rate in healthy range (not too high/low)
    - Sharpe ratio acceptable
    - Drawdown controlled
    """
    
    def __init__(self):
        # Admission thresholds
        self.thresholds = {
            # Minimum EV per trade (in base currency)
            'min_ev_per_trade': 5.0,
            
            # Win rate healthy range
            'min_win_rate': 0.50,
            'max_win_rate': 0.70,  # >70% suspicious
            'optimal_win_rate_low': 0.55,
            'optimal_win_rate_high': 0.62,
            
            # Risk metrics
            'min_profit_factor': 1.15,
            'min_sharpe_ratio': 0.5,
            'max_drawdown_pct': 0.30,  # 30%
            
            # Sample size
            'min_trades': 30,
            
            # EV stability (coefficient of variation)
            'max_ev_cv': 2.0  # Lower is better
        }
        
        # Strategy type adjustments
        self.strategy_adjustments = {
            'trend_following': {
                'min_win_rate': 0.48,  # Can be lower
                'min_profit_factor': 1.5,  # But need higher R:R
                'optimal_win_rate': 0.58
            },
            'mean_reversion': {
                'min_win_rate': 0.52,  # Should be higher
                'min_profit_factor': 1.2,
                'optimal_win_rate': 0.60
            },
            'high_frequency': {
                'min_win_rate': 0.55,  # High WR expected
                'min_profit_factor': 1.1,  # But lower R:R ok
                'optimal_win_rate': 0.65,
                'min_trades': 100  # Need more samples
            },
            'breakout': {
                'min_win_rate': 0.45,  # Can be low
                'min_profit_factor': 2.0,  # But need very high R:R
                'optimal_win_rate': 0.55
            }
        }
    
    def evaluate_admission(
        self,
        metrics: EVMetrics,
        strategy_type: str = 'generic',
        position_size_usd: float = 100.0
    ) -> Tuple[bool, str, float]:
        """
        Evaluate if strategy should be admitted to live trading
        
        Args:
            metrics: Strategy performance metrics
            strategy_type: Type of strategy
            position_size_usd: Expected position size
            
        Returns:
            (admitted, reason, confidence_score)
        """
        # Get strategy-specific thresholds
        thresholds = self._get_thresholds(strategy_type)
        
        # Run all checks
        checks = []
        reasons = []
        
        # 1. Sample size check
        if metrics.total_trades < thresholds['min_trades']:
            return False, f"Insufficient trades: {metrics.total_trades} < {thresholds['min_trades']}", 0.0
        
        # 2. Expected Value check (PRIMARY CRITERION)
        ev_per_trade = metrics.expected_value
        if ev_per_trade < thresholds['min_ev_per_trade']:
            return False, f"EV too low: ${ev_per_trade:.2f} < ${thresholds['min_ev_per_trade']:.2f}", 0.0
        
        # 3. Win rate range check
        if metrics.win_rate < thresholds['min_win_rate']:
            checks.append(False)
            reasons.append(f"Win rate too low: {metrics.win_rate:.1%} < {thresholds['min_win_rate']:.1%}")
        elif metrics.win_rate > thresholds['max_win_rate']:
            checks.append(False)
            reasons.append(f"Win rate suspiciously high: {metrics.win_rate:.1%} > {thresholds['max_win_rate']:.1%} (overfitting?)")
        else:
            checks.append(True)
        
        # 4. Profit factor check
        if metrics.profit_factor < thresholds['min_profit_factor']:
            checks.append(False)
            reasons.append(f"Profit factor too low: {metrics.profit_factor:.2f} < {thresholds['min_profit_factor']:.2f}")
        else:
            checks.append(True)
        
        # 5. Sharpe ratio check
        if metrics.sharpe_ratio < thresholds['min_sharpe_ratio']:
            checks.append(False)
            reasons.append(f"Sharpe ratio too low: {metrics.sharpe_ratio:.2f} < {thresholds['min_sharpe_ratio']:.2f}")
        else:
            checks.append(True)
        
        # 6. Drawdown check
        dd_pct = metrics.max_drawdown / (position_size_usd * metrics.total_trades * 0.02)  # Rough estimate
        if dd_pct > thresholds['max_drawdown_pct']:
            checks.append(False)
            reasons.append(f"Drawdown too high: {dd_pct:.1%} > {thresholds['max_drawdown_pct']:.1%}")
        else:
            checks.append(True)
        
        # Calculate confidence score
        confidence = self._calculate_confidence(metrics, thresholds)
        
        # Decision
        if all(checks):
            return True, f"ADMITTED - EV: ${ev_per_trade:.2f}, WR: {metrics.win_rate:.1%}, PF: {metrics.profit_factor:.2f}", confidence
        else:
            return False, " | ".join(reasons), confidence
    
    def calculate_ev_metrics(self, trades: list[Dict[str, Any]]) -> EVMetrics:
        """
        Calculate EV metrics from trade history
        
        Args:
            trades: List of trade dictionaries with 'pnl' key
            
        Returns:
            EVMetrics object
        """
        if not trades:
            return EVMetrics(0, 0, 0, 0, 0, 0, 0, 0)
        
        total_trades = len(trades)
        winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in trades if t.get('pnl', 0) < 0]
        
        wins = len(winning_trades)
        losses = len(losing_trades)
        win_rate = wins / total_trades if total_trades > 0 else 0
        
        avg_win = sum(t['pnl'] for t in winning_trades) / wins if wins > 0 else 0
        avg_loss = abs(sum(t['pnl'] for t in losing_trades)) / losses if losses > 0 else 0
        
        total_wins = sum(t['pnl'] for t in winning_trades)
        total_losses = abs(sum(t['pnl'] for t in losing_trades))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        expected_value = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        
        # Sharpe ratio (simplified)
        returns = [t.get('pnl', 0) for t in trades]
        if len(returns) > 1:
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            std_dev = math.sqrt(variance) if variance > 0 else 0.0001
            sharpe_ratio = (mean_return / std_dev) * math.sqrt(252) if std_dev > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Max drawdown (simplified)
        cumulative = 0
        peak = 0
        max_dd = 0
        for t in trades:
            cumulative += t.get('pnl', 0)
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
        
        return EVMetrics(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=min(profit_factor, 999.0),
            expected_value=expected_value,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_dd,
            total_trades=total_trades
        )
    
    def _get_thresholds(self, strategy_type: str) -> Dict[str, float]:
        """Get strategy-specific thresholds"""
        base = self.thresholds.copy()
        
        if strategy_type in self.strategy_adjustments:
            adjustments = self.strategy_adjustments[strategy_type]
            base.update(adjustments)
        
        return base
    
    def _calculate_confidence(self, metrics: EVMetrics, thresholds: Dict[str, float]) -> float:
        """
        Calculate confidence score (0-1)
        
        Higher confidence = more reliable metrics
        """
        # Sample size confidence
        sample_confidence = min(1.0, metrics.total_trades / (thresholds['min_trades'] * 3))
        
        # EV strength (how much above minimum)
        ev_strength = min(1.0, metrics.expected_value / (thresholds['min_ev_per_trade'] * 3))
        
        # Win rate in optimal range
        optimal_low = thresholds.get('optimal_win_rate_low', 0.55)
        optimal_high = thresholds.get('optimal_win_rate_high', 0.62)
        if optimal_low <= metrics.win_rate <= optimal_high:
            wr_confidence = 1.0
        else:
            # Penalize deviation from optimal range
            if metrics.win_rate < optimal_low:
                wr_confidence = metrics.win_rate / optimal_low
            else:
                wr_confidence = 1.0 - (metrics.win_rate - optimal_high) / (thresholds['max_win_rate'] - optimal_high)
        
        # Sharpe confidence
        sharpe_confidence = min(1.0, metrics.sharpe_ratio / 1.5)
        
        # Combined confidence
        confidence = (
            sample_confidence * 0.25 +
            ev_strength * 0.35 +
            wr_confidence * 0.25 +
            sharpe_confidence * 0.15
        )
        
        return confidence
    
    def generate_decision_matrix(self) -> str:
        """Generate decision matrix documentation"""
        lines = []
        lines.append("=" * 80)
        lines.append("EV-BASED ADMISSION DECISION MATRIX")
        lines.append("=" * 80)
        lines.append("")
        lines.append("PHILOSOPHY:")
        lines.append("  EV > 0 and stable is the PRIMARY criterion, not just win rate")
        lines.append("")
        lines.append("HEALTHY STRATEGY EXAMPLE:")
        lines.append("  Win Rate: 58%")
        lines.append("  Avg Win: $120, Avg Loss: $75")
        lines.append("  Profit Factor: 1.8")
        lines.append("  Expected Value: $38.40 per trade")
        lines.append("  → This is 'capital-ready' for live trading")
        lines.append("")
        lines.append("=" * 80)
        lines.append("ADMISSION THRESHOLDS (Generic Strategy):")
        lines.append("=" * 80)
        lines.append(f"  Min EV per trade: ${self.thresholds['min_ev_per_trade']:.2f}")
        lines.append(f"  Win Rate Range: {self.thresholds['min_win_rate']:.0%} - {self.thresholds['max_win_rate']:.0%}")
        lines.append(f"  Optimal Win Rate: {self.thresholds['optimal_win_rate_low']:.0%} - {self.thresholds['optimal_win_rate_high']:.0%}")
        lines.append(f"  Min Profit Factor: {self.thresholds['min_profit_factor']:.2f}")
        lines.append(f"  Min Sharpe Ratio: {self.thresholds['min_sharpe_ratio']:.2f}")
        lines.append(f"  Max Drawdown: {self.thresholds['max_drawdown_pct']:.0%}")
        lines.append(f"  Min Trades: {self.thresholds['min_trades']}")
        lines.append("")
        lines.append("=" * 80)
        lines.append("STRATEGY-SPECIFIC ADJUSTMENTS:")
        lines.append("=" * 80)
        
        for strategy_type, adjustments in self.strategy_adjustments.items():
            lines.append(f"\n{strategy_type.upper()}:")
            for key, value in adjustments.items():
                if isinstance(value, float) and 0 < value < 1:
                    lines.append(f"  {key}: {value:.0%}")
                else:
                    lines.append(f"  {key}: {value}")
        
        lines.append("")
        lines.append("=" * 80)
        lines.append("WIN RATE INTERPRETATION:")
        lines.append("=" * 80)
        lines.append("  < 50%: Unacceptable (losing more than winning)")
        lines.append("  50-55%: Marginal (need very high R:R)")
        lines.append("  55-62%: HEALTHY (optimal range for mid-freq futures)")
        lines.append("  62-70%: Good (but verify sustainability)")
        lines.append("  > 70%: SUSPICIOUS (likely overfitting, unsustainable)")
        lines.append("")
        lines.append("Remember: A 58% WR with 1.8 R:R is better than 70% WR with 1.1 R:R!")
        
        return '\n'.join(lines)
    
    def calculate_required_win_rate(
        self,
        avg_win: float,
        avg_loss: float,
        target_ev: float
    ) -> float:
        """
        Calculate required win rate to achieve target EV
        
        Formula: WR = (target_EV + avg_loss) / (avg_win + avg_loss)
        
        Args:
            avg_win: Average winning trade
            avg_loss: Average losing trade (positive number)
            target_ev: Target expected value
            
        Returns:
            Required win rate (0-1)
        """
        if avg_win + avg_loss <= 0:
            return 0
        
        required_wr = (target_ev + avg_loss) / (avg_win + avg_loss)
        return max(0, min(1.0, required_wr))
    
    def calculate_required_risk_reward(
        self,
        win_rate: float,
        target_ev: float,
        avg_loss: float
    ) -> float:
        """
        Calculate required risk:reward ratio to achieve target EV
        
        Formula: R:R = (target_EV + (1-WR) * avg_loss) / (WR * avg_loss)
        
        Args:
            win_rate: Win rate (0-1)
            target_ev: Target expected value
            avg_loss: Average losing trade (positive number)
            
        Returns:
            Required risk:reward ratio
        """
        if win_rate <= 0 or avg_loss <= 0:
            return 0
        
        numerator = target_ev + (1 - win_rate) * avg_loss
        denominator = win_rate * avg_loss
        
        if denominator <= 0:
            return 0
        
        return numerator / denominator
