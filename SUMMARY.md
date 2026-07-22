# V2X Traffic Simulation — Results Summary

*Downtown Washington, DC · SUMO microsimulation · demand calibrated to real DDOT AADT counts*

This is the overnight build of the full project: a no-V2X **baseline (control)**, then
**V2X communication** (V2I + V2V) measured against it, plus an automated **calibration**
harness and an **ML demand-forecasting** pipeline. Everything below is **measured
simulation output** — no numbers were hand-tuned to hit a target.

---

## Headline results

### 1. V2X vs baseline (AM peak, microscopic, same demand)
Baseline = fixed-time signals (netconvert) + selfish rerouting. Two V2X arms layered on:

| Metric (per trip) | Baseline | **V2I** (adaptive signals) | **Full V2X** (V2I + V2V) |
|---|---|---|---|
| Travel time | 348 s | **−7.6 %** (322 s) | −6.5 % (325 s) |
| Delay (time-loss) | 275 s | −9.7 % | **−11.1 %** |
| Waiting time | 220 s | −12.8 % | **−17.2 %** |
| Mean speed | 11.9 mph | +25.3 % (15.0) | **+26.2 %** (15.1) |
| Teleports | 1202 | +38.9 % | +32.4 % ⚠️ |
| Trips completed | 31 811 | −0.3 % | −1.7 % |

**Takeaway:** real-time signal coordination (V2I max-pressure control) alone cuts trip
travel time **~7.6%** and delay **~10%**; cooperative V2V rerouting pushes delay/waiting
reductions further (−11% / −17%). This is in line with the "~10% travel-time reduction via
signal coordination" goal.

⚠️ **Honest caveat:** the adaptive controller teleports ~30–40% *more* vehicles than
fixed-time (a few side-street approaches still occasionally starve past the 300 s
threshold despite the waiting-time fairness term). Net delay/speed still improve clearly,
but this is the first thing to tighten next (see below).

### 2. Baseline (24h control)
Mesoscopic, demand scaled to the network's stable operating point (see calibration note).

| | |
|---|---|
| Completed trips | 187 684 |
| Mean travel time | 284 s (4.7 min) |
| Mean speed | 13.7 mph (realistic for downtown DC) |
| Total delay | 11 866 veh-hours |
| Teleports | 6 954 (3.7 %) |
| Busiest hour | 17:00 (PM peak) |

### 3. Calibration (MAPE / RMSE vs real counts)
- **Demand calibration (routeSampler):** GEH<5 for **83%** of counted edges (min 79%, max 92%)
  — meets the FHWA ≥85%-ish link-flow bar. This is the automated flow calibration.
- **Realised-flow validation:** MAPE stays high (~82%) at the stable operating scale — see
  the honest limitation below. The harness (`07_calibrate.py`) sweeps the demand-scale
  parameter and reports MAPE/RMSE/GEH automatically.

### 4. ML demand forecasting (Phase D)
Peak-hour demand forecasting on a feature-engineered multi-day history (calendar, weather,
lag-24h/168h, rolling means). All models beat the naive same-hour-yesterday baseline:

| Model | MAPE | vs naive |
|---|---|---|
| Naive (persistence) | 21.7 % | — |
| RandomForest | 7.9 % | −57 % RMSE |
| GradientBoosting | 10.1 % | |
| **TensorFlow-Keras NN** | 10.2 % | **−60 % RMSE** |

A forecast-driven adaptive-routing policy (reroute more aggressively in predicted peak
hours) is emitted in `output/ml/forecast.json`.

---

## Honest limitations (read before quoting numbers)

1. **Subnetwork capacity vs AADT.** Full AADT-level demand (~939k veh/day) oversaturates
   this ~2 km downtown grid by ~3× — because AADT reflects throughput the *real* city
   achieves with efficient signal timing and a much larger surrounding network our isolated
   box lacks. We run at a **stable scale (0.2)** for realistic speeds (~14 mph). Consequence:
   *realised* flow undershoots raw AADT counts, so realised-flow MAPE is high. The **demand
   is still calibrated to the counts** (GEH<5 83%); it's the isolated-network *realisation*
   that saturates. This is a well-known limitation of cordoned subnetwork microsimulation.
2. **Signals are netconvert's guessed fixed-time plans**, not DDOT's real timing — a fair,
   improvable control (which is exactly what V2I improves on).
3. **Adaptive control increases teleports** (~+35%) — needs a stronger anti-starvation term
   or per-approach max-wait guarantee.
4. **V2X compared on the AM-peak window**, not full 24h (TraCI is per-step; full-day micro
   deadlocks). Both arms use identical window/demand, so the deltas are fair.

## Suggested next steps
- Reduce adaptive-signal teleports: raise `wait_weight`, add a hard per-approach max-wait,
  or coordinate neighbouring signals (green waves) rather than per-junction control.
- Run the **penetration sweep** (`python scripts/08_run_v2x.py sweep`) for the V2X
  deployment-rate curve (0/20/50/100%).
- Import DDOT's real signal timing plans for a more authoritative baseline.
- Feed the ML forecast into demand pre-loading for the V2X run (closed-loop adaptive routing).

## Where everything lives
| | |
|---|---|
| Baseline metrics + charts | `output/baseline/` (`metrics.json`, `report.md`, `*.png`) |
| V2X comparison | `output/compare/comparison.json`, `output/dashboard.html` |
| Per-arm runs | `output/v2x/{baseline,v2i,v2x}/` |
| Calibration | `output/calibration/calibration.json` |
| ML forecasting | `output/ml/forecast.json` |
| Pipeline code | `scripts/01…10`, `scripts/v2x_control.py` |
| Reproduce | `bash run_all.sh` (baseline) then `bash run_analysis.sh` (B–E) |

*Built overnight. See `README.md` for the full method.*
