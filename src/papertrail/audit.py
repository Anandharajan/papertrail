"""Local SQLite audit log for every MCP tool call (plan A3.2)."""
from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path


def db_path() -> Path:
    return Path(os.environ.get("PAPERTRAIL_HOME", Path.home() / ".papertrail")) / "audit.db"


def log_call(tool: str, args: dict, ok: bool, path: Path | None = None) -> None:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(p) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("CREATE TABLE IF NOT EXISTS audit(ts REAL, tool TEXT, args TEXT, ok INTEGER)")
        con.execute("INSERT INTO audit VALUES (?,?,?,?)",
                    (time.time(), tool, json.dumps(args, default=str)[:4000], int(ok)))
