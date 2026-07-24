#!/usr/bin/env python3
"""Geometry checks on Rev C RF board F.Cu copper for the expert review.

Checks, from the actual .kicad_pcb dump:
1. Same-net segment intersections (real self-crossing loops).
2. Cross-net RF trace proximity (coupling risk) — parallel run lengths.
3. Copper distance to board edge.
4. 90-degree bends on RF nets (unmitered corners).
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "board-geometry.json"

RF_NETS = {
    "RX1", "RX2", "RX3", "RX4", "TX_ANT", "LO_OUT", "RFIN_DIV",
    "Net-(U6-LO_IN)", "Net-(U5-TXOUT1)", "Net-(U5-TXOUT2)", "Net-(U5-LOOUT)",
    "Net-(U4-RFinA)", "Net-(U4-RFinB)", "Net-(C53-Pad2)",
    "Net-(U6-RX1_RF)", "Net-(U6-RX2_RF)", "Net-(U6-RX3_RF)", "Net-(U6-RX4_RF)",
}

BOARD_W, BOARD_H = 82.0, 50.0
EPS = 1e-9


def seg_intersect(a0, a1, b0, b1):
    """Proper segment intersection (excluding shared endpoints)."""

    def orient(p, q, r):
        val = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        if abs(val) < 1e-9:
            return 0
        return 1 if val > 0 else -1

    def on_seg(p, q, r):
        return (
            min(p[0], r[0]) - EPS <= q[0] <= max(p[0], r[0]) + EPS
            and min(p[1], r[1]) - EPS <= q[1] <= max(p[1], r[1]) + EPS
        )

    o1, o2 = orient(a0, a1, b0), orient(a0, a1, b1)
    o3, o4 = orient(b0, b1, a0), orient(b0, b1, a1)
    if o1 != o2 and o3 != o4:
        # exclude touching at exact shared endpoints
        shared = {a0, a1} & {b0, b1}
        if shared:
            return False
        return True
    return False


def point_seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq < EPS:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / length_sq))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def seg_seg_dist(a0, a1, b0, b1):
    if seg_intersect(a0, a1, b0, b1):
        return 0.0
    return min(
        point_seg_dist(a0, b0, b1),
        point_seg_dist(a1, b0, b1),
        point_seg_dist(b0, a0, a1),
        point_seg_dist(b1, a0, a1),
    )


def main() -> int:
    data = json.loads(DATA.read_text())
    fcu = [
        t
        for t in data["tracks"]
        if t["kind"] == "track" and t["layer"] == "F.Cu"
    ]

    print("=== 1. Same-net proper crossings on F.Cu (self-intersecting loops) ===")
    found = False
    by_net: dict[str, list] = {}
    for t in fcu:
        by_net.setdefault(t["net"], []).append(t)
    for net, segs in sorted(by_net.items()):
        for a, b in itertools.combinations(segs, 2):
            a0 = (round(a["x0_mm"], 6), round(a["y0_mm"], 6))
            a1 = (round(a["x1_mm"], 6), round(a["y1_mm"], 6))
            b0 = (round(b["x0_mm"], 6), round(b["y0_mm"], 6))
            b1 = (round(b["x1_mm"], 6), round(b["y1_mm"], 6))
            if seg_intersect(a0, a1, b0, b1):
                print(f"  {net}: {a0}->{a1} crosses {b0}->{b1}")
                found = True
    if not found:
        print("  none")

    print()
    print("=== 2. RF-net proximity: edge-to-edge gap < 1.0 mm, parallel overlap > 2 mm ===")

    def parallel_overlap(a, b):
        """Overlap length if segments are collinear-parallel (H or V)."""
        a_h = abs(a["y0_mm"] - a["y1_mm"]) < 1e-6
        b_h = abs(b["y0_mm"] - b["y1_mm"]) < 1e-6
        if a_h and b_h:
            lo = max(min(a["x0_mm"], a["x1_mm"]), min(b["x0_mm"], b["x1_mm"]))
            hi = min(max(a["x0_mm"], a["x1_mm"]), max(b["x0_mm"], b["x1_mm"]))
            return max(0.0, hi - lo)
        if not a_h and not b_h:
            lo = max(min(a["y0_mm"], a["y1_mm"]), min(b["y0_mm"], b["y1_mm"]))
            hi = min(max(a["y0_mm"], a["y1_mm"]), max(b["y0_mm"], b["y1_mm"]))
            return max(0.0, hi - lo)
        return 0.0

    rf = [t for t in fcu if t["net"] in RF_NETS]
    seen_pairs = set()
    for a, b in itertools.combinations(rf, 2):
        if a["net"] == b["net"]:
            continue
        overlap = parallel_overlap(a, b)
        if overlap < 2.0:
            continue
        gap = seg_seg_dist(
            (a["x0_mm"], a["y0_mm"]),
            (a["x1_mm"], a["y1_mm"]),
            (b["x0_mm"], b["y0_mm"]),
            (b["x1_mm"], b["y1_mm"]),
        ) - (a["width_mm"] + b["width_mm"]) / 2.0
        if gap < 1.0:
            key = tuple(sorted((a["net"], b["net"])))
            if (key, round(gap, 2)) in seen_pairs:
                continue
            seen_pairs.add((key, round(gap, 2)))
            print(
                f"  {a['net']} vs {b['net']}: gap {gap:.2f} mm, overlap {overlap:.1f} mm "
                f"near ({(a['x0_mm']+a['x1_mm'])/2:.1f}, {(a['y0_mm']+a['y1_mm'])/2:.1f})"
            )

    print()
    print("=== 3. F.Cu copper closer than 0.75 mm to board edge ===")
    for t in fcu:
        if t["net"] not in RF_NETS and t["width_mm"] < 0.3:
            continue
        half = t["width_mm"] / 2.0
        for (x, y) in ((t["x0_mm"], t["y0_mm"]), (t["x1_mm"], t["y1_mm"])):
            d = min(x - 0, BOARD_W - x, y - 0, BOARD_H - y) - half
            if d < 0.75:
                edge = (
                    "left" if x - 0 == min(x, BOARD_W - x, y, BOARD_H - y)
                    else "right" if BOARD_W - x == min(x, BOARD_W - x, y, BOARD_H - y)
                    else "top" if y == min(x, BOARD_W - x, y, BOARD_H - y)
                    else "bottom"
                )
                print(
                    f"  {t['net']} w={t['width_mm']:.3f}: ({x:.2f},{y:.2f}) "
                    f"copper edge {d:.2f} mm from {edge} edge"
                )
                break

    print()
    print("=== 4. Unmitered 90-degree bends on RF nets (shared endpoint, axis change) ===")
    for net in sorted(RF_NETS):
        segs = by_net.get(net, [])
        joints: dict[tuple, list] = {}
        for s in segs:
            for end in ((s["x0_mm"], s["y0_mm"]), (s["x1_mm"], s["y1_mm"])):
                joints.setdefault((round(end[0], 4), round(end[1], 4)), []).append(s)
        for point, meeting in joints.items():
            if len(meeting) != 2:
                continue
            dirs = []
            for s in meeting:
                if abs(s["x0_mm"] - s["x1_mm"]) < 1e-6:
                    dirs.append("V")
                elif abs(s["y0_mm"] - s["y1_mm"]) < 1e-6:
                    dirs.append("H")
                else:
                    dirs.append("D")
            if set(dirs) == {"H", "V"}:
                print(f"  {net}: 90-deg corner at {point}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
