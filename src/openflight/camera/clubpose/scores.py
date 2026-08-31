"""Scores for a clubhead pose that are not silhouette IoU.

Section 11f measured IoU running *inversely* to pose correctness on real
segmented masks: the arms that recovered a worse pose scored a better overlap.
That makes every IoU-scored conclusion in this project unreadable rather than
wrong -- including the radar-constrained rotation experiment, which reports a
0.041 IoU penalty for imposing ``|omega| = v / r`` and cannot say whether that
penalty means the constraint is wrong or means the constraint is right and IoU
is punishing it for being right.

Two replacements, chosen because they fail differently from IoU and from each
other:

``chamfer_px``
    Symmetric mean distance between mask BOUNDARIES. IoU on a 200-pixel blob is
    dominated by area, so a pose that is the right size in the right place
    scores well while pointing the wrong way. Edge distance is dominated by
    shape, which is the part we cannot currently read.

``omega_residual_deg_s``
    A pose PAIR implies an angular velocity. The radar independently fixes its
    magnitude at ``v / r``. This is the only score here that uses information
    from outside the image, and it is the one Trackman's OERT leans on -- their
    720p 60 fps camera cannot track impact alone either.

Neither is validated against truth on real pixels. Nothing in this module
should be quoted as an accuracy figure. ``openflight.camera.clubpose/tests/test_pose_scores.py`` shows
only that they rank a known pose first on synthetic masks, which establishes
they are not broken, not that they work.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .fit import iou as _iou, render_mask_6dof, triad


@dataclass(frozen=True)
class Pose:
    """A full clubhead pose: where the centre is, and how it is oriented.

    Angles follow ``fit.triad``: yaw about world up is FACE ANGLE, pitch
    about world right is DYNAMIC LOFT, roll about the face normal is LIE.
    """

    center_world: tuple[float, float, float]
    yaw_deg: float
    pitch_deg: float
    roll_deg: float

    def as_dict(self) -> dict:
        """Plain-JSON form, for annotation files."""
        return {
            "center_world_mm": [float(v) for v in self.center_world],
            "yaw_deg": float(self.yaw_deg),
            "pitch_deg": float(self.pitch_deg),
            "roll_deg": float(self.roll_deg),
        }

    @classmethod
    def from_dict(cls, d: dict) -> Pose:
        """Rebuild a pose from `as_dict` output."""
        return cls(
            tuple(float(v) for v in d["center_world_mm"]),
            float(d["yaw_deg"]),
            float(d["pitch_deg"]),
            float(d["roll_deg"]),
        )

    def basis(self) -> np.ndarray:
        """Orientation as a rotation matrix whose columns are the triad."""
        n, u, v = triad(self.yaw_deg, self.pitch_deg, self.roll_deg)
        return np.column_stack((n, u, v))

    def render(self, mesh, camera) -> np.ndarray | None:
        """Rasterise this pose through the SAME renderer the fitter uses."""
        return render_mask_6dof(
            mesh,
            np.asarray(self.center_world, float),
            self.yaw_deg,
            self.pitch_deg,
            self.roll_deg,
            camera,
        )


@dataclass(frozen=True)
class PoseScores:
    """Three readings of one pose. Directions differ, so they are named."""

    iou: float  # higher is better
    chamfer_px: float  # LOWER is better
    omega_residual_deg_s: float | None  # LOWER is better; None without motion


def mask_edge(mask: np.ndarray) -> np.ndarray:
    """Boundary pixels of a mask: inside it, but touching the outside."""
    m = np.ascontiguousarray(mask.astype(np.uint8))
    eroded = cv2.erode(m, np.ones((3, 3), np.uint8), borderValue=0)
    return (m.astype(bool)) & (~eroded.astype(bool))


def chamfer_px(rendered: np.ndarray, observed: np.ndarray) -> float:
    """Symmetric mean boundary distance in pixels. Lower is better.

    Returns ``inf`` when either mask has no boundary. That is a fail-closed
    choice: an empty render against a real mask is a total failure, and
    reporting 0.0 for it would make the worst possible pose the best scoring.
    """
    ea, eb = mask_edge(rendered), mask_edge(observed)
    if not ea.any() or not eb.any():
        return math.inf
    dt_a = cv2.distanceTransform((~ea).astype(np.uint8), cv2.DIST_L2, 3)
    dt_b = cv2.distanceTransform((~eb).astype(np.uint8), cv2.DIST_L2, 3)
    return 0.5 * (float(dt_b[ea].mean()) + float(dt_a[eb].mean()))


def observed_omega_deg_s(pose_a: Pose, pose_b: Pose, dt_s: float) -> float:
    """Angular speed implied by two poses, in degrees per second."""
    dt = float(dt_s)
    if not math.isfinite(dt) or dt <= 0.0:
        raise ValueError("dt_s must be finite and positive")
    relative = pose_b.basis() @ pose_a.basis().T
    cos_angle = (float(np.trace(relative)) - 1.0) / 2.0
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_angle)))) / dt


def omega_residual_deg_s(
    pose_a: Pose, pose_b: Pose, dt_s: float, speed_mps: float, swing_radius_m: float
) -> float:
    """How far the pose pair's rotation rate sits from the radar's ``v / r``.

    The radar fixes the MAGNITUDE only; the axis stays free. So this constrains
    one number, not three, and a zero residual does not mean the pose is right.
    """
    speed, radius = float(speed_mps), float(swing_radius_m)
    if not math.isfinite(speed) or speed <= 0.0:
        raise ValueError("club speed must be finite and positive")
    if not math.isfinite(radius) or radius <= 0.0:
        raise ValueError("swing radius must be finite and positive")
    required = math.degrees(speed / radius)
    return abs(observed_omega_deg_s(pose_a, pose_b, dt_s) - required)


def score_pose(mesh, pose: Pose, observed_mask, camera, motion=None) -> PoseScores:
    """Score one pose against one observed mask.

    ``motion``, when given, is ``(previous_pose, dt_s, speed_mps, radius_m)``
    and enables the only score that uses non-image information.
    """
    observed = np.asarray(observed_mask).astype(bool)
    rendered = pose.render(mesh, camera)
    if rendered is None:
        return PoseScores(0.0, math.inf, None)
    residual = None
    if motion is not None:
        prev, dt_s, speed_mps, radius_m = motion
        residual = omega_residual_deg_s(prev, pose, dt_s, speed_mps, radius_m)
    return PoseScores(_iou(rendered, observed), chamfer_px(rendered, observed), residual)


def save_annotation(
    path, *, shot: int, frame: int, pose: Pose, annotator: str, pass_index: int
) -> None:
    """Append one hand-labelled pose. Never overwrites: the experiment IS the
    comparison between repeated passes, so losing an earlier pass loses it."""
    record = {
        "shot": int(shot),
        "frame": int(frame),
        "annotator": str(annotator),
        "pass_index": int(pass_index),
        "pose": pose.as_dict(),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def load_annotations(path) -> list[dict]:
    """Every labelled pose from one file; empty when it does not exist yet."""
    p = Path(path)
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
