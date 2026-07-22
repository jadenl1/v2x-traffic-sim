"""Shared helpers for the baseline pipeline: SUMO_HOME wiring, paths, config.

Every stage script imports this first so that:
  * SUMO_HOME points at the pip-installed SUMO inside the venv,
  * the bundled SUMO `tools/` dir is importable and on PATH,
  * project paths and config are resolved from one place.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

# --- Project layout ---------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OSM_DIR = DATA_DIR / "osm"
COUNTS_DIR = DATA_DIR / "counts"
NETWORK_DIR = ROOT / "network"
SIM_DIR = ROOT / "sim"
OUTPUT_DIR = ROOT / "output" / "baseline"

# Canonical artifact paths shared across stages.
NET_FILE = NETWORK_DIR / "downtown_dc.net.xml"
OSM_FILE = OSM_DIR / "downtown_dc.osm.xml"
AADT_GEOJSON = COUNTS_DIR / "dc_aadt_downtown.geojson"
EDGE_COUNTS_FILE = COUNTS_DIR / "edge_counts_24h.xml"
CANDIDATE_ROUTES = SIM_DIR / "candidate.rou.xml"
DEMAND_FILE = SIM_DIR / "demand_baseline.rou.xml"
ADDITIONAL_FILE = SIM_DIR / "additional.xml"
SUMOCFG_FILE = SIM_DIR / "baseline.sumocfg"


def _locate_sumo() -> Path:
    """Return the SUMO package dir and export SUMO_HOME / tools on PATH."""
    import sumo  # provided by the eclipse-sumo wheel

    sumo_home = Path(sumo.__file__).resolve().parent
    os.environ["SUMO_HOME"] = str(sumo_home)
    tools = sumo_home / "tools"
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    os.environ["PATH"] = f"{sumo_home / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"
    return sumo_home


SUMO_HOME = _locate_sumo()
SUMO_TOOLS = SUMO_HOME / "tools"
TYPEMAP = SUMO_HOME / "data" / "typemap" / "osmNetconvert.typ.xml"


def sumo_binary(name: str) -> str:
    """Absolute path to a SUMO binary (sumo, netconvert, duarouter, ...)."""
    import sumolib

    return sumolib.checkBinary(name)


def load_config() -> dict:
    with open(CONFIG_DIR / "params.yaml") as fh:
        return yaml.safe_load(fh)


def ensure_dirs() -> None:
    for d in (OSM_DIR, COUNTS_DIR, NETWORK_DIR, SIM_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def log(stage: str, msg: str) -> None:
    print(f"[{stage}] {msg}", flush=True)
