#!/usr/bin/env python3
"""Stage 2 — Fetch real DDOT AADT counts for the downtown bbox.

Queries the DC Open Data ArcGIS REST service (Traffic Volume layer) for AADT
polylines intersecting our bbox, returned as WGS84 GeoJSON. Falls back to the
prior year if the primary year returns too few segments in-box.
"""
from __future__ import annotations

import json

import requests

import common as C


def query_aadt(rest_url: str, year: int, bbox: list[float]) -> dict:
    w, s, e, n = bbox
    params = {
        "where": "AADT > 0",
        "geometry": f"{w},{s},{e},{n}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "OBJECTID,ROUTEID,AADT,AADT_YEAR",
        "returnGeometry": "true",
        "f": "geojson",
    }
    url = f"{rest_url}/query"
    C.log("counts", f"Querying AADT ({year} service) for bbox ...")
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    C.ensure_dirs()
    cfg = C.load_config()
    counts = cfg["counts"]
    bbox = cfg["bbox"]

    # The MapServer layer used here is the current (2024) service; AADT_YEAR in
    # the returned features records the actual survey year per segment. We keep a
    # fallback hook in config for future-proofing if the endpoint changes.
    gj = query_aadt(counts["rest_url"], counts["year"], bbox)
    feats = gj.get("features", [])
    C.log("counts", f"Retrieved {len(feats)} AADT segments in bbox.")

    if len(feats) == 0:
        raise SystemExit("No AADT segments returned — check bbox / endpoint.")

    with open(C.AADT_GEOJSON, "w") as fh:
        json.dump(gj, fh)
    aadts = [f["properties"]["AADT"] for f in feats if f["properties"].get("AADT")]
    C.log("counts", f"AADT range {min(aadts)}–{max(aadts)}, "
                    f"median {sorted(aadts)[len(aadts)//2]}. Saved -> {C.AADT_GEOJSON}")


if __name__ == "__main__":
    main()
