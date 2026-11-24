import json

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import papertrail
from papertrail import api
from papertrail.algorithms.check import stale
from papertrail.algorithms.match import link, renders_as
from papertrail.algorithms.scan import scan
from papertrail.cli import main

PAPER = r"""\documentclass{article}
\begin{document}
\begin{abstract}
Our model reaches 87.31\% test accuracy, improving F1 to 0.912.
\end{abstract}
\section{Results}  % 99.99 in a comment is ignored
We train for 30 epochs in 2024 \cite{x2019}. Test accuracy is 87.31\% and macro F1 is 0.912.
Declared: \ptval{rmse_val}.
\begin{table}
\caption{Main results}\label{tab:main}
\begin{tabular}{lcc}
Method & Accuracy & F1 \\
Ours & 87.31 & 0.912 \\
Baseline & 81.20 & 0.850 \\
\end{tabular}
\end{table}
An unexplained 42.17 appears here.
\end{document}
"""


def results(acc=0.87314, f1=0.9121, base_acc=0.812, base_f1=0.85, rmse=0.03417, run="r1"):
    return {k: {"value": v, "run_id": run, "commit": "abc1234def"} for k, v in
            {"acc_test": acc, "f1_macro": f1, "baseline_acc": base_acc, "baseline_f1": base_f1, "rmse_val": rmse}.items()}


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "main.tex").write_text(PAPER, encoding="utf-8")
    (tmp_path / "results.json").write_text(json.dumps(results()), encoding="utf-8")
    return tmp_path


def test_scan():
    nums, decl = scan(PAPER)
    texts = [n.text for n in nums]
    assert "99.99" not in texts and "2024" not in texts and "2019" not in texts
    assert texts.count("87.31") == 3 and decl[0].key == "rmse_val"
    assert next(n for n in nums if n.text == "81.20").table == "tab:main"
    assert next(n for n in nums if n.text == "87.31").percent


def test_renders_as():
    nums, _ = scan("acc 87.31\\% and 0.912 and 1.5 \\times 10^{-3}")
    assert renders_as(0.87314, nums[0]) == "x100"
    assert renders_as(0.9121, nums[1]) == "identity"
    assert renders_as(0.9131, nums[1]) is None
    assert nums[2].value == pytest.approx(1.5e-3)


def test_build_links_and_orphans(proj):
    m = api.build(str(proj / "main.tex"), str(proj / "results.json"))
    keys = [(lk["text"] if not lk["declared"] else "decl", lk["key"]) for lk in m["links"]]
    assert ("decl", "rmse_val") in keys
    assert keys.count(("87.31", "acc_test")) == 3 and ("0.850", "baseline_f1") in keys
    assert [o["text"] for o in m["orphans"]] == ["42.17"]
    assert m["inconsistent"] == []
    real = [lk for lk in m["links"] if not lk["declared"]]
    assert all(lk["run_id"] == "r1" for lk in real)


@settings(max_examples=100, deadline=None)
@given(st.floats(0.01, 0.99), st.floats(0.0005, 0.2))
def test_injected_stale_values_always_detected(v, delta):
    """Acceptance: any change larger than the reported precision is flagged STALE."""
    lock = {"acc": {"shown": round(v * 100, 2), "decimals": 2, "percent_transform": True, "run_id": "a"}}
    assert stale(lock, {"acc": {"value": v, "run_id": "a"}}) == []
    out = stale(lock, {"acc": {"value": v + delta, "run_id": "b"}})
    assert out and out[0]["status"] == "STALE"


def test_check_after_rerun(proj, capsys):
    p = str(proj / "main.tex")
    r = str(proj / "results.json")
    api.freeze(p, r)
    assert api.check(p, r)["stale"] == []
    (proj / "results.json").write_text(json.dumps(results(acc=0.8802, run="r2")), encoding="utf-8")
    st_ = api.stale_numbers(p, r)["stale"]
    assert {s["key"] for s in st_ if s["status"] == "STALE"} == {"acc_test"}
    assert main(["check", p, "--results", r]) == 1
    d = json.loads((proj / "results.json").read_text())
    del d["f1_macro"]
    (proj / "results.json").write_text(json.dumps(d))
    assert any(s["status"] == "MISSING SOURCE" for s in api.check(p, r)["stale"])


