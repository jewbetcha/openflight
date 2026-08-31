"""Frozen Phase 1b club-state solver, promoted to the Phase 3 fusion package."""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

NOMINAL_RANGE_MM = 1_575.0
CAMERA_HEIGHT_MM = 209.55
RADAR_STATIC_BIAS_MM = 66.0069821
BALL_RADIUS_MM = 42.67 / 2.0
FRAME_TO_IMPACT_S = 1.0e-3
FRAME_PERIOD_S = 2.137e-3
MAX_EXTRAPOLATION_S = 2.5e-3
CENTROID_NOISE_PX = 0.5
MOMENT_EDGE_NOISE_PX = 0.5
RANGE_NOISE_MM = 3.0
FIT_RESIDUAL_LIMIT_PX = 8.0
AMBIGUITY_RATIO_MIN = 1.10
MODEL_VERSION = "phase1b-v1-frozen"
RADAR_HEIGHT_MM = 152.4

_CAMERA_X_MM = math.sqrt(NOMINAL_RANGE_MM**2 - CAMERA_HEIGHT_MM**2)
CAMERA_CENTER_WORLD = np.array([-_CAMERA_X_MM, 0.0, CAMERA_HEIGHT_MM])
TARGET_WORLD = np.zeros(3)
WORLD_RIGHT = np.array([0.0, 1.0, 0.0])
WORLD_UP = np.array([0.0, 0.0, 1.0])
FACE_NORMAL = np.array([1.0, 0.0, 0.0])
_FORWARD = (TARGET_WORLD - CAMERA_CENTER_WORLD) / np.linalg.norm(TARGET_WORLD - CAMERA_CENTER_WORLD)
_DOWN = np.cross(WORLD_RIGHT, _FORWARD)
_DOWN /= np.linalg.norm(_DOWN)
_R_WC = np.stack([WORLD_RIGHT, _DOWN, _FORWARD])
RADAR_CENTER_WORLD = np.array(
    [
        -math.sqrt(NOMINAL_RANGE_MM**2 - RADAR_HEIGHT_MM**2),
        0.0,
        RADAR_HEIGHT_MM,
    ]
)


@dataclass(frozen=True)
class CameraPreset:
    """One explicit camera/crop configuration from approved spec section 5."""

    name: str
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    plate_scale_px_per_mm: float
    sensor_crop: tuple[int, int, int, int]
    sampling_increment: tuple[int, int]
    isp_offset: tuple[int, int]
    orientation: str
    gate_b1_passed: bool
    physical_status: str

    @property
    def horizontal_fov_deg(self) -> float:
        return math.degrees(2.0 * math.atan(self.width / (2.0 * self.fx)))


@dataclass(frozen=True)
class ClubTemplate:
    """Named analytic rear-view silhouette and speed distribution."""

    name: str
    radius_u_mm: float
    radius_v_mm: float
    speed_mean_mm_s: float
    speed_sd_mm_s: float
    impact_u_limit_mm: float
    impact_v_limit_mm: float
    velocity_direction: tuple[float, float, float]


@dataclass(frozen=True)
class SilhouetteObservation:
    centroid_uv: np.ndarray
    covariance_px2: np.ndarray


@dataclass(frozen=True)
class ClubState:
    ok: bool
    reason: str | None
    frame_center_world: np.ndarray | None
    roll_rad: float | None
    fit_residual_px: float | None
    calibrated_range_mm: float | None
    predicted_covariance_px2: np.ndarray | None


