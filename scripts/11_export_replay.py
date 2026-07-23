#!/usr/bin/env python3
"""Stage F — Export a compact simulation replay for the React viewer.

Runs a short peak-window simulation with FCD (per-timestep vehicle position)
output for both the fixed-signal baseline and the V2X-controlled run, then packs
the road-network geometry plus per-frame vehicle positions into a single JSON the
`viz/` React app animates on a canvas.

Kept small on purpose: a ~2-minute window, 1 Hz frames, integer-rounded coords.
"""
from __future__ import annotations

import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import traci

import common as C
from v2x_control import V2XManager

WARMUP = 24900     # fill the network first
KEEP_FROM = 25200  # 07:00 — start keeping frames
KEEP_TO = 25320    # 120 s window
OUT = C.ROOT / "viz" / "public" / "sim.json"


def export_network(net) -> tuple[list, list]:
    """Edge polylines as flat [x0,y0,x1,y1,...] int arrays, plus bbox."""
    (minx, miny), (maxx, maxy) = net.getBBoxXY()
    edges = []
    for e in net.getEdges():
        if not e.allows("passenger"):
            continue
        flat = []
        for x, y in e.getShape():
            flat.append(round(x - minx))
            flat.append(round(y - miny))
        edges.append(flat)
    return edges, [round(maxx - minx), round(maxy - miny)]


def run_baseline_fcd(fcd: Path) -> None:
    cfg = C.load_config()
    subprocess.run([
        C.sumo_binary("sumo"), "-n", str(C.NET_FILE), "-r", str(C.DEMAND_FILE),
        "--scale", str(cfg["sim"]["demand_scale"]),
        "--device.rerouting.probability", "1.0", "--device.rerouting.period", "300",
        "--begin", str(WARMUP), "--end", str(KEEP_TO), "--step-length", "1",
        "--fcd-output", str(fcd), "--fcd-output.attributes", "x,y,speed",
        "--time-to-teleport", "300", "--no-warnings", "true", "--no-step-log", "true",
        "--seed", str(cfg["sim"]["seed"]),
    ], check=True)


def run_v2x_fcd(fcd: Path) -> None:
    cfg = C.load_config()
    v = cfg["v2x"]
    cmd = [
        C.sumo_binary("sumo"), "-n", str(C.NET_FILE), "-r", str(C.DEMAND_FILE),
        "--scale", str(cfg["sim"]["demand_scale"]),
        "--device.rerouting.probability", "1.0", "--device.rerouting.period", "300",
        "--begin", str(WARMUP), "--end", str(KEEP_TO), "--step-length", "1",
        "--fcd-output", str(fcd), "--fcd-output.attributes", "x,y,speed",
        "--time-to-teleport", "300", "--no-warnings", "true", "--no-step-log", "true",
        "--seed", str(cfg["sim"]["seed"]),
    ]
    traci.start(cmd)
    mgr = V2XManager(v, v["penetration"], enable_v2v=True)
    while traci.simulation.getMinExpectedNumber() > 0 and traci.simulation.getTime() < KEEP_TO:
        traci.simulationStep()
        mgr.step(traci.simulation.getTime(), 1.0)
    traci.close()


def parse_fcd(fcd: Path, minx: float, miny: float) -> list:
    """Frames of flat [x,y,spd, x,y,spd, ...] ints for t in the kept window."""
    frames = []
    for _, el in ET.iterparse(fcd, events=("end",)):
        if el.tag == "timestep":
            t = float(el.get("time"))
            if KEEP_FROM <= t <= KEEP_TO:
                flat = []
                for v in el.findall("vehicle"):
                    flat.append(round(float(v.get("x")) - minx))
                    flat.append(round(float(v.get("y")) - miny))
                    flat.append(round(float(v.get("speed"))))
                frames.append(flat)
            el.clear()
    return frames


def main() -> None:
    import sumolib
    OUT.parent.mkdir(parents=True, exist_ok=True)
    net = sumolib.net.readNet(str(C.NET_FILE))
    (minx, miny), _ = net.getBBoxXY()
    edges, size = export_network(net)
    C.log("replay", f"network: {len(edges)} edges, size {size} m")

    scratch = C.ROOT / "output" / "replay"
    scratch.mkdir(parents=True, exist_ok=True)
    scenarios = {}
    for name, runner in (("baseline", run_baseline_fcd), ("v2x", run_v2x_fcd)):
        fcd = scratch / f"fcd_{name}.xml"
        C.log("replay", f"running {name} (FCD) ...")
        runner(fcd)
        frames = parse_fcd(fcd, minx, miny)
        peak = max((len(f) // 3 for f in frames), default=0)
        scenarios[name] = {"dt": 1, "frames": frames}
        C.log("replay", f"  {name}: {len(frames)} frames, peak {peak} vehicles")
        fcd.unlink(missing_ok=True)

    data = {"size": size, "network": edges, "window": [KEEP_FROM, KEEP_TO],
            "scenarios": scenarios}
    OUT.write_text(json.dumps(data, separators=(",", ":")))
    C.log("replay", f"wrote {OUT} ({OUT.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
