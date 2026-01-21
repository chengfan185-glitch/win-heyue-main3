# core/observability/metrics.py
"""
Metrics Collection for Production Monitoring

Tracks:
- Order success/failure rates
- Execution latency
- Network errors
- Risk control triggers
- System health
"""

from __future__ import annotations
import time
import json
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
from datetime import datetime, timezone

# Import Shanghai time utilities
from core.utils.time import format_dt_shanghai, now_shanghai, shanghai_local_date


@dataclass
class SystemMetrics:
    """System-wide metrics snapshot"""
    timestamp: float
    
    # Order metrics
    orders_submitted: int = 0
    orders_filled: int = 0
    orders_failed: int = 0
    orders_canceled: int = 0
    
    # Execution metrics
    avg_execution_latency_ms: float = 0.0
    max_execution_latency_ms: float = 0.0
    
    # Risk metrics
    risk_blocks: int = 0
    stop_loss_triggers: int = 0
    take_profit_triggers: int = 0
    trailing_stop_triggers: int = 0
    
    # Network metrics
    api_calls_total: int = 0
    api_calls_failed: int = 0
    network_errors: Dict[str, int] = None
    
    # Position metrics
    positions_open: int = 0
    positions_closed: int = 0
    total_realized_pnl: float = 0.0
    
    def __post_init__(self):
        if self.network_errors is None:
            self.network_errors = {}
    
    def to_dict(self) -> Dict:
        d = asdict(self)
        # Convert timestamp to Shanghai timezone ISO format
        dt = datetime.fromtimestamp(self.timestamp, tz=timezone.utc)
        d['timestamp_iso'] = format_dt_shanghai(dt)
        return d


class MetricsCollector:
    """
    Collects and aggregates system metrics
    
    Features:
    - Real-time metric tracking
    - Periodic snapshots
    - JSON export for analysis
    - Rate calculations
    """
    
    def __init__(self, output_dir: str = "logs/metrics"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Current metrics
        self._metrics = SystemMetrics(timestamp=time.time())
        
        # Latency tracking
        self._latencies: List[float] = []
        
        # Network error tracking
        self._network_errors: Dict[str, int] = defaultdict(int)
        
        # Start time
        self._start_time = time.time()
        
        # Last snapshot time
        self._last_snapshot = time.time()
    
    def record_order_submitted(self):
        """Record order submission"""
        self._metrics.orders_submitted += 1
    
    def record_order_filled(self):
        """Record successful fill"""
        self._metrics.orders_filled += 1
    
    def record_order_failed(self):
        """Record order failure"""
        self._metrics.orders_failed += 1
    
    def record_order_canceled(self):
        """Record order cancellation"""
        self._metrics.orders_canceled += 1
    
    def record_execution_latency(self, latency_ms: float):
        """Record execution latency"""
        self._latencies.append(latency_ms)
        if latency_ms > self._metrics.max_execution_latency_ms:
            self._metrics.max_execution_latency_ms = latency_ms
    
    def record_risk_block(self):
        """Record risk management block"""
        self._metrics.risk_blocks += 1
    
    def record_stop_loss(self):
        """Record stop loss trigger"""
        self._metrics.stop_loss_triggers += 1
    
    def record_take_profit(self):
        """Record take profit trigger"""
        self._metrics.take_profit_triggers += 1
    
    def record_trailing_stop(self):
        """Record trailing stop trigger"""
        self._metrics.trailing_stop_triggers += 1
    
    def record_api_call(self, success: bool = True):
        """Record API call"""
        self._metrics.api_calls_total += 1
        if not success:
            self._metrics.api_calls_failed += 1
    
    def record_network_error(self, error_type: str):
        """Record network error by type"""
        self._network_errors[error_type] += 1
        self._metrics.network_errors = dict(self._network_errors)
    
    def record_position_opened(self):
        """Record position opened"""
        self._metrics.positions_open += 1
    
    def record_position_closed(self, realized_pnl: float):
        """Record position closed"""
        self._metrics.positions_closed += 1
        self._metrics.total_realized_pnl += realized_pnl
    
    def get_current_metrics(self) -> SystemMetrics:
        """Get current metrics snapshot"""
        # Update calculated fields
        if self._latencies:
            self._metrics.avg_execution_latency_ms = sum(self._latencies) / len(self._latencies)
        
        self._metrics.timestamp = time.time()
        return self._metrics
    
    def get_success_rate(self) -> float:
        """Calculate order success rate"""
        total = self._metrics.orders_submitted
        if total == 0:
            return 1.0
        return self._metrics.orders_filled / total
    
    def get_api_success_rate(self) -> float:
        """Calculate API success rate"""
        total = self._metrics.api_calls_total
        if total == 0:
            return 1.0
        return (total - self._metrics.api_calls_failed) / total
    
    def save_snapshot(self):
        """Save current metrics snapshot to file"""
        metrics = self.get_current_metrics()
        
        # Use Shanghai time for file naming
        now_sh = now_shanghai()
        
        # Save to timestamped file
        filename = f"metrics_{now_sh.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(metrics.to_dict(), f, indent=2)
        
        # Also append to daily log (using Shanghai date for daily grouping)
        daily_log = self.output_dir / f"metrics_{shanghai_local_date()}.jsonl"
        with open(daily_log, 'a') as f:
            f.write(json.dumps(metrics.to_dict()) + '\n')
        
        self._last_snapshot = time.time()
    
    def get_summary(self) -> str:
        """Get human-readable summary"""
        metrics = self.get_current_metrics()
        uptime = time.time() - self._start_time
        
        lines = [
            "📊 System Metrics Summary",
            f"Uptime: {uptime/3600:.1f}h",
            "",
            "Orders:",
            f"  Submitted: {metrics.orders_submitted}",
            f"  Filled: {metrics.orders_filled}",
            f"  Failed: {metrics.orders_failed}",
            f"  Success Rate: {self.get_success_rate()*100:.1f}%",
            "",
            "Execution:",
            f"  Avg Latency: {metrics.avg_execution_latency_ms:.1f}ms",
            f"  Max Latency: {metrics.max_execution_latency_ms:.1f}ms",
            "",
            "Risk Controls:",
            f"  Blocks: {metrics.risk_blocks}",
            f"  Stop Loss: {metrics.stop_loss_triggers}",
            f"  Take Profit: {metrics.take_profit_triggers}",
            f"  Trailing Stop: {metrics.trailing_stop_triggers}",
            "",
            "API:",
            f"  Total Calls: {metrics.api_calls_total}",
            f"  Failed: {metrics.api_calls_failed}",
            f"  Success Rate: {self.get_api_success_rate()*100:.1f}%",
            "",
            "Positions:",
            f"  Opened: {metrics.positions_open}",
            f"  Closed: {metrics.positions_closed}",
            f"  Total PnL: {metrics.total_realized_pnl:.2f}",
        ]
        
        if metrics.network_errors:
            lines.append("")
            lines.append("Network Errors:")
            for error_type, count in sorted(metrics.network_errors.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"  {error_type}: {count}")
        
        return '\n'.join(lines)
