import json
from pathlib import Path
from datetime import datetime, timezone

path = Path("logs/ledger/positions.jsonl")
if not path.exists():
    print("no positions.jsonl")
    raise SystemExit(0)

lines = path.read_text(encoding="utf-8").splitlines()
open_null = []
for ln in lines[::-1]:
    if not ln.strip():
        continue
    obj = json.loads(ln)
    if obj.get("status") == "OPEN" and obj.get("open_order_id") in (None, "", "null"):
        # 只处理 ETH/SOL（你也可以删掉这行限制）
        if obj.get("symbol") in ("ETHUSDT", "SOLUSDT"):
            open_null.append(obj)

now_iso = datetime.now(timezone.utc).isoformat()
for obj in open_null:
    obj["status"] = "STALE"
    obj["closed_at"] = obj.get("closed_at") or datetime.now(timezone.utc).timestamp()
    obj["close_reason"] = "auto_mark_stale_open_order_id_null"
    obj["updated_at_iso"] = now_iso
    print("APPEND STALE:", obj["symbol"], obj["position_id"])
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
