"""
WebSocket server for OpenFlight UI.

Provides real-time shot data to the web frontend via Flask-SocketIO.
"""

import json
import logging
import os
import random
import statistics
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from flask import Flask, Response, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO

from .ballistics import resolve_launch, simulate
from .launch_monitor import SPIN_CONFIDENCE_HIGH, ClubType, Shot
from .ops243 import Direction, SpeedReading, set_show_raw_readings
from .rolling_buffer.monitor import estimate_carry_with_spin, get_optimal_spin_for_ball_speed
from .session_logger import get_session_logger, init_session_logger, log_session_error
from .sim import (
    IncompleteShotError,
    PlayerState as SimPlayerState,
    PlayerUpdate,
    ShotAck,
    SimError,
    build_connectors,
    load_sim_config,
    resolve_shot,
)
from .speed_correction import correct_ball_speed
from .spin_estimate import calculated_spin_rpm

# Configure logging
logger = logging.getLogger(__name__)

# Camera imports (optional)
REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIST_DIR = REPO_ROOT / "ui" / "dist"
FRONTEND_SOURCE_DIR = REPO_ROOT / "ui"

try:
    import cv2

    from .camera_tracker import CameraTracker

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    CameraTracker = None

try:
    from picamera2 import Picamera2

    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False


app = Flask(__name__, static_folder=str(FRONTEND_DIST_DIR), static_url_path="")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Global state
monitor = None
mock_mode: bool = False
debug_mode: bool = False
debug_log_file = None
debug_log_path: Optional[Path] = None

# K-LD7 angle radars (vertical = launch angle, horizontal = club path)
kld7_vertical = None
kld7_horizontal = None
experimental_kld7_radc_tuning: bool = False
experimental_kld7_raw_radc_logging: bool = False

# Ballistic model toggle. When True, shot carry comes from the physics
# simulator whenever a vertical launch angle is available. When False
# (default), all carry computations go through the legacy table estimator.
# The simulator is opt-in until coefficients are validated against TM.
ballistics_enabled: bool = False

# Simulator connectors (optional). Populated in main() from config/sim.json +
# CLI flags; shots fan out to every connected connector. Player/club state is
# shared across all of them.
sim_connectors: List = []
# Seed the shot counter from the clock (epoch ms) so ShotNumber strictly
# increases across server restarts. Some sims (e.g. OpenGolfSim's Developer API)
# reject any ShotNumber <= the highest they've seen, and that counter persists
# across reconnects — a per-run reset to 1 would get every shot dropped.
sim_player_state = SimPlayerState(shot_counter=int(time.time() * 1000))

_DEFAULT_KLD7_RADC_TUNING = {
    "radc_speed_tolerance_mph": 10.0,
    "radc_centroid_floor_frac": 0.5,
    "radc_spectrum_source": "f1a",
    "radc_ops_bin_outlier_tol": 25,
    "radc_ops_bin_outlier_penalty": 10.0,
    "radc_ops_anchored_peak_min_snr": 5.0,
    "radc_vertical_impact_energy_threshold": 3.0,
    "radc_horizontal_impact_energy_threshold": 1.85,
    "radc_horizontal_retry_impact_energy_threshold": 0.5,
    "radc_horizontal_angle_limit_deg": 15.0,
}
active_kld7_radc_tuning: dict = dict(_DEFAULT_KLD7_RADC_TUNING)

# Camera state
camera: Optional["Picamera2"] = None
camera_tracker: Optional["CameraTracker"] = None
camera_enabled: bool = False
camera_streaming: bool = False
camera_thread: Optional[threading.Thread] = None
camera_stop_event: Optional[threading.Event] = None
ball_detected: bool = False
ball_detection_confidence: float = 0.0
latest_frame: Optional[bytes] = None
frame_lock = threading.Lock()
shutdown_lock = threading.Lock()
shutdown_cleanup_started = False


def _run_shutdown_step(name: str, callback) -> None:
    """Run one shutdown step without preventing later hardware cleanup."""
    try:
        callback()
    except Exception:
        logger.warning("[SERVER] Shutdown cleanup failed during %s", name, exc_info=True)


def _cleanup_hardware_for_shutdown() -> None:
    """Stop hardware resources in an order that leaves serial devices reusable."""
    global shutdown_cleanup_started  # pylint: disable=global-statement

    with shutdown_lock:
        if shutdown_cleanup_started:
            logger.info("[SERVER] Shutdown cleanup already started")
            return
        shutdown_cleanup_started = True

    if kld7_vertical:
        _run_shutdown_step("K-LD7 vertical stop", kld7_vertical.stop)
    if kld7_horizontal:
        _run_shutdown_step("K-LD7 horizontal stop", kld7_horizontal.stop)

    _run_shutdown_step("camera thread stop", stop_camera_thread)
    if camera:
        _run_shutdown_step("camera stop", camera.stop)
        _run_shutdown_step("camera close", camera.close)

    _run_shutdown_step("launch monitor stop", stop_monitor)

    for connector in sim_connectors:
        _run_shutdown_step(f"simulator connector stop ({connector.name})", connector.stop)


def _shutdown_process_after_delay(delay_s: float = 0.5) -> None:
    """Give the HTTP/WebSocket response time to flush, then clean up and exit."""
    time.sleep(delay_s)
    _cleanup_hardware_for_shutdown()
    logger.info("[SERVER] Goodbye")
    os._exit(0)


# Baseline launch angles by club (TrackMan data)
# Format: (avg_launch_deg, avg_ball_speed_mph, deg_per_mph_deviation)
_CLUB_LAUNCH_MODEL = {
    ClubType.DRIVER: (11.0, 143, 0.15),
    ClubType.WOOD_3: (12.5, 135, 0.18),
    ClubType.WOOD_5: (14.0, 128, 0.20),
    ClubType.WOOD_7: (15.5, 122, 0.20),
    ClubType.HYBRID_3: (13.5, 123, 0.22),
    ClubType.HYBRID_5: (15.0, 118, 0.22),
    ClubType.HYBRID_7: (16.5, 112, 0.25),
    ClubType.HYBRID_9: (18.0, 106, 0.25),
    ClubType.IRON_2: (13.0, 120, 0.25),
    ClubType.IRON_3: (14.5, 118, 0.25),
    ClubType.IRON_4: (16.0, 114, 0.28),
    ClubType.IRON_5: (17.5, 110, 0.28),
    ClubType.IRON_6: (19.0, 105, 0.30),
    ClubType.IRON_7: (20.5, 100, 0.30),
    ClubType.IRON_8: (23.0, 94, 0.30),
    ClubType.IRON_9: (25.5, 88, 0.30),
    ClubType.PW: (28.0, 82, 0.30),
    ClubType.GW: (30.0, 76, 0.30),
    ClubType.SW: (32.0, 73, 0.30),
    ClubType.LW: (35.0, 70, 0.30),
    ClubType.UNKNOWN: (18.0, 120, 0.25),
}

# Optimal smash factor by club type (ball_speed / club_speed)
_OPTIMAL_SMASH = {
    ClubType.DRIVER: 1.48,
    ClubType.WOOD_3: 1.44,
    ClubType.WOOD_5: 1.42,
    ClubType.WOOD_7: 1.42,
    ClubType.HYBRID_3: 1.39,
    ClubType.HYBRID_5: 1.38,
    ClubType.HYBRID_7: 1.37,
    ClubType.HYBRID_9: 1.36,
    ClubType.IRON_2: 1.37,
    ClubType.IRON_3: 1.36,
    ClubType.IRON_4: 1.35,
    ClubType.IRON_5: 1.35,
    ClubType.IRON_6: 1.34,
    ClubType.IRON_7: 1.34,
    ClubType.IRON_8: 1.33,
    ClubType.IRON_9: 1.33,
    ClubType.PW: 1.25,
    ClubType.GW: 1.23,
    ClubType.SW: 1.22,
    ClubType.LW: 1.20,
    ClubType.UNKNOWN: 1.35,
}

# Max smash factor adjustment in degrees (clamped to prevent floor-dependence)
_MAX_SMASH_ADJ_LOW = -3.0  # max degrees to subtract for thin/toe hits
_MAX_SMASH_ADJ_HIGH = 2.0  # max degrees to add for high-face hits

# Degrees of launch angle change per 0.01 smash factor unit
_SMASH_DEG_PER_HUNDREDTH_LOW = 0.4  # below optimal (thin hits penalized more)
_SMASH_DEG_PER_HUNDREDTH_HIGH = 0.2  # above optimal

# Spin rate adjustment: degrees per 500 rpm deviation from optimal
_SPIN_DEG_PER_500RPM = 0.3
# Max spin adjustment in degrees (clamped like smash)
_MAX_SPIN_ADJ = 2.0

# Radar launch sanity guard. These windows are intentionally wide:
# they are meant to catch obvious K-LD7 false positives, not to micromanage
# normal shot-to-shot variation or mishits.
_RADAR_SANITY_LOW_CONF_BONUS_DEG = 5.0


def _react_app_dir() -> Path:
    """Return the best available directory containing the React index file."""
    candidates = [
        Path(app.static_folder) if app.static_folder else FRONTEND_DIST_DIR,
        FRONTEND_DIST_DIR,
        FRONTEND_SOURCE_DIR,
    ]
    for candidate in candidates:
        if (candidate / "index.html").is_file():
            return candidate
    return candidates[0]


def estimate_launch_angle(
    club: ClubType,
    ball_speed_mph: float,
    club_speed_mph: Optional[float] = None,
    spin_rpm: Optional[float] = None,
) -> tuple:
    """
    Estimate launch angle from club type, ball speed, and optional smash/spin data.

    Uses TrackMan averages as baseline, then adjusts for:
    - Ball speed deviation from club average
    - Smash factor deviation from optimal (if club_speed provided)
    - Spin rate deviation from optimal (if spin_rpm provided)

    Returns (vertical_angle, confidence).
    """
    avg_launch, avg_speed, deg_per_mph = _CLUB_LAUNCH_MODEL.get(club, (18.0, 120, 0.25))

    # Slower than average → higher launch, faster → lower launch
    speed_delta = ball_speed_mph - avg_speed
    adjustment = -speed_delta * deg_per_mph

    confidence = 0.2

    # Smash factor adjustment: compare actual smash to optimal for this club
    if club_speed_mph is not None and club_speed_mph > 0:
        smash_factor = ball_speed_mph / club_speed_mph
        optimal_smash = _OPTIMAL_SMASH.get(club, 1.35)
        smash_delta = smash_factor - optimal_smash

        if smash_delta < 0:
            smash_adj = max(_MAX_SMASH_ADJ_LOW, smash_delta * 100 * _SMASH_DEG_PER_HUNDREDTH_LOW)
        else:
            smash_adj = min(_MAX_SMASH_ADJ_HIGH, smash_delta * 100 * _SMASH_DEG_PER_HUNDREDTH_HIGH)
        adjustment += smash_adj

        confidence = 0.35

    # Spin rate adjustment: compare actual spin to optimal for this club/speed
    if spin_rpm is not None and spin_rpm > 0:
        optimal_spin = get_optimal_spin_for_ball_speed(ball_speed_mph, club)
        spin_delta = spin_rpm - optimal_spin
        spin_adj = (spin_delta / 500.0) * _SPIN_DEG_PER_500RPM
        spin_adj = max(-_MAX_SPIN_ADJ, min(_MAX_SPIN_ADJ, spin_adj))
        adjustment += spin_adj

        if confidence >= 0.35:
            confidence = 0.5
        else:
            confidence = 0.35

    launch_angle = max(5.0, round(avg_launch + adjustment, 1))

    return (launch_angle, confidence)


def _radar_launch_base_delta_deg(club: ClubType) -> float:
    """Return a conservative club-family window for radar launch sanity checks."""
    if club in {ClubType.PW, ClubType.GW, ClubType.SW, ClubType.LW}:
        return 22.0
    if club in {ClubType.IRON_6, ClubType.IRON_7, ClubType.IRON_8, ClubType.IRON_9}:
        return 20.0
    return 18.0


def radar_launch_is_plausible(
    radar_angle_deg: Optional[float],
    club: ClubType,
    ball_speed_mph: float,
    club_speed_mph: Optional[float] = None,
    spin_rpm: Optional[float] = None,
) -> tuple[bool, dict]:
    """Check whether a radar launch angle is plausible for the shot profile.

    This is a wide guardrail meant to reject only obvious radar outliers. When
    the selected club is unknown or the angle is missing, we skip the guard.
    """
    if radar_angle_deg is None or club in {None, ClubType.UNKNOWN} or ball_speed_mph <= 0:
        return True, {
            "skipped": True,
            "expected_launch_deg": None,
            "allowed_delta_deg": None,
            "delta_deg": None,
        }

    expected_launch_deg, estimate_conf = estimate_launch_angle(
        club,
        ball_speed_mph,
        club_speed_mph=club_speed_mph,
        spin_rpm=spin_rpm,
    )
    allowed_delta_deg = (
        _radar_launch_base_delta_deg(club)
        + (1.0 - estimate_conf) * _RADAR_SANITY_LOW_CONF_BONUS_DEG
    )
    delta_deg = abs(radar_angle_deg - expected_launch_deg)
    if radar_angle_deg <= expected_launch_deg:
        plausible = 0.0 <= radar_angle_deg <= 45.0
    else:
        plausible = delta_deg <= allowed_delta_deg

    return plausible, {
        "skipped": False,
        "expected_launch_deg": round(expected_launch_deg, 1),
        "allowed_delta_deg": round(allowed_delta_deg, 1),
        "delta_deg": round(delta_deg, 1),
    }


