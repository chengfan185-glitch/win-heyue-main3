# shared/intel_bridge.py
import json
import os
import time
from pathlib import Path
from typing import Any, Dict

shared_dir = Path(__file__).resolve().parent
repo_root = shared_dir.parent.parent
git_marker = repo_root / ".git"
if not repo_root.exists():
    raise RuntimeError(f"[INTEL-BRIDGE] repo root not found: {repo_root}")
if not git_marker.exists():
    raise RuntimeError(f"[INTEL-BRIDGE] .git marker not found: {git_marker}")

DST_DEFAULT_TOPN = shared_dir / "topn.json"
DST_DEFAULT_AI = shared_dir / "ai_intel.json"
market_intel_dir = repo_root / "market-intel-bot"
if not market_intel_dir.exists():
    raise RuntimeError(f"[INTEL-BRIDGE] market-intel-bot dir not found: {market_intel_dir}")

SRC_DEFAULT = market_intel_dir / "store" / "topn" / "latest.json"

SRC = Path(os.getenv("INTEL_BRIDGE_SRC", str(SRC_DEFAULT)))
DST_TOPN = Path(os.getenv("INTEL_BRIDGE_DST_TOPN", str(DST_DEFAULT_TOPN)))
DST_AI = Path(os.getenv("INTEL_BRIDGE_DST_AI", str(DST_DEFAULT_AI)))

POLL_SEC = float(os.getenv("INTEL_BRIDGE_POLL_SEC", "2.0"))

def atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)  # atomic on Windows NTFS

def main() -> None:
    print("[INTEL-BRIDGE] started")
    print(f"[INTEL-BRIDGE] SRC={SRC}")
    print(f"[INTEL-BRIDGE] DST_TOPN={DST_TOPN}")
    print(f"[INTEL-BRIDGE] DST_AI={DST_AI}")
    last_mtime = 0.0

    while True:
        try:
            if SRC.exists():
                mtime = SRC.stat().st_mtime
                if mtime != last_mtime:
                    last_mtime = mtime

                    with open(SRC, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    atomic_write_json(DST_TOPN, data)
                    atomic_write_json(DST_AI, data)

                    print(f"[INTEL-BRIDGE] synced @ time={data.get('time')} topn={len(data.get('topn', []))} hold={data.get('global_hold')}")
            else:
                print(f"[INTEL-BRIDGE] waiting for source file: {SRC}")
        except Exception as e:
            print("[INTEL-BRIDGE] error:", repr(e))

        time.sleep(POLL_SEC)

if __name__ == "__main__":
    main()
