#!/usr/bin/env python3
"""
Basic .env verification helper.

- 检查 .env 是否存在
- 检查是否包含 BOM
- 检查是否有重复 key
- 打印 STARTUP_WARMUP_MINUTES 当前值
- 检查 Telegram 配置（TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID）
"""

from pathlib import Path
from collections import defaultdict
import re
import sys
import os

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE_PATH = ROOT / ".env.example"

KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")

def detect_bom(path: Path) -> str | None:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if raw.startswith(b"\xfe\xff"):
        return "utf-16-be"
    if raw.startswith(b"\x00\x00\xfe\xff") or raw.startswith(b"\xff\xfe\x00\x00"):
        return "utf-32"
    return None

def scan_keys(path: Path):
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    lines = text.splitlines()
    keys: dict[str, list[tuple[int,str]]] = defaultdict(list)
    for i, ln in enumerate(lines, start=1):
        m = KEY_RE.match(ln)
        if m:
            keys[m.group(1)].append((i, ln))
    return keys, lines

def check_telegram_vars():
    """Check if Telegram environment variables are set"""
    print("\n" + "=" * 60)
    print("Checking Telegram Configuration")
    print("=" * 60)
    
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
    
    if enabled:
        print("[INFO] TELEGRAM_ENABLED=true")
        
        if token:
            # Mask the token for security
            masked = token[:8] + "..." + token[-4:] if len(token) > 12 else "***"
            print(f"[OK] TELEGRAM_BOT_TOKEN is set: {masked}")
        else:
            print("[WARN] TELEGRAM_BOT_TOKEN is not set")
            print("       Alerts will not be sent to Telegram")
        
        if chat_id:
            print(f"[OK] TELEGRAM_CHAT_ID is set: {chat_id}")
        else:
            print("[WARN] TELEGRAM_CHAT_ID is not set")
            print("       Alerts will not be sent to Telegram")
        
        if not (token and chat_id):
            print("\n[ACTION REQUIRED] To enable Telegram alerts:")
            if ENV_EXAMPLE_PATH.exists():
                print(f"  1. Copy {ENV_EXAMPLE_PATH.name} to {ENV_PATH.name}")
            print(f"  2. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in {ENV_PATH.name}")
            print("  3. Get bot token from @BotFather on Telegram")
            print("  4. Get chat ID by messaging your bot and checking /getUpdates")
    else:
        print("[INFO] TELEGRAM_ENABLED=false (or not set)")
        print("       Telegram alerts are disabled")
        print("       Alerts will only be logged locally")
        
        if token or chat_id:
            print("[NOTE] Telegram credentials are set but TELEGRAM_ENABLED=false")
            print("       Set TELEGRAM_ENABLED=true to enable alerts")

def main() -> int:
    if not ENV_PATH.exists():
        print(f"[ERROR] .env not found at: {ENV_PATH}")
        
        if ENV_EXAMPLE_PATH.exists():
            print(f"\n[ACTION] Copy {ENV_EXAMPLE_PATH.name} to {ENV_PATH.name}:")
            print(f"  cp {ENV_EXAMPLE_PATH} {ENV_PATH}")
            print(f"  # Then edit {ENV_PATH.name} and fill in your values")
        else:
            print(f"\n[ACTION] Create {ENV_PATH.name} with required configuration")
        
        return 2
    
    bom = detect_bom(ENV_PATH)
    if bom:
        print(f"[WARN] Detected BOM encoding: {bom}. 建议保存为 UTF-8 无 BOM。")

    keys, lines = scan_keys(ENV_PATH)
    dupes = {k: v for k,v in keys.items() if len(v) > 1}
    if dupes:
        print("[ERROR] Duplicate keys detected in .env:")
        for k, occ in dupes.items():
            print(f"  {k}:")
            for line_no, ln in occ:
                print(f"    line {line_no}: {ln}")
        print("请删除重复项，避免运行时读取到错误配置。")
        return 3

    content = "\n".join(lines)
    m = re.search(r"^STARTUP_WARMUP_MINUTES\s*=\s*(\d+)", content, flags=re.M)
    if m:
        print(f"[INFO] STARTUP_WARMUP_MINUTES = {m.group(1)}")
    else:
        print("[WARN] STARTUP_WARMUP_MINUTES 未显式设置，将回退到默认值 0。")

    # Load .env for Telegram checks
    try:
        from core.config.env_loader import load_env
        load_env(str(ENV_PATH), override=False)
    except Exception as e:
        print(f"[WARN] Could not load .env with env_loader: {e}")
        # Fallback: parse .env manually
        for line in lines:
            if '=' in line and not line.strip().startswith('#'):
                try:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and not os.getenv(key):
                        os.environ[key] = value
                except Exception:
                    pass
    
    # Check Telegram configuration
    check_telegram_vars()

    print("\n[OK] .env verification passed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

