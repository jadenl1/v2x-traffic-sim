#!/usr/bin/env python3
"""Stage 5 — Run the 24h baseline simulation (headless SUMO, no V2X).

Writes an additional file (per-hour edgeData) and a sumocfg from config, then
runs SUMO collecting tripinfo, summary, and statistics. These outputs are the
raw material for the baseline metrics in Stage 6.
"""
from __future__ import annotations

import subprocess

import common as C

TRIPINFO = C.OUTPUT_DIR / "tripinfo.xml"
SUMMARY = C.OUTPUT_DIR / "summary.xml"
STATS = C.OUTPUT_DIR / "statistics.xml"
EDGEDATA = C.OUTPUT_DIR / "edgedata.xml"


def write_additional(cfg: dict) -> None:
    agg = cfg["sim"]["aggregation_s"]
    emissions = cfg["sim"]["emissions"]
    etype = ' type="emissions"' if emissions else ""
    with open(C.ADDITIONAL_FILE, "w") as fh:
        fh.write('<additional>\n')
        fh.write(f'  <edgeData id="edge_{agg}s" file="{EDGEDATA}" '
                 f'period="{agg}" excludeEmpty="true"{etype}/>\n')
        fh.write('</additional>\n')


def write_sumocfg(cfg: dict) -> None:
    sim = cfg["sim"]
    with open(C.SUMOCFG_FILE, "w") as fh:
        fh.write('<configuration>\n')
        fh.write('  <input>\n')
        fh.write(f'    <net-file value="{C.NET_FILE}"/>\n')
        fh.write(f'    <route-files value="{C.DEMAND_FILE}"/>\n')
        fh.write(f'    <additional-files value="{C.ADDITIONAL_FILE}"/>\n')
        fh.write('  </input>\n')
        fh.write('  <time>\n')
        fh.write(f'    <begin value="{sim["begin"]}"/>\n')
        fh.write(f'    <end value="{sim["end"]}"/>\n')
        fh.write(f'    <step-length value="{sim["step_length"]}"/>\n')
        fh.write('  </time>\n')
        fh.write('  <processing>\n')
        fh.write('    <ignore-route-errors value="true"/>\n')
        fh.write('    <time-to-teleport value="300"/>\n')
        fh.write('  </processing>\n')
        fh.write('</configuration>\n')


def run(cfg: dict) -> None:
    C.log("run", "Launching 24h baseline SUMO run (headless) ...")
    sim = cfg["sim"]
    cmd = [
        C.sumo_binary("sumo"),
        "-c", str(C.SUMOCFG_FILE),
        "--tripinfo-output", str(TRIPINFO),
        "--summary-output", str(SUMMARY),
        "--statistic-output", str(STATS),
        "--duration-log.statistics", "true",
        "--verbose", "true",
        "--scale", str(sim.get("demand_scale", 1.0)),
        f"--seed={sim['seed']}",
    ]
    if sim.get("mesoscopic"):
        # Mesoscopic engine with traffic-light-aware junction control.
        cmd += ["--mesosim", "true", "--meso-junction-control", "true"]
    if sim.get("rerouting"):
        cmd += ["--device.rerouting.probability", "1.0",
                "--device.rerouting.period", str(sim.get("reroute_period_s", 300)),
                "--device.rerouting.adaptation-interval", "10"]
    if sim["emissions"]:
        cmd += ["--device.emissions.probability", "1.0"]
    subprocess.run(cmd, check=True)
    C.log("run", f"Done. Outputs in {C.OUTPUT_DIR}")


def main() -> None:
    cfg = C.load_config()
    write_additional(cfg)
    write_sumocfg(cfg)
    run(cfg)


if __name__ == "__main__":
    main()
