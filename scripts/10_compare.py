#!/usr/bin/env python3
"""Stage E — Compare baseline vs V2X and assemble the results dashboard.

Pulls the peak-window baseline and V2X runs (Stage C), the 24h control metrics
(Stage A/6), the calibration report (Stage B) and the ML report (Stage D) into a
single comparison.json + a self-contained HTML dashboard.
"""
from __future__ import annotations

import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import common as C

MPS_TO_MPH = 2.23694


def _load_parsers():
    spec = importlib.util.spec_from_file_location(
        "rep", str(C.ROOT / "scripts" / "06_report_metrics.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def window_stats(run_dir: Path) -> dict:
    """Aggregate trip stats for one TraCI run from its statistics.xml."""
    stats_path = run_dir / "statistics.xml"
    out = {}
    if not stats_path.exists():
        return out
    root = ET.parse(stats_path).getroot()
    ts = root.find("vehicleTripStatistics")
    veh = root.find("vehicles")
    tp = root.find("teleports")
    if ts is not None:
        f = {k: float(v) for k, v in ts.attrib.items()}
        out = {
            "trips": int(f.get("count", 0)),
            "travel_time_s": round(f.get("duration", 0), 1),
            "delay_time_loss_s": round(f.get("timeLoss", 0), 1),
            "waiting_time_s": round(f.get("waitingTime", 0), 1),
            "speed_mph": round(f.get("speed", 0) * MPS_TO_MPH, 2),
            "route_length_m": round(f.get("routeLength", 0), 1),
        }
    if veh is not None:
        out["inserted"] = int(veh.get("inserted", 0))
    if tp is not None:
        out["teleports"] = int(tp.get("total", 0))
    return out


def pct(base, new):
    return round(100 * (new - base) / base, 1) if base else None


def compare_v2x() -> dict:
    base = window_stats(C.ROOT / "output" / "v2x" / "baseline")
    if not base:
        return {}
    arms = {"baseline": base}
    for name in ("v2i", "v2x"):
        s = window_stats(C.ROOT / "output" / "v2x" / name)
        if s:
            arms[name] = s
    metrics = ("travel_time_s", "delay_time_loss_s", "waiting_time_s", "speed_mph", "teleports")
    deltas = {}
    for arm in ("v2i", "v2x"):
        if arm not in arms:
            continue
        deltas[arm] = {k: {"baseline": base.get(k), arm: arms[arm].get(k),
                           "pct_change": pct(base.get(k), arms[arm].get(k))}
                       for k in metrics if k in base and k in arms[arm]}
    return {"arms": arms, "deltas": deltas}


def load_sweep() -> list:
    rows = []
    sd = C.ROOT / "output" / "v2x"
    for run in sorted(sd.glob("sweep_pen*")):
        pen = int(run.name.replace("sweep_pen", "")) / 100.0
        s = window_stats(run)
        if s:
            rows.append({"penetration": pen, **s})
    return rows


def render_dashboard(data: dict) -> Path:
    """Minimal self-contained HTML dashboard (theme-aware)."""
    deltas = data.get("v2x_comparison", {}).get("deltas", {})
    cal = data.get("calibration", {})
    ml = data.get("ml", {})
    base24 = data.get("baseline_24h", {})

    def card(title, val, sub=""):
        return (f'<div class="card"><div class="t">{title}</div>'
                f'<div class="v">{val}</div><div class="s">{sub}</div></div>')

    def dpct(arm, key):
        return deltas.get(arm, {}).get(key, {}).get("pct_change", "–")
    def dval(arm, key, which):
        return deltas.get(arm, {}).get(key, {}).get(which, "–")

    demand_geh = cal.get("demand_calibration", {}).get("geh_lt5_pct_mean", "–")
    cards = "".join([
        card("V2I signal Δ travel-time", f'{dpct("v2i","travel_time_s")}%',
             f'{dval("v2i","travel_time_s","baseline")}s → {dval("v2i","travel_time_s","v2i")}s'),
        card("Full V2X Δ travel-time", f'{dpct("v2x","travel_time_s")}%',
             f'{dval("v2x","travel_time_s","baseline")}s → {dval("v2x","travel_time_s","v2x")}s'),
        card("V2I Δ delay", f'{dpct("v2i","delay_time_loss_s")}%',
             f'time-loss per trip'),
        card("V2I Δ mean speed", f'+{dpct("v2i","speed_mph")}%'.replace("+-", "-"),
             f'{dval("v2i","speed_mph","baseline")} → {dval("v2i","speed_mph","v2i")} mph'),
        card("Demand calibration", f'{demand_geh}%',
             f'edges GEH&lt;5 vs DDOT counts'),
        card("ML forecast (best)", f'{ml.get("improvement_vs_naive_pct","–")}% better',
             f'{ml.get("best_model","–")} vs naive'),
        card("Baseline 24h speed", f'{base24.get("trip_means",{}).get("speed_mph","–")} mph',
             f'{base24.get("totals",{}).get("completed_trips","–")} trips/day'),
        card("Peak baseline speed", f'{deltas.get("v2i",{}).get("speed_mph",{}).get("baseline","–")} mph',
             f'AM peak, pre-V2X'),
    ])
    html = f"""<title>V2X Traffic Sim — DC Results</title>
<style>
:root{{--bg:#fff;--fg:#111;--muted:#666;--card:#f5f6f8;--accent:#3b6ea5;--good:#1a7f4b}}
@media(prefers-color-scheme:dark){{:root{{--bg:#0f1115;--fg:#e8e8e8;--muted:#9aa0a6;--card:#1a1d23;--accent:#5b9bd5;--good:#3ecf8e}}}}
:root[data-theme=dark]{{--bg:#0f1115;--fg:#e8e8e8;--muted:#9aa0a6;--card:#1a1d23;--accent:#5b9bd5;--good:#3ecf8e}}
:root[data-theme=light]{{--bg:#fff;--fg:#111;--muted:#666;--card:#f5f6f8;--accent:#3b6ea5;--good:#1a7f4b}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif;margin:0;padding:2rem;max-width:1000px;margin:auto}}
h1{{font-size:1.6rem;margin:.2rem 0}} .sub{{color:var(--muted);margin-bottom:1.5rem}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}}
.card{{background:var(--card);border-radius:12px;padding:1.1rem}}
.card .t{{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.04em}}
.card .v{{font-size:1.9rem;font-weight:650;margin:.3rem 0;color:var(--accent)}}
.card .s{{color:var(--muted);font-size:.85rem}}
h2{{margin-top:2rem;font-size:1.15rem}} table{{border-collapse:collapse;width:100%;font-size:.9rem}}
td,th{{text-align:left;padding:.4rem .6rem;border-bottom:1px solid var(--card)}}
</style>
<h1>V2X Traffic Simulation — Washington, DC</h1>
<div class="sub">Downtown core · demand calibrated to DDOT AADT counts · baseline vs V2X (AM peak)</div>
<div class="grid">{cards}</div>
<p style="color:var(--muted);margin-top:2rem;font-size:.85rem">
Generated from real DDOT open data. All figures are measured simulation results.</p>
"""
    d = C.ROOT / "output"
    (d / "dashboard.html").write_text(html)
    return d / "dashboard.html"


def main() -> None:
    data = {}
    # 24h baseline metrics
    m24 = C.ROOT / "output" / "baseline" / "metrics.json"
    if m24.exists():
        data["baseline_24h"] = json.loads(m24.read_text())
    # V2X comparison
    data["v2x_comparison"] = compare_v2x()
    sweep = load_sweep()
    if sweep:
        data["v2x_sweep"] = sweep
    # calibration + ML
    calp = C.ROOT / "output" / "calibration" / "calibration.json"
    if calp.exists():
        data["calibration"] = json.loads(calp.read_text())
    mlp = C.ROOT / "output" / "ml" / "forecast.json"
    if mlp.exists():
        data["ml"] = json.loads(mlp.read_text())

    outd = C.ROOT / "output" / "compare"
    outd.mkdir(parents=True, exist_ok=True)
    (outd / "comparison.json").write_text(json.dumps(data, indent=2))
    dash = render_dashboard(data)
    C.log("compare", f"comparison.json + dashboard -> {outd}, {dash}")

    d = data.get("v2x_comparison", {}).get("deltas", {})
    for arm in ("v2i", "v2x"):
        tt = d.get(arm, {}).get("travel_time_s")
        if tt:
            C.log("compare", f"{arm} travel-time change: {tt['pct_change']}% "
                             f"({tt['baseline']}s -> {tt.get(arm)}s)")


if __name__ == "__main__":
    main()
