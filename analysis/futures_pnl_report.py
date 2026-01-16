#!/usr/bin/env python3
"""
简单的合约 PnL 统计脚本。

从 logs/ledger/positions.jsonl 读取仓位记录：
- 统计 OPEN / CLOSED 数量
- 汇总已实现 PnL
- 每个 symbol 的盈亏情况

注意：这里是操作员辅助工具，不影响核心策略。
"""

from pathlib import Path
import json
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "logs" / "ledger" / "positions.jsonl"

def load_positions(path: Path):
    if not path.exists():
        print(f"[WARN] positions file not found: {path}")
        return []
    items = []
    with path.open("r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                items.append(json.loads(ln))
            except Exception as exc:
                print("skip bad line:", exc)
    return items

def main():
    positions = load_positions(LEDGER_PATH)
    if not positions:
        print("no positions found.")
        return

    open_pos = [p for p in positions if p.get("status") == "OPEN"]
    closed_pos = [p for p in positions if p.get("status") != "OPEN"]

    print(f"Total positions: {len(positions)}")
    print(f"  OPEN   : {len(open_pos)}")
    print(f"  CLOSED : {len(closed_pos)}")

    total_realized = 0.0
    by_symbol = defaultdict(lambda: {"realized": 0.0, "count": 0})

    for p in closed_pos:
        sym = p.get("symbol", "UNKNOWN")
        pnl = float(p.get("realized_pnl") or 0.0)
        total_realized += pnl
        by_symbol[sym]["realized"] += pnl
        by_symbol[sym]["count"] += 1

    print("\n=== Realized PnL by symbol ===")
    for sym, agg in sorted(by_symbol.items()):
        print(f"{sym:10s} trades={agg['count']:4d} realized_pnl={agg['realized']:.6f}")

    print(f"\nTotal realized pnl: {total_realized:.6f}")

if __name__ == "__main__":
    main()
