#!/usr/bin/env bash
# Run the full downtown-DC baseline pipeline, stage 1 -> 6.
# Usage: bash run_all.sh
set -euo pipefail

cd "$(dirname "$0")"
PY=.venv/bin/python

echo "==> Stage 1: build network"
$PY scripts/01_build_network.py
echo "==> Stage 2: fetch AADT counts"
$PY scripts/02_fetch_counts.py
echo "==> Stage 3: map counts -> 24h edge demand"
$PY scripts/03_map_counts.py
echo "==> Stage 4: build calibrated demand"
$PY scripts/04_build_demand.py
echo "==> Stage 5: run 24h baseline simulation"
$PY scripts/05_run_baseline.py
echo "==> Stage 6: baseline metrics + report"
$PY scripts/06_report_metrics.py

echo "Done. See output/baseline/report.md and output/baseline/metrics.json"