def test_consistency_flags_mismatch(tmp_path):
    (tmp_path / "p.tex").write_text("\\begin{abstract}Accuracy 87.31\\%.\\end{abstract}\nAccuracy \\ptval{acc}.")
    (tmp_path / "r.json").write_text(json.dumps({"acc": {"value": 87.29, "run_id": "x"}}))
    m = api.build(str(tmp_path / "p.tex"), str(tmp_path / "r.json"))
    assert m["inconsistent"] == []  # 87.31 does not render from 87.29 -> orphan, not linked
    assert [o["text"] for o in m["orphans"]] == ["87.31"]


def test_where_from_table_badge_macros(proj):
    p, r = str(proj / "main.tex"), str(proj / "results.json")
    assert api.where_from(p, r, "0.912")[0]["key"] == "f1_macro"
    cells = api.rebuild_table(p, r, "tab:main")
    assert {c["key"] for c in cells} == {"acc_test", "f1_macro", "baseline_acc", "baseline_f1"}
    assert "Provenance" in api.badge(p, r)
    assert "\\ptdef{acc_test}{0.87314}{r1}" in api.macros(r)


def test_declare_dry_run_then_write(proj, capsys):
    p, r = str(proj / "main.tex"), str(proj / "results.json")
    before = (proj / "main.tex").read_text()
    assert main(["declare", p, "--results", r]) == 0
    assert (proj / "main.tex").read_text() == before  # never rewrites without --write
    assert main(["declare", p, "--results", r, "--write"]) == 0
    after = (proj / "main.tex").read_text()
    assert "\\ptval[3]{f1_macro}" in after
    assert "87.31" in after  # percent-transformed numbers are never auto-rewritten
    nums, decl = scan(after)
    assert len(decl) > 1


def test_recorder(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERTRAIL_RESULTS", str(tmp_path / "res.json"))
    papertrail.record("acc", 0.9, config={"lr": 1e-3}, split="test")

    @papertrail.recorded("loss")
    def f():
        return 0.25
    assert f() == 0.25
    d = json.loads((tmp_path / "res.json").read_text())
    assert d["acc"]["value"] == 0.9 and d["acc"]["config_hash"] and d["loss"]["value"] == 0.25
    for cmd in (["scan", str(tmp_path / "x.tex")],):
        (tmp_path / "x.tex").write_text("value 0.25")
        assert main(cmd + ["--results", str(tmp_path / "res.json")]) == 0
    assert main(["macros", "--results", str(tmp_path / "res.json")]) == 0
    assert main(["badge", str(tmp_path / "x.tex"), "--results", str(tmp_path / "res.json")]) == 0
    assert main(["freeze", str(tmp_path / "x.tex"), "--results", str(tmp_path / "res.json")]) == 0


def test_linking_precision_on_synthetic_corpus():
    """Proxy for the 20-paper acceptance test: >= 90% of result numbers linked at >= 0.9 precision."""
    rng = np.random.default_rng(0)
    tp = fp = total = 0
    for paper in range(20):
        res = {f"metric{k}_acc": float(rng.uniform(0.5, 0.99)) for k in range(8)}
        lines, gold = [], {}
        for k, v in res.items():
            txt = f"{v * 100:.2f}"
            lines.append(f"The {k.replace('_', ' ')} accuracy is {txt}\\%.")
            gold[len(lines) - 1] = k
        for _ in range(5):
            lines.append(f"We use {int(rng.integers(2, 64))} layers.")
        nums, _ = scan("\n".join(lines))
        links = link(nums, res)
        for lk in links:
            n = nums[lk.number]
            ok = gold.get(n.line - 1) == lk.key
            tp += ok
            fp += not ok
        total += len(gold)
    assert tp / total >= 0.9 and tp / (tp + fp) >= 0.9
