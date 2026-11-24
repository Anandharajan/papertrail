"""A3 staleness / orphans and A4 consistency over a link map (papertrail.lock.json)."""
from __future__ import annotations

from typing import Any


def stale(lock: dict[str, dict[str, Any]], results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """lock: key -> {shown (float), decimals, percent, run_id, commit, ...} at freeze time.

    STALE if the current value differs from the shown value beyond reported precision,
    or the key vanished from results (MISSING SOURCE).
    """
    out = []
    for key, ln in lock.items():
        cur = results.get(key)
        if cur is None:
            out.append({"key": key, "status": "MISSING SOURCE", "shown": ln["shown"]})
            continue
        v = cur["value"] * (100 if ln.get("percent_transform") else 1)
        tol = 0.5 * 10 ** (-int(ln.get("decimals", 2)))
        if abs(round(v, int(ln.get("decimals", 2))) - ln["shown"]) >= tol - 1e-12:
            out.append({"key": key, "status": "STALE", "shown": ln["shown"],
                        "current": round(v, int(ln.get("decimals", 2))),
                        "run_then": ln.get("run_id"), "run_now": cur.get("run_id")})
        elif cur.get("run_id") != ln.get("run_id"):
            out.append({"key": key, "status": "RERUN (same value)", "shown": ln["shown"]})
    return out


def consistency(occurrences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """occurrences: [{key, shown, decimals, line, where}] -> keys whose renderings disagree."""
    by: dict[str, list[dict[str, Any]]] = {}
    for o in occurrences:
        by.setdefault(o["key"], []).append(o)
    out = []
    for key, occ in by.items():
        d = min(o["decimals"] for o in occ)
        vals = {round(o["shown"], d) for o in occ}
        if len(vals) > 1:
            out.append({"key": key, "values": sorted(vals), "lines": [o["line"] for o in occ],
                        "where": sorted({o["where"] for o in occ})})
    return out
