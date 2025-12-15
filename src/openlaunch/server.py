"""
WebSocket server for OpenLaunch UI.

Provides real-time shot data to the web frontend via Flask-SocketIO.
"""

import json
import random
import statistics
from datetime import datetime
from typing import Optional, List

from flask import Flask, send_from_directory
from flask_socketio import SocketIO
from flask_cors import CORS

from .launch_monitor import LaunchMonitor, Shot, ClubType


app = Flask(__name__, static_folder="../../ui/dist", static_url_path="")
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
monitor: Optional["LaunchMonitor | MockLaunchMonitor"] = None
mock_mode: bool = False


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


@socketio.on("connect")
def handle_connect():
    """Handle client connection."""
    print("Client connected")
    if monitor:
        stats = monitor.get_session_stats()
        shots = [shot_to_dict(s) for s in monitor.get_shots()]
        socketio.emit("session_state", {"stats": stats, "shots": shots, "mock_mode": mock_mode})


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
    monitor.start(shot_callback=on_shot_detected)


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
        socketio.run(app, host=args.host, port=args.web_port, debug=args.debug)
    finally:
        stop_monitor()


if __name__ == "__main__":
    main()
