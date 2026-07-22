#!/usr/bin/env python3
"""Stage 6 — Compute baseline KPIs and render the control report.

Parses tripinfo / summary / statistics / edgedata (streaming, memory-safe) into
output/baseline/metrics.json — the frozen control that future V2X runs diff
against — plus a human-readable report.md and two diagnostic charts.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C

MPS_TO_MPH = 2.23694


def parse_statistics(path) -> dict:
    out = {}
    if not path.exists():
        return out
    root = ET.parse(path).getroot()
    veh = root.find("vehicles")
    if veh is not None:
        out["vehicles"] = {k: int(v) for k, v in veh.attrib.items()}
    ts = root.find("vehicleTripStatistics")
    if ts is not None:
        f = {k: float(v) for k, v in ts.attrib.items()}
        out["trip_means"] = {
            "count": int(f.get("count", 0)),
            "travel_time_s": f.get("duration"),
            "delay_time_loss_s": f.get("timeLoss"),
            "waiting_time_s": f.get("waitingTime"),
            "route_length_m": f.get("routeLength"),
            "depart_delay_s": f.get("departDelay"),
            "speed_mps": f.get("speed"),
            "speed_mph": round(f.get("speed", 0) * MPS_TO_MPH, 2),
        }
    tp = root.find("teleports")
    if tp is not None:
        out["teleports"] = {k: int(v) for k, v in tp.attrib.items()}
    return out


def parse_tripinfo(path):
    """Stream tripinfo: completed count + total delay / distance."""
    completed = 0
    total_timeloss = 0.0
    total_length = 0.0
    if not path.exists():
        return {}
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag == "tripinfo":
            completed += 1
            total_timeloss += float(el.get("timeLoss", 0))
            total_length += float(el.get("routeLength", 0))
            el.clear()
    return {
        "completed_trips": completed,
        "vehicle_hours_delay": round(total_timeloss / 3600.0, 1),
        "vehicle_km_travelled": round(total_length / 1000.0, 1),
    }


def parse_summary_hourly(path):
    """Bin per-step summary into hourly means (running vehicles, speed)."""
    buckets = {h: {"running": [], "speed": [], "arrived_end": 0} for h in range(24)}
    if not path.exists():
        return []
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag == "step":
            t = float(el.get("time", 0))
            h = min(int(t // 3600), 23)
            buckets[h]["running"].append(int(el.get("running", 0)))
            ms = el.get("meanSpeed")
            if ms is not None and float(ms) >= 0:
                buckets[h]["speed"].append(float(ms))
            el.clear()
    hourly = []
    for h in range(24):
        run = buckets[h]["running"]
        spd = buckets[h]["speed"]
        hourly.append({
            "hour": h,
            "running_mean": round(sum(run) / len(run), 1) if run else 0,
            "running_max": max(run) if run else 0,
            "speed_mean_mph": round((sum(spd) / len(spd)) * MPS_TO_MPH, 2) if spd else 0.0,
        })
    return hourly


def parse_worst_edges(path, top_n=15):
    """Aggregate edgeData across intervals; rank edges by total waiting time."""
    agg = {}
    if not path.exists():
        return []
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag == "edge":
            eid = el.get("id")
            wt = float(el.get("waitingTime", 0) or 0)
            spd = el.get("speed")
            a = agg.setdefault(eid, {"waiting": 0.0, "speeds": []})
            a["waiting"] += wt
            if spd is not None:
                a["speeds"].append(float(spd))
            el.clear()
    ranked = sorted(agg.items(), key=lambda kv: kv[1]["waiting"], reverse=True)[:top_n]
    return [{
        "edge": eid,
        "total_waiting_s": round(v["waiting"], 1),
        "mean_speed_mph": round((sum(v["speeds"]) / len(v["speeds"])) * MPS_TO_MPH, 2)
        if v["speeds"] else None,
    } for eid, v in ranked]


def make_charts(hourly):
    hours = [h["hour"] for h in hourly]
    running = [h["running_mean"] for h in hourly]
    speed = [h["speed_mean_mph"] for h in hourly]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(hours, running, color="#3b6ea5")
    ax.set_xlabel("Hour of day"); ax.set_ylabel("Mean vehicles in network")
    ax.set_title("Baseline: vehicles in network by hour (downtown DC)")
    ax.set_xticks(range(0, 24, 2)); fig.tight_layout()
    fig.savefig(C.OUTPUT_DIR / "hourly_vehicles.png", dpi=120); plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(hours, speed, "-o", color="#c1462f")
    ax.set_xlabel("Hour of day"); ax.set_ylabel("Mean speed (mph)")
    ax.set_title("Baseline: network mean speed by hour (downtown DC)")
    ax.set_xticks(range(0, 24, 2)); ax.set_ylim(bottom=0); fig.tight_layout()
    fig.savefig(C.OUTPUT_DIR / "hourly_speed.png", dpi=120); plt.close(fig)


def render_report(metrics):
    tm = metrics.get("trip_means", {})
    tot = metrics.get("totals", {})
    veh = metrics.get("vehicles", {})
    lines = [
        "# Downtown DC Baseline — Traffic Metrics (Control, no V2X)",
        "",
        f"Scenario: **{metrics['scenario']}** · window: **{metrics['window_h']}h** "
        f"· demand calibrated to DDOT AADT counts.",
        "",
        "## Headline KPIs",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Vehicles loaded | {veh.get('loaded', 'n/a'):,} |" if isinstance(veh.get('loaded'), int) else "| Vehicles loaded | n/a |",
        f"| Completed trips | {tot.get('completed_trips', 'n/a'):,} |" if isinstance(tot.get('completed_trips'), int) else "| Completed trips | n/a |",
        f"| Mean travel time | {tm.get('travel_time_s', 0):.0f} s |",
        f"| Mean delay (time loss) | {tm.get('delay_time_loss_s', 0):.0f} s |",
        f"| Mean waiting time | {tm.get('waiting_time_s', 0):.0f} s |",
        f"| Mean trip length | {tm.get('route_length_m', 0)/1000:.2f} km |",
        f"| Mean speed | {tm.get('speed_mph', 0):.1f} mph |",
        f"| Total delay | {tot.get('vehicle_hours_delay', 0):,.0f} veh-hours |",
        f"| Total distance | {tot.get('vehicle_km_travelled', 0):,.0f} veh-km |",
        "",
        "## Diurnal pattern",
        "",
        "![Vehicles by hour](hourly_vehicles.png)",
        "",
        "![Speed by hour](hourly_speed.png)",
        "",
        "## Worst edges by total waiting time",
        "",
        "| Edge | Total waiting (s) | Mean speed (mph) |",
        "|---|---|---|",
    ]
    for e in metrics.get("worst_edges", [])[:10]:
        lines.append(f"| `{e['edge']}` | {e['total_waiting_s']:,.0f} | {e['mean_speed_mph']} |")
    lines += [
        "",
        "---",
        "*This is the frozen control. V2X experiments are evaluated as deltas "
        "against `metrics.json`.*",
        "",
    ]
    (C.OUTPUT_DIR / "report.md").write_text("\n".join(lines))


def main() -> None:
    stats = parse_statistics(C.OUTPUT_DIR / "statistics.xml")
    trip = parse_tripinfo(C.OUTPUT_DIR / "tripinfo.xml")
    hourly = parse_summary_hourly(C.OUTPUT_DIR / "summary.xml")
    worst = parse_worst_edges(C.OUTPUT_DIR / "edgedata.xml")

    metrics = {
        "scenario": "downtown_dc_baseline",
        "window_h": 24,
        "vehicles": stats.get("vehicles", {}),
        "trip_means": stats.get("trip_means", {}),
        "teleports": stats.get("teleports", {}),
        "totals": trip,
        "hourly": hourly,
        "worst_edges": worst,
    }
    with open(C.OUTPUT_DIR / "metrics.json", "w") as fh:
        json.dump(metrics, fh, indent=2)
    make_charts(hourly)
    render_report(metrics)
    C.log("report", f"Baseline metrics -> {C.OUTPUT_DIR / 'metrics.json'}")
    tm = metrics["trip_means"]
    C.log("report", f"Mean travel {tm.get('travel_time_s',0):.0f}s, "
                    f"delay {tm.get('delay_time_loss_s',0):.0f}s, "
                    f"speed {tm.get('speed_mph',0):.1f} mph.")


if __name__ == "__main__":
    main()
