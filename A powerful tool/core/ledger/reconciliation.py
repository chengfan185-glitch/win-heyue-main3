# core/ledger/reconciliation.py
"""
State Reconciliation and Recovery

Ensures consistency between local ledger and exchange state on startup.
"""

from __future__ import annotations

import os
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from .trade_ledger import TradeLedger


class ReconciliationMode:
    """Recovery mode after reconciliation"""
    NORMAL = "NORMAL"              # All consistent, normal operation
    CLOSE_ONLY = "CLOSE_ONLY"      # Inconsistencies found, only allow closes
    EMERGENCY_STOP = "EMERGENCY_STOP"  # Critical issues, stop all trading
    OPEN_WITH_RISK = "OPEN_WITH_RISK"  # Inconsistencies remain, but opening is allowed (explicit override)


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

        # Reconciliation behavior toggles (prefer safety by default)
        self.strict = str(os.getenv("RECONCILE_STRICT", "false")).lower() in ("1", "true", "yes")
        self.auto_adopt = str(os.getenv("AUTO_ADOPT_EXCHANGE_POSITIONS", "true")).lower() in ("1", "true", "yes")
        self.auto_close_stale = str(os.getenv("AUTO_CLOSE_STALE_POSITIONS", "true")).lower() in ("1", "true", "yes")

        # Explicit override: allow opening even when reconciliation is not consistent.
        # Default is safety-first (False). When enabled, the runner may still operate with risk constraints.
        self.allow_open_override = str(
            os.getenv("ALLOW_OPEN_WHEN_RECONCILIATION_FAILED", "false")
        ).lower() in ("1", "true", "yes")
    
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
            exchange_dict = []
            exchange_map: Dict[str, Dict[str, Any]] = {}
            for pos in exchange_positions:
                try:
                    amt = float(pos.position_amt)
                except Exception:
                    continue
                if abs(amt) <= 0:
                    continue
                side = str(getattr(pos, "position_side", ""))
                if not side:
                    side = "LONG" if amt > 0 else "SHORT"
                item = {
                    "symbol": str(pos.symbol),
                    "positionAmt": amt,
                    "entryPrice": float(getattr(pos, "entry_price", 0.0) or 0.0),
                    "side": side,
                    "leverage": int(getattr(pos, "leverage", 1) or 1),
                }
                exchange_dict.append(item)
                # key includes side to be consistent with reconcile_positions keys
                exchange_map[f"{item['symbol']}:{str(item['side']).upper()}"] = item
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

        # Optional auto-heal: if exchange has zero positions but local ledger thinks there are opens,
        # we can mark them as CLOSED so next startup is NORMAL.
        auto_heal = str(os.getenv("AUTO_HEAL_LEDGER", "false")).lower() in ("1", "true", "yes")
        if auto_heal and not exchange_dict and comparison.get("local_only"):
            try:
                for sym in list(comparison.get("local_only") or []):
                    self.ledger.mark_position_stale(sym, note="AUTO_HEAL_LEDGER")
                # Re-run compare after healing
                comparison = self.ledger.reconcile_positions(exchange_dict)
                if comparison.get("is_consistent"):
                    print("[RECONCILIATION] ✅ Auto-heal succeeded; local stale positions closed")
            except Exception as _e:
                print(f"[RECONCILIATION] Auto-heal failed: {_e}")
        
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

        # If inconsistencies remain but operator explicitly allows opening, switch to OPEN_WITH_RISK.
        if self.mode == ReconciliationMode.CLOSE_ONLY and self.allow_open_override:
            self.mode = ReconciliationMode.OPEN_WITH_RISK
            print("[RECONCILIATION] ⚠️  OPEN override enabled: switching to OPEN_WITH_RISK mode")
        
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
        if self.mode in (ReconciliationMode.CLOSE_ONLY, ReconciliationMode.OPEN_WITH_RISK):
            try:
                self._handle_close_only_mode(comparison, exchange_map)
                # Re-run compare after corrective actions
                comparison2 = self.ledger.reconcile_positions(exchange_dict)
                self.reconciliation_report["matches"] = comparison2.get("matches", [])
                self.reconciliation_report["local_only"] = comparison2.get("local_only", [])
                self.reconciliation_report["exchange_only"] = comparison2.get("exchange_only", [])
                self.reconciliation_report["discrepancies"] = comparison2.get("discrepancies", [])
                self.reconciliation_report["is_consistent"] = bool(comparison2.get("is_consistent"))

                if comparison2.get("is_consistent"):
                    self.mode = ReconciliationMode.NORMAL
                    self.reconciliation_report["mode"] = self.mode
                    print("[RECONCILIATION] ✅ Recovery actions achieved consistency; switching to NORMAL")
                elif self.strict:
                    self.mode = ReconciliationMode.EMERGENCY_STOP
                    self.reconciliation_report["mode"] = self.mode
                    self.reconciliation_report["status"] = "error"
                    self.reconciliation_report["error"] = "strict reconciliation failed"
                    print("[RECONCILIATION] 🚨 STRICT mode - inconsistencies remain; EMERGENCY_STOP")
            except Exception as e:
                self.mode = ReconciliationMode.EMERGENCY_STOP
                self.reconciliation_report = {
                    "status": "error",
                    "mode": self.mode,
                    "strict": self.strict,
                    "auto_adopt": self.auto_adopt,
                    "auto_close_stale": self.auto_close_stale,
                    "local_positions": len(local_positions),
                    "exchange_positions": len(exchange_dict),
                    "matches": comparison.get("matches", []),
                    "local_only": comparison.get("local_only", []),
                    "exchange_only": comparison.get("exchange_only", []),
                    "discrepancies": comparison.get("discrepancies", []),
                    "error": repr(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                print(f"[RECONCILIATION] 🚨 Recovery action failed; EMERGENCY_STOP err={e}")
        
        # Explicit override: allow opening new positions even if inconsistencies remain.
        # NOTE: This does NOT claim the state is consistent; it only relaxes the entry hard-block at the runner layer.
        if self.mode == ReconciliationMode.CLOSE_ONLY and self.allow_open_override:
            self.mode = ReconciliationMode.OPEN_WITH_RISK
            self.reconciliation_report["mode"] = self.mode
            self.reconciliation_report["allow_open_override"] = True
            print("[RECONCILIATION] ⚠️  OPEN override enabled: switching to OPEN_WITH_RISK")

        return self.mode, self.reconciliation_report
    
    def _handle_close_only_mode(self, comparison: Dict[str, Any], exchange_map: Dict[str, Dict[str, Any]]):
        """Handle discrepancies in CLOSE_ONLY mode.

        Principle: **Exchange is source of truth** for live trading.
        - If exchange has positions that local ledger does not: adopt them (if enabled).
        - If local ledger has positions that exchange does not: mark them stale/closed (if enabled).
        """
        # Adopt exchange-only positions
        adopted = 0
        if self.auto_adopt:
            for key in comparison.get("exchange_only", []) or []:
                pinfo = exchange_map.get(key)
                if not pinfo:
                    continue
                try:
                    self.ledger.adopt_exchange_position_info(pinfo, source="reconciliation_auto_adopt")
                    adopted += 1
                    print(f"[RECONCILIATION] ✅ Adopted exchange position: {key}")
                except Exception as e:
                    print(f"[RECONCILIATION] ⚠️  adopt failed key={key} err={e}")
        if adopted > 0:
            print(f"[RECONCILIATION] ✅ Adopted {adopted} exchange positions into local ledger")

        # Close local-only positions (ghosts)
        closed = 0
        if self.auto_close_stale:
            for sym in comparison.get("local_only", []) or []:
                try:
                    if self.ledger.mark_position_stale(sym, note="RECONCILE_STALE"):
                        closed += 1
                        print(f"[RECONCILIATION] ✅ Marked local position stale: {sym}")
                except Exception as e:
                    print(f"[RECONCILIATION] ⚠️  mark stale failed sym={sym} err={e}")
        if closed > 0:
            print(f"[RECONCILIATION] ✅ Closed {closed} stale local positions in ledger")
    
    def can_open_new_positions(self) -> bool:
        """Check if we can open new positions"""
        return self.mode in (ReconciliationMode.NORMAL, ReconciliationMode.OPEN_WITH_RISK)
    
    def can_close_positions(self) -> bool:
        """Check if we can close positions"""
        return self.mode in (ReconciliationMode.NORMAL, ReconciliationMode.CLOSE_ONLY)
    
    def get_mode(self) -> str:
        """Get current reconciliation mode"""
        return self.mode
    
    def get_report(self) -> Dict[str, Any]:
        """Get reconciliation report"""
        return self.reconciliation_report