def camera_presets() -> dict[str, CameraPreset]:
    """Return independent intrinsics; no fixed-FOV scaling is permitted."""
    return {
        "A0": CameraPreset(
            name="A0",
            width=320,
            height=200,
            fx=1033.0,
            fy=1033.0,
            cx=160.0,
            cy=100.0,
            plate_scale_px_per_mm=0.656,
            sensor_crop=(336, 150, 816, 516),
            sampling_increment=(2, 2),
            isp_offset=(4, 4),
            orientation="landscape_register_window",
            gate_b1_passed=False,
            physical_status="existing_320x200_plus_10us_strobe",
        ),
        "A1": CameraPreset(
            name="A1",
            width=320,
            height=200,
            fx=2063.0,
            fy=2063.0,
            cx=160.0,
            cy=100.0,
            plate_scale_px_per_mm=1.31,
            sensor_crop=(480, 150, 320, 200),
            sampling_increment=(1, 1),
            isp_offset=(0, 0),
            orientation="landscape_crop_metadata_sensitivity",
            gate_b1_passed=False,
            physical_status="plate_scale_sensitivity_only",
        ),
        "B": CameraPreset(
            name="B",
            width=1280,
            height=200,
            fx=2095.0,
            fy=2095.0,
            cx=640.0,
            cy=100.0,
            plate_scale_px_per_mm=1.33,
            sensor_crop=(0, 300, 1280, 200),
            sampling_increment=(1, 1),
            isp_offset=(0, 0),
            orientation="portrait_experimental",
            gate_b1_passed=False,
            physical_status="experimental_gate_b1_not_run",
        ),
    }


def _project(points_world: np.ndarray, camera: CameraPreset) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points_world, dtype=float).reshape(-1, 3)
    cam = (points - CAMERA_CENTER_WORLD) @ _R_WC.T
    in_front = cam[:, 2] > 1e-9
    safe_z = np.where(in_front, cam[:, 2], 1.0)
    uv = np.column_stack(
        [
            camera.fx * cam[:, 0] / safe_z + camera.cx,
            camera.fy * cam[:, 1] / safe_z + camera.cy,
        ]
    )
    return uv, in_front


def _ray_world(uv: np.ndarray, camera: CameraPreset) -> np.ndarray:
    xy = np.array([(uv[0] - camera.cx) / camera.fx, (uv[1] - camera.cy) / camera.fy, 1.0])
    ray = xy @ _R_WC
    return ray / np.linalg.norm(ray)


def _backproject_range(
    uv: np.ndarray,
    range_mm: float,
    camera: CameraPreset,
    range_origin_world: np.ndarray = CAMERA_CENTER_WORLD,
) -> np.ndarray:
    """Intersect a camera ray with a range sphere around the supplied sensor."""
    ray = _ray_world(uv, camera)
    offset = CAMERA_CENTER_WORLD - np.asarray(range_origin_world, dtype=float)
    projection = float(offset @ ray)
    discriminant = projection**2 - float(offset @ offset) + float(range_mm) ** 2
    if discriminant < 0.0:
        return np.full(3, np.nan)
    distance = -projection + math.sqrt(discriminant)
    return CAMERA_CENTER_WORLD + ray * distance


def _range_mm(
    point_world: np.ndarray, range_origin_world: np.ndarray = CAMERA_CENTER_WORLD
) -> float:
    return float(np.linalg.norm(np.asarray(point_world) - range_origin_world))


def _face_axes(roll_rad: float) -> tuple[np.ndarray, np.ndarray]:
    c = math.cos(float(roll_rad))
    s = math.sin(float(roll_rad))
    return c * WORLD_RIGHT + s * WORLD_UP, -s * WORLD_RIGHT + c * WORLD_UP


def _velocity(template: ClubTemplate, speed_mm_s: float, reverse: bool = False) -> np.ndarray:
    direction = np.asarray(template.velocity_direction, dtype=float)
    direction /= np.linalg.norm(direction)
    return direction * float(speed_mm_s) * (-1.0 if reverse else 1.0)


def _projected_velocity(
    center_world: np.ndarray, velocity_world: np.ndarray, camera: CameraPreset
) -> np.ndarray:
    dt = 1.0e-5
    uv_pair, front = _project(
        np.stack([center_world - velocity_world * dt / 2, center_world + velocity_world * dt / 2]),
        camera,
    )
    if not bool(np.all(front)):
        return np.zeros(2)
    return (uv_pair[1] - uv_pair[0]) / dt


def _projection_jacobian(center_world: np.ndarray, camera: CameraPreset) -> np.ndarray:
    """Pixel derivative for one millimetre along world-right/world-up."""
    epsilon = 1.0e-3
    points = np.stack(
        [
            center_world - WORLD_RIGHT * epsilon,
            center_world + WORLD_RIGHT * epsilon,
            center_world - WORLD_UP * epsilon,
            center_world + WORLD_UP * epsilon,
        ]
    )
    uv, front = _project(points, camera)
    if not bool(np.all(front)):
        return np.full((2, 2), np.nan)
    return np.column_stack([(uv[1] - uv[0]) / (2.0 * epsilon), (uv[3] - uv[2]) / (2.0 * epsilon)])


