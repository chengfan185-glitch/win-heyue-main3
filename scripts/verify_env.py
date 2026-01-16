"""Verify environment variables required for alerts

Checks TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in environment and suggests copying .env.example to .env if missing.
"""
import os
import sys

missing = []
if not os.environ.get('TELEGRAM_BOT_TOKEN'):
    missing.append('TELEGRAM_BOT_TOKEN')
if not os.environ.get('TELEGRAM_CHAT_ID'):
    missing.append('TELEGRAM_CHAT_ID')

if missing:
    print('Missing environment variables for Telegram alerts:')
    for m in missing:
        print(' -', m)
    print('\nSuggestion: copy .env.example to .env and fill these values, or export them in your shell:')
    print("export TELEGRAM_BOT_TOKEN=xxxxx")
    print("export TELEGRAM_CHAT_ID=yyyyy")
    sys.exit(2)
else:
    print('All required env vars present')
    sys.exit(0)
