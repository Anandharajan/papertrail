"""papertrail command line."""
from __future__ import annotations

import argparse
import json

from . import api


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="papertrail")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("scan", "freeze", "check", "badge", "declare"):
        p = sub.add_parser(name)
        p.add_argument("paper")
        p.add_argument("--results", default="results.json")
        if name == "declare":
            p.add_argument("--write", action="store_true", help="actually rewrite .tex (default: dry run)")
    im = sub.add_parser("import", help="import results from MLflow, W&B or DVC into results.json")
    im.add_argument("tracker", choices=["mlflow", "wandb", "dvc"])
    im.add_argument("target", help="MLflow tracking URI (e.g. sqlite:///mlflow.db), W&B run folder or "
                                   "entity/project/run_id, or DVC repo folder")
    im.add_argument("--experiment", help="MLflow experiment name")
    im.add_argument("--run", help="MLflow run ID")
    im.add_argument("--api", action="store_true", help="W&B: target is entity/project/run_id (uses WANDB_API_KEY)")
    im.add_argument("--results", default="results.json")
    m = sub.add_parser("macros")
    m.add_argument("--results", default="results.json")
    a = ap.parse_args(argv)
    if a.cmd == "import":
        from .io import importers as imp
        if a.tracker == "mlflow":
            entries = imp.from_mlflow(a.target, a.experiment, a.run)
        elif a.tracker == "wandb":
            entries = imp.from_wandb_api(a.target) if a.api else imp.from_wandb_dir(a.target)
        else:
            entries = imp.from_dvc(a.target)
        n = imp.merge_into(a.results, entries)
        for k, v in sorted(entries.items()):
            print(f"{k} = {v['value']:g}  ({v['source']} run {v['run_id']}, commit {(v.get('commit') or '-')[:8]})")
        print(f"imported {n} value(s) into {a.results}")
        return 0
    if a.cmd == "scan":
        print(json.dumps(api.build(a.paper, a.results), indent=2))
    elif a.cmd == "freeze":
        print(api.freeze(a.paper, a.results))
    elif a.cmd == "check":
        r = api.check(a.paper, a.results)
        print(json.dumps(r, indent=2))
        return 1 if r["stale"] or r["inconsistent"] else 0
    elif a.cmd == "badge":
        print(api.badge(a.paper, a.results))
    elif a.cmd == "declare":
        edits = api.write_declared(a.paper, a.results, write=a.write)
        verb = "rewrote" if a.write else "would rewrite (pass --write)"
        for e in edits:
            print(f"{verb} {e['file']}:{e['line']} {e['text']} -> \\ptval{{{e['key']}}}")
    else:
        print(api.macros(a.results), end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