def _silhouette_moments(
    center_world: np.ndarray,
    roll_rad: float,
    velocity_world: np.ndarray,
    exposure_us: float,
    camera: CameraPreset,
    template: ClubTemplate,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    center_uv, front = _project(center_world[None, :], camera)
    if not bool(front[0]):
        nan = np.full(2, np.nan)
        return nan, np.full((2, 2), np.nan), nan, nan, nan
    center_uv = center_uv[0]
    axis_u, axis_v = _face_axes(roll_rad)
    jacobian = _projection_jacobian(center_world, camera)
    if not bool(np.all(np.isfinite(jacobian))):
        nan = np.full(2, np.nan)
        return nan, np.full((2, 2), np.nan), nan, nan, nan
    body_u = np.array([float(axis_u @ WORLD_RIGHT), float(axis_u @ WORLD_UP)])
    body_v = np.array([float(axis_v @ WORLD_RIGHT), float(axis_v @ WORLD_UP)])
    vector_u = jacobian @ body_u * template.radius_u_mm
    vector_v = jacobian @ body_v * template.radius_v_mm
    blur_vector = _projected_velocity(center_world, velocity_world, camera) * (
        float(exposure_us) * 1e-6
    )
    covariance = (
        np.outer(vector_u, vector_u) / 4.0
        + np.outer(vector_v, vector_v) / 4.0
        + np.outer(blur_vector, blur_vector) / 12.0
    )
    extents = np.sqrt(vector_u**2 + vector_v**2) + np.abs(blur_vector) / 2.0
    return center_uv, covariance, extents, vector_u, vector_v


def _visible(center_uv: np.ndarray, extents: np.ndarray, camera: CameraPreset) -> bool:
    if not bool(np.all(np.isfinite(center_uv))) or not bool(np.all(np.isfinite(extents))):
        return False
    return bool(
        center_uv[0] - extents[0] >= 0.0
        and center_uv[0] + extents[0] < camera.width
        and center_uv[1] - extents[1] >= 0.0
        and center_uv[1] + extents[1] < camera.height
    )


def _ball_geometry(
    ball_center_world: np.ndarray, camera: CameraPreset
) -> tuple[np.ndarray, np.ndarray]:
    center_uv, front = _project(ball_center_world[None, :], camera)
    if not bool(front[0]):
        return np.full(2, np.nan), np.full(2, np.nan)
    center_uv = center_uv[0]
    endpoints, endpoint_front = _project(
        np.stack(
            [
                ball_center_world + WORLD_RIGHT * BALL_RADIUS_MM,
                ball_center_world + WORLD_UP * BALL_RADIUS_MM,
            ]
        ),
        camera,
    )
    if not bool(np.all(endpoint_front)):
        return np.full(2, np.nan), np.full(2, np.nan)
    extents = np.abs(endpoints - center_uv).max(axis=0)
    return center_uv, extents


def _silhouette_polygon(
    center_uv: np.ndarray, vector_u: np.ndarray, vector_v: np.ndarray, blur_vector: np.ndarray
) -> np.ndarray:
    theta = np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False)
    ellipse = (
        center_uv[None, :]
        + np.cos(theta)[:, None] * vector_u[None, :]
        + np.sin(theta)[:, None] * vector_v[None, :]
    )
    points = np.vstack([ellipse - blur_vector / 2.0, ellipse + blur_vector / 2.0])
    return cv2.convexHull(points.astype(np.float32)).reshape(-1, 2)


def _polygon_iou(a: np.ndarray, b: np.ndarray) -> float:
    area_a = abs(float(cv2.contourArea(a)))
    area_b = abs(float(cv2.contourArea(b)))
    if area_a <= 0.0 or area_b <= 0.0:
        return 0.0
    intersection, _ = cv2.intersectConvexConvex(a.astype(np.float32), b.astype(np.float32))
    union = area_a + area_b - float(intersection)
    return float(intersection / union) if union > 0.0 else 0.0


def _normalize_roll(angle: float) -> float:
    return (float(angle) + math.pi / 2.0) % math.pi - math.pi / 2.0
