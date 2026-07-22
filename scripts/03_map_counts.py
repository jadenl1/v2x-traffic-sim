#!/usr/bin/env python3
"""Stage 3 — Map AADT counts onto SUMO edges and expand to a 24h profile.

For each AADT polyline we find the nearest network edge(s) whose orientation
agrees with the segment, split the (bidirectional) AADT across directions, then
apply an urban weekday diurnal curve to turn each daily total into 24 hourly
counts. Output is a SUMO edgedata file consumed by routeSampler in Stage 4.
"""
from __future__ import annotations

import math
from collections import defaultdict

import pandas as pd

import common as C


def bearing(p0, p1) -> float:
    """Compass-free bearing (degrees, 0-360) of vector p0->p1 in net XY."""
    return math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])) % 360.0


def angle_diff(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return min(d, 360.0 - d)


def load_diurnal() -> list[float]:
    df = pd.read_csv(C.CONFIG_DIR / "diurnal_weekday.csv").sort_values("hour")
    w = df["weight"].to_numpy(dtype=float)
    return (w / w.sum()).tolist()  # normalise to sum 1.0


def match_counts(net, features, max_dist: float, split: float):
    """Return {edge_id: daily_directional_count}, plus coverage stats.

    Each AADT segment is assigned to its best forward edge and (if the road is
    two-way) its best reverse edge. When both directions match, the AADT is
    split; a one-way match keeps the full total. Per edge we retain the count
    from the closest-matching segment.
    """
    best_dist: dict[str, float] = {}
    counts: dict[str, float] = {}
    matched_segments = 0

    for feat in features:
        aadt = feat["properties"].get("AADT")
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if not aadt or not coords:
            continue
        # Handle both LineString and MultiLineString.
        if geom["type"] == "MultiLineString":
            line = max(coords, key=len)
        else:
            line = coords
        if len(line) < 2:
            continue

        xy = [net.convertLonLat2XY(lon, lat) for lon, lat in line]
        mid = xy[len(xy) // 2]
        seg_b = bearing(xy[0], xy[-1])

        neigh = net.getNeighboringEdges(mid[0], mid[1], max_dist)
        if not neigh:
            continue
        neigh.sort(key=lambda ed: ed[1])  # by distance

        fwd = rev = None
        fwd_d = rev_d = None
        for edge, dist in neigh:
            if not edge.allows("passenger"):
                continue
            shp = edge.getShape()
            eb = bearing(shp[0], shp[-1])
            same = angle_diff(eb, seg_b) < 35.0
            opp = angle_diff(eb, (seg_b + 180) % 360) < 35.0
            if same and fwd is None:
                fwd, fwd_d = edge, dist
            elif opp and rev is None:
                rev, rev_d = edge, dist
            if fwd is not None and rev is not None:
                break

        matched = [(fwd, fwd_d), (rev, rev_d)]
        matched = [(e, d) for e, d in matched if e is not None]
        if not matched:
            continue
        matched_segments += 1

        two_way = len(matched) == 2
        for edge, dist in matched:
            eid = edge.getID()
            if two_way:
                share = aadt * (split if edge is fwd else (1.0 - split))
            else:
                share = float(aadt)
            # Keep the count from the closest-matching segment for this edge.
            if eid not in best_dist or dist < best_dist[eid]:
                best_dist[eid] = dist
                counts[eid] = share

    return counts, matched_segments


def write_edgedata(counts: dict[str, float], diurnal: list[float]) -> None:
    with open(C.EDGE_COUNTS_FILE, "w") as fh:
        fh.write('<data>\n')
        for h in range(24):
            begin, end = h * 3600, (h + 1) * 3600
            fh.write(f'  <interval id="h{h}" begin="{begin}" end="{end}">\n')
            for eid, daily in counts.items():
                entered = int(round(daily * diurnal[h]))
                if entered > 0:
                    fh.write(f'    <edge id="{eid}" entered="{entered}"/>\n')
            fh.write('  </interval>\n')
        fh.write('</data>\n')


def main() -> None:
    import json
    import sumolib

    cfg = C.load_config()
    ccfg = cfg["counts"]
    C.log("map", "Loading network + AADT features ...")
    net = sumolib.net.readNet(str(C.NET_FILE))
    with open(C.AADT_GEOJSON) as fh:
        features = json.load(fh)["features"]

    diurnal = load_diurnal()
    counts, matched = match_counts(net, features, ccfg["match_max_dist_m"], ccfg["direction_split"])

    total_edges = len([e for e in net.getEdges() if e.allows("passenger")])
    daily_total = sum(counts.values())
    C.log("map", f"Matched {matched}/{len(features)} AADT segments.")
    C.log("map", f"Counted edges: {len(counts)}/{total_edges} passenger edges "
                 f"({100*len(counts)/max(total_edges,1):.1f}% directly calibrated; "
                 f"remainder is demand-only).")
    C.log("map", f"Total calibrated daily volume across counted edges: {daily_total:,.0f}.")

    write_edgedata(counts, diurnal)
    C.log("map", f"24h edge counts -> {C.EDGE_COUNTS_FILE}")


if __name__ == "__main__":
    main()
