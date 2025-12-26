"""
WebSocket server for OpenLaunch UI.

Provides real-time shot data to the web frontend via Flask-SocketIO.
"""

import json
import os
import random
import statistics
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from flask import Flask, send_from_directory, Response
from flask_socketio import SocketIO
from flask_cors import CORS

from .launch_monitor import LaunchMonitor, Shot, ClubType
from .ops243 import SpeedReading

# Camera imports (optional)
try:
    import cv2
    import numpy as np
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
monitor: Optional["LaunchMonitor | MockLaunchMonitor"] = None
mock_mode: bool = False
debug_mode: bool = False
debug_log_file = None
debug_log_path: Optional[Path] = None

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
        # Launch angle from camera
        "launch_angle_vertical": shot.launch_angle_vertical,
        "launch_angle_horizontal": shot.launch_angle_horizontal,
        "launch_angle_confidence": shot.launch_angle_confidence,
    }


@app.route("/")
def index():
    """Serve the React app."""
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_files(path):
    """Serve static files."""
    return send_from_directory(app.static_folder, path)


# Camera functions
def init_camera(model_path: str = "models/golf_ball_yolo11n.onnx", imgsz: int = 256):
    """Initialize camera and YOLO tracker."""
    global camera, camera_tracker  # pylint: disable=global-statement

    if not CV2_AVAILABLE:
        print("OpenCV not available - camera disabled")
        return False

    if not PICAMERA_AVAILABLE:
        print("picamera2 not available - camera disabled")
        return False

    try:
        # Initialize PiCamera
        camera = Picamera2()
        config = camera.create_video_configuration(
            main={"size": (640, 480), "format": "RGB888"},
            buffer_count=2,
            controls={"FrameRate": 30}
        )
        camera.configure(config)
        camera.start()
        time.sleep(0.5)

        # Initialize YOLO tracker
        if os.path.exists(model_path):
            camera_tracker = CameraTracker(model_path=model_path)
            print(f"Camera initialized with model: {model_path}")
        else:
            # Try default models
            for fallback in ["models/golf_ball_yolo11n.pt", "yolov8n.pt"]:
                if os.path.exists(fallback):
                    camera_tracker = CameraTracker(model_path=fallback)
                    print(f"Camera initialized with fallback model: {fallback}")
                    break
            else:
                print("No YOLO model found - detection disabled")
                camera_tracker = None

        return True

    except Exception as e:
        print(f"Failed to initialize camera: {e}")
        camera = None
        camera_tracker = None
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
                if new_detected != ball_detected or abs(new_confidence - ball_detection_confidence) > 0.05:
                    ball_detected = new_detected
                    ball_detection_confidence = new_confidence
                    socketio.emit("ball_detection", {
                        "detected": ball_detected,
                        "confidence": round(ball_detection_confidence, 2),
                    })

                # Get debug frame with overlay if streaming
                if camera_streaming:
                    frame = camera_tracker.get_debug_frame(frame)

            # Encode frame for streaming
            if camera_streaming:
                # Convert RGB to BGR for cv2
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                _, jpeg = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 70])
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
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            time.sleep(0.03)