def _vertical_soft_launch_lane_deg(club: ClubType) -> tuple[float, float]:
    """Return broad club-family lanes for low-confidence vertical radar candidates."""
    if club == ClubType.DRIVER:
        return (4.0, 22.0)
    if club in {ClubType.WOOD_3, ClubType.WOOD_5, ClubType.WOOD_7}:
        return (5.0, 24.0)
    if club in {ClubType.HYBRID_3, ClubType.HYBRID_5, ClubType.HYBRID_7, ClubType.HYBRID_9}:
        return (6.0, 26.0)
    if club in {ClubType.IRON_2, ClubType.IRON_3, ClubType.IRON_4, ClubType.IRON_5}:
        return (5.0, 25.0)
    if club in {ClubType.IRON_6, ClubType.IRON_7, ClubType.IRON_8, ClubType.IRON_9}:
        return (7.0, 28.0)
    if club in {ClubType.PW, ClubType.GW, ClubType.SW, ClubType.LW}:
        return (10.0, 45.0)
    return (5.0, 35.0)


def _select_vertical_radar_launch(kld7_angle, shot: Shot) -> tuple[bool, dict]:
    """Decide whether a vertical K-LD7 candidate should set the shot launch angle.

    High-confidence candidates keep the existing production behavior. Marginal
    candidates get a stricter second pass: they must agree with the launch
    estimator, sit inside a club-family lane, and avoid very long frame spans
    that often indicate clutter rather than the ball transit. Very low
    confidence candidates are still rejected, but near-threshold candidates
    that pass every other guard are allowed through so the UI can show them as
    low-confidence radar measurements instead of silently replacing them with
    the launch estimator.
    """
    details = {
        "accepted": False,
        "selection_reason": "no_candidate",
        "acceptance_path": None,
        "strict_min_confidence": _MIN_VERTICAL_RADAR_CONFIDENCE,
        "soft_min_confidence": _MIN_VERTICAL_SOFT_RADAR_CONFIDENCE,
        "low_confidence_min_confidence": _MIN_VERTICAL_LOW_CONFIDENCE_RADAR_CONFIDENCE,
        "soft_allowed_delta_deg": _VERTICAL_SOFT_ESTIMATE_DELTA_DEG,
        "soft_max_frame_count": _VERTICAL_SOFT_MAX_FRAME_COUNT,
    }
    if not kld7_angle or kld7_angle.vertical_deg is None:
        return False, details

    radar_angle_deg = kld7_angle.vertical_deg
    plausible, guard_details = radar_launch_is_plausible(
        radar_angle_deg=radar_angle_deg,
        club=shot.club,
        ball_speed_mph=shot.ball_speed_mph,
        club_speed_mph=shot.club_speed_mph,
        spin_rpm=shot.spin_rpm,
    )
    details.update(guard_details)
    if not plausible:
        details["selection_reason"] = "implausible_launch"
        return False, details

    if kld7_angle.confidence >= _MIN_VERTICAL_RADAR_CONFIDENCE:
        details["accepted"] = True
        details["selection_reason"] = "strict_accept"
        details["acceptance_path"] = "strict"
        return True, details

    if kld7_angle.confidence < _MIN_VERTICAL_LOW_CONFIDENCE_RADAR_CONFIDENCE:
        details["selection_reason"] = "low_confidence"
        return False, details

    if guard_details.get("skipped"):
        details["selection_reason"] = "soft_guard_unavailable"
        return False, details

    lane_min, lane_max = _vertical_soft_launch_lane_deg(shot.club)
    details["soft_lane_min_deg"] = lane_min
    details["soft_lane_max_deg"] = lane_max
    if radar_angle_deg < lane_min or radar_angle_deg > lane_max:
        details["selection_reason"] = "outside_soft_lane"
        return False, details

    delta_deg = guard_details.get("delta_deg")
    if delta_deg is None or delta_deg > _VERTICAL_SOFT_ESTIMATE_DELTA_DEG:
        details["selection_reason"] = "estimator_delta_too_large"
        return False, details

    if kld7_angle.num_frames <= 0:
        details["selection_reason"] = "no_candidate_frames"
        return False, details

    if (
        kld7_angle.num_frames > _VERTICAL_SOFT_MAX_FRAME_COUNT
        and delta_deg > _VERTICAL_SOFT_TIGHT_DELTA_FOR_LONG_FRAME_DEG
    ):
        details["selection_reason"] = "suspicious_frame_span"
        return False, details

    details["accepted"] = True
    if kld7_angle.confidence >= _MIN_VERTICAL_SOFT_RADAR_CONFIDENCE:
        details["selection_reason"] = "soft_accept"
        details["acceptance_path"] = "soft"
    else:
        details["selection_reason"] = "low_confidence_accept"
        details["acceptance_path"] = "low_confidence"
    return True, details


def _select_horizontal_radar_launch(kld7_angle, horizontal_limit: float) -> tuple[bool, dict]:
    """Decide whether a horizontal K-LD7 candidate should set the shot angle."""
    soft_limit = min(_HORIZONTAL_SOFT_ANGLE_LIMIT_DEG, max(horizontal_limit, 0.0))
    details = {
        "accepted": False,
        "selection_reason": "no_candidate",
        "acceptance_path": None,
        "horizontal_limit_deg": horizontal_limit,
        "strict_min_confidence": _MIN_HORIZONTAL_RADAR_CONFIDENCE,
        "soft_min_confidence": _MIN_HORIZONTAL_SOFT_RADAR_CONFIDENCE,
        "soft_angle_limit_deg": soft_limit,
        "soft_max_frame_count": _HORIZONTAL_SOFT_MAX_FRAME_COUNT,
        "near_limit_min_confidence": _HORIZONTAL_NEAR_LIMIT_MIN_CONFIDENCE,
        "near_limit_max_frame_count": _HORIZONTAL_NEAR_LIMIT_MAX_FRAMES,
    }
    if not kld7_angle or kld7_angle.horizontal_deg is None:
        return False, details

    abs_angle = abs(kld7_angle.horizontal_deg)
    if abs_angle > horizontal_limit:
        details["selection_reason"] = "outside_horizontal_limit"
        return False, details

    near_limit_angle = horizontal_limit * _HORIZONTAL_NEAR_LIMIT_FRACTION
    if (
        abs_angle >= near_limit_angle
        and kld7_angle.num_frames <= _HORIZONTAL_NEAR_LIMIT_MAX_FRAMES
        and kld7_angle.confidence < _HORIZONTAL_NEAR_LIMIT_MIN_CONFIDENCE
    ):
        details["selection_reason"] = "weak_near_limit"
        details["near_limit_angle_deg"] = round(near_limit_angle, 1)
        return False, details

    if kld7_angle.confidence >= _MIN_HORIZONTAL_RADAR_CONFIDENCE:
        details["accepted"] = True
        details["selection_reason"] = "strict_accept"
        details["acceptance_path"] = "strict"
        return True, details

    if kld7_angle.confidence < _MIN_HORIZONTAL_SOFT_RADAR_CONFIDENCE:
        details["selection_reason"] = "low_confidence"
        return False, details

    if abs_angle > soft_limit:
        details["selection_reason"] = "outside_soft_lane"
        return False, details

    if kld7_angle.num_frames <= 0:
        details["selection_reason"] = "no_candidate_frames"
        return False, details

    if kld7_angle.num_frames > _HORIZONTAL_SOFT_MAX_FRAME_COUNT:
        details["selection_reason"] = "suspicious_frame_span"
        return False, details

    details["accepted"] = True
    details["selection_reason"] = "soft_accept"
    details["acceptance_path"] = "soft"
    return True, details


def _ensure_user_facing_launch_angles(shot: Shot) -> None:
    """Guarantee emitted shots have launch angles without overwriting measurements."""
    estimated: tuple[float, float] | None = None

    if shot.launch_angle_vertical is None:
        estimated = estimate_launch_angle(
            shot.club,
            shot.ball_speed_mph,
            club_speed_mph=shot.club_speed_mph,
            spin_rpm=shot.spin_rpm,
        )
        shot.launch_angle_vertical = estimated[0]
        shot.launch_angle_confidence = estimated[1]
        shot.launch_angle_vertical_confidence = estimated[1]
        shot.launch_angle_vertical_source = "estimated"
        shot.angle_source = "estimated"
        logger.info(
            "[SERVER] Angle source: estimated (%.1f°, conf=%.0f%%)",
            estimated[0],
            estimated[1] * 100,
        )

    if shot.launch_angle_horizontal is None:
        shot.launch_angle_horizontal = 0.0
        if shot.launch_angle_confidence is None:
            if estimated is None:
                estimated = estimate_launch_angle(
                    shot.club,
                    shot.ball_speed_mph,
                    club_speed_mph=shot.club_speed_mph,
                    spin_rpm=shot.spin_rpm,
                )
            shot.launch_angle_confidence = estimated[1]
        if shot.launch_angle_horizontal_confidence is None:
            if estimated is None:
                estimated = estimate_launch_angle(
                    shot.club,
                    shot.ball_speed_mph,
                    club_speed_mph=shot.club_speed_mph,
                    spin_rpm=shot.spin_rpm,
                )
            shot.launch_angle_horizontal_confidence = estimated[1]
        shot.launch_angle_horizontal_source = "estimated"
        if shot.angle_source is None:
            shot.angle_source = "estimated"
        logger.info("[SERVER] Horizontal angle source: neutral estimate (0.0°)")


# K-LD7 produces ~34 RADC frames/sec at 3 Mbaud. With buffer_seconds=6
# the steady-state buffer is ~204 frames. If the snapshot at shot time
# is dramatically less than that, the radar's stream rate dropped.
# Surface as WARN so cabling/USB issues are visible without a replay.
_KLD7_FRAME_HZ = 34.0
_KLD7_BUFFER_SECONDS = 6.0
_KLD7_BUFFER_UNDERFILL_FRAC = 0.5
_KLD7_POST_SHOT_CAPTURE_DELAY_S = 0.18
_MIN_VERTICAL_RADAR_CONFIDENCE = 0.80
_MIN_VERTICAL_SOFT_RADAR_CONFIDENCE = 0.68
_MIN_VERTICAL_LOW_CONFIDENCE_RADAR_CONFIDENCE = 0.65
_VERTICAL_SOFT_ESTIMATE_DELTA_DEG = 4.5
_VERTICAL_SOFT_MAX_FRAME_COUNT = 40
_VERTICAL_SOFT_TIGHT_DELTA_FOR_LONG_FRAME_DEG = 2.0
_MIN_HORIZONTAL_RADAR_CONFIDENCE = 0.40
_MIN_HORIZONTAL_SOFT_RADAR_CONFIDENCE = 0.30
_HORIZONTAL_SOFT_ANGLE_LIMIT_DEG = 5.0
_HORIZONTAL_SOFT_MAX_FRAME_COUNT = 40
_HORIZONTAL_NEAR_LIMIT_FRACTION = 0.80
_HORIZONTAL_NEAR_LIMIT_MAX_FRAMES = 2
_HORIZONTAL_NEAR_LIMIT_MIN_CONFIDENCE = 0.80


def _maybe_wait_for_kld7_post_shot_frames(shot_timestamp: float) -> None:
    """Let the K-LD7 stream collect post-impact RADC frames for extraction.

    TrackMan test logs showed immediate snapshots ending at or just before
    the OPS impact timestamp, leaving the configured post-shot extraction
    window empty. Wait only until the bounded target time; if processing is
    already past that point, this adds no latency.
    """
    target_time = shot_timestamp + _KLD7_POST_SHOT_CAPTURE_DELAY_S
    delay_s = target_time - time.time()
    if delay_s <= 0:
        return
    logger.info(
        "[SERVER] Waiting %.0fms for post-impact K-LD7 RADC frames",
        delay_s * 1000.0,
    )
    time.sleep(delay_s)


def _warn_if_kld7_buffer_underfilled(orientation: str, frame_count: int) -> None:
    """Log a WARNING when the K-LD7 ring-buffer snapshot is far below
    the expected steady-state size at shot time.
    """
    expected = int(_KLD7_FRAME_HZ * _KLD7_BUFFER_SECONDS)
    if expected <= 0 or frame_count <= 0:
        return
    if frame_count < expected * _KLD7_BUFFER_UNDERFILL_FRAC:
        logger.warning(
            "[SERVER] K-LD7 %s buffer underfilled: %d/%d frames (%.0f%%) — "
            "stream rate dropped, check USB cabling and contention.",
            orientation,
            frame_count,
            expected,
            100.0 * frame_count / expected,
        )


def _warn_if_kld7_raw_payload_missing(
    orientation: str,
    buffer_frames: list,
    *,
    raw_payload_expected: bool,
) -> None:
    """Log a WARNING when experimental replay logging lacks raw RADC bytes."""
    if not raw_payload_expected or not buffer_frames:
        return

    radc_frames = sum(
        1 for frame in buffer_frames if frame.get("has_radc") or frame.get("radc_b64")
    )
    if radc_frames == 0:
        logger.warning(
            "[SERVER] K-LD7 %s raw RADC replay payload missing: buffer has no RADC frames. "
            "TrackMan replay will fail; verify RADC streaming.",
            orientation,
        )
        return

    payload_frames = sum(1 for frame in buffer_frames if frame.get("radc_b64"))
    if payload_frames == radc_frames:
        invalid_payload_frames = sum(
            1
            for frame in buffer_frames
            if frame.get("radc_b64") and frame.get("radc_payload_valid") is False
        )
        if invalid_payload_frames:
            logger.warning(
                "[SERVER] K-LD7 %s raw RADC replay payload invalid: %d/%d payloads "
                "have the wrong byte length. TrackMan replay will fail for those frames.",
                orientation,
                invalid_payload_frames,
                payload_frames,
            )
        return

    if payload_frames == 0:
        logger.warning(
            "[SERVER] K-LD7 %s raw RADC replay payload missing: 0/%d RADC frames have radc_b64. "
            "TrackMan replay will fail; verify RADC streaming and raw payload logging.",
            orientation,
            radc_frames,
        )
        return

    logger.warning(
        "[SERVER] K-LD7 %s raw RADC replay payload incomplete: %d/%d RADC frames have radc_b64. "
        "TrackMan replay may fail for some shots.",
        orientation,
        payload_frames,
        radc_frames,
    )


