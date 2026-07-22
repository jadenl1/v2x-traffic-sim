# V2X Traffic Sim — Downtown DC Baseline

Milestone 1 of a V2X (vehicle-to-everything) traffic study: a **control**
simulation of downtown Washington, DC traffic under today's conditions (no V2X),
built in [SUMO](https://sumo.dlr.de). Future V2X experiments are measured as
deltas against the metrics this baseline produces.

## What it does

A staged, reproducible pipeline that builds a microsimulation of the downtown DC
core over a full 24-hour average weekday, with demand **calibrated to real DDOT
traffic counts** (Annual Average Daily Traffic from DC Open Data).

| Stage | Script | Output |
|---|---|---|
| 1 | `scripts/01_build_network.py` | OSM → `network/downtown_dc.net.xml` (car network, guessed fixed-time signals) |
| 2 | `scripts/02_fetch_counts.py` | DDOT AADT GeoJSON for the bbox |
| 3 | `scripts/03_map_counts.py` | AADT mapped to edges + 24h diurnal profile → `data/counts/edge_counts_24h.xml` |
| 4 | `scripts/04_build_demand.py` | routeSampler-calibrated demand → `sim/demand_baseline.rou.xml` |
| 5 | `scripts/05_run_baseline.py` | headless 24h SUMO run → tripinfo / summary / edgedata |
| 6 | `scripts/06_report_metrics.py` | `output/baseline/metrics.json` + `report.md` + charts |

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # includes eclipse-sumo (bundles the SUMO binaries)
```

## Run

```bash
bash run_all.sh                 # full pipeline
# or run a single stage, e.g.:
.venv/bin/python scripts/03_map_counts.py
```

Results land in `output/baseline/` — `metrics.json` is the frozen control;
`report.md` is the human-readable summary.

## Configuration

Everything tunable lives in `config/params.yaml` — bounding box, count year,
AADT→edge match distance, direction split, simulation window/step, truck
fraction, seed. The 24h shape is `config/diurnal_weekday.csv`.

## Data source

DDOT Traffic Volume (AADT), DC Open Data ArcGIS REST service:
`Transportation_TrafficVolume_WebMercator/MapServer/5`. AADT is total daily
volume (both directions) on HPMS-sampled road segments.

## Known limitations (baseline, by design)

- **Coverage:** AADT samples major roads (HPMS), so minor streets are demand-only,
  not directly count-calibrated (~60% of passenger edges are calibrated).
- **Direction split:** bidirectional AADT is split 50/50 by default (the dataset
  has no per-direction volumes).
- **Signals:** fixed-time timings are `netconvert`'s guess from OSM, not DDOT's
  actual timing plans — a fair, improvable control for V2X to beat.

## Analysis phases (B–E)

Built on top of the baseline. Run with `bash run_analysis.sh` (needs the
baseline network + demand from `run_all.sh`).

| Stage | Script | What it does |
|---|---|---|
| B · Calibration | `scripts/07_calibrate.py` | Sweeps a demand-scale parameter, measures **MAPE / RMSE / GEH** of realised flow vs real AADT counts, picks the lowest-error setting → `output/calibration/calibration.json` |
| C · V2X | `scripts/08_run_v2x.py` + `scripts/v2x_control.py` | Peak-window TraCI runs: **V2I** max-pressure adaptive signals + **V2V** congestion-sharing rerouting, penetration-rate knob. `baseline`/`v2x`/`sweep` modes → `output/v2x/*` |
| D · ML | `scripts/09_ml_forecast.py` | Peak-hour demand forecasting (RandomForest / GradientBoosting / **TensorFlow-Keras** NN) vs a naive baseline, + adaptive-routing policy → `output/ml/forecast.json` |
| E · Compare | `scripts/10_compare.py` | Baseline-vs-V2X deltas + a self-contained HTML **dashboard** → `output/compare/comparison.json`, `output/dashboard.html` |

### V2X model

- **V2I (adaptive signals):** each signal runs max-pressure control over its
  existing conflict-free phases — every few seconds it serves the green phase
  clearing the most queued demand on its approaches, honouring min-green +
  yellow. Replaces the fixed-time control the baseline uses.
- **V2V (rerouting):** equipped vehicles pool live edge travel-times (a shared
  real-time belief) and periodically re-route around congestion.
- **Penetration rate** gates both; `penetration = 0` reproduces the fixed-signal
  baseline exactly, so the same harness produces both arms of the comparison.

All V2X/baseline comparison runs use the same AM-peak window so results are
directly comparable. TraCI is per-step, so the full 24h is reserved for the
baseline; V2X is evaluated on the peak where congestion (and V2X benefit) is
greatest.
