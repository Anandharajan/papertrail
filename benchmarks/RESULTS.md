# PaperTrail: results and honest status

All numbers come from the automated tests (`python -m pytest -q`). Synthetic papers unless stated.

| Check | Data | Result |
|---|---|---|
| Injected stale values detected | 100 random values and shifts larger than the shown precision | all detected; no false STALE |
| Linking precision / recall (inferred links) | 20 synthetic papers × 8 metrics + distractor integers | ≥ 0.90 / ≥ 0.90 |
| MLflow import | a real MLflow run in a SQLite store (`mlflow.db`, the MLflow 3 default), created by MLflow in the test | latest metric value, run ID, git commit and params hash imported; `where_from` resolves the paper number to that run |
| W&B import | run folder in the documented `files/` layout; API path with a stand-in object | values, run ID, commit and config hash imported; offline runs give a clear "run `wandb sync`" error |
| DVC import | `dvc.yaml` with stage and top-level metrics (JSON + YAML) | all metrics imported with the repo's git commit |
| Quickstart notebook | executed end to end | STALE number caught after a rerun |

## Gaps and caveats

- Evaluation on 20 published papers with public code (the plan's acceptance test) and the MutRoute case study are not done.
- The W&B run-folder importer was checked against the documented file layout, not against files from a live online run
  (offline runs in this environment only produce the binary `.wandb` log).
- `latex/papertrail.sty` has not been compiled in CI yet.
