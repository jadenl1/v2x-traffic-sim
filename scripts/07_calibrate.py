#!/usr/bin/env python3
"""Stage B — MAPE/RMSE calibration & validation against real AADT counts.

Two parts:

  1. VALIDATION (authoritative): compare the fully-loaded 24h baseline's realised
     per-edge flow against the real DDOT-count targets, per hour and overall
     (MAPE, RMSE, GEH). This is the honest "how well does the sim reproduce
     reality" number — it needs a loaded network, which only the 24h run gives.

  2. AUTOMATED TUNING: sweep a global demand-scale parameter on a *properly
     warmed* peak window (2h warm-up so mid-network edges are loaded) and pick
     the scale minimising flow MAPE.

Measuring on a cold-started short window is invalid (edges never reach their
real flow), so both parts guarantee the network is loaded before measuring.
"""
from __future__ import annotations

import json
import math
import subprocess
import xml.etree.ElementTree as ET

import common as C

BASE_EDGEDATA = C.OUTPUT_DIR / "edgedata.xml"
DEMAND_LOG = C.OUTPUT_DIR / "stage4_v3.log"


def demand_level_geh() -> dict:
    """Parse the routeSampler demand-calibration quality (GEH<5 %) from its log.

    This is the primary calibration result: the automated route-flow optimiser
    fits generated demand to the real AADT counts. GEH<5 is the traffic-
    engineering acceptance metric (target: >=85% of links)."""
    import re
    if not DEMAND_LOG.exists():
        return {"available": False}
    txt = DEMAND_LOG.read_text()
    m = re.search(r"avg interval GEH%:.*?mean ([0-9.]+)", txt)
    geh = float(m.group(1)) if m else None
    counts = [float(x) for x in re.findall(r"GEH<5 for ([0-9.]+)%", txt)]
    return {"available": geh is not None,
            "geh_lt5_pct_mean": round(geh, 1) if geh else None,
            "geh_lt5_pct_min": round(min(counts), 1) if counts else None,
            "geh_lt5_pct_max": round(max(counts), 1) if counts else None,
            "note": "routeSampler fits per-hour edge flows to real DDOT AADT counts; "
                    "GEH<5 is the FHWA link-flow acceptance metric."}


