"""Polarity-agnostic ball detection with known-radius arc fitting.

Replaces the fixed-polarity, fixed-magnitude rule used by the superseded
synthetic pipeline (on the fork's feat/silhouette-poc branch):

    ball_mask = frame >= percentile(frame, 10) + 210.0

That rule fails on real captures in both directions at once. Measured on the real
OpenFlight archive (`frames.npz`, 2026-08-24):

    at address   ball 192 DN on a clipped 255 DN mat   ->  -62 DN   WRONG SIGN
    in flight    ball 224 DN on a  102 DN dark wall    -> +122 DN   right sign,
                                                                    still under +210

No constant fixes it, because the background swings 102..255 DN inside one shot.

What this does instead:
  1. estimate the LOCAL background, so a clipped mat and a dark wall are both handled
  2. threshold the SIGNED residual in BOTH directions, scaled to measured noise
     rather than an absolute DN offset
  3. confirm candidates by SHAPE, since the ball is the one object in frame with a
     known fixed physical diameter
  4. fit a circle to the reliable part of the boundary, so a ball whose lit side has
     blended into the background still yields an honest radius

Rejections are named, matching the project's fail-closed convention.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

SENSOR_NOISE_DN = 5.6  # measured: 50 static frames of the real archive at gain 15.94
SATURATION_DN = 253  # within noise of the 8-bit ceiling
BALL_DIAMETER_MM = 42.67


@dataclass
class BallFit:
    center: np.ndarray  # (x, y) subpixel
    radius_px: float
    polarity: str  # "dark_on_light" | "light_on_dark"
    contrast_dn: float  # signed, ball minus local background
    arc_coverage_deg: float  # angular span of boundary used for the fit
    visible_area_px: int
    circularity: float
    mask: np.ndarray = field(repr=False)

    @property
    def px_per_mm(self) -> float:
        return 2.0 * self.radius_px / BALL_DIAMETER_MM


class BallNotFound(ValueError):
    """Named rejection, so a failure says which gate it failed."""


def _local_background(frame: np.ndarray, ball_px: int) -> np.ndarray:
    """Median over a window several ball-widths across.

    A ball is small relative to the window, so it is smoothed away while real scene
    structure (the mat, the wall, the boundary between them) survives.
    """
    k = min(int(max(15, ball_px * 3)), 99) | 1
    return cv2.medianBlur(frame, k)


def _robust_sigma(residual: np.ndarray) -> float:
    """MAD-based noise estimate, floored at the sensor's measured read noise."""
    mad = float(np.median(np.abs(residual - np.median(residual))))
    return max(1.4826 * mad, SENSOR_NOISE_DN)


def _fit_circle(points: np.ndarray) -> tuple[np.ndarray, float]:
    """Circle fit: algebraic (Kasa) seed, then geometric Gauss-Newton refinement.

    The refinement minimises true perpendicular distance, which is the statistically
    correct objective and — unlike a purely algebraic fit — stays unbiased on the
    short arcs this detector actually sees when the ball's lit side has blended into
    a saturated background.
    """
    x, y = points[:, 0].astype(float), points[:, 1].astype(float)
    if len(x) < 4:
        raise BallNotFound("too_few_boundary_points")
    # Kasa seed: x^2 + y^2 = 2a.x + 2b.y + c, linear in (a, b, c)
    design = np.column_stack([x, y, np.ones_like(x)])
    try:
        sol, *_ = np.linalg.lstsq(design, x * x + y * y, rcond=None)
    except np.linalg.LinAlgError:
        raise BallNotFound("circle_fit_degenerate") from None
    cx, cy = sol[0] / 2.0, sol[1] / 2.0
    seed = sol[2] + cx * cx + cy * cy
    if not np.isfinite(seed) or seed <= 0.0:
        raise BallNotFound("circle_fit_degenerate")
    r = float(np.sqrt(seed))

    for _ in range(50):  # geometric refinement
        dx, dy = x - cx, y - cy
        dist = np.hypot(dx, dy)
        if np.any(dist < 1e-9):
            break
        residual = dist - r
        jac = np.column_stack([-dx / dist, -dy / dist, -np.ones_like(dist)])
        try:
            step, *_ = np.linalg.lstsq(jac, -residual, rcond=None)
        except np.linalg.LinAlgError:
            break
        cx, cy, r = cx + step[0], cy + step[1], r + step[2]
        if not np.isfinite([cx, cy, r]).all() or r <= 0.0:
            raise BallNotFound("circle_fit_degenerate")
        if np.linalg.norm(step) < 1e-9:
            break
    return np.array([cx, cy]), float(r)


