"""
WebSocket server for OpenFlight UI.

Provides real-time shot data to the web frontend via Flask-SocketIO.
"""

import json
import logging
import os
import random
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from flask import Flask, Response, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO

from .launch_monitor import ClubType, Shot
from .ops243 import Direction, SpeedReading, set_show_raw_readings
from .rolling_buffer.monitor import estimate_carry_with_spin, get_optimal_spin_for_ball_speed
from .session_logger import get_session_logger, init_session_logger

# Configure logging
logger = logging.getLogger(__name__)

# Camera imports (optional)
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


app = Flask(__name__, static_folder="../../ui/dist", static_url_path="")
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
    allowed_delta_deg = _radar_launch_base_delta_deg(club) + (
        1.0 - estimate_conf
    ) * _RADAR_SANITY_LOW_CONF_BONUS_DEG
    delta_deg = abs(radar_angle_deg - expected_launch_deg)

    return delta_deg <= allowed_delta_deg, {
        "skipped": False,
        "expected_launch_deg": round(expected_launch_deg, 1),
        "allowed_delta_deg": round(allowed_delta_deg, 1),
        "delta_deg": round(delta_deg, 1),
    }


def shot_to_dict(shot: Shot) -> dict:
    """Convert Shot to JSON-serializable dict."""
    return {
        "ball_speed_mph": round(shot.ball_speed_mph, 1),
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
        "angle_source": shot.angle_source,
        "club_angle_deg": shot.club_angle_deg,
        "club_path_deg": shot.club_path_deg,
        "spin_axis_deg": shot.spin_axis_deg,
        # Spin data from rolling buffer mode
        "spin_rpm": round(shot.spin_rpm) if shot.spin_rpm else None,
        "spin_confidence": round(shot.spin_confidence, 2) if shot.spin_confidence else None,
        "spin_quality": shot.spin_quality,
        "carry_spin_adjusted": round(shot.carry_spin_adjusted)
        if shot.carry_spin_adjusted
        else None,
    }


@app.route("/")
def index():
    """Serve the React app."""
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_files(path):
    """Serve static files."""
    return send_from_directory(app.static_folder, path)


@app.route("/api/shutdown", methods=["POST"])
def api_shutdown():
    """Cleanly shut down the server via REST API."""
    logger.info("[SERVER] Shutdown requested via REST API")

    import threading
    def _shutdown():
        import time as _time, os
        _time.sleep(0.5)
        # Clean up before exit
        try:
            if kld7_vertical:
                kld7_vertical.stop()
            if kld7_horizontal:
                kld7_horizontal.stop()
            stop_monitor()
        except Exception:
            pass
        logger.info("[SERVER] Goodbye")
        os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()
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


def init_kld7(port=None, orientation="vertical", angle_offset_deg=0.0, base_freq=0) -> bool:
    """Initialize a single K-LD7 angle radar tracker.

    Returns True if the tracker connected and started successfully.
    Sets the appropriate global (kld7_vertical or kld7_horizontal).
    """
    global kld7_vertical, kld7_horizontal  # pylint: disable=global-statement
    try:
        from openflight.kld7 import KLD7Tracker

        tracker = KLD7Tracker(
            port=port, orientation=orientation,
            angle_offset_deg=angle_offset_deg, base_freq=base_freq,
        )
        if tracker.connect():
            tracker.start()
            logger.info("[SERVER] K-LD7 %s initialized (port=%s, offset=%.1f°, RBFR=%d)",
                         orientation, port or "auto", angle_offset_deg, base_freq)
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
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
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
        print(f"Error setting radar config: {e}")
        socketio.emit("radar_config_error", {"error": str(e)})


