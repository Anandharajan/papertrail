"""A2: link undeclared manuscript numbers to run outputs.

Transforms T = {round(x, d), x*100 (percent), scientific, thousands separator}. Candidate score
combines value match, context-token overlap with metric names, and table header similarity;
resolved with max-weight bipartite matching (scipy linear_sum_assignment). Every link carries
a confidence; numbers below min_conf stay unlinked (ORPHAN).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from scipy.optimize import linear_sum_assignment

from .scan import Number


@dataclass
class Link:
    number: int  # index into the scanned numbers
    key: str
    transform: str
    confidence: float


def renders_as(x: float, n: Number) -> str | None:
    """Return the transform name if run value x prints as the manuscript number n."""
    cands = [("identity", x), ("x100", x * 100)] if not n.percent else [("x100", x * 100), ("identity", x)]
    for name, v in cands:
        if abs(round(v, n.decimals) - n.value) < 0.5 * 10 ** (-n.decimals) + 1e-12:
            return name
        if n.value != 0 and abs(v - n.value) / abs(n.value) < 1e-3 and "e" in f"{n.value:g}":
            return "scientific"
    return None


def _tokens(key: str) -> set[str]:
    parts = re.split(r"[_\-.\s/]+|(?<=[a-z])(?=[A-Z])", key)
    syn = {"acc": "accuracy", "f1": "f1", "auc": "auroc", "rmse": "rmse", "lr": "learning", "bs": "batch"}
    out = set()
    for p in parts:
        p = p.lower()
        if p:
            out.add(p)
            if p in syn:
                out.add(syn[p])
    return out


def score(n: Number, key: str, x: float) -> tuple[float, str | None]:
    t = renders_as(x, n)
    if t is None:
        return 0.0, None
    kt = _tokens(key)
    ctx = set(n.context)
    overlap = len(kt & ctx) / max(1, len(kt))
    hdr = 0.0
    if n.header:
        hw = set(re.findall(r"[a-z0-9]+", n.header.lower()))
        hdr = len(kt & hw) / max(1, len(kt))
    precision_bonus = min(n.decimals, 4) / 4  # "87.31" is less likely a coincidence than "3"
    s = 0.45 + 0.25 * precision_bonus + 0.2 * overlap + 0.2 * hdr
    if t == "x100" and not n.percent and n.value > 1 and n.where != "table":
        s -= 0.05  # tables often drop the % sign; running text usually keeps it
    return min(s, 1.0), t


def link(numbers: list[Number], results: dict[str, float], min_conf: float = 0.6) -> list[Link]:
    keys = sorted(results)
    if not numbers or not keys:
        return []
    S = np.zeros((len(numbers), len(keys)))
    T: dict[tuple[int, int], str] = {}
    for i, n in enumerate(numbers):
        for j, k in enumerate(keys):
            s, t = score(n, k, results[k])
            if t:
                S[i, j], T[(i, j)] = s, t
    # one key may legitimately appear several times (abstract + table): allow up to 3 uses per key
    reps = 3
    big = np.repeat(S, reps, axis=1)
    r, c = linear_sum_assignment(-big)
    out = []
    for i, cc in zip(r, c):
        j = cc // reps
        if S[i, j] >= min_conf:
            out.append(Link(int(i), keys[j], T[(i, j)], float(S[i, j])))
    return sorted(out, key=lambda lk: lk.number)