def _warn_if_kld7_snapshot_lacks_post_shot_frames(
    orientation: str,
    buffer_frames: list,
    shot_timestamp: float,
    *,
    raw_payload_expected: bool,
) -> None:
    """Warn when a TrackMan replay snapshot cannot contain post-impact ball frames."""
    if not raw_payload_expected or not buffer_frames:
        return
    post_shot_frames = [
        frame
        for frame in buffer_frames
        if frame.get("timestamp") is not None and float(frame["timestamp"]) > shot_timestamp
    ]
    if post_shot_frames:
        return
    logger.warning(
        "[SERVER] K-LD7 %s snapshot has no frames after shot timestamp %.3f; "
        "angle replay may be using pre-impact clutter.",
        orientation,
        shot_timestamp,
    )


def _kld7_angle_log_payload(
    angle,
    axis_field: str,
    selection_details: Optional[dict] = None,
) -> Optional[dict]:
    """Build the compact K-LD7 angle payload used in session logs."""
    if angle is None:
        return None

    payload = {
        axis_field: getattr(angle, axis_field),
        "confidence": angle.confidence,
        "detection_class": angle.detection_class,
        "magnitude": angle.magnitude,
        "num_frames": angle.num_frames,
        "frames_examined": angle.frames_examined,
        "frames_available": angle.frames_available,
        "frames_ignored_stale": angle.frames_ignored_stale,
    }
    radc_selection = getattr(angle, "radc_selection", None)
    if radc_selection:
        payload["radc_selection"] = radc_selection
    if selection_details:
        payload.update(selection_details)
    return payload


def _experimental_kld7_raw_radc_logging_enabled() -> bool:
    """Return whether K-LD7 buffers should include raw RADC payloads."""
    return experimental_kld7_raw_radc_logging or experimental_kld7_radc_tuning


def _kld7_radc_tuning_kwargs(args) -> dict:
    """Return K-LD7 RADC extraction parameters for startup.

    The experimental CLI knobs are intentionally ignored unless the
    dedicated experiment gate is enabled. This keeps default/prod startup
    behavior stable even if stale args are passed through a shell wrapper.
    """
    if not getattr(args, "experimental_kld7_radc_tuning", False):
        return dict(_DEFAULT_KLD7_RADC_TUNING)

    return {
        "radc_speed_tolerance_mph": args.experimental_kld7_speed_tolerance,
        "radc_centroid_floor_frac": args.experimental_kld7_centroid_floor,
        "radc_spectrum_source": args.experimental_kld7_spectrum_source,
        "radc_ops_bin_outlier_tol": args.experimental_kld7_ops_bin_tol,
        "radc_ops_bin_outlier_penalty": args.experimental_kld7_ops_bin_penalty,
        "radc_ops_anchored_peak_min_snr": args.experimental_kld7_ops_anchored_min_snr,
        "radc_vertical_impact_energy_threshold": (args.experimental_kld7_vertical_impact_energy),
        "radc_horizontal_impact_energy_threshold": (
            args.experimental_kld7_horizontal_impact_energy
        ),
        "radc_horizontal_retry_impact_energy_threshold": (
            args.experimental_kld7_horizontal_retry_impact_energy
        ),
        "radc_horizontal_angle_limit_deg": args.experimental_kld7_horizontal_angle_limit,
    }


def _session_start_config() -> dict:
    """Return session-start config including experimental K-LD7 provenance."""
    config = radar_config.copy()
    config["kld7_experiments"] = {
        "trackman_calibration_enabled": False,
        "trackman_calibration_model": None,
        "raw_radc_payload_logging_enabled": _experimental_kld7_raw_radc_logging_enabled(),
        "raw_radc_payload_logging_requested": experimental_kld7_raw_radc_logging,
        "radc_tuning_enabled": experimental_kld7_radc_tuning,
        "radc_tuning_params": dict(active_kld7_radc_tuning),
    }
    return config


ball_speed_correction_enabled = False
ball_speed_correction_distance_ft = 5.5
ball_speed_correction_ball_above_radar_ft = -4.0 / 12.0
calculated_spin_enabled = False


def shot_to_dict(shot: Shot) -> dict:
    """Convert Shot to JSON-serializable dict."""
    return {
        "ball_speed_mph": round(shot.ball_speed_mph, 1),
        "ball_speed_raw_mph": (
            round(shot.ball_speed_raw_mph, 1) if shot.ball_speed_raw_mph else None
        ),
        "club_speed_mph": round(shot.club_speed_mph, 1) if shot.club_speed_mph else None,
        "smash_factor": round(shot.smash_factor, 2) if shot.smash_factor else None,
        "estimated_carry_yards": round(shot.estimated_carry_yards),
        "carry_range": [
            round(shot.estimated_carry_range[0]),
            round(shot.estimated_carry_range[1]),
        ],
        "club": shot.club.value,
        "timestamp": shot.timestamp.isoformat(),
        "peak_magnitude": shot.peak_magnitude,
        # Launch angle data
        "launch_angle_vertical": shot.launch_angle_vertical,
        "launch_angle_horizontal": shot.launch_angle_horizontal,
        "launch_angle_confidence": shot.launch_angle_confidence,
        "launch_angle_vertical_confidence": shot.launch_angle_vertical_confidence,
        "launch_angle_horizontal_confidence": shot.launch_angle_horizontal_confidence,
        "launch_angle_vertical_source": shot.launch_angle_vertical_source,
        "launch_angle_horizontal_source": shot.launch_angle_horizontal_source,
        "angle_source": shot.angle_source,
        "club_angle_deg": shot.club_angle_deg,
        "club_path_deg": shot.club_path_deg,
        "spin_axis_deg": shot.spin_axis_deg,
        # Spin data from rolling buffer mode
        "spin_rpm": round(shot.spin_rpm) if shot.spin_rpm else None,
        "spin_rpm_measured": (
            round(shot.spin_rpm_measured) if shot.spin_rpm_measured else None
        ),
        "spin_source": shot.spin_source,
        "spin_confidence": round(shot.spin_confidence, 2) if shot.spin_confidence else None,
        "spin_quality": shot.spin_quality,
        "spin_snr": round(shot.spin_snr, 2) if shot.spin_snr is not None else None,
        "spin_modulation_depth": (
            round(shot.spin_modulation_depth, 4) if shot.spin_modulation_depth is not None else None
        ),
        "spin_peak_freq_hz": (
            round(shot.spin_peak_freq_hz, 2) if shot.spin_peak_freq_hz is not None else None
        ),
        "spin_candidate_rpm": (
            round(shot.spin_peak_freq_hz * 60) if shot.spin_peak_freq_hz is not None else None
        ),
        "spin_seam_cycles": (
            round(shot.spin_seam_cycles, 2) if shot.spin_seam_cycles is not None else None
        ),
        "spin_at_lower_rail": shot.spin_at_lower_rail,
        "spin_at_upper_rail": shot.spin_at_upper_rail,
        "spin_candidates": shot.spin_candidates,
        "spin_phase_method": shot.spin_phase_method,
        "spin_phase_rpm": round(shot.spin_phase_rpm) if shot.spin_phase_rpm else None,
        "spin_phase_snr": (
            round(shot.spin_phase_snr, 2) if shot.spin_phase_snr is not None else None
        ),
        "spin_phase_agreement_pct": (
            round(shot.spin_phase_agreement_pct, 1)
            if shot.spin_phase_agreement_pct is not None
            else None
        ),
        "spin_phase_confirmed": shot.spin_phase_confirmed,
        "spin_rejection_reason": shot.spin_rejection_reason,
        "carry_spin_adjusted": round(shot.carry_spin_adjusted)
        if shot.carry_spin_adjusted
        else None,
    }


@app.route("/")
def index():
    """Serve the React app."""
    return send_from_directory(_react_app_dir(), "index.html")


@app.route("/display", strict_slashes=False)
def display():
    """Serve the React app for TV display mode."""
    return send_from_directory(_react_app_dir(), "index.html")


@app.route("/<path:path>")
def static_files(path):
    """Serve static files."""
    return send_from_directory(app.static_folder, path)


@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    """Cleanly shut down the server via REST API."""
    logger.info("[SERVER] Shutdown requested via REST API")
    threading.Thread(target=_shutdown_process_after_delay, daemon=True).start()
    return {"status": "shutting_down"}, 200


# Camera functions
def init_camera(
    model_path: str = None,
    roboflow_model_id: str = None,
    roboflow_api_key: str = None,
    imgsz: int = 256,
    use_hough: bool = True,  # Default to Hough detection
    hough_param2: int = 33,
    hough_param1: int = 48,
    hough_min_radius: int = 4,
    hough_max_radius: int = 43,
    hough_min_dist: int = 266,
):
    """Initialize camera and ball tracker (Hough, YOLO, or Roboflow)."""
    global camera, camera_tracker, camera_enabled  # pylint: disable=global-statement

    if not CV2_AVAILABLE:
        print("OpenCV not available - camera disabled")
        return False

    if not PICAMERA_AVAILABLE:
        print("picamera2 not available - camera disabled")
        return False

    try:
        # Initialize PiCamera with optimized settings for speed
        camera = Picamera2()
        config = camera.create_video_configuration(
            main={"size": (640, 480), "format": "RGB888"},
            buffer_count=2,  # Balance between latency and stability
            controls={"FrameRate": 60},  # Higher FPS for ball tracking
        )
        camera.configure(config)
        camera.start()
        time.sleep(0.5)

        # Initialize tracker - default to Hough + ByteTrack
        if roboflow_model_id:
            camera_tracker = CameraTracker(
                roboflow_model_id=roboflow_model_id,
                roboflow_api_key=roboflow_api_key,
                imgsz=imgsz,
                use_hough=False,
            )
        elif not use_hough and model_path and os.path.exists(model_path):
            camera_tracker = CameraTracker(
                model_path=model_path,
                imgsz=imgsz,
                use_hough=False,
            )
        else:
            camera_tracker = CameraTracker(
                use_hough=True,
                hough_param2=hough_param2,
                hough_param1=hough_param1,
                hough_min_radius=hough_min_radius,
                hough_max_radius=hough_max_radius,
                hough_min_dist=hough_min_dist,
            )

        # Auto-enable camera when initialized
        camera_enabled = True
        return True

    except Exception as e:
        print(f"Failed to initialize camera: {e}")
        camera = None
        camera_tracker = None
        return False


def init_kld7(
    port=None,
    orientation="vertical",
    angle_offset_deg=0.0,
    base_freq=0,
    radc_speed_tolerance_mph=10.0,
    radc_centroid_floor_frac=0.5,
    radc_spectrum_source="f1a",
    radc_ops_bin_outlier_tol=25,
    radc_ops_bin_outlier_penalty=10.0,
    radc_ops_anchored_peak_min_snr=5.0,
    radc_vertical_impact_energy_threshold=3.0,
    radc_horizontal_impact_energy_threshold=1.85,
    radc_horizontal_retry_impact_energy_threshold=0.5,
    radc_horizontal_angle_limit_deg=15.0,
    vertical_estimator="naive",
    mount_tilt_deg=18.0,
    ball_distance_ft=5.5,
) -> bool:
    """Initialize a single K-LD7 angle radar tracker.

    Returns True if the tracker connected and started successfully.
    Sets the appropriate global (kld7_vertical or kld7_horizontal).
    """
    global kld7_vertical, kld7_horizontal  # pylint: disable=global-statement
    try:
        from openflight.kld7 import KLD7Tracker

        tracker = KLD7Tracker(
            port=port,
            orientation=orientation,
            angle_offset_deg=angle_offset_deg,
            base_freq=base_freq,
            buffer_seconds=6.0,
            radc_speed_tolerance_mph=radc_speed_tolerance_mph,
            radc_centroid_floor_frac=radc_centroid_floor_frac,
            radc_spectrum_source=radc_spectrum_source,
            radc_ops_bin_outlier_tol=radc_ops_bin_outlier_tol,
            radc_ops_bin_outlier_penalty=radc_ops_bin_outlier_penalty,
            radc_ops_anchored_peak_min_snr=radc_ops_anchored_peak_min_snr,
            radc_vertical_impact_energy_threshold=radc_vertical_impact_energy_threshold,
            radc_horizontal_impact_energy_threshold=(radc_horizontal_impact_energy_threshold),
            radc_horizontal_retry_impact_energy_threshold=(
                radc_horizontal_retry_impact_energy_threshold
            ),
            radc_horizontal_angle_limit_deg=radc_horizontal_angle_limit_deg,
            vertical_estimator=vertical_estimator,
            mount_tilt_deg=mount_tilt_deg,
            ball_distance_ft=ball_distance_ft,
        )
        if tracker.connect():
            tracker.start()
            logger.info(
                "[SERVER] K-LD7 %s initialized (port=%s, offset=%.1f°, RBFR=%d)",
                orientation,
                port or "auto",
                angle_offset_deg,
                base_freq,
            )
            session_log = get_session_logger()
            if session_log:
                session_log.log_connection(
                    device="kld7_%s" % orientation,
                    port=tracker.port or "auto",
                    baud=3000000,
                    radc_available=True,
                    base_freq=base_freq,
                )
            if orientation == "vertical":
                kld7_vertical = tracker
            else:
                kld7_horizontal = tracker
            return True
        else:
            return False
    except Exception as e:
        logger.warning("[SERVER] K-LD7 %s initialization failed: %s", orientation, e, exc_info=True)
        log_session_error(
            "K-LD7 initialization failed",
            component="kld7",
            context={"orientation": orientation},
            exc=e,
        )
        return False


