#!/usr/bin/env bash
# One command: tests + benchmarks (regenerates every paper table/figure).
set -euo pipefail
cd "$(dirname "$0")"
python -m pytest -q
for b in benchmarks/*.py; do [ -e "$b" ] && PYTHONPATH=src python "$b"; done
