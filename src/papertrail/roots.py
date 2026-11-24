"""Least-privilege file access for the MCP layer (plan A3.2).

Set PAPERTRAIL_ROOTS to an os.pathsep-separated list of directories. When set, the
MCP tools may only read files inside those roots. The CLI is not restricted.
"""
from __future__ import annotations

import os
from pathlib import Path


def check(path: str | Path) -> Path:
    p = Path(path).resolve()
    roots = os.environ.get("PAPERTRAIL_ROOTS")
    if roots:
        allowed = [Path(r).resolve() for r in roots.split(os.pathsep) if r]
        if not any(p == r or r in p.parents for r in allowed):
            raise PermissionError(f"{p} is outside the configured read-only roots")
    return p
