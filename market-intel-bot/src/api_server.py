# -*- coding: utf-8 -*-
"""Minimal HTTP API for exposing TopN to the trading "tool-bot".

Endpoints
- GET /health
- GET /topn  -> current TopN JSON

This intentionally avoids heavy frameworks (FastAPI) to keep the project portable.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Tuple


def _store_paths(store_dir: str) -> Tuple[Path, Path]:
    d = Path(store_dir)
    return d / "topn_latest.json", d / "topn_latest_enriched.json"


class Handler(BaseHTTPRequestHandler):
    store_dir: str = "store"

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/health"):
            return self._send(200, {"ok": True})

        if self.path.startswith("/topn"):
            p1, p2 = _store_paths(self.store_dir)
            p = p2 if p2.exists() else p1
            if not p.exists():
                return self._send(404, {"ok": False, "error": "topn not generated yet"})
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                return self._send(500, {"ok": False, "error": f"failed to read topn: {e}"})
            return self._send(200, data)

        return self._send(404, {"ok": False, "error": "not found"})


def serve(host: str = "127.0.0.1", port: int = 8787, store_dir: str = "store") -> None:
    Handler.store_dir = store_dir
    httpd = HTTPServer((host, int(port)), Handler)
    print(f"[api] serving on http://{host}:{port} | store_dir={store_dir}")
    httpd.serve_forever()


if __name__ == "__main__":
    import os

    host = os.getenv("INTEL_API_HOST", "127.0.0.1")
    port = int(os.getenv("INTEL_API_PORT", "8787"))
    store_dir = os.getenv("STORE_DIR", "store")
    serve(host=host, port=port, store_dir=store_dir)