def camera_processing_loop():
    """Background thread for camera processing."""
    global ball_detected, ball_detection_confidence, latest_frame  # pylint: disable=global-statement

    while not camera_stop_event.is_set():
        if not camera or not camera_enabled:
            time.sleep(0.1)
            continue

        try:
            frame = camera.capture_array()

            # Run detection if tracker available
            if camera_tracker:
                detection = camera_tracker.process_frame(frame)
                new_detected = detection is not None
                new_confidence = detection.confidence if detection else 0.0

                # Emit update if state changed
                if (
                    new_detected != ball_detected
                    or abs(new_confidence - ball_detection_confidence) > 0.05
                ):
                    ball_detected = new_detected
                    ball_detection_confidence = new_confidence
                    socketio.emit(
                        "ball_detection",
                        {
                            "detected": ball_detected,
                            "confidence": round(ball_detection_confidence, 2),
                        },
                    )

                # Get debug frame with overlay if streaming
                if camera_streaming:
                    frame = camera_tracker.get_debug_frame(frame)

            # Encode frame for streaming
            if camera_streaming:
                # Convert RGB to BGR for cv2
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                _, jpeg = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 70])
                with frame_lock:
                    latest_frame = jpeg.tobytes()

        except Exception as e:
            print(f"Camera processing error: {e}")
            time.sleep(0.1)


def start_camera_thread():
    """Start the camera processing thread."""
    global camera_thread, camera_stop_event  # pylint: disable=global-statement

    if camera_thread and camera_thread.is_alive():
        return

    camera_stop_event = threading.Event()
    camera_thread = threading.Thread(target=camera_processing_loop, daemon=True)
    camera_thread.start()
    print("Camera processing thread started")


def stop_camera_thread():
    """Stop the camera processing thread."""
    global camera_thread, camera_stop_event  # pylint: disable=global-statement

    if camera_stop_event:
        camera_stop_event.set()
    if camera_thread:
        camera_thread.join(timeout=2.0)
        camera_thread = None


def generate_mjpeg():
    """Generator for MJPEG stream."""
    while True:
        if not camera_streaming:
            break

        with frame_lock:
            frame = latest_frame

        if frame:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        else:
            time.sleep(0.03)


@app.route("/camera/stream")
def camera_stream():
    """MJPEG stream endpoint."""
    if not camera_enabled or not camera_streaming:
        return "Camera not available", 503

    return Response(generate_mjpeg(), mimetype="multipart/x-mixed-replace; boundary=frame")


@socketio.on("toggle_camera")
def handle_toggle_camera():
    """Toggle camera on/off."""
    global camera_enabled  # pylint: disable=global-statement

    if not camera:
        socketio.emit(
            "camera_status",
            {"enabled": False, "available": False, "error": "Camera not initialized"},
        )
        return

    camera_enabled = not camera_enabled
    socketio.emit(
        "camera_status",
        {
            "enabled": camera_enabled,
            "available": True,
            "streaming": camera_streaming,
        },
    )
    print(f"Camera {'enabled' if camera_enabled else 'disabled'}")


@socketio.on("toggle_camera_stream")
def handle_toggle_camera_stream():
    """Toggle camera streaming on/off."""
    global camera_streaming  # pylint: disable=global-statement

    if not camera or not camera_enabled:
        socketio.emit(
            "camera_status",
            {
                "enabled": camera_enabled,
                "available": camera is not None,
                "streaming": False,
                "error": "Camera not enabled",
            },
        )
        return

    camera_streaming = not camera_streaming
    socketio.emit(
        "camera_status",
        {
            "enabled": camera_enabled,
            "available": True,
            "streaming": camera_streaming,
        },
    )
    print(f"Camera streaming {'started' if camera_streaming else 'stopped'}")


@socketio.on("get_camera_status")
def handle_get_camera_status():
    """Get current camera status."""
    socketio.emit(
        "camera_status",
        {
            "enabled": camera_enabled,
            "available": camera is not None,
            "streaming": camera_streaming,
            "ball_detected": ball_detected,
            "ball_confidence": round(ball_detection_confidence, 2),
        },
    )


def start_debug_logging():
    """Start logging raw readings to a file."""
    global debug_log_file, debug_log_path  # pylint: disable=global-statement

    # Create logs directory
    log_dir = Path.home() / "openflight_logs"
    log_dir.mkdir(exist_ok=True)

    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_log_path = log_dir / f"debug_{timestamp}.jsonl"
    debug_log_file = open(debug_log_path, "w")  # pylint: disable=consider-using-with

    # Enable radar raw logging
    radar_logger = logging.getLogger("ops243")
    radar_raw_logger = logging.getLogger("ops243.raw")
    radar_logger.setLevel(logging.DEBUG)
    radar_raw_logger.setLevel(logging.DEBUG)

    # Add file handler for raw radar data
    raw_log_path = log_dir / f"radar_raw_{timestamp}.log"
    file_handler = logging.FileHandler(raw_log_path)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    radar_raw_logger.addHandler(file_handler)
    radar_logger.addHandler(file_handler)

    print(f"Debug logging to: {debug_log_path}")
    print(f"Raw radar logging to: {raw_log_path}")
    return str(debug_log_path)


def stop_debug_logging():
    """Stop logging and close the file."""
    global debug_log_file, debug_log_path  # pylint: disable=global-statement

    if debug_log_file:
        debug_log_file.close()
        debug_log_file = None
        print(f"Debug log saved: {debug_log_path}")


def log_debug_reading(reading: SpeedReading):
    """Log a raw reading to the debug file."""
    if debug_log_file:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "type": "reading",
            "speed": reading.speed,
            "direction": reading.direction.value,
            "magnitude": reading.magnitude,
            "unit": reading.unit,
        }
        debug_log_file.write(json.dumps(entry) + "\n")
        debug_log_file.flush()

        # Also print to console for immediate feedback
        print(
            f"[RADAR] {reading.speed:.1f} mph {reading.direction.value} (mag={reading.magnitude})"
        )


def on_live_reading(reading: SpeedReading):
    """Callback for live radar readings - used in debug mode."""
    # Log ALL readings first (before filtering) so we can debug direction issues
    if debug_mode:
        log_debug_reading(reading)

        # Emit ALL readings to UI debug panel (including inbound)
        socketio.emit(
            "debug_reading",
            {
                "speed": reading.speed,
                "direction": reading.direction.value,
                "magnitude": reading.magnitude,
                "timestamp": datetime.now().isoformat(),
                "filtered": reading.direction != Direction.OUTBOUND,
            },
        )

    # Filter out inbound readings for shot detection
    # Note: shot filtering happens in launch_monitor.py but we also filter here
    # for any UI purposes that need only outbound readings
    if reading.direction != Direction.OUTBOUND:
        return


def _get_trigger_status() -> dict:
    """Build trigger status payload for the UI."""
    from .rolling_buffer import RollingBufferMonitor  # pylint: disable=import-outside-toplevel

    is_rolling_buffer = isinstance(monitor, RollingBufferMonitor)
    session_logger = get_session_logger()
    stats = session_logger.stats if session_logger else {}

    mode = "mock" if mock_mode else "rolling-buffer"
    trigger_type = None
    radar_port = None

    if is_rolling_buffer:
        trigger_type = monitor.trigger_type
        if hasattr(monitor, "radar") and hasattr(monitor.radar, "port"):
            radar_port = monitor.radar.port

    return {
        "mode": mode,
        "trigger_type": trigger_type,
        "radar_connected": monitor is not None and not mock_mode,
        "radar_port": radar_port,
        "triggers_total": stats.get("triggers_total", 0),
        "triggers_accepted": stats.get("triggers_accepted", 0),
        "triggers_rejected": stats.get("triggers_rejected", 0),
    }


@socketio.on("connect")
def handle_connect():
    """Handle client connection."""
    print("Client connected")
    if monitor:
        stats = monitor.get_session_stats()
        shots = [shot_to_dict(s) for s in monitor.get_shots()]
        socketio.emit(
            "session_state",
            {
                "stats": stats,
                "shots": shots,
                "mock_mode": mock_mode,
                "debug_mode": debug_mode,
                "camera_available": camera is not None,
                "camera_enabled": camera_enabled,
                "camera_streaming": camera_streaming,
                "ball_detected": ball_detected,
            },
        )
        socketio.emit("trigger_status", _get_trigger_status())


