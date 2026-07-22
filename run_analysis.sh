#!/usr/bin/env bash
# Run the analysis phases (B–E) after the baseline pipeline (run_all.sh) exists.
#   B calibration · C V2X (baseline+v2x windows) · D ML forecasting · E compare
# Usage: bash run_analysis.sh
set -euo pipefail
cd "$(dirname "$0")"
PY=.venv/bin/python

echo "==> B: MAPE/RMSE calibration"
$PY scripts/07_calibrate.py

echo "==> C: V2X peak-window runs (baseline + v2x)"
$PY scripts/08_run_v2x.py baseline
$PY scripts/08_run_v2x.py v2x

echo "==> D: ML demand forecasting + adaptive routing"
$PY scripts/09_ml_forecast.py

echo "==> E: baseline-vs-V2X comparison + dashboard"
$PY scripts/10_compare.py

echo "Done. See output/compare/comparison.json and output/dashboard.html"