def load_targets_by_hour() -> dict:
    """{hour: {edge: entered_target}} from the calibrated counts file."""
    per_hour: dict[int, dict] = {}
    for _, el in ET.iterparse(C.EDGE_COUNTS_FILE, events=("end",)):
        if el.tag == "interval":
            h = int(float(el.get("begin")) // 3600)
            per_hour[h] = {e.get("id"): float(e.get("entered")) for e in el.findall("edge")}
            el.clear()
    return per_hour


def flow_by_hour(edgedata_path) -> dict:
    """{hour: {edge: entered}} from an hourly-binned edgeData output."""
    per_hour: dict[int, dict] = {}
    tree = ET.parse(edgedata_path)
    for interval in tree.getroot().findall("interval"):
        h = int(float(interval.get("begin")) // 3600)
        d = per_hour.setdefault(h, {})
        for edge in interval.findall("edge"):
            d[edge.get("id")] = d.get(edge.get("id"), 0.0) + float(edge.get("entered", 0) or 0)
    return per_hour


def error_metrics(sim: dict, target: dict) -> dict:
    keys = [k for k, v in target.items() if v > 0]
    if not keys:
        return {"n_edges": 0, "mape": None, "rmse": None, "geh_lt5_pct": None}
    ape, se, geh_ok = [], [], 0
    for k in keys:
        t = target[k]
        s = sim.get(k, 0.0)
        ape.append(abs(s - t) / t)
        se.append((s - t) ** 2)
        geh = math.sqrt(2 * (s - t) ** 2 / (s + t)) if (s + t) > 0 else 0.0
        if geh < 5:
            geh_ok += 1
    return {"n_edges": len(keys),
            "mape": round(sum(ape) / len(ape), 4),
            "rmse": round(math.sqrt(sum(se) / len(se)), 2),
            "geh_lt5_pct": round(100 * geh_ok / len(keys), 1)}


def validate_24h(targets_by_hour: dict) -> dict:
    if not BASE_EDGEDATA.exists():
        return {"available": False,
                "note": "run the 24h baseline (stage 5) first to populate edgedata.xml"}
    sim_by_hour = flow_by_hour(BASE_EDGEDATA)
    # Overall: pool all hours together.
    all_sim, all_tgt = {}, {}
    per_hour = {}
    for h, tgt in targets_by_hour.items():
        sim = sim_by_hour.get(h, {})
        per_hour[h] = error_metrics(sim, tgt)
        for k, v in tgt.items():
            all_tgt[f"{h}:{k}"] = v
            all_sim[f"{h}:{k}"] = sim.get(k, 0.0)
    overall = error_metrics(all_sim, all_tgt)
    return {"available": True, "overall": overall,
            "by_hour": {str(h): per_hour[h] for h in sorted(per_hour)}}


def run_scaled(scale: float, warm: int, begin: int, end: int):
    d = C.ROOT / "output" / "calibration" / f"scale{int(scale*100):03d}"
    d.mkdir(parents=True, exist_ok=True)
    add = d / "additional.xml"
    with open(add, "w") as fh:
        fh.write(f'<additional>\n  <edgeData id="ed" file="{d/"edgedata.xml"}" '
                 f'begin="{begin}" end="{end}" excludeEmpty="true"/>\n</additional>\n')
    subprocess.run([
        C.sumo_binary("sumo"), "-n", str(C.NET_FILE), "-r", str(C.DEMAND_FILE),
        "--additional-files", str(add), "--scale", str(scale),
        # Mesoscopic + rerouting for a fast, stable calibration sweep.
        "--mesosim", "true", "--meso-junction-control", "true",
        "--device.rerouting.probability", "1.0", "--device.rerouting.period", "300",
        "--begin", str(warm), "--end", str(end), "--step-length", "1",
        "--time-to-teleport", "300", "--no-warnings", "true", "--no-step-log", "true",
        "--seed", str(C.load_config()["sim"]["seed"]),
    ], check=True)
    return d / "edgedata.xml"


def auto_tune(targets_by_hour: dict, cal: dict) -> dict:
    b, e = cal["window_begin"], cal["window_end"]
    warm = max(0, b - 7200)  # 2h warm-up so mid-network edges are loaded
    hours = [h for h in range(b // 3600, e // 3600 + 1) if h in targets_by_hour]
    tgt = {}
    for h in hours:
        for k, v in targets_by_hour[h].items():
            tgt[k] = tgt.get(k, 0.0) + v
    results = []
    for scale in cal["scale_grid"]:
        C.log("calib", f"[tune] scale={scale} (warm {warm}->{e}) ...")
        edp = run_scaled(scale, warm, b, e)
        sim_hours = flow_by_hour(edp)
        sim = {}
        for h in hours:
            for k, v in sim_hours.get(h, {}).items():
                sim[k] = sim.get(k, 0.0) + v
        err = error_metrics(sim, tgt)
        err["scale"] = scale
        results.append(err)
        C.log("calib", f"  scale={scale}: MAPE={err['mape']*100:.1f}% "
                       f"RMSE={err['rmse']} GEH<5={err['geh_lt5_pct']}%")
    best = min(results, key=lambda r: (r["mape"] is None, r["mape"] or 1e9))
    return {"window": [b, e], "warmup_begin": warm, "results": results, "best": best}


def main() -> None:
    cfg = C.load_config()
    cal = cfg["calibration"]
    targets = load_targets_by_hour()

    C.log("calib", "Validating 24h baseline realised flow vs real AADT counts ...")
    validation = validate_24h(targets)
    if validation.get("available"):
        ov = validation["overall"]
        C.log("calib", f"  24h validation: MAPE={ov['mape']*100:.1f}% RMSE={ov['rmse']} "
                       f"GEH<5={ov['geh_lt5_pct']}% over {ov['n_edges']} edge-hours")

    C.log("calib", "Automated demand-scale tuning (warmed window) ...")
    tuning = auto_tune(targets, cal)

    demand_geh = demand_level_geh()
    if demand_geh.get("available"):
        C.log("calib", f"  demand-level calibration (routeSampler): "
                       f"GEH<5 mean {demand_geh['geh_lt5_pct_mean']}% "
                       f"(min {demand_geh['geh_lt5_pct_min']}, max {demand_geh['geh_lt5_pct_max']})")

    out = {
        "target_mape": cal["target_mape"],
        # Primary: how well the calibrated demand reproduces real counts.
        "demand_calibration": demand_geh,
        # Secondary: realised-flow validation + demand-scale sensitivity. NB the
        # isolated subnetwork saturates below full AADT throughput, so realised
        # flow undershoots the raw daily counts — a documented limitation.
        "validation_24h": validation,
        "auto_tuning": tuning,
        "operating_scale": C.load_config()["sim"]["demand_scale"],
        "best_scale": tuning["best"]["scale"],
        "best_mape": tuning["best"]["mape"],
        "goal_met": (tuning["best"]["mape"] is not None
                     and tuning["best"]["mape"] <= cal["target_mape"]),
    }
    outd = C.ROOT / "output" / "calibration"
    outd.mkdir(parents=True, exist_ok=True)
    with open(outd / "calibration.json", "w") as fh:
        json.dump(out, fh, indent=2)
    C.log("calib", f"BEST scale={out['best_scale']} MAPE={(out['best_mape'] or 0)*100:.1f}% "
                   f"goal {'MET' if out['goal_met'] else 'NOT met'} -> {outd/'calibration.json'}")


if __name__ == "__main__":
    main()
