"""Render a per-shot HTML report from an OpenFlight session log.

For every shot in the session, this re-runs the ``two_ray`` vertical
estimator **offline** on the saved RADC frames, applies the production
tier classifier, and lays the result next to what the system logged
**live** (the displayed launch angle, its source, two_ray's own answer,
the server's accept/reject gate, frame timing, etc.).

The offline columns use the *current* checked-out code, so this doubles as
a regression lens: replay an old session and see how today's tier gates,
boost, and de-aliasing would classify each shot.

Usage::

    uv run python scripts/analysis/session_shot_report.py SESSION.jsonl
    uv run python scripts/analysis/session_shot_report.py SESSION.jsonl -o report.html --open

Geometry note
-------------
The mount tilt, ball distance, radar height, and net distance are **not**
recorded in the session log, so they must be supplied (defaults match a
typical TrackMan-test setup). The angle offset *is* logged per shot and is
auto-detected unless ``--angle-offset`` is given. The RADC tuning knobs are
read from ``session_start`` so the replay matches the live run. The exact
geometry used is printed into the report header so a result is never
ambiguous.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import logging
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from openflight.kld7.radc import extract_launch_angle, select_best_shot_result
from openflight.kld7.two_ray import classify_two_ray_tier
from openflight.launch_monitor import ClubType

# session_start RADC tuning keys -> extract_launch_angle kwargs
_TUNING_KEY_MAP = {
    "radc_speed_tolerance_mph": "speed_tolerance_mph",
    "radc_centroid_floor_frac": "centroid_floor_frac",
    "radc_spectrum_source": "spectrum_source",
    "radc_ops_bin_outlier_tol": "ops_bin_outlier_tol",
    "radc_ops_bin_outlier_penalty": "ops_bin_outlier_penalty",
    "radc_ops_anchored_peak_min_snr": "ops_anchored_peak_min_snr",
    "radc_horizontal_angle_limit_deg": "horizontal_angle_limit_deg",
    "radc_vertical_impact_energy_threshold": "impact_energy_threshold",
}
_TUNING_DEFAULTS = {
    "speed_tolerance_mph": 10.0,
    "centroid_floor_frac": 0.5,
    "spectrum_source": "f1a",
    "ops_bin_outlier_tol": 25,
    "ops_bin_outlier_penalty": 10.0,
    "ops_anchored_peak_min_snr": 5.0,
    "horizontal_angle_limit_deg": 15.0,
    "impact_energy_threshold": 3.0,
}


@dataclass
class Geometry:
    """Physical setup the offline replay assumes (see module geometry note)."""

    mount_tilt_deg: float
    angle_offset_deg: float
    ball_distance_ft: float
    ball_above_radar_ft: float
    net_distance_ft: float
    angle_offset_auto: bool = False


@dataclass
class Session:
    """Parsed session: per-shot records keyed by shot number, plus config."""

    shots: dict = field(default_factory=dict)
    vbufs: dict = field(default_factory=dict)
    ball_speeds: dict = field(default_factory=dict)
    tuning: dict = field(default_factory=dict)
    logged_offset_deg: float | None = None


def club_type(club_str: str | None) -> ClubType:
    """Map a session ``club`` string ("7-iron") to a ClubType; UNKNOWN if unmatched."""
    if not club_str:
        return ClubType.UNKNOWN
    try:
        return ClubType(club_str)
    except ValueError:
        return ClubType.UNKNOWN


def tuning_from_session(session_start: dict) -> dict:
    """Build the extract_launch_angle tuning kwargs from a session_start entry,
    falling back to production defaults for anything missing."""
    params = ((session_start.get("config") or {}).get("kld7_experiments") or {}).get(
        "radc_tuning_params"
    ) or {}
    tuning = dict(_TUNING_DEFAULTS)
    for src_key, dst_key in _TUNING_KEY_MAP.items():
        if src_key in params and params[src_key] is not None:
            tuning[dst_key] = params[src_key]
    return tuning


def load_session(path: Path) -> Session:
    """Parse a session JSONL into a :class:`Session`."""
    sess = Session()
    offsets: Counter = Counter()
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = obj.get("type")
            sn = obj.get("shot_number")
            if kind == "session_start":
                sess.tuning = tuning_from_session(obj)
            elif kind == "shot_detected":
                sess.shots[sn] = obj
            elif kind == "rolling_buffer_capture":
                sess.ball_speeds[sn] = obj.get("ball_speed_mph")
            elif kind == "kld7_buffer" and obj.get("orientation") == "vertical":
                sess.vbufs[sn] = obj
                sel = (obj.get("ball_angle") or {}).get("radc_selection") or {}
                off = sel.get("angle_offset_deg")
                if off is not None:
                    offsets[off] += 1
    if offsets:
        sess.logged_offset_deg = offsets.most_common(1)[0][0]
    if not sess.tuning:
        sess.tuning = dict(_TUNING_DEFAULTS)
    return sess


def _frames(vbuf: dict) -> list[dict]:
    out = []
    for q in vbuf.get("frames", []):
        b64 = q.get("radc_b64")
        if not b64:
            continue
        out.append(
            {
                "timestamp": q.get("timestamp"),
                "radc": base64.b64decode(b64),
                "arrival_timestamp": q.get("arrival_timestamp"),
                "complete_timestamp": q.get("complete_timestamp"),
                "read_duration_ms": q.get("read_duration_ms"),
            }
        )
    return out


def replay_shot(
    shot: dict, vbuf: dict | None, ball_speed: float | None, geom: Geometry, tuning: dict
) -> dict:
    """Re-run two_ray offline for one shot and classify its tier.

    Returns a dict with tier/launch_angle/boost/dealias/nval/maxsep/maxel and a
    refusal reason when two_ray declines the shot.
    """
    out = {
        "tier": None,
        "launch_angle_deg": None,
        "boosted": False,
        "dealias": None,
        "nval": 0,
        "maxsep": 0.0,
        "maxel": 0.0,
        "refusal": None,
    }
    if vbuf is None or ball_speed is None:
        out["refusal"] = "no_buffer" if vbuf is None else "no_ball_speed"
        return out
    impact = (
        shot.get("impact_timestamp_kld7")
        or vbuf.get("shot_timestamp")
        or shot.get("impact_timestamp")
    )
    club = club_type(shot.get("club"))
    results = extract_launch_angle(
        _frames(vbuf),
        ops243_ball_speed_mph=ball_speed,
        angle_offset_deg=geom.angle_offset_deg,
        orientation="vertical",
        vertical_estimator="two_ray",
        shot_timestamp=impact,
        impact_timestamp=impact,
        mount_deg=geom.mount_tilt_deg,
        distance_ft=geom.ball_distance_ft,
        ball_above_radar_ft=geom.ball_above_radar_ft,
        vertical_flight_window_net_distance_ft=geom.net_distance_ft,
        club=club,
        **tuning,
    )
    best = select_best_shot_result(results) if results else None
    diag = (best or {}).get("two_ray") or {}
    out["refusal"] = diag.get("refusal_reason") or (None if best else "no_result")
    out["dealias"] = diag.get("dealias")
    out["nval"] = diag.get("n_frames_valid") or 0
    frames = diag.get("frames") or []
    out["maxsep"] = max(
        [abs(f["el_deg"] - f["el_image_deg"]) for f in frames if f.get("el_image_deg") is not None]
        + [0.0]
    )
    out["maxel"] = max([f["el_deg"] for f in frames] + [0.0])
    if best and not out["refusal"]:
        tier = classify_two_ray_tier(diag, best.get("launch_angle_deg"), club)
        if tier is not None:
            out["tier"] = tier.tier
            out["launch_angle_deg"] = tier.launch_angle_deg
            out["boosted"] = tier.boosted
    return out


def collect_rows(sess: Session, geom: Geometry, tuning: dict) -> list[dict]:
    """One merged live+offline record per shot, in shot-number order."""
    rows = []
    for sn in sorted(sess.shots):
        shot = sess.shots[sn]
        vbuf = sess.vbufs.get(sn)
        ball = sess.ball_speeds.get(sn) or shot.get("ball_speed_mph")
        ball_angle = (vbuf.get("ball_angle") or {}) if vbuf else {}
        sel = ball_angle.get("radc_selection") or {}
        t_ms = sel.get("selected_t_ms") or []
        offline = replay_shot(shot, vbuf, ball, geom, tuning)
        rows.append(
            {
                "shot": sn,
                "club": shot.get("club"),
                "ball": ball,
                "club_speed": shot.get("club_speed_mph"),
                "smash": shot.get("smash_factor"),
                "spin": shot.get("spin_rpm") or shot.get("spin_candidate_rpm"),
                "spin_confirmed": bool(shot.get("spin_rpm")),
                "carry": shot.get("carry_spin_adjusted") or shot.get("estimated_carry_yards"),
                "disp": shot.get("launch_angle_vertical"),
                "disp_conf": shot.get("launch_angle_vertical_confidence"),
                "source": shot.get("launch_angle_vertical_source"),
                "hla": shot.get("launch_angle_horizontal"),
                "live_2r": ball_angle.get("vertical_deg"),
                "live_2r_conf": ball_angle.get("confidence"),
                "live_frames": ball_angle.get("num_frames"),
                "live_t_ms": ", ".join(f"{x:.0f}" for x in t_ms) if t_ms else "",
                "live_snr": sel.get("avg_snr_db"),
                "accepted": ball_angle.get("accepted"),
                "reason": ball_angle.get("selection_reason") or "",
                **offline,
            }
        )
    return rows


def _fmt(x, p: int = 1) -> str:
    return f"{x:.{p}f}" if isinstance(x, (int, float)) and not isinstance(x, bool) else "—"


def _int(x) -> str:
    return f"{int(round(x))}" if isinstance(x, (int, float)) and not isinstance(x, bool) else "—"


def render_html(rows: list[dict], session_name: str, geom: Geometry) -> str:
    """Render the merged per-shot records into a self-contained HTML page."""
    any_dealias = any(r.get("dealias") for r in rows)
    body_rows = []
    for r in rows:
        src = r["source"]
        src_cls = "ok" if src == "radar" else "bad" if src else "mut"
        acc = r["accepted"]
        acc_txt = "✓" if acc else "✗" if acc is not None else "—"
        acc_cls = "ok" if acc else "bad" if acc is not None else "mut"
        tier = r["tier"]
        if tier == 1:
            tier_html = '<span class="pill t1">T1</span>'
        elif tier == 2:
            tier_html = '<span class="pill t2">T2</span>'
        else:
            tier_html = '<span class="pill rf">—</span>'
        boost = '<span class="boost">+boost</span>' if r["boosted"] else ""
        dealias_cell = (
            ('<td class="ctr ok">✓</td>' if r.get("dealias") else '<td class="ctr mut">·</td>')
            if any_dealias
            else ""
        )
        sep_cls = "ok" if r["maxsep"] >= 9 else "mut"
        el_cls = "ok" if r["maxel"] >= 9 else "mut"
        spin = (
            (_int(r["spin"]) + ("" if r["spin_confirmed"] else "<sup>c</sup>"))
            if r["spin"]
            else "—"
        )
        body_rows.append(
            "<tr>"
            f'<td class="num b">{r["shot"]}</td>'
            f'<td class="sm mut">{html.escape(str(r["club"] or "—"))}</td>'
            f'<td class="num">{_fmt(r["ball"])}</td>'
            f'<td class="num">{_fmt(r["club_speed"])}</td>'
            f'<td class="num">{_fmt(r["smash"], 3)}</td>'
            f'<td class="num mut">{spin}</td>'
            f'<td class="num mut">{_fmt(r["carry"])}</td>'
            f'<td class="sep num b">{_fmt(r["disp"])}</td>'
            f'<td class="num mut">{_fmt(r["disp_conf"], 2)}</td>'
            f'<td class="{src_cls}">{html.escape(str(src or "—"))}</td>'
            f'<td class="num">{_fmt(r["live_2r"])}</td>'
            f'<td class="num mut">{_fmt(r["live_2r_conf"], 2)}</td>'
            f'<td class="num">{r["live_frames"] if r["live_frames"] is not None else "—"}</td>'
            f'<td class="num mut sm">{r["live_t_ms"] or "—"}</td>'
            f'<td class="num mut">{_fmt(r["live_snr"])}</td>'
            f'<td class="{acc_cls} ctr">{acc_txt}</td>'
            f'<td class="sm mut">{html.escape(r["reason"])}</td>'
            f'<td class="num mut">{_fmt(r["hla"])}</td>'
            f'<td class="sep ctr">{tier_html}</td>'
            f'<td class="num b">{_fmt(r["launch_angle_deg"])}</td>'
            f'<td class="ctr">{boost}</td>'
            f"{dealias_cell}"
            f'<td class="num">{r["nval"]}</td>'
            f'<td class="num {sep_cls}">{_fmt(r["maxsep"])}</td>'
            f'<td class="num {el_cls}">{_fmt(r["maxel"])}</td>'
            f'<td class="sm bad">{html.escape(r["refusal"] or "")}</td>'
            "</tr>"
        )

    n = len(rows)
    t1 = sum(1 for r in rows if r["tier"] == 1)
    t2 = sum(1 for r in rows if r["tier"] == 2)
    rf = sum(1 for r in rows if r["tier"] is None)
    boosted = sum(1 for r in rows if r["boosted"])
    radar = sum(1 for r in rows if r["source"] == "radar")
    formula = sum(1 for r in rows if r["source"] == "estimated")
    clubs = Counter(r["club"] for r in rows if r["club"])
    club_summary = ", ".join(f"{v}× {k}" for k, v in clubs.most_common())
    off_label = "auto" if geom.angle_offset_auto else "set"
    dealias_col = "<th>de-alias</th>" if any_dealias else ""
    dealias_grp = 8 if any_dealias else 7

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(session_name)} — Shot Report</title><style>
:root{{--bg:#0a0a0f;--card:#12121a;--elev:#1a1a24;--gold:#d4af37;--cream:#f5f0e6;
--dim:rgba(245,240,230,.55);--line:rgba(245,240,230,.12);--ok:#4ade80;--warn:#fbbf24;--bad:#f87171;}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;background:var(--bg);color:var(--cream);padding:28px 22px 80px}}
h1{{font-size:1.5rem;font-weight:600}}h1 b{{color:var(--gold)}}
.sub{{color:var(--dim);font-size:.9rem;margin:6px 0 18px;line-height:1.6}}
.cards{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}}
.c{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 16px}}
.c .v{{font-size:1.4rem;font-weight:700}}.c .k{{font-size:.72rem;color:var(--dim);text-transform:uppercase;letter-spacing:.08em}}
.c.t1 .v{{color:var(--ok)}}.c.t2 .v{{color:var(--warn)}}.c.rf .v{{color:var(--bad)}}
.scroll{{overflow-x:auto;border:1px solid var(--line);border-radius:12px}}
table{{border-collapse:collapse;font-size:.82rem;white-space:nowrap;min-width:100%}}
thead .grp th{{font-size:.68rem;letter-spacing:.1em;text-transform:uppercase;color:var(--gold);
background:var(--elev);padding:8px 10px;text-align:center;border-bottom:1px solid var(--line)}}
thead .col th{{position:sticky;top:0;background:var(--elev);color:var(--dim);font-weight:600;font-size:.72rem;
padding:7px 9px;text-align:right;border-bottom:1px solid var(--line)}}
td{{padding:6px 9px;border-bottom:1px solid rgba(245,240,230,.06);text-align:left}}
td.num{{text-align:right;font-variant-numeric:tabular-nums;font-family:'SF Mono',ui-monospace,monospace}}
td.ctr{{text-align:center}}td.b{{font-weight:700;color:var(--cream)}}td.mut{{color:var(--dim)}}
td.sm{{font-size:.74rem}}td.ok{{color:var(--ok)}}td.bad{{color:var(--bad)}}
td.sep{{border-left:2px solid var(--line)}}
tbody tr:hover{{background:rgba(255,255,255,.03)}}
.pill{{padding:2px 8px;border-radius:10px;font-size:.7rem;font-weight:700}}
.pill.t1{{background:rgba(74,222,128,.18);color:var(--ok)}}
.pill.t2{{background:rgba(251,191,36,.16);color:var(--warn)}}
.pill.rf{{background:rgba(248,113,113,.14);color:var(--bad)}}
.boost{{color:var(--warn);font-weight:700;font-size:.74rem}}
.note{{color:var(--dim);font-size:.82rem;margin-top:16px;line-height:1.6}}
.note code{{background:var(--elev);padding:1px 5px;border-radius:4px;color:var(--gold);font-size:.92em}}
</style></head><body>
<h1>{html.escape(session_name)} — <b>{n} shots</b></h1>
<div class="sub">{html.escape(club_summary or "—")} · live ran <b>two_ray</b> · offline replay uses the current branch.<br>
geometry: mount {geom.mount_tilt_deg}° / offset {geom.angle_offset_deg}° ({off_label}) /
ball-dist {geom.ball_distance_ft} ft / ball {geom.ball_above_radar_ft * 12:.0f}″ / net {geom.net_distance_ft} ft</div>
<div class="cards">
<div class="c"><div class="v">{n}</div><div class="k">shots</div></div>
<div class="c t1"><div class="v">{t1}</div><div class="k">Tier 1</div></div>
<div class="c t2"><div class="v">{t2}</div><div class="k">Tier 2</div></div>
<div class="c rf"><div class="v">{rf}</div><div class="k">refused</div></div>
<div class="c"><div class="v" style="color:var(--warn)">{boosted}</div><div class="k">boosted</div></div>
<div class="c"><div class="v" style="color:var(--ok)">{radar}</div><div class="k">live: radar</div></div>
<div class="c"><div class="v" style="color:var(--bad)">{formula}</div><div class="k">live: formula</div></div>
</div>
<div class="scroll"><table>
<thead>
<tr class="grp"><th colspan="7">shot</th><th colspan="11">what was logged LIVE</th>
<th colspan="{dealias_grp}">offline two_ray (current code)</th></tr>
<tr class="col">
<th>#</th><th>club</th><th>ball</th><th>club</th><th>smash</th><th>spin</th><th>carry</th>
<th>disp °</th><th>conf</th><th>source</th><th>2R °</th><th>2Rconf</th><th>fr</th><th>t_ms</th><th>SNR</th>
<th>acc</th><th>reject reason</th><th>HLA°</th>
<th>tier</th><th>LA °</th><th>boost</th>{dealias_col}<th>nval</th><th>maxsep</th><th>maxel</th><th>refusal</th></tr>
</thead><tbody>
{"".join(body_rows)}
</tbody></table></div>
<div class="note">
<b>LIVE</b> is what the Pi recorded: <code>disp °</code> is the launch angle the UI showed and <code>source</code>
says whether it came from the radar or the ball-speed <b>formula</b> fallback; <code>2R °</code> is two_ray's own
answer (even when rejected), with <code>acc</code>/<code>reject reason</code> the server's accept gate.
<b>OFFLINE</b> re-runs two_ray through the current code + tier classifier — <code>maxsep</code>/<code>maxel</code>
are the Tier-1 gates (both need ≥ 9°, green = passed). <sup>c</sup> = spin candidate (unconfirmed).
{"" if any_dealias else "All shots had de-alias off (net within the range wrap), so that column is hidden."}
</div>
</body></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("session", type=Path, help="Path to a session_*.jsonl log")
    parser.add_argument(
        "-o", "--output", type=Path, help="Output HTML path (default: <session>.report.html)"
    )
    parser.add_argument(
        "--open", action="store_true", help="Open the report in the default browser when done"
    )
    parser.add_argument(
        "--mount-tilt", type=float, default=10.3, help="Mount tilt in degrees (default: 10.3)"
    )
    parser.add_argument(
        "--angle-offset",
        type=float,
        default=None,
        help="Angle offset in degrees (default: auto-detect from the log, else 2.5)",
    )
    parser.add_argument(
        "--ball-distance",
        type=float,
        default=5.0,
        help="Radar-to-tee distance in feet (default: 5.0)",
    )
    parser.add_argument(
        "--radar-height-inches",
        type=float,
        default=4.0,
        help="Radar height above the ball in inches (default: 4.0)",
    )
    parser.add_argument(
        "--net-distance",
        type=float,
        default=10.0,
        help="Ball-to-net distance in feet; enables de-aliasing past the range wrap (default: 10.0)",
    )
    args = parser.parse_args(argv)

    if not args.session.exists():
        parser.error(f"session not found: {args.session}")

    logging.disable(logging.WARNING)
    sess = load_session(args.session)
    if not sess.shots:
        parser.error("no shot_detected entries found in session")

    auto_offset = args.angle_offset is None
    offset = args.angle_offset
    if auto_offset:
        offset = sess.logged_offset_deg if sess.logged_offset_deg is not None else 2.5
    geom = Geometry(
        mount_tilt_deg=args.mount_tilt,
        angle_offset_deg=offset,
        ball_distance_ft=args.ball_distance,
        ball_above_radar_ft=-args.radar_height_inches / 12.0,
        net_distance_ft=args.net_distance,
        angle_offset_auto=auto_offset,
    )

    # Match the replay's RADC tuning to the live run (read from session_start).
    rows = collect_rows(sess, geom, sess.tuning)
    out_html = render_html(rows, args.session.stem, geom)
    out_path = args.output or args.session.with_suffix(".report.html")
    # Explicit encoding: the report contains non-ASCII glyphs (″, °), which
    # crash on Windows' default cp1252 codec.
    out_path.write_text(out_html, encoding="utf-8")

    t1 = sum(1 for r in rows if r["tier"] == 1)
    t2 = sum(1 for r in rows if r["tier"] == 2)
    rf = sum(1 for r in rows if r["tier"] is None)
    print(f"{len(rows)} shots  ·  Tier-1 {t1}  Tier-2 {t2}  refused {rf}")
    print(
        f"geometry: mount {geom.mount_tilt_deg}  offset {geom.angle_offset_deg}"
        f"{' (auto)' if auto_offset else ''}  ball-dist {geom.ball_distance_ft}"
        f"  ball {geom.ball_above_radar_ft * 12:.0f}in  net {geom.net_distance_ft}"
    )
    print(f"wrote {out_path}")
    if args.open:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.run([opener, str(out_path)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