def _reliable_boundary(mask: np.ndarray, frame: np.ndarray) -> np.ndarray:
    """Boundary pixels whose edge is trustworthy.

    Discards boundary where the BALL'S OWN pixel is saturated: there its lit surface
    has merged into a clipped background, so the apparent edge marks where clipping
    began, not where the ball ends, and including it biases the radius low.

    It deliberately does NOT discard boundary merely because the background beside it
    is saturated. A dark ball against a blown-out mat has a real, sharp edge all the
    way round; rejecting it there threw away 17 of 28 boundary points and left a
    45-degree arc that no circle fit can use.
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise BallNotFound("no_boundary")
    pts = max(contours, key=cv2.contourArea).reshape(-1, 2)
    h, w = mask.shape
    keep = [
        (px, py)
        for px, py in pts
        if 0 < px < w - 1 and 0 < py < h - 1 and frame[py, px] < SATURATION_DN
    ]
    return np.array(keep if len(keep) >= 8 else pts, dtype=float)


def _arc_coverage(points: np.ndarray, center: np.ndarray) -> float:
    """Angular span covered by the fitted boundary, in degrees.

    A radius fitted to a 90 degree arc is far less trustworthy than one fitted to
    300 degrees, and the caller should be able to tell the difference.
    """
    ang = np.degrees(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))
    occupied = np.zeros(72, dtype=bool)  # 5 degree bins
    occupied[((ang + 180.0) / 5.0).astype(int) % 72] = True
    return float(occupied.sum() * 5)


def candidates(
    frame: np.ndarray,
    *,
    expected_radius_px: float | None = None,
    radius_tolerance: float = 0.6,
    sigma_k: float = 3.5,
    min_area_px: int = 20,
) -> list[BallFit]:
    """Every region that could be a ball, whether darker or brighter than background."""
    if frame.ndim != 2:
        raise BallNotFound("frame_not_2d")
    f = frame.astype(np.float32)
    nominal = int(expected_radius_px * 2) if expected_radius_px else 14
    background = _local_background(frame, nominal).astype(np.float32)
    residual = f - background
    sigma = _robust_sigma(residual)

    found: list[BallFit] = []
    for polarity, signed in (("light_on_dark", residual), ("dark_on_light", -residual)):
        mask = (signed > sigma_k * sigma).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
        for idx in range(1, count):
            w, h, area = stats[idx, 2], stats[idx, 3], stats[idx, 4]
            if area < min_area_px:
                continue
            if max(w, h) / max(min(w, h), 1) > 3.0:  # a long smear is not a ball
                continue
            comp = (labels == idx).astype(np.uint8)
            try:
                pts = _reliable_boundary(comp, frame)
                if len(pts) < 8:
                    continue
                center, radius = _fit_circle(pts)
            except BallNotFound:
                continue
            if not np.isfinite(radius) or radius <= 1.0 or radius > 0.25 * max(frame.shape):
                continue
            if expected_radius_px is not None:
                lo = expected_radius_px * (1.0 - radius_tolerance)
                hi = expected_radius_px * (1.0 + radius_tolerance)
                if not lo <= radius <= hi:
                    continue
            circularity = float(area) / (np.pi * radius * radius)
            if not 0.30 <= circularity <= 1.60:
                continue
            contrast = float(np.median(f[comp > 0]) - np.median(background[comp > 0]))
            found.append(
                BallFit(
                    center=center,
                    radius_px=float(radius),
                    polarity=polarity,
                    contrast_dn=contrast,
                    arc_coverage_deg=_arc_coverage(pts, center),
                    visible_area_px=int(area),
                    circularity=circularity,
                    mask=comp,
                )
            )

    return found


def fit_teed_ball(frame: np.ndarray, **kwargs) -> BallFit:
    """Single-frame best guess. Shape only — see find_ball_at_address for the real one."""
    found = candidates(frame, **kwargs)
    if not found:
        raise BallNotFound("no_candidate_passed_shape_gate")
    return max(found, key=lambda c: (c.arc_coverage_deg / 360.0) * min(c.circularity, 1.0))


def fit_teed_ball_sequence(
    frames: np.ndarray,
    impact_index: int,
    tee_region: tuple[int, int, int, int],
    *,
    stride: int = 2,
    lead: int = 60,
    settle: int = 2,
    look_after: int = 4,
    cluster_px: float = 5.0,
    min_persistence: float = 0.25,
    **kwargs,
) -> BallFit:
    """Locate the teed ball inside a known tee region.

    `tee_region` is (x0, y0, x1, y1). This is not a shortcut: the camera is fixed to
    the unit and aimed at the ball, so where the ball can be is a property of the rig,
    established once at install. Searching the whole frame is a harder problem than
    the system actually poses, and on the real capture it is not reliably solvable —
    a bay contains signage, shoes and knees that fit a circle better than a ball whose
    lit side has blended into the mat.

    Within the region, two physical facts do the work:
      * the ball is stationary for the whole address period
      * the ball is GONE once the club has sent it away

    The second is the strong one. Static clutter scores 0.00 on departure; the ball
    scores 1.00.

    Ambient captures can change illumination mid-sequence (the real archive drops
    58% six frames after the trigger), so the "after" window is checked to be in the
    same illumination regime and truncated if not — otherwise everything looks like
    it departed.
    """
    x0, y0, x1, y1 = tee_region
    inside = lambda p: x0 <= p[0] <= x1 and y0 <= p[1] <= y1  # noqa: E731

    lo, hi = max(1, impact_index - lead), max(2, impact_index - settle)
    clusters: list[dict] = []
    for index in range(lo, hi, stride):
        for cand in candidates(frames[index], **kwargs):
            if not inside(cand.center):
                continue
            for cluster in clusters:
                if np.linalg.norm(cand.center - cluster["center"]) <= cluster_px:
                    cluster["fits"].append(cand)
                    cluster["frames"].add(index)
                    cluster["center"] = np.mean([f.center for f in cluster["fits"]], axis=0)
                    break
            else:
                clusters.append({"center": cand.center.copy(), "fits": [cand], "frames": {index}})
    if not clusters:
        raise BallNotFound("no_candidate_in_tee_region")

    # keep the post-impact window inside the same illumination regime
    level = float(frames[lo:hi].reshape(hi - lo, -1).mean())
    after = [
        j
        for j in range(impact_index + settle, min(impact_index + settle + look_after, len(frames)))
        if abs(float(frames[j].mean()) - level) < 12.0
    ]
    if not after:
        raise BallNotFound("no_comparable_post_impact_frame")

    sampled = len(range(lo, hi, stride))
    scored = []
    for cluster in clusters:
        persistence = len(cluster["frames"]) / max(sampled, 1)
        if persistence < min_persistence:
            continue
        survives = sum(
            any(
                np.linalg.norm(c.center - cluster["center"]) <= cluster_px * 2
                for c in candidates(frames[j], **kwargs)
                if inside(c.center)
            )
            for j in after
        )
        departed = 1.0 - survives / len(after)
        if departed < 0.75:  # a ball that is still there is not the ball
            continue
        scored.append((departed, persistence, cluster))
    if not scored:
        raise BallNotFound("no_departing_candidate_in_tee_region")

    # Departure ranks above persistence. A bay can hold several balls, and a spare
    # that the club sweeps across is briefly hidden — that scrapes past the gate as a
    # partial departure. The struck ball is gone completely, so ranking on departure
    # first separates them instead of leaving it to a persistence tie-break.
    _, _, best = max(scored, key=lambda s: (round(s[0], 3), s[1]))
    fit = max(best["fits"], key=lambda f: f.arc_coverage_deg)
    fit.center = best["center"]
    fit.radius_px = float(np.median([f.radius_px for f in best["fits"]]))
    return fit
