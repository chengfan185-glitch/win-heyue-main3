from __future__ import annotations

import os
from dotenv import load_dotenv

from src.store import read_json


def main() -> None:
    load_dotenv()
    path = os.getenv("TOPN_FILE", "store/topn/latest.json")
    obj = read_json(path, {})
    topn = obj.get("topn") or []
    print(f"TopN file: {path}")
    for r in topn:
        print(f"{r['symbol']:10s} score={r['score']:.3f} trend={r['trend']:.4f} breakout={r['breakout']:.3f} vol={r['vol']:.6f} noise={r['noise']:.2f}")


if __name__ == "__main__":
    main()
