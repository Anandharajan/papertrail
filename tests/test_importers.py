"""Importers from MLflow, W&B and DVC. No network: MLflow uses a local SQLite store created by
MLflow itself (skipped if MLflow is not installed); the W&B API is a stand-in object."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from papertrail import api
from papertrail.cli import main
from papertrail.io import importers as imp


def test_mlflow_sqlite_real_client(tmp_path, monkeypatch):
    mlflow = pytest.importorskip("mlflow")
    pytest.importorskip("alembic")
    monkeypatch.setenv("MLFLOW_DISABLE_AGENT_HINT", "1")
    uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment("resnet")
    with mlflow.start_run(run_name="baseline") as r:
        mlflow.log_params({"lr": 0.001})
        for i, a in enumerate([0.71, 0.80, 0.8731]):
            mlflow.log_metric("acc_test", a, step=i)
        mlflow.set_tag("mlflow.source.git.commit", "abc1234")
    with mlflow.start_run(run_name="ablation"):
        mlflow.log_metric("acc_test", 0.8512)
    one = imp.from_mlflow(uri, run_id=r.info.run_id)
    assert one["acc_test"]["value"] == pytest.approx(0.8731)  # latest step, not the first
    assert one["acc_test"]["commit"] == "abc1234" and one["acc_test"]["config_hash"]
    both = imp.from_mlflow(uri, experiment="resnet")
    assert set(both) == {"baseline.acc_test", "ablation.acc_test"}
    res = tmp_path / "results.json"
    assert main(["import", "mlflow", uri, "--run", r.info.run_id, "--results", str(res)]) == 0
    (tmp_path / "p.tex").write_text("Our test accuracy is 87.31\\%.")
    link = api.where_from(str(tmp_path / "p.tex"), str(res), "87.31")[0]
    assert link["key"] == "acc_test" and link["run_id"] == r.info.run_id and link["commit"] == "abc1234"


def wandb_run(tmp_path, summary, offline=False):
    rd = tmp_path / "wandb" / "run-20261124_101500-abc123"
    files = rd / "files"
    files.mkdir(parents=True)
    if offline:
        (rd / "run-abc123.wandb").write_bytes(b"\x00")
        return rd
    (files / "wandb-summary.json").write_text(json.dumps(summary))
    (files / "config.yaml").write_text("_wandb:\n  value: {cli_version: 0.17}\nlr:\n  desc: null\n  value: 0.001\nbatch:\n  value: 64\n")
    (files / "wandb-metadata.json").write_text(json.dumps({"git": {"commit": "def5678", "remote": "x"}}))
    return rd


def test_wandb_run_folder(tmp_path):
    rd = wandb_run(tmp_path, {"acc_test": 0.8731, "eval": {"f1": 0.91}, "_step": 3, "_runtime": 9.5, "note": "x"})
    e = imp.from_wandb_dir(rd)
    assert set(e) == {"acc_test", "eval.f1"}  # internal _keys and non-numeric values dropped
    assert e["acc_test"]["run_id"] == "abc123" and e["acc_test"]["commit"] == "def5678" and e["acc_test"]["config_hash"]
    assert imp._wandb_config(rd / "files" / "config.yaml") == {"lr": 0.001, "batch": 64}


def test_wandb_offline_run_gives_clear_error(tmp_path):
    rd = wandb_run(tmp_path, {}, offline=True)
    with pytest.raises(ValueError, match="wandb sync"):
        imp.from_wandb_dir(rd)
    with pytest.raises(FileNotFoundError):
        imp.from_wandb_dir(tmp_path)


def test_wandb_api_stand_in():
    run = SimpleNamespace(id="r9", summary={"acc": 0.9, "_step": 1}, config={"lr": 1e-3, "_wandb": {}},
                          commit="c0ffee", metadata=None)
    e = imp.from_wandb_api("me/proj/r9", api=SimpleNamespace(run=lambda path: run))
    assert e == {"acc": {"value": 0.9, "source": "wandb", "run_id": "r9", "commit": "c0ffee",
                         "config_hash": e["acc"]["config_hash"]}}


def test_dvc_metrics(tmp_path):
    (tmp_path / "dvc.yaml").write_text(
        "stages:\n  train:\n    cmd: python train.py\n    metrics:\n      - metrics/eval.json:\n          cache: false\n"
        "metrics:\n  - metrics/speed.yaml\n")
    (tmp_path / "metrics").mkdir()
    (tmp_path / "metrics" / "eval.json").write_text(json.dumps({"acc": 0.8731, "per_class": {"cat": 0.9}}))
    (tmp_path / "metrics" / "speed.yaml").write_text("latency_ms: 12.5\n")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    e = imp.from_dvc(tmp_path)
    assert set(e) == {"eval.acc", "eval.per_class.cat", "speed.latency_ms"}
    assert e["eval.acc"]["source"] == "dvc" and e["eval.acc"]["run_id"] == "dvc:metrics/eval.json"
    res = tmp_path / "r.json"
    assert main(["import", "dvc", str(tmp_path), "--results", str(res)]) == 0
    assert json.loads(res.read_text())["speed.latency_ms"]["value"] == 12.5