@socketio.on("shutdown")
def handle_shutdown():
    """Cleanly shut down the server and all hardware."""
    logger.info("[SERVER] Shutdown requested from UI (WebSocket)")
    socketio.emit("shutdown_ack", {"message": "Shutting down..."})

    import threading
    def _shutdown():
        import time as _time, os
        _time.sleep(0.5)
        try:
            if kld7_vertical:
                kld7_vertical.stop()
            if kld7_horizontal:
                kld7_horizontal.stop()
            stop_monitor()
        except Exception:
            pass
        logger.info("[SERVER] Goodbye")
        os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()


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

            # --- Vertical K-LD7 (launch angle) ---
            if kld7_vertical:
                raw_buffer = kld7_vertical.snapshot_buffer()
                kld7_angle = kld7_vertical.get_angle_for_shot(
                    shot_timestamp=shot_ts,
                    ball_speed_mph=shot.ball_speed_mph,
                )
                if kld7_angle and kld7_angle.vertical_deg is not None:
                    accepted, guard_details = radar_launch_is_plausible(
                        radar_angle_deg=kld7_angle.vertical_deg,
                        club=shot.club,
                        ball_speed_mph=shot.ball_speed_mph,
                        club_speed_mph=shot.club_speed_mph,
                        spin_rpm=shot.spin_rpm,
                    )
                    if accepted:
                        shot.launch_angle_vertical = kld7_angle.vertical_deg
                        shot.launch_angle_confidence = kld7_angle.confidence
                        shot.angle_source = "radar"
                        logger.info(
                            "[SERVER] Vertical angle: %.1f° (conf=%.0f%%, %d frames)",
                            kld7_angle.vertical_deg, kld7_angle.confidence * 100,
                            kld7_angle.num_frames,
                        )
                    else:
                        logger.warning(
                            "[SERVER] Vertical angle %.1f° rejected: expected %.1f° ± %.1f°",
                            kld7_angle.vertical_deg,
                            guard_details["expected_launch_deg"],
                            guard_details["allowed_delta_deg"],
                        )
                if session_log and raw_buffer:
                    session_log.log_kld7_buffer(
                        shot_number=session_log.stats.get("shots_detected", 0) + 1,
                        shot_timestamp=shot_ts,
                        orientation="vertical",
                        buffer_frames=raw_buffer,
                        ball_angle={
                            "vertical_deg": kld7_angle.vertical_deg,
                            "confidence": kld7_angle.confidence,
                            "detection_class": kld7_angle.detection_class,
                            "magnitude": kld7_angle.magnitude,
                            "num_frames": kld7_angle.num_frames,
                        } if kld7_angle else None,
                    )
                # Club angle of attack (same RADC buffer, club speed from OPS)
                if shot.club_speed_mph:
                    club_angle_v = kld7_vertical.get_club_angle(club_speed_mph=shot.club_speed_mph)
                    if club_angle_v and club_angle_v.vertical_deg is not None:
                        # Negate: the radar sees where the club IS (above center = positive),
                        # but AoA is the club's attack direction (descending = negative).
                        candidate_aoa = -club_angle_v.vertical_deg
                        # Reject physically impossible AoA values.
                        # Real AoA ranges from ~-15° (steep iron) to ~+8° (ascending driver).
                        if -15.0 <= candidate_aoa <= 8.0:
                            shot.club_angle_deg = candidate_aoa
                            logger.info("[SERVER] Club AoA: %.1f° (conf=%.0f%%)",
                                         shot.club_angle_deg, club_angle_v.confidence * 100)
                        else:
                            logger.warning("[SERVER] Club AoA rejected: %.1f° outside plausible range",
                                           candidate_aoa)

                kld7_vertical.reset()

            # --- Horizontal K-LD7 (club path / aim direction) ---
            if kld7_horizontal:
                raw_buffer_h = kld7_horizontal.snapshot_buffer()
                kld7_angle_h = kld7_horizontal.get_angle_for_shot(
                    shot_timestamp=shot_ts,
                    ball_speed_mph=shot.ball_speed_mph,
                )
                if kld7_angle_h and kld7_angle_h.horizontal_deg is not None:
                    shot.launch_angle_horizontal = kld7_angle_h.horizontal_deg
                    if shot.angle_source is None:
                        shot.angle_source = "radar"
                    if shot.launch_angle_confidence is None:
                        shot.launch_angle_confidence = kld7_angle_h.confidence
                    logger.info(
                        "[SERVER] Horizontal angle: %.1f° (conf=%.0f%%, %d frames)",
                        kld7_angle_h.horizontal_deg, kld7_angle_h.confidence * 100,
                        kld7_angle_h.num_frames,
                    )
                if session_log and raw_buffer_h:
                    session_log.log_kld7_buffer(
                        shot_number=session_log.stats.get("shots_detected", 0) + 1,
                        shot_timestamp=shot_ts,
                        orientation="horizontal",
                        buffer_frames=raw_buffer_h,
                        ball_angle={
                            "horizontal_deg": kld7_angle_h.horizontal_deg,
                            "confidence": kld7_angle_h.confidence,
                            "detection_class": kld7_angle_h.detection_class,
                            "magnitude": kld7_angle_h.magnitude,
                            "num_frames": kld7_angle_h.num_frames,
                        } if kld7_angle_h else None,
                    )
                # Club path (same RADC buffer, club speed from OPS)
                if shot.club_speed_mph:
                    club_angle_h = kld7_horizontal.get_club_angle(club_speed_mph=shot.club_speed_mph)
                    if club_angle_h and club_angle_h.horizontal_deg is not None:
                        shot.club_path_deg = club_angle_h.horizontal_deg
                        logger.info("[SERVER] Club path: %.1f° (conf=%.0f%%)",
                                     club_angle_h.horizontal_deg, club_angle_h.confidence * 100)

                kld7_horizontal.reset()

            # Derive spin axis from face angle (H. launch) minus club path
            if shot.launch_angle_horizontal is not None and shot.club_path_deg is not None:
                shot.spin_axis_deg = round(shot.launch_angle_horizontal - shot.club_path_deg, 1)
                logger.info("[SERVER] Spin axis: %+.1f° (face=%+.1f° - path=%+.1f°)",
                             shot.spin_axis_deg, shot.launch_angle_horizontal, shot.club_path_deg)

            if kld7_vertical or kld7_horizontal:
                kld7_ms = (time.time() - kld7_start) * 1000
                logger.info("[SERVER] K-LD7 processing: %.1fms", kld7_ms)
    except Exception as e:
        logger.warning("[SERVER] K-LD7 processing error: %s", e, exc_info=True)

    # Try to get launch angle from camera BEFORE emitting shot
    # Skip camera for mock shots — they already have simulated launch angle
    # Skip if K-LD7 already provided vertical angle
    camera_data = None
    try:
        if camera_tracker and camera_enabled and shot.mode != "mock" and shot.launch_angle_vertical is None:
            launch_angle = camera_tracker.calculate_launch_angle()
            if launch_angle:
                # Update shot object with launch angle data
                shot.launch_angle_vertical = launch_angle.vertical
                shot.launch_angle_horizontal = launch_angle.horizontal
                shot.launch_angle_confidence = launch_angle.confidence
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
        camera_data = None

    # If no camera or radar launch angle, estimate from club type and ball speed
    if shot.launch_angle_vertical is None and shot.mode != "mock":
        estimated = estimate_launch_angle(
            shot.club,
            shot.ball_speed_mph,
            club_speed_mph=shot.club_speed_mph,
            spin_rpm=shot.spin_rpm,
        )
        shot.launch_angle_vertical = estimated[0]
        shot.launch_angle_horizontal = 0.0
        shot.launch_angle_confidence = estimated[1]
        shot.angle_source = "estimated"
        logger.info(
            "[SERVER] Angle source: estimated (%.1f°, conf=%.0f%%)", estimated[0], estimated[1] * 100
        )

    # Compute spin-adjusted carry using measured spin (if reliable) or club average
    _MIN_RELIABLE_SPIN_CONF = 0.6
    if shot.carry_spin_adjusted is None and shot.mode != "mock":
        has_reliable_spin = (
            shot.spin_rpm and shot.spin_rpm > 0
            and shot.spin_confidence is not None
            and shot.spin_confidence >= _MIN_RELIABLE_SPIN_CONF
        )
        spin_for_carry = shot.spin_rpm if has_reliable_spin else get_optimal_spin_for_ball_speed(shot.ball_speed_mph, shot.club)
        shot.carry_spin_adjusted = estimate_carry_with_spin(
            shot.ball_speed_mph,
            spin_for_carry,
            shot.club,
            club_speed_mph=shot.club_speed_mph,
        )
        logger.info(
            "[SERVER] Spin-adjusted carry: %.0f yds (spin: %.0f rpm%s)",
            shot.carry_spin_adjusted, spin_for_carry,
            "" if shot.spin_rpm and shot.spin_rpm > 0 else " avg",
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
                carry_spin_adjusted=shot.carry_spin_adjusted,
                mode=shot.mode,
                launch_angle_vertical=shot.launch_angle_vertical,
                launch_angle_horizontal=shot.launch_angle_horizontal,
                launch_angle_confidence=shot.launch_angle_confidence,
                angle_source=shot.angle_source,
                club_angle_deg=shot.club_angle_deg,
                club_path_deg=shot.club_path_deg,
                spin_axis_deg=shot.spin_axis_deg,
                pipeline_ms={
                    "kld7": round(kld7_ms, 1) if kld7_ms is not None else None,
                },
            )
    except Exception as e:
        logger.warning("[SERVER] Failed to log shot: %s", e, exc_info=True)

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
        return

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
            f"[MODE] Rolling buffer mode (trigger: {trigger_type}, sample_rate: {sample_rate_ksps}ksps)"
        )

    monitor.connect()

    logger.info("[SERVER] Starting monitor: mode=%s, trigger=%s, sample_rate=%dksps",
                "mock" if mock else "rolling-buffer", trigger_type, sample_rate_ksps)

    # Start session logging
    session_logger = get_session_logger()
    if session_logger:
        radar_info = monitor.get_radar_info() if not mock else {}
        session_logger.start_session(
            radar_port=port if not mock else "mock",
            firmware_version=radar_info.get("Version"),
            camera_enabled=camera is not None,
            camera_model="hough" if (camera_tracker and camera_tracker.use_hough) else None,
            config=radar_config.copy(),
            mode="mock" if mock else "rolling-buffer",
            trigger_type=trigger_type if not mock else None,
        )
        if not mock and radar_info:
            session_logger.log_connection(
                device="ops243",
                port=port or "auto",
                baud=getattr(monitor.radar, 'baud', 0) if hasattr(monitor, 'radar') else 0,
                firmware=radar_info.get("Version"),
            )

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


