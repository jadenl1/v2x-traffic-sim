#!/usr/bin/env python3
"""Stage C — Run a peak-window simulation under TraCI, with or without V2X.

Usage:
    python scripts/08_run_v2x.py baseline          # fixed signals, no reroute
    python scripts/08_run_v2x.py v2x               # adaptive signals + V2V reroute
    python scripts/08_run_v2x.py v2x --pen 0.5     # override penetration
    python scripts/08_run_v2x.py sweep             # run the penetration sweep

Both arms share the same network, demand and window, so results are directly
comparable. Outputs land in output/v2x/<label>/ and are parsed by Stage 6's
metric functions in Stage E (10_compare.py).
"""
from __future__ import annotations

import argparse

import traci

import common as C
from v2x_control import V2XManager

WARMUP_S = 3600  # 1h warm-up so the network is genuinely congested at the peak


def out_dir(label: str):
    d = C.ROOT / "output" / "v2x" / label
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_additional(d, agg=900):
    path = d / "additional.xml"
    with open(path, "w") as fh:
        fh.write('<additional>\n')
        fh.write(f'  <edgeData id="ed" file="{(d / "edgedata.xml")}" '
                 f'period="{agg}" excludeEmpty="true"/>\n')
        fh.write('</additional>\n')
    return path


def run(mode: str, penetration: float, label: str) -> None:
    cfg = C.load_config()
    v = cfg["v2x"]
    begin = max(0, v["peak_begin"] - WARMUP_S)
    end = v["peak_end"]
    d = out_dir(label)
    add = write_additional(d)

    cmd = [
        C.sumo_binary("sumo"),
        "-n", str(C.NET_FILE),
        "-r", str(C.DEMAND_FILE),
        "--additional-files", str(add),
        "--begin", str(begin), "--end", str(end), "--step-length", "1",
        "--scale", str(cfg["sim"].get("demand_scale", 1.0)),
        # Both arms share a selfish rerouting device (today's nav apps); the V2X
        # arm adds adaptive signals + cooperative V2V routing on top via TraCI.
        "--device.rerouting.probability", "1.0",
        "--device.rerouting.period", str(cfg["sim"].get("reroute_period_s", 300)),
        "--tripinfo-output", str(d / "tripinfo.xml"),
        "--summary-output", str(d / "summary.xml"),
        "--statistic-output", str(d / "statistics.xml"),
        "--duration-log.statistics", "true",
        "--time-to-teleport", "300",
        "--no-warnings", "true", "--no-step-log", "true",
        "--seed", str(cfg["sim"]["seed"]),
    ]
    C.log("v2x", f"[{label}] starting TraCI run: mode={mode} pen={penetration} "
                 f"window=[{begin},{end}]s")
    traci.start(cmd)
    # mode 'v2i' = adaptive signals only (no V2V rerouting); 'v2x' = both.
    enable_v2v = (mode == "v2x")
    mgr = V2XManager(v, penetration if mode != "baseline" else 0.0, enable_v2v=enable_v2v)

    dt = 1.0
    while traci.simulation.getMinExpectedNumber() > 0 and traci.simulation.getTime() < end:
        traci.simulationStep()
        mgr.step(traci.simulation.getTime(), dt)
    traci.close()
    C.log("v2x", f"[{label}] done -> {d}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["baseline", "v2i", "v2x", "sweep"])
    ap.add_argument("--pen", type=float, default=None)
    args = ap.parse_args()
    cfg = C.load_config()
    v = cfg["v2x"]

    if args.mode == "sweep":
        for pen in v["penetration_sweep"]:
            mode = "baseline" if pen == 0 else "v2x"
            run(mode, pen, label=f"sweep_pen{int(pen*100):03d}")
    else:
        pen = args.pen if args.pen is not None else (0.0 if args.mode == "baseline"
                                                     else v["penetration"])
        run(args.mode, pen, label=args.mode)


if __name__ == "__main__":
    main()
