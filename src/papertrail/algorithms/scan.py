"""Extract numbers (with context) and declared \\ptval{key} links from LaTeX source."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUM = re.compile(r"(?<![\w\\{.])(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+\.\d+|-?\d+)(\s*\\?%)?(?:\s*\\times\s*10\^\{?(-?\d+)\}?)?(?!\w|\.\d)")
_PTVAL = re.compile(r"\\ptval(?:\[(\d+)\])?\{([^}]+)\}")
_ENV = re.compile(r"\\begin\{(table\*?|tabular)\}|\\end\{(table\*?)\}")
_LABEL = re.compile(r"\\label\{([^}]+)\}")
_SKIP = re.compile(r"\\(?:cite[tp]?|ref|eqref|label|section|subsection|includegraphics|vspace|hspace|usepackage|documentclass|begin|end|setlength|bibliography\w*)\*?(\[[^\]]*\])?\{[^}]*\}")


@dataclass
class Number:
    text: str
    value: float
    decimals: int
    percent: bool
    line: int
    col: int
    context: list[str] = field(default_factory=list)
    where: str = "text"  # text | table | abstract
    table: str | None = None
    header: str | None = None


@dataclass
class Declared:
    key: str
    decimals: int | None
    line: int
    where: str


def _clean(line: str) -> str:
    line = re.sub(r"(?<!\\)%.*", "", line)
    return _SKIP.sub(lambda m: " " * len(m.group(0)), line)


def scan(tex: str) -> tuple[list[Number], list[Declared]]:
    nums: list[Number] = []
    decl: list[Declared] = []
    where, table, header = "text", None, None
    for ln, raw in enumerate(tex.splitlines(), 1):
        if "\\begin{abstract}" in raw:
            where = "abstract"
        if "\\end{abstract}" in raw:
            where = "text"
        m = _ENV.search(raw)
        if m and m.group(1):
            if m.group(1).startswith("table") or where != "table":
                table = None
            where, header = "table", None
        lab = _LABEL.search(raw)
        if lab and where == "table":
            table = lab.group(1)
        for d in _PTVAL.finditer(raw):
            decl.append(Declared(d.group(2), int(d.group(1)) if d.group(1) else None, ln, where))
        line = _PTVAL.sub(lambda x: " " * len(x.group(0)), _clean(raw))
        if where == "table" and "&" in line and header is None:
            cells = [c.strip(" \\") for c in line.split("&")]
            if not any(re.fullmatch(r"-?[\d.,]+\s*%?", c) for c in cells if c):
                header = line  # first row with no purely numeric cell
        words = re.findall(r"[A-Za-z][A-Za-z0-9\-]*", line)
        for mm in _NUM.finditer(line):
            txt = mm.group(1)
            if re.fullmatch(r"(19|20)\d\d", txt) and not mm.group(2):
                continue  # years
            v = float(txt.replace(",", ""))
            if mm.group(3):
                v *= 10 ** int(mm.group(3))
            dec = len(txt.split(".")[1]) if "." in txt else 0
            col_hdr = header
            if where == "table" and header and "&" in line:
                hcells = header.split("&")
                ci = line[:mm.start(1)].count("&")
                col_hdr = hcells[ci].strip(" \\") if ci < len(hcells) else header
            nums.append(Number(txt, v, dec, bool(mm.group(2)), ln, mm.start(1), [w.lower() for w in words],
                               where, table, col_hdr))
        if m and m.group(2):
            where, table, header = "text", None, None
    return nums, decl
