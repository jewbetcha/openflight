"""
WebSocket server for OpenLaunch UI.

Provides real-time shot data to the web frontend via Flask-SocketIO.
"""

import json
import os
import random
import statistics
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from flask import Flask, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS

from .launch_monitor import LaunchMonitor, Shot, ClubType
from .ops243 import SpeedReading


app = Flask(__name__, static_folder="../../ui/dist", static_url_path="")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Global state
monitor: Optional["LaunchMonitor | MockLaunchMonitor"] = None
mock_mode: bool = False
debug_mode: bool = False
debug_log_file = None
debug_log_path: Optional[Path] = None


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
    }


@app.route("/")
def index():
    """Serve the React app."""
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_files(path):
    """Serve static files."""
    return send_from_directory(app.static_folder, path)


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
    shot_data = shot_to_dict(shot)
    stats = monitor.get_session_stats() if monitor else {}

    # Log shot details
    log_data = {"shot": shot_data, "session_stats": stats}
    print(f"[SHOT] {json.dumps(log_data)}")

    socketio.emit("shot", {"shot": shot_data, "stats": stats})


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
    print(f"Server starting at http://{args.host}:{args.web_port}")
    print()

    try:
        socketio.run(app, host=args.host, port=args.web_port, debug=args.debug, allow_unsafe_werkzeug=True)
    finally:
        stop_monitor()


if __name__ == "__main__":
    main()
