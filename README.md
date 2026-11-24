# PaperTrail

**Where did the 87.3% in Table 4 come from?** PaperTrail links every number in your LaTeX paper to the experiment
run that produced it — from **MLflow**, **Weights & Biases**, **DVC** or plain Python — and flags numbers that went
**stale** after a rerun, before reviewers find the mismatch.

[![CI](https://github.com/Anandharajan/papertrail/actions/workflows/ci.yml/badge.svg)](https://github.com/Anandharajan/papertrail/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE) ![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue) [![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/Anandharajan/papertrail/blob/main/notebooks/quickstart.ipynb) [![Open in GitHub Codespaces](https://img.shields.io/badge/Open%20in-Codespaces-black?logo=github)](https://codespaces.new/Anandharajan/papertrail) [![GitHub stars](https://img.shields.io/github/stars/Anandharajan/papertrail?style=social)](https://github.com/Anandharajan/papertrail/stargazers)

> ⭐ **If PaperTrail saves you one embarrassing table mismatch, please [star the repo](https://github.com/Anandharajan/papertrail).**

## Try it in 60 seconds

- **No install:** [open the Colab notebook](https://colab.research.google.com/github/Anandharajan/papertrail/blob/main/notebooks/quickstart.ipynb) and press *Run all*.
- **In the browser with VS Code:** [open in GitHub Codespaces](https://codespaces.new/Anandharajan/papertrail).
- **On your machine:**

```bash
pip install "papertrail[mlflow] @ git+https://github.com/Anandharajan/papertrail"
papertrail import mlflow sqlite:///mlflow.db --experiment my-exp     # or: import wandb <run dir> / import dvc .
papertrail scan paper/        # which number came from which run?
papertrail freeze paper/      # snapshot the links (papertrail.lock.json)
papertrail check paper/       # after reruns: STALE / orphan / inconsistent numbers (exit 1 if any)
```

Real output after rerunning an experiment (from the quickstart notebook):

```json
"stale": [{"key": "acc_test", "status": "STALE", "shown": 87.31, "current": 88.02,
            "run_then": "3fda443f…", "run_now": "1371f4b9…"}],
"orphans": [{"file": "main.tex", "line": 2, "text": "42.17", "reason": "no source"}]
```

## Two ways to link numbers

**Declared (exact):** record results in code and write `\ptval{acc_test}` in LaTeX (`latex/papertrail.sty`).

```python
import papertrail
papertrail.record("acc_test", 0.8731, config={"lr": 1e-3})   # stores value, run ID, git commit, config hash
```

**Inferred (legacy papers):** `papertrail scan` matches raw numbers to run outputs under rounding, ×100 and
scientific-notation transforms, using context words and table headers, with a confidence score.
`papertrail declare --write` then rewrites confident matches to `\ptval` (dry run by default — your `.tex` is never
changed without `--write`).

## Experiment trackers

| Tracker | How | Extra install |
|---|---|---|
| MLflow | through MLflow's own client: SQLite `mlflow.db` (MLflow 3 default), tracking server or legacy `./mlruns` | `papertrail[mlflow]` |
| Weights & Biases | run folder (`files/wandb-summary.json`) or `--api entity/project/run_id` | `papertrail[wandb]` for the API |
| DVC | metrics files declared in `dvc.yaml` (JSON/YAML) | none |

Each imported value keeps its run ID, git commit and config hash. (W&B *offline* runs need `wandb sync` first: until
then W&B keeps only a binary log.)

## Use it from your AI assistant (MCP)

papertrail ships a local [Model Context Protocol](https://modelcontextprotocol.io) server (stdio only, nothing leaves
your machine). Install with `pip install "papertrail[mcp] @ git+https://github.com/Anandharajan/papertrail"`, then add this to
your client's MCP config (Claude Desktop, Cursor, VS Code and others use the same shape):

```json
{
  "mcpServers": {
    "papertrail": { "command": "papertrail-mcp" }
  }
}
```

Every tool call is written to a local audit log, and you can limit file access to chosen folders with the
`PAPERTRAIL_ROOTS` environment variable.

Tools: `where_from` ("where did 87.31 come from?"), `stale_numbers`, `rebuild_table`.

## Status

Tested on synthetic papers and real MLflow (SQLite) runs; linking precision/recall ≥ 0.9 on the synthetic set.
Evaluation on published papers with public code is next — see [benchmarks/RESULTS.md](benchmarks/RESULTS.md).

## Contributing

Bug reports, ideas and pull requests are welcome: [open an issue](https://github.com/Anandharajan/papertrail/issues).
Run `python -m pytest -q` before sending a pull request.

## Citation

If you use papertrail in research, please cite it (see [CITATION.cff](CITATION.cff), or GitHub's *Cite this repository* button).

## Licence

MIT © 2026 Anandharajan TRV, Department of ECE, St. Joseph College of Engineering, Chennai.

---

**If papertrail saved you time, please ⭐ [star the repository](https://github.com/Anandharajan/papertrail/stargazers)** — it is
the simplest way to help other researchers find it.
