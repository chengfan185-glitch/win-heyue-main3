# core/execution/__init__.py
"""
Order Execution Module

Production-grade order lifecycle management.
"""

from .order_executor import OrderExecutor, ExecutionResult

__all__ = ['OrderExecutor', 'ExecutionResult']
