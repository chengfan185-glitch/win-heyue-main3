# core/config/env_loader.py
from __future__ import annotations

import os
from typing import Any, Callable, Optional, TypeVar

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None  # type: ignore

T = TypeVar("T")


_LOADED = False


def load_env(dotenv_path: Optional[str] = None, *, override: bool = False) -> None:
    """
    Loads environment variables from .env (if python-dotenv is installed).
    Safe to call multiple times.
    """
    global _LOADED
    if _LOADED:
        return
    if load_dotenv is None:
        _LOADED = True
        return
    try:
        load_dotenv(dotenv_path=dotenv_path, override=override)
    finally:
        _LOADED = True


def get_env(
    key: str,
    default: Any = None,
    *,
    cast: Optional[Callable[[str], T]] = None,
    required: bool = False,
    strip: bool = True,
) -> Any:
    """
    Read env var with optional casting.

    Examples:
      ENABLE_REAL_TRADING = get_env("ENABLE_REAL_TRADING", "false", cast=env_bool)
      FORCE_TRADE_AMOUNT  = get_env("FORCE_TRADE_AMOUNT", 10, cast=float)
    """
    v = os.getenv(key)
    if v is None:
        if required:
            raise RuntimeError(f"Missing required env: {key}")
        return default

    if strip and isinstance(v, str):
        v = v.strip()

    if cast is None:
        return v

    try:
        return cast(v)
    except Exception as e:
        raise RuntimeError(f"Invalid env {key}={v!r}: {e}") from e


def env_bool(v: str) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(v: str) -> int:
    return int(str(v).strip())


def env_float(v: str) -> float:
    return float(str(v).strip())
