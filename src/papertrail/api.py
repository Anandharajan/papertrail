"""Public API (CLI and MCP). Never rewrites the user's .tex unless write=True."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import roots
from .algorithms.check import consistency, stale
from .algorithms.match import link
from .algorithms.scan import scan

LOCK = "papertrail.lock.json"


def _tex_files(paper: Path) -> list[Path]:
    return sorted(paper.rglob("*.tex")) if paper.is_dir() else [paper]


def _results(path: Path) -> dict[str, dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def build(paper: str, results: str, min_conf: float = 0.6) -> dict[str, Any]:
    """Scan the manuscript, link declared and undeclared numbers, return the link map."""
    res = _results(roots.check(results))
    values = {k: v["value"] for k, v in res.items()}
    links, orphans, occ = [], [], []
    for f in _tex_files(roots.check(paper)):
        nums, decl = scan(f.read_text(encoding="utf-8"))
        for d in decl:
            if d.key in res:
                dec = d.decimals if d.decimals is not None else 2
                shown = round(values[d.key], dec)
                links.append({"file": f.name, "line": d.line, "key": d.key, "declared": True, "confidence": 1.0,
                              "shown": shown, "decimals": dec, "percent_transform": False, "where": d.where})
                occ.append({"key": d.key, "shown": shown, "decimals": dec, "line": d.line, "where": d.where})
            else:
                orphans.append({"file": f.name, "line": d.line, "text": f"\\ptval{{{d.key}}}", "reason": "unknown key"})
        linked = {lk.number: lk for lk in link(nums, values, min_conf)}
        for i, n in enumerate(nums):
            lk = linked.get(i)
            if lk is None:
                if n.decimals > 0 or n.percent:  # integers like "3 layers" are rarely results
                    orphans.append({"file": f.name, "line": n.line, "text": n.text, "reason": "no source"})
                continue
            links.append({"file": f.name, "line": n.line, "col": n.col, "text": n.text, "key": lk.key,
                          "declared": False, "confidence": round(lk.confidence, 3), "transform": lk.transform,
                          "shown": n.value, "decimals": n.decimals, "percent_transform": lk.transform == "x100",
                          "where": n.where, "table": n.table})
            occ.append({"key": lk.key, "shown": n.value / (100 if lk.transform == "x100" else 1) * (100 if lk.transform == "x100" else 1),
                        "decimals": n.decimals, "line": n.line, "where": n.where})
    for lk in links:
        r = res.get(lk["key"], {})
        lk.update(run_id=r.get("run_id"), commit=r.get("commit"), config_hash=r.get("config_hash"))
    return {"links": links, "orphans": orphans, "inconsistent": consistency(occ)}


def freeze(paper: str, results: str, out: str | None = None) -> Path:
    """Write papertrail.lock.json next to the paper (the provenance snapshot)."""
    m = build(paper, results)
    p = Path(out) if out else (Path(paper) if Path(paper).is_dir() else Path(paper).parent) / LOCK
    p.write_text(json.dumps(m, indent=2), encoding="utf-8")
    return p


def check(paper: str, results: str, lock: str | None = None) -> dict[str, Any]:
    lp = Path(lock) if lock else (Path(paper) if Path(paper).is_dir() else Path(paper).parent) / LOCK
    cur = build(paper, results)
    if lp.exists():
        old = json.loads(lp.read_text(encoding="utf-8"))
        lockmap = {lk["key"]: lk for lk in old["links"]}
    else:
        lockmap = {lk["key"]: lk for lk in cur["links"]}
    st = stale(lockmap, _results(Path(results)))
    # a number that was linked at freeze time and is now STALE is reported once, as stale, not also as an orphan
    stale_texts = {str(lockmap[s["key"]].get("text")) for s in st if s["status"] == "STALE" and s["key"] in lockmap}
    orphans = [o for o in cur["orphans"] if o["text"] not in stale_texts]
    return {"stale": st, "orphans": orphans, "inconsistent": cur["inconsistent"]}


def write_declared(paper: str, results: str, min_conf: float = 0.8, write: bool = False) -> list[dict[str, Any]]:
    """Replace confidently-linked raw numbers with \\ptval{key}. Dry run unless write=True."""
    m = build(paper, results)
    edits = [lk for lk in m["links"] if not lk["declared"] and lk["confidence"] >= min_conf and not lk["percent_transform"]]
    if write:
        for f in _tex_files(Path(paper)):
            lines = f.read_text(encoding="utf-8").splitlines(keepends=True)
            for e in sorted((e for e in edits if e["file"] == f.name), key=lambda e: (-e["line"], -e["col"])):
                ln = lines[e["line"] - 1]
                c = e["col"]
                if ln[c:c + len(e["text"])] == e["text"]:
                    lines[e["line"] - 1] = ln[:c] + f"\\ptval[{e['decimals']}]{{{e['key']}}}" + ln[c + len(e["text"]):]
            f.write_text("".join(lines), encoding="utf-8")
    return edits


def macros(results: str) -> str:
    """papertrail-values.tex: \\ptdef{key}{value}{run_id} lines consumed by papertrail.sty."""
    res = _results(Path(results))
    return "".join(f"\\ptdef{{{k}}}{{{v['value']!r}}}{{{v.get('run_id') or ''}}}\n" for k, v in sorted(res.items()))


def badge(paper: str, results: str) -> str:
    """Provenance appendix (LaTeX) listing every linked number and its run."""
    m = build(paper, results)
    def esc(s: str) -> str:  # no backslashes inside f-string expressions: they need Python 3.12
        return s.replace("_", r"\_")

    rows = "\n".join(f"{esc(lk['key'])} & {lk['shown']} & {lk.get('run_id') or '--'} & "
                     f"{(lk.get('commit') or '--')[:8]} & {lk['confidence']} \\\\" for lk in m["links"])
    return ("\\section*{Provenance of reported numbers}\n\\begin{tabular}{lllll}\n"
            "Key & Value & Run & Commit & Confidence \\\\ \\hline\n" + rows + "\n\\end{tabular}\n")


# ---------------- MCP tools ----------------

def where_from(paper: str, results: str, number_or_key: str) -> list[dict[str, Any]]:
    """Where did this number (e.g. '87.3') or key come from? Returns run_id, commit and confidence."""
    m = build(paper, results)
    return [lk for lk in m["links"] if lk["key"] == number_or_key or lk.get("text") == number_or_key
            or str(lk["shown"]) == number_or_key]


def stale_numbers(paper: str, results: str) -> dict[str, Any]:
    """Stale, orphan and inconsistent numbers relative to the frozen lock file."""
    return check(paper, results)


def rebuild_table(paper: str, results: str, table_id: str) -> list[dict[str, Any]]:
    """Cells of a labelled table with the value shown vs the current run value."""
    m = build(paper, results)
    res = _results(Path(results))
    out = []
    for lk in m["links"]:
        if lk.get("table") == table_id:
            v = res[lk["key"]]["value"] * (100 if lk["percent_transform"] else 1)
            out.append({"line": lk["line"], "key": lk["key"], "shown": lk["shown"], "current": round(v, lk["decimals"])})
    return out


TOOLS = [where_from, stale_numbers, rebuild_table]
