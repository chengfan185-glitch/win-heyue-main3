"""Quick local test for AlertManager

Usage:
  python scripts/test_alerts.py

This script imports AlertManager, creates a disabled instance and an enabled-but-no-token instance,
verifies send_alert exists and does not raise. It does not require valid Telegram credentials.
"""
import os
import sys
import logging
from pathlib import Path

# Add repo root to path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.alerts.alert_manager import AlertManager

logging.basicConfig(level=logging.DEBUG)

# disabled instance (no sending)
a1 = AlertManager(enabled=False)
print("disabled has_send_alert:", hasattr(a1, 'send_alert'))
a1.send_alert('INFO', 'test', 'this is a test (disabled)')

# enabled flag true but no token => send should be disabled internally
# this checks no exception is raised when send_alert is called
try:
    a2 = AlertManager(enabled=True, bot_token=os.environ.get('TELEGRAM_BOT_TOKEN'), chat_id=os.environ.get('TELEGRAM_CHAT_ID'))
    print("enabled-instance has_send_alert:", hasattr(a2, 'send_alert'))
    a2.send_alert('INFO', 'test', 'this is a test (maybe disabled)')
    print('send_alert called successfully')
except Exception as e:
    print('ERROR during test_alerts:', e)
    raise