@app.route("/camera/stream")
def camera_stream():
    """MJPEG stream endpoint."""
    if not camera_enabled or not camera_streaming:
        return "Camera not available", 503

    return Response(
        generate_mjpeg(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@socketio.on("toggle_camera")
def handle_toggle_camera():
    """Toggle camera on/off."""
    global camera_enabled  # pylint: disable=global-statement

    if not camera:
        socketio.emit("camera_status", {
            "enabled": False,
            "available": False,
            "error": "Camera not initialized"
        })
        return

    camera_enabled = not camera_enabled
    socketio.emit("camera_status", {
        "enabled": camera_enabled,
        "available": True,
        "streaming": camera_streaming,
    })
    print(f"Camera {'enabled' if camera_enabled else 'disabled'}")


@socketio.on("toggle_camera_stream")
def handle_toggle_camera_stream():
    """Toggle camera streaming on/off."""
    global camera_streaming  # pylint: disable=global-statement

    if not camera or not camera_enabled:
        socketio.emit("camera_status", {
            "enabled": camera_enabled,
            "available": camera is not None,
            "streaming": False,
            "error": "Camera not enabled"
        })
        return

    camera_streaming = not camera_streaming
    socketio.emit("camera_status", {
        "enabled": camera_enabled,
        "available": True,
        "streaming": camera_streaming,
    })
    print(f"Camera streaming {'started' if camera_streaming else 'stopped'}")


@socketio.on("get_camera_status")
def handle_get_camera_status():
    """Get current camera status."""
    socketio.emit("camera_status", {
        "enabled": camera_enabled,
        "available": camera is not None,
        "streaming": camera_streaming,
        "ball_detected": ball_detected,
        "ball_confidence": round(ball_detection_confidence, 2),
    })


def start_debug_logging():
    """Start logging raw readings to a file."""
    global debug_log_file, debug_log_path  # pylint: disable=global-statement

    # Create logs directory
    log_dir = Path.home() / "openlaunch_logs"
    log_dir.mkdir(exist_ok=True)

    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_log_path = log_dir / f"debug_{timestamp}.jsonl"
    debug_log_file = open(debug_log_path, "w")  # pylint: disable=consider-using-with

    print(f"Debug logging to: {debug_log_path}")
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
            "speed": reading.speed,
            "direction": reading.direction.value,
            "magnitude": reading.magnitude,
            "unit": reading.unit,
        }
        debug_log_file.write(json.dumps(entry) + "\n")
        debug_log_file.flush()


def on_live_reading(reading: SpeedReading):
    """Callback for live radar readings - used in debug mode."""
    # Log to file if debug mode is on
    if debug_mode:
        log_debug_reading(reading)

        # Emit to UI
        socketio.emit("debug_reading", {
            "speed": reading.speed,
            "direction": reading.direction.value,
            "magnitude": reading.magnitude,
            "timestamp": datetime.now().isoformat(),
        })


@socketio.on("connect")
def handle_connect():
    """Handle client connection."""
    print("Client connected")
    if monitor:
        stats = monitor.get_session_stats()
        shots = [shot_to_dict(s) for s in monitor.get_shots()]
        socketio.emit("session_state", {
            "stats": stats,
            "shots": shots,
            "mock_mode": mock_mode,
            "debug_mode": debug_mode,
            "camera_available": camera is not None,
            "camera_enabled": camera_enabled,
            "camera_streaming": camera_streaming,
            "ball_detected": ball_detected,
        })


@socketio.on("disconnect")
def handle_disconnect():
    """Handle client disconnection."""
    print("Client disconnected")


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
    socketio.emit("debug_status", {
        "enabled": debug_mode,
        "log_path": str(debug_log_path) if debug_log_path else None,
    })


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

        # Log config change if debug mode is on
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


def on_shot_detected(shot: Shot):
    """Callback when a shot is detected - emit to all clients."""
    global ball_detected, ball_detection_confidence  # pylint: disable=global-statement

    # Capture camera tracking data if available
    camera_data = None
    if camera_tracker and camera_enabled:
        launch_angle = camera_tracker.calculate_launch_angle()
        if launch_angle:
            # Update shot with launch angle data
            shot.launch_angle_vertical = launch_angle.vertical
            shot.launch_angle_horizontal = launch_angle.horizontal
            shot.launch_angle_confidence = launch_angle.confidence

            camera_data = {
                "launch_angle_vertical": launch_angle.vertical,
                "launch_angle_horizontal": launch_angle.horizontal,
                "launch_angle_confidence": launch_angle.confidence,
                "positions_tracked": len(launch_angle.positions),
                "launch_detected": camera_tracker.launch_detected,
            }

        # Reset camera tracker for next shot
        camera_tracker.reset()
        ball_detected = False
        ball_detection_confidence = 0.0

    shot_data = shot_to_dict(shot)
    stats = monitor.get_session_stats() if monitor else {}

    # Create debug log entry
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

    # Log shot details
    print(f"[SHOT] {json.dumps(debug_log_entry)}")

    # Log to debug file if enabled
    if debug_mode and debug_log_file:
        debug_log_file.write(json.dumps(debug_log_entry) + "\n")
        debug_log_file.flush()

    # Emit shot to clients
    socketio.emit("shot", {"shot": shot_data, "stats": stats})

    # Emit debug shot log if debug mode is on
    if debug_mode:
        socketio.emit("debug_shot", debug_log_entry)


def start_monitor(port: Optional[str] = None, mock: bool = False):
    """Start the launch monitor."""
    global monitor, mock_mode  # pylint: disable=global-statement

    mock_mode = mock
    if mock:
        # Mock mode for testing without radar
        monitor = MockLaunchMonitor()
    else:
        monitor = LaunchMonitor(port=port)

    monitor.connect()
    monitor.start(shot_callback=on_shot_detected, live_callback=on_live_reading)


def stop_monitor():
    """Stop the launch monitor."""
    global monitor  # pylint: disable=global-statement
    if monitor:
        monitor.stop()
        monitor.disconnect()
        monitor = None


class MockLaunchMonitor:
    """Mock launch monitor for UI development without radar hardware."""

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
        # Typical ball speeds by club (TrackMan averages for amateur golfers)
        # Format: (avg_ball_speed, std_dev, typical_smash_factor)
        club_ball_speeds = {
            ClubType.DRIVER: (143, 12, 1.45),
            ClubType.WOOD_3: (135, 10, 1.42),
            ClubType.WOOD_5: (128, 10, 1.40),
            ClubType.HYBRID: (122, 9, 1.38),
            ClubType.IRON_3: (118, 9, 1.35),
            ClubType.IRON_4: (114, 8, 1.33),
            ClubType.IRON_5: (110, 8, 1.31),
            ClubType.IRON_6: (105, 7, 1.29),
            ClubType.IRON_7: (100, 7, 1.27),
            ClubType.IRON_8: (94, 6, 1.25),
            ClubType.IRON_9: (88, 6, 1.23),
            ClubType.PW: (82, 5, 1.21),
            ClubType.UNKNOWN: (120, 15, 1.35),
        }

        avg_speed, std_dev, smash = club_ball_speeds.get(
            self._current_club, (120, 15, 1.35)
        )

        # Generate realistic ball speed with normal distribution
        if ball_speed is None:
            ball_speed = random.gauss(avg_speed, std_dev)
            ball_speed = max(50, min(200, ball_speed))  # Clamp to realistic range

        # Calculate club speed from smash factor with small variance
        smash_factor = smash + random.uniform(-0.03, 0.03)
        club_speed = ball_speed / smash_factor

        shot = Shot(
            ball_speed_mph=ball_speed,
            club_speed_mph=club_speed,
            timestamp=datetime.now(),
            club=self._current_club,
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
            "avg_carry_est": statistics.mean(
                [s.estimated_carry_yards for s in self._shots]
            ),
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

    parser = argparse.ArgumentParser(description="OpenLaunch UI Server")
    parser.add_argument("--port", "-p", help="Serial port for radar")
    parser.add_argument(
        "--mock", "-m", action="store_true", help="Run in mock mode without radar"
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--web-port", type=int, default=8080, help="Web server port (default: 8080)"
    )
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug mode")
    parser.add_argument(
        "--camera", "-c", action="store_true", help="Enable camera for ball detection"
    )
    parser.add_argument(
        "--camera-model", default="models/golf_ball_yolo11n.onnx",
        help="Path to YOLO model for ball detection"
    )
    args = parser.parse_args()

    print("=" * 50)
    print("  OpenLaunch UI Server")
    print("=" * 50)
    print()

    # Start the monitor
    start_monitor(port=args.port, mock=args.mock)

    if args.mock:
        print("Running in MOCK mode - no radar required")
        print("Simulate shots via WebSocket or API")

    # Initialize camera if requested
    if args.camera:
        if init_camera(model_path=args.camera_model):
            start_camera_thread()
            print(f"Camera enabled with model: {args.camera_model}")
        else:
            print("Camera initialization failed - running without camera")

    print(f"Server starting at http://{args.host}:{args.web_port}")
    print()

    try:
        socketio.run(app, host=args.host, port=args.web_port, debug=args.debug, allow_unsafe_werkzeug=True)
    finally:
        stop_camera_thread()
        if camera:
            camera.stop()
            camera.close()
        stop_monitor()


if __name__ == "__main__":
    main()
