#!/usr/bin/env python3
"""Stage 4 — Build calibrated 24h demand.

  * randomTrips.py generates a large candidate-route pool covering the network
    (fringe-biased so through-traffic enters/exits at the boundary).
  * routeSampler.py samples from that pool so per-edge, per-hour flows match the
    real AADT-derived counts from Stage 3.
"""
from __future__ import annotations

import subprocess
import sys

import common as C


def gen_candidate_routes(cfg: dict) -> None:
    """Generate a large, diverse pool of shortest-path routes for routeSampler.

    Count-matching quality is driven by the number of *distinct* candidate routes
    (degrees of freedom for the optimizer). We generate a big pool of varied O-D
    shortest paths — a low insertion period plus a moderate fringe-factor keeps a
    mix of through-traffic (fringe) and interior trips so major counted edges are
    covered from many directions.
    """
    period = cfg["demand"]["trip_period"]
    C.log("demand", f"Generating candidate routes (randomTrips, period={period}) ...")
    subprocess.run(
        [sys.executable, str(C.SUMO_TOOLS / "randomTrips.py"),
         "-n", str(C.NET_FILE),
         "-r", str(C.CANDIDATE_ROUTES),          # routed output (runs duarouter)
         "-o", str(C.SIM_DIR / "candidate.trips.xml"),
         "-b", "0", "-e", "3600", "-p", str(period),
         "--fringe-factor", "3",                  # mix of through + interior O-D
         "--min-distance", "300",
         "--vehicle-class", "passenger",
         "--validate",                            # drop trips with no valid route
         f"--seed={cfg['sim']['seed']}"],
        check=True,
    )
    C.log("demand", f"Candidate routes -> {C.CANDIDATE_ROUTES}")


def run_route_sampler(cfg: dict) -> None:
    C.log("demand", "Calibrating demand to edge counts (routeSampler) ...")
    subprocess.run(
        [sys.executable, str(C.SUMO_TOOLS / "routeSampler.py"),
         "-r", str(C.CANDIDATE_ROUTES),
         "--edgedata-files", str(C.EDGE_COUNTS_FILE),
         "--edgedata-attribute", "entered",
         "-o", str(C.DEMAND_FILE),
         "--prefix", "veh",
         "--optimize", "full",
         "--minimize-vehicles", "1",
         f"--seed={cfg['sim']['seed']}"],
        check=True,
    )
    C.log("demand", f"Calibrated demand -> {C.DEMAND_FILE}")


def summarise() -> None:
    import gzip
    import re

    opener = gzip.open if str(C.DEMAND_FILE).endswith(".gz") else open
    n = 0
    with opener(C.DEMAND_FILE, "rt") as fh:
        for line in fh:
            if "<vehicle " in line:
                n += 1
    C.log("demand", f"Generated {n:,} vehicles for the 24h baseline.")


def main() -> None:
    cfg = C.load_config()
    gen_candidate_routes(cfg)
    run_route_sampler(cfg)
    summarise()


if __name__ == "__main__":
    main()
