# core/ledger/__init__.py
"""
Trading Ledger System - Single Source of Truth

Provides audit trail for all trading activities with proper entity relationships.
"""

from .trade_ledger import (
    TradeLedger,
    Order,
    Fill,
    Position,
    Trade,
    LedgerQuery
)

# Backward-compatible alias (many scripts expect `from core.ledger import Ledger`)
Ledger = TradeLedger

__all__ = [
    'TradeLedger',
    'Ledger',
    'Order', 
    'Fill',
    'Position',
    'Trade',
    'LedgerQuery'
]
