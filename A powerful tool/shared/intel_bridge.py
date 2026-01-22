# shared/intel_bridge.py
import json
import os
import time
from pathlib import Path
from typing import Any, Dict

SRC = Path(r"C:\Users\ASUS\Desktop\market-intel-bot\store\topn\latest.json")
DST_TOPN = Path(r"C:\Users\ASUS\Desktop\win-heyue-main3\shared\topn.json")
DST_AI = Path(r"C:\Users\ASUS\Desktop\win-heyue-main3\shared\ai_intel.json")

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

                    # 1) shared/topn.json：工具人主入口（保持 market-intel 最新结构）
                    atomic_write_json(DST_TOPN, data)

                    # 2) shared/ai_intel.json：兼容旧接口（同内容镜像）
                    atomic_write_json(DST_AI, data)

                    print(f"[INTEL-BRIDGE] synced @ time={data.get('time')} topn={len(data.get('topn', []))} hold={data.get('global_hold')}")
        except Exception as e:
            print("[INTEL-BRIDGE] error:", repr(e))

        time.sleep(POLL_SEC)

if __name__ == "__main__":
    main()