def stop_monitor():
    """Stop the launch monitor."""
    global monitor  # pylint: disable=global-statement

    # End session logging
    session_logger = get_session_logger()
    if session_logger:
        session_logger.end_session()

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
            launch_angle_confidence=round(random.uniform(0.5, 0.95), 2),
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
        "--trigger",
        choices=["polling", "threshold", "speed", "sound"],
        default="polling",
        help="Trigger strategy (default: polling)",
    )
    parser.add_argument(
        "--sound-pre-trigger",
        type=int,
        default=16,
        help="Pre-trigger segments S#n, 0-32 (default: 16 = 50/50 split, each segment ~4.27ms at 30ksps)",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=30,
        help="Radar sample rate in ksps (default: 30). Lower = longer buffer but lower max speed. 25=174mph/164ms, 27=187mph/152ms",
    )
    parser.add_argument(
        "--kld7", action="store_true", help="Enable K-LD7 vertical angle radar (launch angle)"
    )
    parser.add_argument(
        "--kld7-port", default=None, help="K-LD7 vertical serial port (auto-detect if not specified)"
    )
    parser.add_argument(
        "--kld7-angle-offset",
        type=float,
        default=0.0,
        help="K-LD7 vertical angle offset in degrees (default: 0.0)",
    )
    parser.add_argument(
        "--kld7-horizontal", action="store_true", help="Enable K-LD7 horizontal angle radar (club path)"
    )
    parser.add_argument(
        "--kld7-horizontal-port", default=None, help="K-LD7 horizontal serial port"
    )
    parser.add_argument(
        "--kld7-horizontal-offset",
        type=float,
        default=0.0,
        help="K-LD7 horizontal angle offset in degrees (default: 0.0)",
    )
    args = parser.parse_args()

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

    # Initialize K-LD7 angle radars (if enabled)
    if args.kld7:
        if init_kld7(port=args.kld7_port, orientation="vertical",
                     angle_offset_deg=args.kld7_angle_offset, base_freq=0):
            offset_str = f", offset: {args.kld7_angle_offset:+.1f}°" if args.kld7_angle_offset else ""
            print(f"K-LD7 vertical radar enabled (launch angle{offset_str})")
        else:
            print("ERROR: K-LD7 vertical requested but failed to connect. Exiting.")
            sys.exit(1)

    if args.kld7_horizontal:
        if init_kld7(port=args.kld7_horizontal_port, orientation="horizontal",
                     angle_offset_deg=args.kld7_horizontal_offset, base_freq=2):
            offset_str = f", offset: {args.kld7_horizontal_offset:+.1f}°" if args.kld7_horizontal_offset else ""
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
        if kld7_vertical:
            kld7_vertical.stop()
        if kld7_horizontal:
            kld7_horizontal.stop()
        stop_camera_thread()
        if camera:
            camera.stop()
            camera.close()
        stop_monitor()


if __name__ == "__main__":
    main()
