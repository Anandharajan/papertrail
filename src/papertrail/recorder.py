"""A1 (declared links): record named results from experiment runs into results.json.

    import papertrail
    papertrail.record("acc_test", 0.8731, split="test")

    @papertrail.recorded("f1_macro")
    def evaluate(...): return 0.91
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, TypeVar
from collections.abc import Callable

F = TypeVar("F", bound=Callable[..., Any])
_RUN_ID = os.environ.get("PAPERTRAIL_RUN_ID") or uuid.uuid4().hex[:12]


def results_path() -> Path:
    return Path(os.environ.get("PAPERTRAIL_RESULTS", "results.json"))


def git_commit(cwd: str | None = None) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def config_hash(config: Any) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, default=str).encode()).hexdigest()[:16]


def record(name: str, value: float, *, config: Any = None, path: Path | None = None, **meta: Any) -> dict[str, Any]:
    p = path or results_path()
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    entry = {"value": float(value), "run_id": _RUN_ID, "commit": git_commit(),
             "config_hash": config_hash(config) if config is not None else None,
             "time": time.strftime("%Y-%m-%dT%H:%M:%S"), **meta}
    data[name] = entry
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(p)
    return entry


def recorded(name: str, **meta: Any) -> Callable[[F], F]:
    def deco(fn: F) -> F:
        @functools.wraps(fn)
        def wrap(*a: Any, **k: Any) -> Any:
            v = fn(*a, **k)
            record(name, v, **meta)
            return v
        return wrap  # type: ignore[return-value]
    return deco
