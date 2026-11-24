"""Import results from experiment trackers into PaperTrail's results.json format.

Every imported value keeps its provenance: source tracker, run ID, git commit and a config
hash, so `papertrail check` can flag paper numbers that no longer match the latest runs.

  * MLflow  -- through MLflow's own client, so any backend works (SQLite `mlflow.db`, a
               tracking server, or a legacy `./mlruns` folder). Needs `pip install "papertrail[mlflow]"`.
  * W&B     -- a run folder's files/wandb-summary.json, config.yaml and wandb-metadata.json
               (written by online runs and by `wandb sync`), or a synced run via the public API
               (`papertrail[wandb]`, reads WANDB_API_KEY from the environment; never logged).
               Note: *offline* runs keep only a binary .wandb log until synced.
  * DVC     -- the metrics files declared in dvc.yaml (JSON or YAML); no DVC install needed.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from collections.abc import Iterable

import yaml

from ..recorder import config_hash

Entry = dict[str, Any]


def _flatten(d: dict[str, Any], prefix: str = "") -> Iterable[tuple[str, float]]:
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from _flatten(v, key + ".")
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            yield key, float(v)


def _git_head(path: Path) -> str | None:
    try:
        return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


# ------------------------------------------------------------------ MLflow
def from_mlflow(tracking_uri: str, experiment: str | None = None, run_id: str | None = None,
                prefix_with_run: bool | None = None, client: Any = None) -> dict[str, Entry]:
    """Latest value of every metric in the selected run(s). With several runs, keys are
    '<run_name>.<metric>' unless prefix_with_run=False."""
    if client is None:
        try:
            from mlflow.tracking import MlflowClient
        except ImportError as e:  # pragma: no cover
            raise SystemExit('MLflow import needs: pip install "papertrail[mlflow]"') from e
        client = MlflowClient(tracking_uri)
    if run_id:
        runs = [client.get_run(run_id)]
    else:
        exps = [client.get_experiment_by_name(experiment)] if experiment else client.search_experiments()
        ids = [e.experiment_id for e in exps if e is not None]
        runs = list(client.search_runs(ids)) if ids else []
    multi = len(runs) > 1 if prefix_with_run is None else prefix_with_run
    out: dict[str, Entry] = {}
    for r in runs:
        name = r.info.run_name or r.info.run_id[:8]
        meta = {"source": "mlflow", "run_id": r.info.run_id, "run_name": name,
                "commit": r.data.tags.get("mlflow.source.git.commit"),
                "config_hash": config_hash(dict(r.data.params)) if r.data.params else None,
                "tracking_uri": tracking_uri}
        for metric, value in r.data.metrics.items():
            out[f"{name}.{metric}" if multi else metric] = {"value": float(value), **meta}
    return out


# ------------------------------------------------------------------ Weights & Biases
def _wandb_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {k: (v.get("value") if isinstance(v, dict) and "value" in v else v)
            for k, v in raw.items() if not k.startswith("_")}


def from_wandb_dir(run_dir: str | Path) -> dict[str, Entry]:
    """A W&B run folder (e.g. wandb/run-20261124_101500-abc123), using its files/ subfolder."""
    rd = Path(run_dir)
    files = rd / "files" if (rd / "files").is_dir() else rd
    summary_p = files / "wandb-summary.json"
    if not summary_p.exists():
        if any(rd.glob("*.wandb")):
            raise ValueError(f"{rd} is an offline run with no summary yet: run `wandb sync {rd}` first, "
                             "or use from_wandb_api for a synced run")
        raise FileNotFoundError(summary_p)
    summary = json.loads(summary_p.read_text(encoding="utf-8"))
    meta_p = files / "wandb-metadata.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    run_id = rd.name.rsplit("-", 1)[-1] if "-" in rd.name else rd.name
    cfg = _wandb_config(files / "config.yaml")
    base = {"source": "wandb", "run_id": run_id, "commit": (meta.get("git") or {}).get("commit"),
            "config_hash": config_hash(cfg) if cfg else None}
    return {k: {"value": v, **base} for k, v in _flatten({k: v for k, v in summary.items() if not k.startswith("_")})}


def from_wandb_api(path: str, api: Any = None) -> dict[str, Entry]:
    """A synced run, given as 'entity/project/run_id'. Uses WANDB_API_KEY from the environment."""
    if api is None:  # pragma: no cover - network
        try:
            import wandb
        except ImportError as e:
            raise SystemExit('W&B API import needs: pip install "papertrail[wandb]"') from e
        api = wandb.Api()
    run = api.run(path)
    summary = {k: v for k, v in dict(run.summary).items() if not k.startswith("_")}
    cfg = {k: v for k, v in dict(run.config).items() if not k.startswith("_")}
    commit = (getattr(run, "commit", None) or (getattr(run, "metadata", None) or {}).get("git", {}).get("commit"))
    base = {"source": "wandb", "run_id": run.id, "commit": commit, "config_hash": config_hash(cfg) if cfg else None}
    return {k: {"value": v, **base} for k, v in _flatten(summary)}


# ------------------------------------------------------------------ DVC
def from_dvc(repo: str | Path) -> dict[str, Entry]:
    """Metrics files declared in dvc.yaml (top-level `metrics:` and per-stage `metrics:`)."""
    root = Path(repo)
    spec = yaml.safe_load((root / "dvc.yaml").read_text(encoding="utf-8")) or {}
    files: list[str] = []

    def add(items: Any) -> None:
        for it in items or []:
            files.append(next(iter(it)) if isinstance(it, dict) else str(it))
    add(spec.get("metrics"))
    for stage in (spec.get("stages") or {}).values():
        add((stage or {}).get("metrics"))
    commit = _git_head(root)
    out: dict[str, Entry] = {}
    for f in dict.fromkeys(files):
        p = root / f
        if not p.exists():
            continue
        data = json.loads(p.read_text(encoding="utf-8")) if p.suffix == ".json" else yaml.safe_load(p.read_text(encoding="utf-8"))
        stem = Path(f).stem
        for k, v in _flatten(data or {}):
            out[f"{stem}.{k}" if len(files) > 1 else k] = {"value": v, "source": "dvc", "run_id": f"dvc:{f}",
                                                              "commit": commit, "config_hash": None}
    return out


def merge_into(results_json: str | Path, entries: dict[str, Entry]) -> int:
    p = Path(results_json)
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    data.update(entries)
    p.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return len(entries)
