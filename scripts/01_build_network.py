#!/usr/bin/env python3
"""Stage 1 — Build the downtown DC SUMO network from OpenStreetMap.

  * osmGet.py downloads OSM data for the configured bbox.
  * netconvert builds a car-focused, signalized urban network.

Fixed-time signals guessed by netconvert are intentional: they are the *control*
that V2X signal coordination will later be measured against.
"""
from __future__ import annotations

import glob
import subprocess
import sys

import common as C


def download_osm(bbox: list[float]) -> str:
    w, s, e, n = bbox
    C.log("net", f"Downloading OSM for bbox {w},{s},{e},{n} ...")
    subprocess.run(
        [sys.executable, str(C.SUMO_TOOLS / "osmGet.py"),
         f"--bbox={w},{s},{e},{n}",  # '=' form: leading '-' in lon is not a flag
         "--prefix", "downtown_dc",
         "--output-dir", str(C.OSM_DIR)],
        check=True,
    )
    # osmGet writes <prefix>_bbox.osm.xml; normalise to our canonical name.
    produced = sorted(glob.glob(str(C.OSM_DIR / "downtown_dc*.osm.xml")))
    if not produced:
        raise SystemExit("osmGet produced no .osm.xml — check network / Overpass availability.")
    src = produced[0]
    if src != str(C.OSM_FILE):
        import shutil
        shutil.copyfile(src, C.OSM_FILE)
    C.log("net", f"OSM saved -> {C.OSM_FILE}")
    return str(C.OSM_FILE)


def build_net(osm_file: str) -> None:
    C.log("net", "Running netconvert ...")
    cmd = [
        C.sumo_binary("netconvert"),
        "--osm-files", osm_file,
        "--output-file", str(C.NET_FILE),
        "--type-files", str(C.TYPEMAP),
        # Keep only roads usable by passenger cars (drop footways/cycleways/rail).
        "--keep-edges.by-vclass", "passenger",
        "--remove-edges.isolated", "true",
        # Urban geometry / junction cleanup.
        "--geometry.remove", "true",
        "--roundabouts.guess", "true",
        "--ramps.guess", "false",
        "--junctions.join", "true",
        "--junctions.corner-detail", "5",
        "--rectangular-lane-cut", "true",
        # Traffic signals: guess from OSM signal nodes, merge clustered ones,
        # drop signals at trivial junctions. Default TLS type = static (fixed-time).
        "--tls.guess-signals", "true",
        "--tls.discard-simple", "true",
        "--tls.join", "true",
        "--tls.default-type", "static",
        # Lanes / turns from OSM.
        "--osm.turn-lanes", "true",
        "--default.spreadtype", "roadCenter",
        "--no-turnarounds", "true",
    ]
    subprocess.run(cmd, check=True)
    C.log("net", f"Network built -> {C.NET_FILE}")


def summarise() -> None:
    import sumolib
    net = sumolib.net.readNet(str(C.NET_FILE))
    edges = net.getEdges()
    tls = net.getTrafficLights()
    C.log("net", f"Summary: {len(edges)} edges, {len(net.getNodes())} nodes, "
                 f"{len(tls)} traffic lights.")


def main() -> None:
    C.ensure_dirs()
    cfg = C.load_config()
    osm_file = download_osm(cfg["bbox"])
    build_net(osm_file)
    summarise()


if __name__ == "__main__":
    main()
