#!/usr/bin/env python3
"""Collision-check the proposed RX feed routes against pads/tracks/vias/edges."""
import json
import math

AN = "/Users/colemanrollins/code/openflight/hardware/24ghz-adf590x-fmcw-rev-c/analysis/expert-review-2026-07-18"
W = 0.556  # RF trace width
HW = W / 2
CLR = 0.2  # clearance

ROUTES = {
    "RX1": [(5.512, 5.547178), (5.512, 2.05), (32.0, 2.05), (32.0, 20.27), (32.75, 20.27)],
    "RX2": [(18.012, 5.547178), (18.012, 5.15), (8.612, 5.15), (8.612, 4.2), (29.0, 4.2), (29.0, 20.27), (30.75, 20.27)],
    "RX3": [(10.988, 44.452822), (10.988, 45.0), (9.0, 45.0), (9.0, 48.7), (32.0, 48.7), (32.0, 29.73), (32.75, 29.73)],
    "RX4": [(23.488, 44.452822), (23.488, 45.0), (11.8, 45.0), (11.8, 46.75), (29.0, 46.75), (29.0, 29.73), (30.75, 29.73)],
}


def segs(pts):
    return list(zip(pts[:-1], pts[1:]))


def seg_rect_intersect(a, b, r):
    """Does segment a-b intersect rect r=(x0,y0,x1,y1)? Liang-Barsky."""
    x0, y0, x1, y1 = r
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                if t > t1:
                    return False
                t0 = max(t0, t)
            else:
                if t < t0:
                    return False
                t1 = min(t1, t)
    return True


def seg_seg_dist(a, b, c, d):
    """Min distance between segments a-b and c-d."""

    def dot(u, v):
        return u[0] * v[0] + u[1] * v[1]

    def pt_seg(p, a, b):
        ab = (b[0] - a[0], b[1] - a[1])
        l2 = dot(ab, ab)
        if l2 == 0:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        t = max(0, min(1, dot((p[0] - a[0], p[1] - a[1]), ab) / l2))
        proj = (a[0] + t * ab[0], a[1] + t * ab[1])
        return math.hypot(p[0] - proj[0], p[1] - proj[1])

    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    if ((o1 > 0) != (o2 > 0)) and ((o3 > 0) != (o4 > 0)):
        return 0.0
    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


def pt_seg_dist(p, a, b):
    ab = (b[0] - a[0], b[1] - a[1])
    l2 = ab[0] ** 2 + ab[1] ** 2
    if l2 == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0, min(1, ((p[0] - a[0]) * ab[0] + (p[1] - a[1]) * ab[1]) / l2))
    return math.hypot(p[0] - a[0] - t * ab[0], p[1] - a[1] - t * ab[1])


def main():
    pads = json.load(open(f"{AN}/pads.json"))
    geom = json.load(open(f"{AN}/board-geometry.json"))
    tracks = geom["tracks"]
    vias = geom["vias"]
    violations = []
    notes = []

    for net, pts in ROUTES.items():
        ss = segs(pts)
        # 1) foreign pads
        for p in pads:
            if p["net"] == net:
                continue
            exp = HW + CLR
            r = (p["x0"] - exp, p["y0"] - exp, p["x1"] + exp, p["y1"] + exp)
            for a, b in ss:
                if seg_rect_intersect(a, b, r):
                    violations.append(
                        f"{net}: seg {a}->{b} violates pad {p['ref']}.{p['pad']} "
                        f"net={p['net']} bbox=({p['x0']:.2f},{p['y0']:.2f})-({p['x1']:.2f},{p['y1']:.2f})"
                    )
        # 2) foreign tracks
        for t in tracks:
            if t["net"] == net or t["layer"] != "F.Cu":
                continue
            req = HW + CLR + t["width"] / 2
            a2 = (t["x1"], t["y1"])
            b2 = (t["x2"], t["y2"])
            for a, b in ss:
                d = seg_seg_dist(a, b, a2, b2)
                if d < req - 1e-9:
                    violations.append(
                        f"{net}: seg {a}->{b} dist {d:.3f} < {req:.3f} to track "
                        f"net={t['net']} {a2}->{b2} w={t['width']}"
                    )
        # 3) foreign vias
        for v in vias:
            if v["net"] == net:
                continue
            req = HW + CLR + v["diameter"] / 2
            for a, b in ss:
                d = pt_seg_dist((v["x"], v["y"]), a, b)
                if d < req - 1e-9:
                    violations.append(
                        f"{net}: seg {a}->{b} dist {d:.3f} < {req:.3f} to via "
                        f"net={v['net']} at ({v['x']},{v['y']}) d={v['diameter']}"
                    )
        # 4) board edge (report min edge clearance)
        min_edge = 1e9
        for a, b in ss:
            for x, y in (a, b):
                min_edge = min(min_edge, x, y, 82 - x, 50 - y)
        notes.append(f"{net}: min center-to-edge {min_edge:.3f} (edge-copper {min_edge - HW:.3f})")
        # 5) route length
        length = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in ss)
        notes.append(f"{net}: pre-miter length {length:.4f} mm, corners={len(pts) - 2}")

    # 6) inter-route spacing (different nets)
    nets = list(ROUTES)
    for i in range(len(nets)):
        for j in range(i + 1, len(nets)):
            best = 1e9
            where = None
            for a, b in segs(ROUTES[nets[i]]):
                for c, d in segs(ROUTES[nets[j]]):
                    dd = seg_seg_dist(a, b, c, d)
                    if dd < best:
                        best = dd
                        where = (a, b, c, d)
            edge_gap = best - W
            status = "OK" if edge_gap >= CLR else "VIOLATION"
            notes.append(f"{nets[i]}-{nets[j]}: min edge gap {edge_gap:.3f} mm [{status}] at {where}")
            if edge_gap < CLR:
                violations.append(f"{nets[i]}-{nets[j]} edge gap {edge_gap:.3f} < {CLR}")

    print("== NOTES ==")
    for n in notes:
        print(n)
    print("\n== VIOLATIONS ==")
    if violations:
        for v in violations:
            print(v)
    else:
        print("none")


main()
