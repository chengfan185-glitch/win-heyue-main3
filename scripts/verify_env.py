#!/usr/bin/env python3
"""
Basic .env verification helper.

- 检查 .env 是否存在
- 检查是否包含 BOM
- 检查是否有重复 key
- 打印 STARTUP_WARMUP_MINUTES 当前值
"""

from pathlib import Path
from collections import defaultdict
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

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

def main() -> int:
    if not ENV_PATH.exists():
        print(f"[ERROR] .env not found at: {ENV_PATH}")
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

    print("[OK] .env verification passed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
