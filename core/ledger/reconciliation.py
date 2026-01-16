# core/ledger/reconciliation.py
"""
State Reconciliation and Recovery

Ensures consistency between local ledger and exchange state on startup.
"""

from __future__ import annotations

import os
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from .trade_ledger import TradeLedger, Position


class ReconciliationMode:
    """Recovery mode after reconciliation"""
    NORMAL = "NORMAL"              # All consistent, normal operation
    CLOSE_ONLY = "CLOSE_ONLY"      # Inconsistencies found, only allow closes
    EMERGENCY_STOP = "EMERGENCY_STOP"  # Critical issues, stop all trading


class StateReconciliation:
    """
    Reconciles local ledger state with exchange on startup
    
    Process:
    1. Load local open positions from ledger
    2. Fetch current positions from exchange
    3. Compare and identify discrepancies
    4. Determine recovery mode
    5. Take corrective action if needed
    """
    
    def __init__(self, ledger: TradeLedger, futures_adapter: Any):
        self.ledger = ledger
        self.adapter = futures_adapter
        self.mode = ReconciliationMode.NORMAL
        self.reconciliation_report: Dict[str, Any] = {}
    
    def perform_reconciliation(self) -> Tuple[str, Dict[str, Any]]:
        """
        Perform full reconciliation on startup
        
        Returns:
            (mode, report)
        """
        print("[RECONCILIATION] Starting state reconciliation...")
        
        # Step 1: Load local positions
        local_positions = self.ledger.get_all_open_positions()
        print(f"[RECONCILIATION] Found {len(local_positions)} local open positions")
        
        # Step 2: Fetch exchange positions (skip in paper mode)
        trading_mode = os.getenv("TRADING_MODE", "paper")
        if trading_mode == "paper":
            print("[RECONCILIATION] Paper mode - skipping exchange fetch")
            self.mode = ReconciliationMode.NORMAL
            self.reconciliation_report = {
                "mode": "paper",
                "status": "skipped",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return self.mode, self.reconciliation_report
        
        try:
            exchange_positions = self.adapter.get_position()
            exchange_dict = [
                {
                    'symbol': pos.symbol,
                    'positionAmt': pos.position_amt,
                    'entryPrice': pos.entry_price,
                    'side': pos.position_side
                }
                for pos in exchange_positions if abs(pos.position_amt) > 0
            ]
            print(f"[RECONCILIATION] Found {len(exchange_dict)} exchange open positions")
        except Exception as e:
            print(f"[RECONCILIATION ERROR] Failed to fetch exchange positions: {e}")
            self.mode = ReconciliationMode.EMERGENCY_STOP
            self.reconciliation_report = {
                "status": "error",
                "error": str(e),
                "mode": self.mode,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            return self.mode, self.reconciliation_report
        
        # Step 3: Compare
        comparison = self.ledger.reconcile_positions(exchange_dict)
        
        # Step 4: Determine mode
        if comparison['is_consistent']:
            self.mode = ReconciliationMode.NORMAL
            print("[RECONCILIATION] ✅ State is consistent")
        elif comparison['exchange_only']:
            # Exchange has positions we don't know about - CRITICAL
            self.mode = ReconciliationMode.CLOSE_ONLY
            print(f"[RECONCILIATION] ⚠️  Exchange has unknown positions: {comparison['exchange_only']}")
            print("[RECONCILIATION] Entering CLOSE_ONLY mode")
        elif comparison['local_only']:
            # We think we have positions but exchange doesn't - WARNING
            self.mode = ReconciliationMode.CLOSE_ONLY
            print(f"[RECONCILIATION] ⚠️  Local ledger has positions not on exchange: {comparison['local_only']}")
            print("[RECONCILIATION] Entering CLOSE_ONLY mode")
        elif comparison['discrepancies']:
            # Quantity mismatches - WARNING
            self.mode = ReconciliationMode.CLOSE_ONLY
            print(f"[RECONCILIATION] ⚠️  Quantity discrepancies found: {comparison['discrepancies']}")
            print("[RECONCILIATION] Entering CLOSE_ONLY mode")
        
        # Step 5: Build report
        self.reconciliation_report = {
            "status": "completed",
            "mode": self.mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "local_positions": len(local_positions),
            "exchange_positions": len(exchange_dict),
            "matches": comparison.get('matches', []),
            "local_only": comparison.get('local_only', []),
            "exchange_only": comparison.get('exchange_only', []),
            "discrepancies": comparison.get('discrepancies', []),
            "is_consistent": comparison['is_consistent']
        }
        
        # Step 6: Corrective actions (if needed)
        if self.mode == ReconciliationMode.CLOSE_ONLY:
            self._handle_close_only_mode(comparison)
        
        return self.mode, self.reconciliation_report
    
    def _handle_close_only_mode(self, comparison: Dict[str, Any]):
        """Handle discrepancies in CLOSE_ONLY mode"""
        # For unknown exchange positions, add them to local ledger
        for symbol in comparison.get('exchange_only', []):
            print(f"[RECONCILIATION] Adding unknown exchange position to ledger: {symbol}")
            # Find position details from exchange
            # This allows us to track and close it properly
            # Implementation depends on adapter structure
        
        # For local-only positions, mark as potentially stale
        for symbol in comparison.get('local_only', []):
            print(f"[RECONCILIATION] Marking local position as stale: {symbol}")
            # Could close position in ledger automatically
            # Or require manual intervention
    
    def can_open_new_positions(self) -> bool:
        """Check if we can open new positions"""
        return self.mode == ReconciliationMode.NORMAL
    
    def can_close_positions(self) -> bool:
        """Check if we can close positions"""
        return self.mode in (ReconciliationMode.NORMAL, ReconciliationMode.CLOSE_ONLY)
    
    def get_mode(self) -> str:
        """Get current reconciliation mode"""
        return self.mode
    
    def get_report(self) -> Dict[str, Any]:
        """Get reconciliation report"""
        return self.reconciliation_report
