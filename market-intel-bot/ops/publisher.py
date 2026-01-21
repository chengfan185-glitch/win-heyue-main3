from __future__ import annotations

import time
from typing import Any, Dict, List

import requests

from src.store import write_json


def publish_file(topn_file: str, payload: Dict[str, Any]) -> None:
    write_json(topn_file, payload)


def publish_webhook(url: str, bearer: str, payload: Dict[str, Any], timeout: int = 15) -> None:
    if not url:
        return
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    r.raise_for_status()
