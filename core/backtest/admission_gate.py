# core/backtest/admission_gate.py
"""
Paper-to-Live Admission Gate

Enforces validation requirements before allowing strategies to trade live.
"""

from __future__ import annotations
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import json
from pathlib import Path

from .strategy_registry import StrategyRegistry, StrategyMetrics
from .market_state import MarketState, MarketRegime


class AdmissionGate:
    """
    Gateway for paper -> live transitions
    
    Enforces multi-stage validation:
    1. Backtest validation (historical performance)
    2. Walk-forward validation (robustness check)
    3. Paper trading validation (live data performance)
    4. Market state compatibility check
    """
    
    def __init__(self, registry_dir: str = "logs/strategy_registry"):
        self.registry = StrategyRegistry(registry_dir)
        
        # Default requirements for live approval
        self.default_requirements = {
            'min_trades': 30,
            'min_win_rate': 0.52,
            'min_profit_factor': 1.2,
            'min_sharpe': 0.5,
            'min_total_pnl': 0.0,
            'max_drawdown': 3000.0  # Maximum acceptable drawdown in USD
        }
    
    def check_admission(
        self,
        strategy_id: str,
        version: str,
        market_state: Optional[MarketState] = None,
        force_approval: bool = False
    ) -> tuple[bool, str]:
        """
        Check if a strategy can trade live
        
        Args:
            strategy_id: Strategy identifier
            version: Strategy version
            market_state: Current market conditions (optional)
            force_approval: Bypass checks (for manual override)
            
        Returns:
            (allowed, reason) - True if strategy can trade, reason string
        """
        if force_approval:
            return True, "Force approval enabled"
        
        # Check if strategy exists
        metrics = self.registry.get_metrics(strategy_id, version)
        if not metrics:
            return False, f"Strategy {strategy_id} v{version} not found in registry"
        
        # Check if live trading is enabled
        if not metrics.live_enabled:
            if not metrics.live_approved:
                return False, "Strategy not approved for live trading"
            else:
                return False, "Strategy approved but not enabled (use enable_live_trading)"
        
        # Check market state compatibility (if provided)
        if market_state:
            # Simple example: don't trade in extremely volatile markets
            if market_state.regime == MarketRegime.VOLATILE and market_state.regime_confidence > 0.8:
                return False, f"Market too volatile (regime: {market_state.regime.value})"
            
            # Don't trade when market regime is unknown
            if market_state.regime == MarketRegime.UNKNOWN:
                return False, "Market regime unknown - insufficient data"
        
        # All checks passed
        return True, "Strategy approved and enabled for live trading"
    
    def request_approval(
        self,
        strategy_id: str,
        version: str,
        backtest_passed: bool,
        walkforward_passed: bool,
        custom_requirements: Optional[Dict[str, float]] = None
    ) -> bool:
        """
        Request approval for live trading
        
        Args:
            strategy_id: Strategy identifier
            version: Strategy version
            backtest_passed: Did strategy pass backtest validation?
            walkforward_passed: Did strategy pass walk-forward validation?
            custom_requirements: Custom performance requirements (optional)
            
        Returns:
            True if approved
        """
        metrics = self.registry.get_metrics(strategy_id, version)
        if not metrics:
            print(f"[AdmissionGate] Strategy {strategy_id} v{version} not found")
            return False
        
        # Update validation status
        metrics.backtest_passed = backtest_passed
        metrics.walkforward_passed = walkforward_passed
        
        # Check validation stages
        if not backtest_passed:
            print(f"[AdmissionGate] ❌ Backtest validation failed for {strategy_id} v{version}")
            return False
        
        if not walkforward_passed:
            print(f"[AdmissionGate] ❌ Walk-forward validation failed for {strategy_id} v{version}")
            return False
        
        # Check performance requirements
        requirements = custom_requirements or self.default_requirements
        
        approved = self.registry.approve_for_live(strategy_id, version, requirements)
        
        if approved:
            print(f"[AdmissionGate] ✅ {strategy_id} v{version} approved for live trading")
            self._log_approval(strategy_id, version, metrics)
        else:
            print(f"[AdmissionGate] ❌ {strategy_id} v{version} does not meet performance requirements")
            self._log_rejection(strategy_id, version, metrics, requirements)
        
        return approved
    
    def enable_strategy(self, strategy_id: str, version: str):
        """Enable an approved strategy for live trading"""
        try:
            self.registry.enable_live_trading(strategy_id, version)
            print(f"[AdmissionGate] ✅ Enabled live trading for {strategy_id} v{version}")
            return True
        except ValueError as e:
            print(f"[AdmissionGate] ❌ Cannot enable: {e}")
            return False
    
    def disable_strategy(self, strategy_id: str, version: str, reason: str = ""):
        """Disable live trading for a strategy"""
        self.registry.disable_live_trading(strategy_id, version, reason)
        print(f"[AdmissionGate] ⛔ Disabled live trading for {strategy_id} v{version}: {reason}")
    
    def _log_approval(self, strategy_id: str, version: str, metrics: StrategyMetrics):
        """Log approval decision"""
        log_dir = Path("logs/admission_gate")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"approvals_{datetime.now(timezone.utc).strftime('%Y%m')}.jsonl"
        
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'action': 'APPROVED',
            'strategy_id': strategy_id,
            'version': version,
            'metrics': metrics.to_dict()
        }
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    
    def _log_rejection(
        self,
        strategy_id: str,
        version: str,
        metrics: StrategyMetrics,
        requirements: Dict[str, float]
    ):
        """Log rejection decision"""
        log_dir = Path("logs/admission_gate")
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"rejections_{datetime.now(timezone.utc).strftime('%Y%m')}.jsonl"
        
        # Identify which requirements failed
        failures = []
        if metrics.total_trades < requirements.get('min_trades', 0):
            failures.append(f"trades: {metrics.total_trades} < {requirements['min_trades']}")
        if metrics.win_rate < requirements.get('min_win_rate', 0):
            failures.append(f"win_rate: {metrics.win_rate:.2%} < {requirements['min_win_rate']:.2%}")
        if metrics.profit_factor < requirements.get('min_profit_factor', 0):
            failures.append(f"profit_factor: {metrics.profit_factor:.2f} < {requirements['min_profit_factor']:.2f}")
        if metrics.sharpe_ratio < requirements.get('min_sharpe', 0):
            failures.append(f"sharpe: {metrics.sharpe_ratio:.2f} < {requirements['min_sharpe']:.2f}")
        
        entry = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'action': 'REJECTED',
            'strategy_id': strategy_id,
            'version': version,
            'failures': failures,
            'metrics': metrics.to_dict(),
            'requirements': requirements
        }
        
        with open(log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    
    def get_status_report(self) -> str:
        """Generate status report of all strategies"""
        return self.registry.generate_report()


def create_default_admission_gate() -> AdmissionGate:
    """Create admission gate with default configuration"""
    return AdmissionGate()