@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection."""
    print("Client disconnected")


@socketio.on("get_trigger_status")
def handle_get_trigger_status():
    """Get current trigger/mode status for debug UI."""
    socketio.emit("trigger_status", _get_trigger_status())


@socketio.on("set_club")
def handle_set_club(data):
    """Handle club selection change."""
    club_name = data.get("club", "driver")
    try:
        club = ClubType(club_name)
        if monitor:
            monitor.set_club(club)
        socketio.emit("club_changed", {"club": club.value})
    except ValueError:
        pass


@socketio.on("clear_session")
def handle_clear_session():
    """Clear all recorded shots."""
    if monitor:
        monitor.clear_session()
        socketio.emit("session_cleared")


@socketio.on("get_session")
def handle_get_session():
    """Get current session data."""
    if monitor:
        stats = monitor.get_session_stats()
        shots = [shot_to_dict(s) for s in monitor.get_shots()]
        socketio.emit("session_state", {"stats": stats, "shots": shots})


@socketio.on("simulate_shot")
def handle_simulate_shot():
    """Simulate a shot (only works in mock mode)."""
    if monitor and isinstance(monitor, MockLaunchMonitor):
        monitor.simulate_shot()


@socketio.on("toggle_debug")
def handle_toggle_debug():
    """Toggle debug mode on/off."""
    global debug_mode  # pylint: disable=global-statement

    debug_mode = not debug_mode

    if debug_mode:
        log_path = start_debug_logging()
        socketio.emit("debug_toggled", {"enabled": True, "log_path": log_path})
        print("Debug mode ENABLED")
    else:
        stop_debug_logging()
        socketio.emit("debug_toggled", {"enabled": False})
        print("Debug mode DISABLED")


@socketio.on("get_debug_status")
def handle_get_debug_status():
    """Get current debug mode status."""
    socketio.emit(
        "debug_status",
        {
            "enabled": debug_mode,
            "log_path": str(debug_log_path) if debug_log_path else None,
        },
    )


# Radar tuning state
radar_config = {
    "min_speed": 10,
    "max_speed": 220,
    "min_magnitude": 0,
    "transmit_power": 0,
}


@socketio.on("get_radar_config")
def handle_get_radar_config():
    """Get current radar configuration."""
    socketio.emit("radar_config", radar_config)


@socketio.on("set_radar_config")
def handle_set_radar_config(data):
    """Update radar configuration."""
    global radar_config  # pylint: disable=global-statement

    if not monitor or mock_mode:
        log_session_error(
            "Radar config update rejected: radar not connected",
            component="server",
            context={"stage": "set_radar_config", "mock_mode": mock_mode},
        )
        socketio.emit("radar_config_error", {"error": "Radar not connected"})
        return

    try:
        # Update min speed filter
        if "min_speed" in data:
            new_min = int(data["min_speed"])
            monitor.radar.set_min_speed_filter(new_min)
            radar_config["min_speed"] = new_min
            print(f"Set min speed filter: {new_min} mph")

        # Update max speed filter
        if "max_speed" in data:
            new_max = int(data["max_speed"])
            monitor.radar.set_max_speed_filter(new_max)
            radar_config["max_speed"] = new_max
            print(f"Set max speed filter: {new_max} mph")

        # Update magnitude filter
        if "min_magnitude" in data:
            new_mag = int(data["min_magnitude"])
            monitor.radar.set_magnitude_filter(min_mag=new_mag)
            radar_config["min_magnitude"] = new_mag
            print(f"Set min magnitude filter: {new_mag}")

        # Update transmit power (0=max, 7=min)
        if "transmit_power" in data:
            new_power = int(data["transmit_power"])
            if 0 <= new_power <= 7:
                monitor.radar.set_transmit_power(new_power)
                radar_config["transmit_power"] = new_power
                print(f"Set transmit power: {new_power}")

        # Log config change
        session_logger = get_session_logger()
        if session_logger:
            session_logger.log_config_change(radar_config.copy(), source="user")

        # Legacy debug logging
        if debug_mode and debug_log_file:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "type": "config_change",
                "config": radar_config.copy(),
            }
            debug_log_file.write(json.dumps(entry) + "\n")
            debug_log_file.flush()

        socketio.emit("radar_config", radar_config)

    except Exception as e:
        logger.warning("[SERVER] Error setting radar config: %s", e, exc_info=True)
        log_session_error(
            "Radar config update failed",
            component="server",
            context={"stage": "set_radar_config", "requested": data},
            exc=e,
        )
        socketio.emit("radar_config_error", {"error": str(e)})


@socketio.on("shutdown")
def handle_shutdown():
    """Cleanly shut down the server and all hardware."""
    logger.info("[SERVER] Shutdown requested from UI (WebSocket)")
    socketio.emit("shutdown_ack", {"message": "Shutting down..."})
    threading.Thread(target=_shutdown_process_after_delay, daemon=True).start()


def _forward_shot_to_simulators(shot: Shot) -> None:
    """Resolve a shot once and fan it out to every connected simulator.

    The shot pipeline is untouched: this is called after the UI emit and never
    raises into it. A shot number is only allocated when at least one connector
    is connected, so the sequence doesn't drift while sims are offline.
    """
    if not any(c.is_connected() for c in sim_connectors):
        return
    try:
        resolved = resolve_shot(shot, sim_player_state)
    except IncompleteShotError as e:
        logger.warning("[sim] shot not sendable: %s", e)
        socketio.emit("sim_shot_dropped", {"reason": str(e)})
        return

    values = resolved.as_values()
    for connector in sim_connectors:
        if not connector.is_connected():
            continue
        try:
            # Sends are synchronous on this thread, in connector order. Local sims
            # (the only target today) ack in microseconds; if a remote or laggy sim
            # is ever added, move this behind a per-connector send queue so one slow
            # sim can't stall delivery to the others (PR #115 review #2).
            connector.send_shot(resolved)
        except OSError as e:
            logger.warning("[sim] %s send failed: %s", connector.name, e)
            socketio.emit("sim_send_failed", {"target": connector.name, "reason": str(e)})
            continue
        sl = get_session_logger()
        if sl:
            sl.log_sim_send(
                target=connector.name,
                shot_number=resolved.shot_number,
                provenance=resolved.provenance,
                values=values,
            )
        socketio.emit(
            "sim_shot",
            {
                "target": connector.name,
                "shot_number": resolved.shot_number,
                "fields": connector.codec.fields_for_target(),
                "values": values,
                "provenance": resolved.provenance,
            },
        )
        if debug_mode:
            measured = sum(1 for p in resolved.provenance.values() if p == "measured")
            estimated = len(resolved.provenance) - measured
            logger.info(
                "[sim] → %s shot #%d: ball=%.1f vla=%.1f hla=%.1f spin=%.0f axis=%.1f "
                "carry=%.1f (%dM/%dE)",
                connector.name, resolved.shot_number, resolved.ball_speed_mph,
                resolved.vla, resolved.hla, resolved.total_spin_rpm,
                resolved.spin_axis_deg, resolved.carry_yards, measured, estimated,
            )


def _sim_on_status(target: str, event) -> None:
    """Relay a connector status change to the UI and session log."""
    state = event.state.value
    if state == "connected":
        logger.info("[sim] %s connected (%s:%s)", target, event.host, event.port)
    elif state == "reconnecting":
        logger.info(
            "[sim] %s reconnecting — attempt %s, retry in %.0fs",
            target, event.attempt, event.next_retry_in_s,
        )
    elif state == "error":
        logger.warning("[sim] %s error: %s", target, event.message)
    elif debug_mode:
        logger.info("[sim] %s %s", target, state)
    socketio.emit(
        "sim_status",
        {
            "target": target,
            "state": event.state.value,
            "host": event.host,
            "port": event.port,
            "attempt": event.attempt,
            "next_retry_in_s": event.next_retry_in_s,
            "message": event.message,
        },
    )
    sl = get_session_logger()
    if sl:
        sl.log_sim_status(
            target=target,
            state=event.state.value,
            host=event.host,
            port=event.port,
            message=event.message,
            attempt=event.attempt,
            next_retry_in_s=event.next_retry_in_s,
        )


def _sim_on_inbound(target: str, event) -> None:
    """Apply an inbound simulator event (player/club update, error, ack)."""
    if isinstance(event, PlayerUpdate):
        sim_player_state.apply(event)
        club_value = sim_player_state.club.value
        logger.info("[sim] ← %s player update: club=%s", target, club_value)
        socketio.emit(
            "sim_player",
            {"target": target, "handed": sim_player_state.handed, "club": club_value},
        )
        sl = get_session_logger()
        if sl:
            sl.log_sim_player(
                target=target, handed=sim_player_state.handed, club=club_value
            )
        # The monitor owns current-club state for shot tagging and carry/spin
        # model selection; keep it in sync with the sim's canonical club.
        if monitor is not None:
            try:
                monitor.set_club(sim_player_state.club)
            except Exception:  # pylint: disable=broad-except
                logger.exception("[sim] monitor.set_club failed")
        socketio.emit("club_changed", {"club": club_value})
    elif isinstance(event, SimError):
        logger.warning("[sim] ← %s error: %s", target, event.message)
        socketio.emit("sim_status", {"target": target, "state": "error", "message": event.message})
    elif isinstance(event, ShotAck):
        if not event.ok:
            logger.info("[sim] ← %s rejected shot %s: %s", target, event.shot_number, event.message)
        elif debug_mode:
            logger.info("[sim] ← %s ack: shot %s ok", target, event.shot_number)


def _apply_calculated_spin(shot: Shot) -> bool:
    """Replace radar-measured spin with the kinematic estimate.

    The 24 GHz OPS return carries no usable spin line (see
    spin_estimate.py), so when the vertical launch angle was actually
    measured (radar/camera, not the club-table estimate), spin_rpm is
    rewritten with 170*v*sin(LA)^1.2. The displaced measured value is
    kept in spin_rpm_measured for offline scoring. Returns True when
    the shot was rewritten.
    """
    if shot.launch_angle_vertical is None:
        return False
    if shot.launch_angle_vertical_source not in ("radar", "camera"):
        return False
    spin_calc = calculated_spin_rpm(shot.ball_speed_mph, shot.launch_angle_vertical)
    if spin_calc is None:
        return False
    shot.spin_rpm_measured = shot.spin_rpm
    shot.spin_rpm = spin_calc
    shot.spin_confidence = SPIN_CONFIDENCE_HIGH
    shot.spin_source = "calculated"
    shot.spin_rejection_reason = None
    logger.info(
        "[SERVER] Calculated spin: %.0f rpm (v=%.1f mph, LA=%.1f deg, measured was %s)",
        spin_calc,
        shot.ball_speed_mph,
        shot.launch_angle_vertical,
        "%.0f rpm" % shot.spin_rpm_measured if shot.spin_rpm_measured else "none",
    )
    return True


def on_shot_detected(shot: Shot):
    """Callback when a shot is detected - emit to all clients."""
    global ball_detected, ball_detection_confidence  # pylint: disable=global-statement

    logger.info("[SERVER] Shot callback: %.1f mph", shot.ball_speed_mph)

    kld7_ms = None
    # Process K-LD7 angle radars (vertical = launch angle, horizontal = club path)
    try:
        if shot.mode != "mock":
            kld7_start = time.time()
            shot_ts = shot.impact_timestamp or kld7_start
            session_log = get_session_logger()
            if kld7_vertical or kld7_horizontal:
                _maybe_wait_for_kld7_post_shot_frames(shot_ts)

            # --- Vertical K-LD7 (launch angle) ---
            if kld7_vertical:
                raw_payload_expected = _experimental_kld7_raw_radc_logging_enabled()
                if raw_payload_expected:
                    raw_buffer = kld7_vertical.snapshot_buffer(include_radc_payload=True)
                else:
                    raw_buffer = kld7_vertical.snapshot_buffer()
                _warn_if_kld7_buffer_underfilled("vertical", len(raw_buffer))
                _warn_if_kld7_raw_payload_missing(
                    "vertical",
                    raw_buffer,
                    raw_payload_expected=raw_payload_expected,
                )
                _warn_if_kld7_snapshot_lacks_post_shot_frames(
                    "vertical",
                    raw_buffer,
                    shot_ts,
                    raw_payload_expected=raw_payload_expected,
                )
                kld7_angle = kld7_vertical.get_angle_for_shot(
                    shot_timestamp=shot_ts,
                    ball_speed_mph=shot.ball_speed_mph,
                    impact_timestamp=shot.impact_timestamp_kld7,
                )
                vertical_selection_details = None
                if kld7_angle and kld7_angle.vertical_deg is not None:
                    accepted, vertical_selection_details = _select_vertical_radar_launch(
                        kld7_angle, shot
                    )
                    selection_reason = vertical_selection_details["selection_reason"]
                    if not accepted:
                        logger.warning(
                            "[SERVER] Vertical angle %.1f° rejected: %s "
                            "(expected=%s°, delta=%s°, conf=%.0f%%)",
                            kld7_angle.vertical_deg,
                            selection_reason,
                            vertical_selection_details.get("expected_launch_deg"),
                            vertical_selection_details.get("delta_deg"),
                            kld7_angle.confidence * 100,
                        )
                    else:
                        shot.launch_angle_vertical = kld7_angle.vertical_deg
                        shot.launch_angle_confidence = kld7_angle.confidence
                        shot.launch_angle_vertical_confidence = kld7_angle.confidence
                        shot.launch_angle_vertical_source = "radar"
                        shot.angle_source = "radar"
                        logger.info(
                            "[SERVER] Vertical angle: %.1f° (conf=%.0f%%, %d frames, %s)",
                            kld7_angle.vertical_deg,
                            kld7_angle.confidence * 100,
                            kld7_angle.num_frames,
                            selection_reason,
                        )
                # Club angle of attack (same RADC buffer, club speed from OPS).
                # Compute BEFORE logging the buffer so the log entry can
                # include club_angle alongside ball_angle for offline analysis.
                club_angle_v = None
                if shot.club_speed_mph:
                    club_angle_v = kld7_vertical.get_club_angle(
                        club_speed_mph=shot.club_speed_mph,
                        shot_timestamp=shot_ts,
                    )
                    if club_angle_v and club_angle_v.vertical_deg is not None:
                        # Negate: the radar sees where the club IS (above center = positive),
                        # but AoA is the club's attack direction (descending = negative).
                        candidate_aoa = -club_angle_v.vertical_deg
                        # Reject physically impossible AoA values.
                        # Real AoA ranges from ~-15° (steep iron) to ~+8° (ascending driver).
                        if -15.0 <= candidate_aoa <= 8.0:
                            shot.club_angle_deg = candidate_aoa
                            logger.info(
                                "[SERVER] Club AoA: %.1f° (conf=%.0f%%)",
                                shot.club_angle_deg,
                                club_angle_v.confidence * 100,
                            )
                        else:
                            logger.warning(
                                "[SERVER] Club AoA rejected: %.1f° outside plausible range",
                                candidate_aoa,
                            )

                if session_log and raw_buffer:
                    session_log.log_kld7_buffer(
                        shot_number=session_log.stats.get("shots_detected", 0) + 1,
                        shot_timestamp=shot_ts,
                        orientation="vertical",
                        buffer_frames=raw_buffer,
                        ball_angle=_kld7_angle_log_payload(
                            kld7_angle,
                            "vertical_deg",
                            selection_details=vertical_selection_details,
                        ),
                        club_angle=_kld7_angle_log_payload(club_angle_v, "vertical_deg"),
                        raw_payload_expected=raw_payload_expected,
                    )

                kld7_vertical.reset()

            # --- Horizontal K-LD7 (club path / aim direction) ---
            if kld7_horizontal:
                raw_payload_expected_h = _experimental_kld7_raw_radc_logging_enabled()
                if raw_payload_expected_h:
                    raw_buffer_h = kld7_horizontal.snapshot_buffer(include_radc_payload=True)
                else:
                    raw_buffer_h = kld7_horizontal.snapshot_buffer()
                _warn_if_kld7_buffer_underfilled("horizontal", len(raw_buffer_h))
                _warn_if_kld7_raw_payload_missing(
                    "horizontal",
                    raw_buffer_h,
                    raw_payload_expected=raw_payload_expected_h,
                )
                _warn_if_kld7_snapshot_lacks_post_shot_frames(
                    "horizontal",
                    raw_buffer_h,
                    shot_ts,
                    raw_payload_expected=raw_payload_expected_h,
                )
                kld7_angle_h = kld7_horizontal.get_angle_for_shot(
                    shot_timestamp=shot_ts,
                    ball_speed_mph=shot.ball_speed_mph,
                )
                horizontal_selection_details = None
                if kld7_angle_h and kld7_angle_h.horizontal_deg is not None:
                    horizontal_limit = (
                        float(
                            active_kld7_radc_tuning.get(
                                "radc_horizontal_angle_limit_deg",
                                15.0,
                            )
                        )
                        if experimental_kld7_radc_tuning
                        else 15.0
                    )
                    accepted_h, horizontal_selection_details = _select_horizontal_radar_launch(
                        kld7_angle_h, horizontal_limit
                    )
                    selection_reason_h = horizontal_selection_details["selection_reason"]
                    if accepted_h:
                        shot.launch_angle_horizontal = kld7_angle_h.horizontal_deg
                        shot.launch_angle_horizontal_confidence = kld7_angle_h.confidence
                        shot.launch_angle_horizontal_source = "radar"
                        if shot.angle_source is None:
                            shot.angle_source = "radar"
                        if shot.launch_angle_confidence is None:
                            shot.launch_angle_confidence = kld7_angle_h.confidence
                        logger.info(
                            "[SERVER] Horizontal angle: %.1f° (conf=%.0f%%, %d frames, %s)",
                            kld7_angle_h.horizontal_deg,
                            kld7_angle_h.confidence * 100,
                            kld7_angle_h.num_frames,
                            selection_reason_h,
                        )
                    else:
                        logger.warning(
                            "[SERVER] Horizontal angle %.1f° rejected: %s "
                            "(limit=±%.0f°, conf=%.0f%%)",
                            kld7_angle_h.horizontal_deg,
                            selection_reason_h,
                            horizontal_limit,
                            kld7_angle_h.confidence * 100,
                        )
                # Club path (same RADC buffer, club speed from OPS).
                # Compute BEFORE logging the buffer so the log entry can
                # include club_angle alongside ball_angle for offline analysis.
                club_angle_h = None
                if shot.club_speed_mph:
                    club_angle_h = kld7_horizontal.get_club_angle(
                        club_speed_mph=shot.club_speed_mph,
                        shot_timestamp=shot_ts,
                    )
                    if club_angle_h and club_angle_h.horizontal_deg is not None:
                        shot.club_path_deg = club_angle_h.horizontal_deg
                        logger.info(
                            "[SERVER] Club path: %.1f° (conf=%.0f%%)",
                            club_angle_h.horizontal_deg,
                            club_angle_h.confidence * 100,
                        )

                if session_log and raw_buffer_h:
                    session_log.log_kld7_buffer(
                        shot_number=session_log.stats.get("shots_detected", 0) + 1,
                        shot_timestamp=shot_ts,
                        orientation="horizontal",
                        buffer_frames=raw_buffer_h,
                        ball_angle=_kld7_angle_log_payload(
                            kld7_angle_h,
                            "horizontal_deg",
                            selection_details=horizontal_selection_details,
                        ),
                        club_angle=_kld7_angle_log_payload(club_angle_h, "horizontal_deg"),
                        raw_payload_expected=raw_payload_expected_h,
                    )

                kld7_horizontal.reset()

            # Derive spin axis from face angle (H. launch) minus club path
            if shot.launch_angle_horizontal is not None and shot.club_path_deg is not None:
                shot.spin_axis_deg = round(shot.launch_angle_horizontal - shot.club_path_deg, 1)
                logger.info(
                    "[SERVER] Spin axis: %+.1f° (face=%+.1f° - path=%+.1f°)",
                    shot.spin_axis_deg,
                    shot.launch_angle_horizontal,
                    shot.club_path_deg,
                )

            if kld7_vertical or kld7_horizontal:
                kld7_ms = (time.time() - kld7_start) * 1000
                logger.info("[SERVER] K-LD7 processing: %.1fms", kld7_ms)
    except Exception as e:
        logger.warning("[SERVER] K-LD7 processing error: %s", e, exc_info=True)
        log_session_error(
            "K-LD7 shot processing failed",
            component="server",
            context={
                "stage": "kld7",
                "ball_speed_mph": shot.ball_speed_mph,
                "club": shot.club.value,
            },
            exc=e,
        )

    # Try to get launch angle from camera BEFORE emitting shot
    # Skip camera for mock shots — they already have simulated launch angle
    # Skip if K-LD7 already provided vertical angle
    camera_data = None
    try:
        if (
            camera_tracker
            and camera_enabled
            and shot.mode != "mock"
            and shot.launch_angle_vertical is None
        ):
            launch_angle = camera_tracker.calculate_launch_angle()
            if launch_angle:
                # Update shot object with launch angle data
                shot.launch_angle_vertical = launch_angle.vertical
                shot.launch_angle_horizontal = launch_angle.horizontal
                shot.launch_angle_confidence = launch_angle.confidence
                shot.launch_angle_vertical_confidence = launch_angle.confidence
                shot.launch_angle_horizontal_confidence = launch_angle.confidence
                shot.launch_angle_vertical_source = "camera"
                shot.launch_angle_horizontal_source = "camera"
                shot.angle_source = "camera"

                camera_data = {
                    "launch_angle_vertical": launch_angle.vertical,
                    "launch_angle_horizontal": launch_angle.horizontal,
                    "launch_angle_confidence": launch_angle.confidence,
                    "positions_tracked": len(launch_angle.positions),
                    "launch_detected": camera_tracker.launch_detected,
                }
                logger.info(
                    "[SERVER] Angle source: camera (%.1f° V, %.1f° H, conf=%.0f%%)",
                    launch_angle.vertical,
                    launch_angle.horizontal,
                    launch_angle.confidence * 100,
                )

            # Reset camera tracker for next shot
            camera_tracker.reset()
            ball_detected = False
            ball_detection_confidence = 0.0
    except Exception as e:
        logger.warning("[SERVER] Camera processing error: %s", e, exc_info=True)
        log_session_error(
            "Camera shot processing failed",
            component="server",
            context={"stage": "camera", "ball_speed_mph": shot.ball_speed_mph},
            exc=e,
        )
        camera_data = None

    # Always emit user-facing launch angles. Radar/camera measurements win;
    # rejected or missing axes fall back to conservative estimates.
    _ensure_user_facing_launch_angles(shot)

    # Ball-speed cosine correction: the OPS reads the radial component of
    # a ball departing at the launch angle. Applied AFTER the K-LD7 (which
    # must anchor to the radial speed) and BEFORE carry/ballistics.
    if ball_speed_correction_enabled and shot.launch_angle_vertical is not None:
        raw_speed = shot.ball_speed_mph
        shot.ball_speed_raw_mph = raw_speed
        shot.ball_speed_mph = correct_ball_speed(
            raw_speed,
            shot.launch_angle_vertical,
            ball_speed_correction_distance_ft,
            ball_speed_correction_ball_above_radar_ft,
        )
        logger.info(
            "[SERVER] Ball speed cosine correction: %.1f -> %.1f mph (LA %.1f)",
            raw_speed,
            shot.ball_speed_mph,
            shot.launch_angle_vertical,
        )

    # Calculated spin runs AFTER the cosine correction (the model is
    # calibrated on true ball speed) and BEFORE carry/ballistics.
    if calculated_spin_enabled:
        _apply_calculated_spin(shot)

    # Compute carry. Prefer the physics simulator (drag + Magnus, RK4) when
    # ballistics is enabled and a vertical launch angle is available; fall
    # back to the table estimator otherwise (either ballistics disabled or
    # angle missing → resolve_launch returns None).
    _MIN_RELIABLE_SPIN_CONF = 0.6
    if shot.carry_spin_adjusted is None and shot.mode != "mock":
        conditions = resolve_launch(shot) if ballistics_enabled else None
        if conditions is not None:
            trajectory = simulate(conditions)
            shot.carry_spin_adjusted = trajectory.carry_yards
            logger.info(
                "[SERVER] Ballistic carry: %.0f yds (spin: %.0f rpm, source: %s)",
                shot.carry_spin_adjusted,
                conditions.spin_rpm,
                conditions.spin_source,
            )
        else:
            has_reliable_spin = (
                shot.spin_rpm
                and shot.spin_rpm > 0
                and shot.spin_confidence is not None
                and shot.spin_confidence >= _MIN_RELIABLE_SPIN_CONF
            )
            spin_for_carry = (
                shot.spin_rpm
                if has_reliable_spin
                else get_optimal_spin_for_ball_speed(shot.ball_speed_mph, shot.club)
            )
            shot.carry_spin_adjusted = estimate_carry_with_spin(
                shot.ball_speed_mph,
                spin_for_carry,
                shot.club,
                club_speed_mph=shot.club_speed_mph,
            )
            reason = "ballistics disabled" if not ballistics_enabled else "no launch angle"
            logger.info(
                "[SERVER] Table carry (%s): %.0f yds (spin: %.0f rpm%s)",
                reason,
                shot.carry_spin_adjusted,
                spin_for_carry,
                "" if shot.spin_rpm and shot.spin_rpm > 0 else " avg",
            )
    if shot.spin_rejection_reason:
        logger.info(
            "[SERVER] Spin unavailable: %s (snr=%s, candidate=%s rpm)",
            shot.spin_rejection_reason,
            "%.2f" % shot.spin_snr if shot.spin_snr is not None else "N/A",
            "%.0f" % (shot.spin_peak_freq_hz * 60) if shot.spin_peak_freq_hz is not None else "N/A",
        )

    # Log shot with all data (radar + spin + camera) in one entry
    try:
        session_log = get_session_logger()
        if session_log:
            session_log.log_shot(
                ball_speed_mph=shot.ball_speed_mph,
                club_speed_mph=shot.club_speed_mph,
                smash_factor=shot.smash_factor,
                estimated_carry_yards=shot.estimated_carry_yards,
                club=shot.club.value,
                peak_magnitude=shot.peak_magnitude,
                readings_count=len(shot.readings),
                readings=shot.readings_data,
                spin_rpm=shot.spin_rpm,
                spin_confidence=shot.spin_confidence,
                spin_quality=shot.spin_quality,
                spin_snr=shot.spin_snr,
                spin_modulation_depth=shot.spin_modulation_depth,
                spin_peak_freq_hz=shot.spin_peak_freq_hz,
                spin_seam_cycles=shot.spin_seam_cycles,
                spin_at_lower_rail=shot.spin_at_lower_rail,
                spin_at_upper_rail=shot.spin_at_upper_rail,
                spin_candidates=shot.spin_candidates,
                spin_phase_method=shot.spin_phase_method,
                spin_phase_rpm=shot.spin_phase_rpm,
                spin_phase_snr=shot.spin_phase_snr,
                spin_phase_agreement_pct=shot.spin_phase_agreement_pct,
                spin_phase_confirmed=shot.spin_phase_confirmed,
                spin_rejection_reason=shot.spin_rejection_reason,
                carry_spin_adjusted=shot.carry_spin_adjusted,
                mode=shot.mode,
                launch_angle_vertical=shot.launch_angle_vertical,
                launch_angle_horizontal=shot.launch_angle_horizontal,
                launch_angle_confidence=shot.launch_angle_confidence,
                launch_angle_vertical_confidence=shot.launch_angle_vertical_confidence,
                launch_angle_horizontal_confidence=shot.launch_angle_horizontal_confidence,
                launch_angle_vertical_source=shot.launch_angle_vertical_source,
                launch_angle_horizontal_source=shot.launch_angle_horizontal_source,
                angle_source=shot.angle_source,
                club_angle_deg=shot.club_angle_deg,
                club_path_deg=shot.club_path_deg,
                spin_axis_deg=shot.spin_axis_deg,
                impact_timestamp=shot.impact_timestamp,
                pipeline_ms={
                    "kld7": round(kld7_ms, 1) if kld7_ms is not None else None,
                },
            )
    except Exception as e:
        logger.warning("[SERVER] Failed to log shot: %s", e, exc_info=True)
        log_session_error(
            "Session shot logging failed",
            component="server",
            context={"stage": "session_log_shot", "ball_speed_mph": shot.ball_speed_mph},
            exc=e,
        )

    # Emit shot with launch angle data included
    try:
        shot_data = shot_to_dict(shot)
        stats = monitor.get_session_stats() if monitor else {}
        socketio.emit("shot", {"shot": shot_data, "stats": stats})

        # Log shot info
        angle_str = ""
        if shot.launch_angle_vertical is not None:
            angle_str = ", Launch: %.1f°" % shot.launch_angle_vertical
        logger.info(
            "[SERVER] Shot: ball=%.1f mph, carry=%.0f yds%s",
            shot.ball_speed_mph,
            shot.estimated_carry_yards,
            angle_str,
        )
    except Exception as e:
        logger.error("[SERVER] Failed to emit shot: %s", e, exc_info=True)
        log_session_error(
            "WebSocket shot emit failed",
            component="server",
            context={"stage": "emit_shot", "ball_speed_mph": shot.ball_speed_mph},
            exc=e,
        )
        return

    # Forward to simulator connectors (optional)
    _forward_shot_to_simulators(shot)

    # Debug logging (optional)
    if debug_mode:
        try:
            debug_log_entry = {
                "type": "shot",
                "timestamp": datetime.now().isoformat(),
                "radar": {
                    "ball_speed_mph": shot_data["ball_speed_mph"],
                    "club_speed_mph": shot_data["club_speed_mph"],
                    "smash_factor": shot_data["smash_factor"],
                    "peak_magnitude": shot_data["peak_magnitude"],
                },
                "camera": camera_data,
                "club": shot_data["club"],
            }

            if debug_log_file:
                debug_log_file.write(json.dumps(debug_log_entry) + "\n")
                debug_log_file.flush()

            socketio.emit("debug_shot", debug_log_entry)
        except Exception as e:
            print(f"[WARN] Debug logging error: {e}")


def start_monitor(
    port: Optional[str] = None,
    mock: bool = False,
    trigger_type: str = "polling",
    debug: bool = False,
    trigger_kwargs: Optional[dict] = None,
    sample_rate_ksps: int = 30,
):
    """
    Start the launch monitor in rolling buffer mode.

    Args:
        port: Serial port for radar
        mock: Run in mock mode without radar
        trigger_type: Trigger strategy (sound, speed, polling)
        debug: Enable verbose debug output
    """
    global monitor, mock_mode  # pylint: disable=global-statement

    # Stop any existing monitor first
    if monitor is not None:
        print("[MONITOR] Stopping existing monitor before starting new one")
        stop_monitor()

    mock_mode = mock
    if mock:
        # Mock mode for testing without radar
        monitor = MockLaunchMonitor()
    else:
        from .rolling_buffer import RollingBufferMonitor

        monitor = RollingBufferMonitor(
            port=port,
            trigger_type=trigger_type,
            sample_rate_ksps=sample_rate_ksps,
            **(trigger_kwargs or {}),
        )
        print(
            "[MODE] Rolling buffer mode "
            f"(trigger: {trigger_type}, sample_rate: {sample_rate_ksps}ksps)"
        )

    monitor.connect()

    logger.info(
        "[SERVER] Starting monitor: mode=%s, trigger=%s, sample_rate=%dksps",
        "mock" if mock else "rolling-buffer",
        trigger_type,
        sample_rate_ksps,
    )

    # Start session logging
    session_logger = get_session_logger()
    if session_logger:
        radar_info = monitor.get_radar_info() if not mock else {}
        session_logger.start_session(
            radar_port=port if not mock else "mock",
            firmware_version=radar_info.get("Version"),
            camera_enabled=camera is not None,
            camera_model="hough" if (camera_tracker and camera_tracker.use_hough) else None,
            config=_session_start_config(),
            mode="mock" if mock else "rolling-buffer",
            trigger_type=trigger_type if not mock else None,
        )
        if not mock and radar_info:
            session_logger.log_connection(
                device="ops243",
                port=port or "auto",
                baud=getattr(monitor.radar, "baud", 0) if hasattr(monitor, "radar") else 0,
                firmware=radar_info.get("Version"),
            )
            # Capture the OPS radar-clock -> host-epoch offset once at startup
            # before the trigger loop runs. Sound-triggered captures use this to
            # anchor K-LD7 correlation to the OPS trigger_time instead of the
            # USB first-byte arrival time.
            radar = getattr(monitor, "radar", None)
            if radar is not None and hasattr(radar, "read_clock_sync"):
                try:
                    clock_sync = radar.read_clock_sync()
                    session_logger.log_clock_sync(
                        device="ops243",
                        port=port or "auto",
                        summary=clock_sync,
                    )
                except Exception:  # pylint: disable=broad-except
                    # Instrumentation must never break startup.
                    logger.warning("[SERVER] OPS clock sync read failed", exc_info=True)

    if not mock:

        def on_trigger_diagnostic(data: dict):
            """Forward trigger diagnostics to connected UI clients."""
            socketio.emit("trigger_diagnostic", data)

        monitor.start(  # pylint: disable=unexpected-keyword-arg
            shot_callback=on_shot_detected,
            live_callback=on_live_reading,
            diagnostic_callback=on_trigger_diagnostic,
        )
    else:
        monitor.start(shot_callback=on_shot_detected, live_callback=on_live_reading)


def _fire_cloud_push(session_logger):
    """Best-effort, non-blocking cloud push on session end.

    Fully guarded: the uploader is opt-in and must never delay or break the
    shot/session path. The systemd timer is the safety net if this no-ops.
    """
    try:
        from .cloud.config import load_config
        from .cloud.trigger import fire_push_async

        config = load_config()
        if config is None or not config.is_active():
            return
        log_dir = getattr(session_logger, "log_dir", None)
        if log_dir is not None:
            fire_push_async(config, log_dir=log_dir)
    except Exception:  # pylint: disable=broad-exception-caught
        pass


def stop_monitor():
    """Stop the launch monitor."""
    global monitor  # pylint: disable=global-statement

    # End session logging
    session_logger = get_session_logger()
    if session_logger:
        session_logger.end_session()
        _fire_cloud_push(session_logger)

    if monitor:
        monitor.stop()
        monitor.disconnect()
        monitor = None


class MockLaunchMonitor:
    """Mock launch monitor for UI development without radar hardware."""

    # TrackMan averages for amateur golfers: (avg_ball_speed, std_dev, smash_factor)
    _CLUB_BALL_SPEEDS = {
        ClubType.DRIVER: (143, 12, 1.45),
        ClubType.WOOD_3: (135, 10, 1.42),
        ClubType.WOOD_5: (128, 10, 1.40),
        ClubType.WOOD_7: (122, 9, 1.40),
        ClubType.HYBRID_3: (123, 9, 1.39),
        ClubType.HYBRID_5: (118, 9, 1.37),
        ClubType.HYBRID_7: (112, 8, 1.35),
        ClubType.HYBRID_9: (106, 8, 1.33),
        ClubType.IRON_2: (120, 9, 1.35),
        ClubType.IRON_3: (118, 9, 1.35),
        ClubType.IRON_4: (114, 8, 1.33),
        ClubType.IRON_5: (110, 8, 1.31),
        ClubType.IRON_6: (105, 7, 1.29),
        ClubType.IRON_7: (100, 7, 1.27),
        ClubType.IRON_8: (94, 6, 1.25),
        ClubType.IRON_9: (88, 6, 1.23),
        ClubType.PW: (82, 5, 1.21),
        ClubType.GW: (76, 5, 1.20),
        ClubType.SW: (73, 5, 1.19),
        ClubType.LW: (70, 5, 1.18),
        ClubType.UNKNOWN: (120, 15, 1.35),
    }

    # Spin rates (avg_rpm, std_dev) — drivers: low spin, wedges: high spin
    _CLUB_SPIN = {
        ClubType.DRIVER: (2700, 400),
        ClubType.WOOD_3: (3200, 400),
        ClubType.WOOD_5: (3700, 400),
        ClubType.WOOD_7: (4200, 500),
        ClubType.HYBRID_3: (3800, 400),
        ClubType.HYBRID_5: (4200, 500),
        ClubType.HYBRID_7: (4600, 500),
        ClubType.HYBRID_9: (5000, 500),
        ClubType.IRON_2: (3800, 400),
        ClubType.IRON_3: (4100, 400),
        ClubType.IRON_4: (4500, 500),
        ClubType.IRON_5: (5000, 500),
        ClubType.IRON_6: (5500, 600),
        ClubType.IRON_7: (6000, 600),
        ClubType.IRON_8: (7000, 700),
        ClubType.IRON_9: (7800, 800),
        ClubType.PW: (8500, 800),
        ClubType.GW: (9200, 900),
        ClubType.SW: (9800, 1000),
        ClubType.LW: (10200, 1000),
        ClubType.UNKNOWN: (5000, 800),
    }

    # Launch angles in degrees (avg, std_dev) — drivers: low, wedges: high
    _CLUB_LAUNCH = {
        ClubType.DRIVER: (11.0, 2.0),
        ClubType.WOOD_3: (12.5, 2.0),
        ClubType.WOOD_5: (14.0, 2.0),
        ClubType.WOOD_7: (15.5, 2.0),
        ClubType.HYBRID_3: (13.5, 2.0),
        ClubType.HYBRID_5: (15.0, 2.0),
        ClubType.HYBRID_7: (16.5, 2.0),
        ClubType.HYBRID_9: (18.0, 2.5),
        ClubType.IRON_2: (13.0, 2.0),
        ClubType.IRON_3: (14.5, 2.0),
        ClubType.IRON_4: (16.0, 2.0),
        ClubType.IRON_5: (17.5, 2.0),
        ClubType.IRON_6: (19.0, 2.5),
        ClubType.IRON_7: (20.5, 2.5),
        ClubType.IRON_8: (23.0, 3.0),
        ClubType.IRON_9: (25.5, 3.0),
        ClubType.PW: (28.0, 3.0),
        ClubType.GW: (30.0, 3.5),
        ClubType.SW: (32.0, 4.0),
        ClubType.LW: (35.0, 4.0),
        ClubType.UNKNOWN: (18.0, 3.0),
    }

    def __init__(self):
        """Initialize mock monitor."""
        self._shots: List[Shot] = []
        self._running = False
        self._shot_callback = None
        self._current_club = ClubType.DRIVER

    def connect(self):
        """Connect to mock radar (no-op)."""
        return True

    def disconnect(self):
        """Disconnect from mock radar."""
        self.stop()

    def start(self, shot_callback=None, live_callback=None):  # pylint: disable=unused-argument
        """Start mock monitoring."""
        self._shot_callback = shot_callback
        self._running = True
        print("Mock monitor started - simulate shots via WebSocket")

    def stop(self):
        """Stop mock monitoring."""
        self._running = False

    def simulate_shot(self, ball_speed: float = None):
        """Simulate a shot for testing using realistic TrackMan-based values."""
        avg_speed, std_dev, smash = self._CLUB_BALL_SPEEDS.get(self._current_club, (120, 15, 1.35))

        if ball_speed is None:
            ball_speed = max(50, min(200, random.gauss(avg_speed, std_dev)))

        smash_factor = smash + random.uniform(-0.03, 0.03)
        club_speed = ball_speed / smash_factor

        # Generate spin
        avg_spin, spin_std = self._CLUB_SPIN.get(self._current_club, (5000, 800))
        spin_rpm = max(1000, random.gauss(avg_spin, spin_std))

        # Generate launch angle (vertical always positive, minimum 5°)
        avg_launch, launch_std = self._CLUB_LAUNCH.get(self._current_club, (18.0, 3.0))
        launch_v = max(5.0, random.gauss(avg_launch, launch_std))
        launch_h = random.gauss(0, 2.0)
        launch_confidence = round(random.uniform(0.5, 0.95), 2)

        # Generate club angle of attack (negative for irons, near-zero for driver)
        club_aoa = round(random.gauss(-4.0, 2.5), 1)

        shot = Shot(
            ball_speed_mph=ball_speed,
            club_speed_mph=club_speed,
            timestamp=datetime.now(),
            club=self._current_club,
            spin_rpm=spin_rpm,
            spin_confidence=random.choice([0.3, 0.6, 0.7, 0.9]),
            launch_angle_vertical=round(launch_v, 1),
            launch_angle_horizontal=round(launch_h, 1),
            launch_angle_confidence=launch_confidence,
            launch_angle_vertical_confidence=launch_confidence,
            launch_angle_horizontal_confidence=launch_confidence,
            launch_angle_vertical_source="mock",
            launch_angle_horizontal_source="mock",
            angle_source="mock",
            club_angle_deg=club_aoa,
            club_path_deg=round(random.uniform(-5.0, 5.0), 1),
            spin_axis_deg=round(launch_h - random.uniform(-5.0, 5.0), 1),
            mode="mock",
        )

        self._shots.append(shot)

        if self._shot_callback:
            self._shot_callback(shot)

        return shot

    def get_shots(self) -> List[Shot]:
        """Get all recorded shots."""
        return self._shots.copy()

    def get_session_stats(self) -> dict:
        """Get session statistics."""
        if not self._shots:
            return {
                "shot_count": 0,
                "avg_ball_speed": 0,
                "max_ball_speed": 0,
                "min_ball_speed": 0,
                "avg_club_speed": None,
                "avg_smash_factor": None,
                "avg_carry_est": 0,
            }

        ball_speeds = [s.ball_speed_mph for s in self._shots]
        club_speeds = [s.club_speed_mph for s in self._shots if s.club_speed_mph]
        smash_factors = [s.smash_factor for s in self._shots if s.smash_factor]

        return {
            "shot_count": len(self._shots),
            "avg_ball_speed": statistics.mean(ball_speeds),
            "max_ball_speed": max(ball_speeds),
            "min_ball_speed": min(ball_speeds),
            "std_dev": statistics.stdev(ball_speeds) if len(ball_speeds) > 1 else 0,
            "avg_club_speed": statistics.mean(club_speeds) if club_speeds else None,
            "avg_smash_factor": statistics.mean(smash_factors) if smash_factors else None,
            "avg_carry_est": statistics.mean([s.estimated_carry_yards for s in self._shots]),
        }

    def clear_session(self):
        """Clear all recorded shots."""
        self._shots = []

    def set_club(self, club: ClubType):
        """Set the current club for future shots."""
        self._current_club = club


def main():
    """Run the server."""
    import argparse  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser(description="OpenFlight UI Server")
    parser.add_argument("--port", "-p", help="Serial port for radar")
    parser.add_argument("--mock", "-m", action="store_true", help="Run in mock mode without radar")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    parser.add_argument(
        "--web-port", type=int, default=8080, help="Web server port (default: 8080)"
    )
    parser.add_argument(
        "--debug", "-d", action="store_true", help="Enable verbose FFT/CFAR debug output"
    )
    parser.add_argument(
        "--radar-log", action="store_true", help="Log raw radar data to console (Python logging)"
    )
    parser.add_argument(
        "--show-raw", action="store_true", help="Show raw radar readings in console (signed values)"
    )
    parser.add_argument(
        "--no-camera", action="store_true", help="Disable camera (auto-enabled if available)"
    )
    parser.add_argument(
        "--camera-model",
        default=None,
        help="Path to YOLO model for ball detection (uses Hough by default)",
    )
    parser.add_argument(
        "--camera-imgsz",
        type=int,
        default=256,
        help="YOLO inference input size (256 for speed, 640 for accuracy)",
    )
    parser.add_argument(
        "--hough-param2",
        type=int,
        default=33,
        help="Hough accumulator threshold (lower = more sensitive, default 33)",
    )
    parser.add_argument(
        "--hough-param1",
        type=int,
        default=48,
        help="Canny edge threshold (lower = detects weaker edges, default 48)",
    )
    parser.add_argument(
        "--hough-min-radius", type=int, default=4, help="Min ball radius in pixels (default 4)"
    )
    parser.add_argument(
        "--hough-max-radius", type=int, default=43, help="Max ball radius in pixels (default 43)"
    )
    parser.add_argument(
        "--hough-min-dist",
        type=int,
        default=266,
        help="Min distance between detected circles in pixels (default 266)",
    )
    parser.add_argument(
        "--roboflow-model",
        help="Roboflow model ID (e.g., 'golfballdetector/10'). Uses Roboflow API instead of Hough.",
    )
    parser.add_argument(
        "--roboflow-api-key", help="Roboflow API key (can also use ROBOFLOW_API_KEY env var)"
    )
    parser.add_argument(
        "--session-location",
        "-l",
        default="range",
        help="Location identifier for session logs (e.g., 'range', 'course', 'home')",
    )
    parser.add_argument(
        "--log-dir", help="Directory for session logs (default: ~/openflight_sessions)"
    )
    parser.add_argument("--no-logging", action="store_true", help="Disable session logging")
    parser.add_argument(
        "--sim",
        action="store_true",
        help="Enable simulator connectors from config/sim.json (GSPro / OpenGolfSim). "
        "Off by default.",
    )
    parser.add_argument(
        "--ballistics",
        action="store_true",
        help=(
            "Enable the physics-based carry simulator (drag + Magnus, RK4). "
            "When set, shots with a vertical launch angle use the simulator "
            "for carry; otherwise they fall back to the legacy table estimator. "
            "Default: disabled (all shots use the table)."
        ),
    )
    parser.add_argument(
        "--trigger",
        choices=["polling", "threshold", "speed", "sound"],
        default="polling",
        help="Trigger strategy (default: polling)",
    )
    parser.add_argument(
        "--sound-pre-trigger",
        type=int,
        default=16,
        help=(
            "Pre-trigger segments S#n, 0-32 "
            "(default: 16 = 50/50 split, each segment ~4.27ms at 30ksps)"
        ),
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=30,
        help=(
            "Radar sample rate in ksps (default: 30). "
            "Lower = longer buffer but lower max speed. "
            "25=174mph/164ms, 27=187mph/152ms"
        ),
    )
    parser.add_argument(
        "--kld7", action="store_true", help="Enable K-LD7 vertical angle radar (launch angle)"
    )
    parser.add_argument(
        "--kld7-port",
        default=None,
        help="K-LD7 vertical serial port (auto-detect if not specified)",
    )
    parser.add_argument(
        "--kld7-angle-offset",
        type=float,
        default=0.0,
        help="K-LD7 vertical angle offset in degrees (default: 0.0)",
    )
    parser.add_argument(
        "--ball-speed-cosine-correction",
        action="store_true",
        help=(
            "Correct OPS radial ball speed to true ball speed using the launch "
            "angle and radar geometry (validated vs TrackMan; see "
            "src/openflight/speed_correction.py)"
        ),
    )
    parser.add_argument(
        "--calculated-spin",
        action="store_true",
        help=(
            "Replace radar-measured spin with the kinematic estimate "
            "(170*v*sin(LA)^1.2) when the launch angle was measured. The 24 GHz "
            "OPS return carries no usable spin line (see "
            "src/openflight/spin_estimate.py); the measured value is kept in "
            "spin_rpm_measured for offline scoring"
        ),
    )
    parser.add_argument(
        "--kld7-vertical-estimator",
        choices=("geometry", "naive"),
        default="naive",
        help=(
            "Vertical launch-angle estimator: 'naive' (legacy bearing average + offset, "
            "default) or 'geometry' (trajectory fit)"
        ),
    )
    parser.add_argument(
        "--kld7-mount-tilt",
        type=float,
        default=18.0,
        help="K-LD7 vertical radar mount tilt in degrees, for the geometry estimator (default: 18.0)",
    )
    parser.add_argument(
        "--kld7-ball-distance",
        type=float,
        default=5.5,
        help=(
            "Ball-to-radar-front distance in feet, for the geometry estimator "
            "(weak lever; default: 5.5)"
        ),
    )
    parser.add_argument(
        "--kld7-radar-height-inches",
        dest="kld7_radar_height_inches",
        type=float,
        default=4.0,
        help=(
            "K-LD7 radar height above the ball in inches, used by the ball-speed "
            "cosine correction geometry (default: 4.0)"
        ),
    )
    parser.add_argument(
        "--kld7-horizontal",
        action="store_true",
        help="Enable K-LD7 horizontal angle radar (club path)",
    )
    parser.add_argument("--kld7-horizontal-port", default=None, help="K-LD7 horizontal serial port")
    parser.add_argument(
        "--kld7-horizontal-offset",
        type=float,
        default=0.0,
        help="K-LD7 horizontal angle offset in degrees (default: 0.0)",
    )
    parser.add_argument(
        "--experimental-kld7-raw-radc-logging",
        action="store_true",
        help=(
            "Include base64 raw K-LD7 RADC payloads in kld7_buffer session logs "
            "for TrackMan replay without changing live angle extraction"
        ),
    )
    parser.add_argument(
        "--experimental-kld7-radc-tuning",
        action="store_true",
        help=("Enable temporary K-LD7 RADC extraction tuning parameters (off by default)"),
    )
    parser.add_argument(
        "--experimental-kld7-speed-tolerance",
        type=float,
        default=10.0,
        help="Experimental K-LD7 RADC speed tolerance in mph (default: 10.0)",
    )
    parser.add_argument(
        "--experimental-kld7-centroid-floor",
        type=float,
        default=0.5,
        help="Experimental K-LD7 RADC centroid floor fraction (default: 0.5)",
    )
    parser.add_argument(
        "--experimental-kld7-spectrum-source",
        choices=("f1a", "f2a", "f1b", "sum12", "sum1b", "sumall", "min12", "geom12"),
        default="f1a",
        help=(
            "Experimental K-LD7 spectrum used for target-bin selection "
            "(default: f1a; try sum12 for F1A+F2A non-coherent selection)"
        ),
    )
    parser.add_argument(
        "--experimental-kld7-ops-bin-tol",
        type=int,
        default=25,
        help="Experimental K-LD7 RADC OPS-bin outlier tolerance (default: 25)",
    )
    parser.add_argument(
        "--experimental-kld7-ops-bin-penalty",
        type=float,
        default=10.0,
        help="Experimental K-LD7 RADC OPS-bin outlier penalty (default: 10.0)",
    )
    parser.add_argument(
        "--experimental-kld7-ops-anchored-min-snr",
        type=float,
        default=5.0,
        help="Experimental K-LD7 RADC OPS-anchored local peak minimum SNR (default: 5.0)",
    )
    parser.add_argument(
        "--experimental-kld7-vertical-impact-energy",
        type=float,
        default=3.0,
        help="Experimental vertical K-LD7 RADC impact energy threshold (default: 3.0)",
    )
    parser.add_argument(
        "--experimental-kld7-horizontal-impact-energy",
        type=float,
        default=1.85,
        help="Experimental horizontal K-LD7 RADC impact energy threshold (default: 1.85)",
    )
    parser.add_argument(
        "--experimental-kld7-horizontal-retry-impact-energy",
        type=float,
        default=0.5,
        help=("Experimental horizontal K-LD7 RADC retry impact energy threshold (default: 0.5)"),
    )
    parser.add_argument(
        "--experimental-kld7-horizontal-angle-limit",
        type=float,
        default=15.0,
        help="Experimental horizontal K-LD7 RADC angle acceptance limit in degrees (default: 15.0)",
    )
    args = parser.parse_args()

    global experimental_kld7_radc_tuning
    global experimental_kld7_raw_radc_logging
    global active_kld7_radc_tuning
    global ballistics_enabled
    experimental_kld7_raw_radc_logging = args.experimental_kld7_raw_radc_logging
    experimental_kld7_radc_tuning = args.experimental_kld7_radc_tuning
    global ball_speed_correction_enabled
    global ball_speed_correction_distance_ft
    global ball_speed_correction_ball_above_radar_ft
    ball_speed_correction_enabled = args.ball_speed_cosine_correction
    ball_speed_correction_distance_ft = args.kld7_ball_distance
    ball_speed_correction_ball_above_radar_ft = -args.kld7_radar_height_inches / 12.0
    global calculated_spin_enabled
    calculated_spin_enabled = args.calculated_spin
    ballistics_enabled = args.ballistics
    kld7_radc_tuning_kwargs = _kld7_radc_tuning_kwargs(args)
    active_kld7_radc_tuning = dict(kld7_radc_tuning_kwargs)

    # Configure logging - always show INFO and above for openflight modules
    # This ensures trigger events and important messages are visible
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    # Set rolling buffer logger to INFO so trigger events are visible
    logging.getLogger("openflight.rolling_buffer").setLevel(logging.INFO)
    logging.getLogger("openflight.rolling_buffer.trigger").setLevel(logging.INFO)
    logging.getLogger("openflight.rolling_buffer.monitor").setLevel(logging.INFO)

    print("=" * 50)
    print("  OpenFlight UI Server")
    print("=" * 50)
    print()

    # Initialize session logger (enabled for both real and mock modes)
    if not args.no_logging:
        from pathlib import Path

        log_dir = Path(args.log_dir) if args.log_dir else None
        init_session_logger(log_dir=log_dir, location=args.session_location, enabled=True)
        print(f"Session logging enabled (location: {args.session_location})")
    else:
        init_session_logger(enabled=False)
        print("Session logging DISABLED")

    if ballistics_enabled:
        print("Ballistic carry model: ENABLED (simulator + drag/Magnus)")
    else:
        print("Ballistic carry model: DISABLED (table fallback for all shots)")

    # Configure radar logging if requested
    if args.radar_log:
        logging.basicConfig(
            level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        radar_logger = logging.getLogger("ops243")
        radar_raw_logger = logging.getLogger("ops243.raw")
        radar_logger.setLevel(logging.DEBUG)
        radar_raw_logger.setLevel(logging.DEBUG)
        print("Radar raw logging ENABLED - all readings will be logged")

    # Enable raw reading console output if requested
    if args.show_raw:
        set_show_raw_readings(True)
        print("Raw radar readings display ENABLED - signed speed values will be shown")

    # Start the monitor
    # Build trigger-specific kwargs (pre_trigger_segments always passed)
    trigger_kwargs = {"pre_trigger_segments": args.sound_pre_trigger}

    # Initialize camera BEFORE starting monitor (so session log is accurate)
    if not args.no_camera:
        # Determine if we should use Hough (default) or YOLO
        use_hough = args.camera_model is None and args.roboflow_model is None

        if init_camera(
            model_path=args.camera_model,
            roboflow_model_id=args.roboflow_model,
            roboflow_api_key=args.roboflow_api_key,
            imgsz=args.camera_imgsz,
            use_hough=use_hough,
            hough_param2=args.hough_param2,
            hough_param1=args.hough_param1,
            hough_min_radius=args.hough_min_radius,
            hough_max_radius=args.hough_max_radius,
            hough_min_dist=args.hough_min_dist,
        ):
            start_camera_thread()
        else:
            print("Camera not available - running without camera")
    else:
        print("Camera disabled by --no-camera flag")

    if experimental_kld7_raw_radc_logging:
        print("Experimental K-LD7 raw RADC payload logging enabled")
    if experimental_kld7_radc_tuning:
        print(f"Experimental K-LD7 RADC tuning enabled: {kld7_radc_tuning_kwargs}")

    # Initialize K-LD7 angle radars (if enabled)
    if args.kld7:
        if init_kld7(
            port=args.kld7_port,
            orientation="vertical",
            angle_offset_deg=args.kld7_angle_offset,
            base_freq=0,
            vertical_estimator=args.kld7_vertical_estimator,
            mount_tilt_deg=args.kld7_mount_tilt,
            ball_distance_ft=args.kld7_ball_distance,
            **kld7_radc_tuning_kwargs,
        ):
            offset_str = (
                f", offset: {args.kld7_angle_offset:+.1f}°" if args.kld7_angle_offset else ""
            )
            print(f"K-LD7 vertical radar enabled (launch angle{offset_str})")
        else:
            print("ERROR: K-LD7 vertical requested but failed to connect. Exiting.")
            sys.exit(1)

    if args.kld7_horizontal:
        if init_kld7(
            port=args.kld7_horizontal_port,
            orientation="horizontal",
            angle_offset_deg=args.kld7_horizontal_offset,
            base_freq=2,
            **kld7_radc_tuning_kwargs,
        ):
            offset_str = (
                f", offset: {args.kld7_horizontal_offset:+.1f}°"
                if args.kld7_horizontal_offset
                else ""
            )
            print(f"K-LD7 horizontal radar enabled (club path{offset_str})")
        else:
            print("ERROR: K-LD7 horizontal requested but failed to connect. Exiting.")
            sys.exit(1)

    start_monitor(
        port=args.port,
        mock=args.mock,
        trigger_type=args.trigger,
        debug=args.debug,
        trigger_kwargs=trigger_kwargs,
        sample_rate_ksps=args.sample_rate,
    )

    # Simulator connectors (off unless --sim). Started after the monitor exists
    # so inbound club updates can call monitor.set_club().
    global sim_connectors  # pylint: disable=global-statement
    sim_cfgs = load_sim_config() if args.sim else []
    sim_connectors = build_connectors(
        sim_cfgs, on_status=_sim_on_status, on_inbound=_sim_on_inbound
    )
    for connector in sim_connectors:
        connector.start()
        print(f"Simulator connector enabled: {connector.name} -> {connector.host}:{connector.port}")
    if args.sim and not sim_connectors:
        print("Simulator connectors enabled (--sim) but none are enabled in config/sim.json")

    if args.mock:
        print("Running in MOCK mode - no radar required")
        print("Simulate shots via WebSocket or API")

    print(f"Server starting at http://{args.host}:{args.web_port}")
    print()

    try:
        # Note: Flask debug mode (reloader) is disabled to prevent duplicate processes
        # fighting over the serial port. OpenFlight --debug enables verbose logging only.
        socketio.run(
            app, host=args.host, port=args.web_port, debug=False, allow_unsafe_werkzeug=True
        )
    finally:
        _cleanup_hardware_for_shutdown()


if __name__ == "__main__":
    main()
