"""
Golf Launch Monitor using OPS243-A Radar.

This module provides the main launch monitor functionality,
detecting golf ball speeds and displaying results.
"""

import time
import statistics
from dataclasses import dataclass, field
from typing import Optional, List, Callable
from datetime import datetime

from .ops243 import OPS243Radar, SpeedReading, Direction


@dataclass
class Shot:
    """Represents a detected golf shot."""
    ball_speed_mph: float
    timestamp: datetime
    peak_magnitude: Optional[float] = None
    readings: List[SpeedReading] = field(default_factory=list)

    @property
    def ball_speed_ms(self) -> float:
        """Ball speed in meters per second."""
        return self.ball_speed_mph * 0.44704

    @property
    def estimated_carry_yards(self) -> float:
        """
        Rough carry distance estimate based on ball speed.

        This is a simplified estimate assuming:
        - Optimal launch angle (~12-15 degrees)
        - Driver-like spin rates
        - Sea level conditions

        Real launch monitors use additional data (launch angle, spin)
        for accurate distance calculations.
        """
        # Simplified: roughly 2.5 yards per mph of ball speed for driver
        # This is a rough approximation!
        return self.ball_speed_mph * 2.5


class LaunchMonitor:
    """
    Golf Launch Monitor using OPS243-A Doppler Radar.

    Detects golf ball speeds and provides shot analysis.

    Example:
        monitor = LaunchMonitor()
        monitor.start()

        # Wait for a shot
        shot = monitor.wait_for_shot(timeout=30)
        if shot:
            print(f"Ball Speed: {shot.ball_speed_mph:.1f} mph")
            print(f"Est. Carry: {shot.estimated_carry_yards:.0f} yards")
    """

    # Detection parameters
    MIN_BALL_SPEED_MPH = 30      # Minimum realistic golf ball speed
    MAX_BALL_SPEED_MPH = 220     # Maximum realistic ball speed
    SHOT_TIMEOUT_SEC = 0.5       # Gap between readings to consider shot complete
    MIN_READINGS_FOR_SHOT = 2    # Minimum readings to validate a shot

    def __init__(self, port: Optional[str] = None):
        """
        Initialize launch monitor.

        Args:
            port: Serial port for radar. Auto-detect if None.
        """
        self.radar = OPS243Radar(port=port)
        self._running = False
        self._current_readings: List[SpeedReading] = []
        self._last_reading_time: float = 0
        self._shots: List[Shot] = []
        self._shot_callback: Optional[Callable[[Shot], None]] = None
        self._live_callback: Optional[Callable[[SpeedReading], None]] = None

    def connect(self) -> bool:
        """
        Connect to radar and configure for golf.

        Returns:
            True if successful
        """
        self.radar.connect()
        self.radar.configure_for_golf()
        return True

    def disconnect(self):
        """Disconnect from radar."""
        self.stop()
        self.radar.disconnect()

    def get_radar_info(self) -> dict:
        """Get radar module information."""
        return self.radar.get_info()

    def start(self, shot_callback: Optional[Callable[[Shot], None]] = None,
              live_callback: Optional[Callable[[SpeedReading], None]] = None):
        """
        Start monitoring for shots.

        Args:
            shot_callback: Called when a complete shot is detected
            live_callback: Called for each raw speed reading
        """
        self._shot_callback = shot_callback
        self._live_callback = live_callback
        self._running = True
        self.radar.start_streaming(self._on_reading)

    def stop(self):
        """Stop monitoring."""
        self._running = False
        self.radar.stop_streaming()

    def _on_reading(self, reading: SpeedReading):
        """Process incoming speed readings."""
        now = time.time()

        # Call live callback if set
        if self._live_callback:
            self._live_callback(reading)

        # Filter by realistic ball speeds
        if not (self.MIN_BALL_SPEED_MPH <= reading.speed <= self.MAX_BALL_SPEED_MPH):
            return

        # Check if this is part of current shot or new shot
        if self._current_readings and (now - self._last_reading_time) > self.SHOT_TIMEOUT_SEC:
            # Previous shot complete, process it
            self._process_shot()

        # Add to current readings
        self._current_readings.append(reading)
        self._last_reading_time = now

    def _process_shot(self):
        """Process accumulated readings into a shot."""
        if len(self._current_readings) < self.MIN_READINGS_FOR_SHOT:
            self._current_readings = []
            return

        # Get peak speed (ball speed is typically the fastest reading)
        speeds = [r.speed for r in self._current_readings]
        peak_speed = max(speeds)

        # Get peak magnitude if available
        magnitudes = [r.magnitude for r in self._current_readings if r.magnitude]
        peak_mag = max(magnitudes) if magnitudes else None

        shot = Shot(
            ball_speed_mph=peak_speed,
            timestamp=datetime.now(),
            peak_magnitude=peak_mag,
            readings=self._current_readings.copy()
        )

        self._shots.append(shot)

        # Callback
        if self._shot_callback:
            self._shot_callback(shot)

        # Clear for next shot
        self._current_readings = []

    def wait_for_shot(self, timeout: float = 60) -> Optional[Shot]:
        """
        Wait for a shot to be detected.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Shot object or None if timeout
        """
        shot_detected = []

        def on_shot(shot):
            shot_detected.append(shot)

        original_callback = self._shot_callback
        self._shot_callback = on_shot

        start = time.time()
        while not shot_detected and (time.time() - start) < timeout:
            time.sleep(0.1)

        self._shot_callback = original_callback

        return shot_detected[0] if shot_detected else None

    def get_session_stats(self) -> dict:
        """
        Get statistics for the current session.

        Returns:
            Dict with shot count, averages, etc.
        """
        if not self._shots:
            return {
                "shot_count": 0,
                "avg_ball_speed": 0,
                "max_ball_speed": 0,
                "min_ball_speed": 0,
                "avg_carry_est": 0
            }

        speeds = [s.ball_speed_mph for s in self._shots]

        return {
            "shot_count": len(self._shots),
            "avg_ball_speed": statistics.mean(speeds),
            "max_ball_speed": max(speeds),
            "min_ball_speed": min(speeds),
            "std_dev": statistics.stdev(speeds) if len(speeds) > 1 else 0,
            "avg_carry_est": statistics.mean([s.estimated_carry_yards for s in self._shots])
        }

    def get_shots(self) -> List[Shot]:
        """Get all detected shots."""
        return self._shots.copy()

    def clear_session(self):
        """Clear all recorded shots."""
        self._shots = []

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False


def main():
    """CLI entry point for launch monitor."""
    import argparse

    parser = argparse.ArgumentParser(description="Golf Launch Monitor")
    parser.add_argument("--port", "-p", help="Serial port (auto-detect if not specified)")
    parser.add_argument("--live", "-l", action="store_true", help="Show live readings")
    parser.add_argument("--info", "-i", action="store_true", help="Show radar info and exit")
    args = parser.parse_args()

    print("=" * 50)
    print("  OpenLaunch - Golf Launch Monitor")
    print("  Using OPS243-A Doppler Radar")
    print("=" * 50)
    print()

    try:
        with LaunchMonitor(port=args.port) as monitor:
            info = monitor.get_radar_info()
            print(f"Connected to: {info.get('Product', 'OPS243')}")
            print(f"Firmware: {info.get('Version', 'unknown')}")
            print()

            if args.info:
                print("Radar Configuration:")
                for key, value in info.items():
                    print(f"  {key}: {value}")
                return

            print("Ready! Swing when ready...")
            print("Press Ctrl+C to stop")
            print()

            def on_shot(shot):
                print("-" * 40)
                print(f"  Ball Speed: {shot.ball_speed_mph:.1f} mph")
                print(f"  Est. Carry: {shot.estimated_carry_yards:.0f} yards")
                print(f"  Readings: {len(shot.readings)}")
                if shot.peak_magnitude:
                    print(f"  Signal Strength: {shot.peak_magnitude:.0f}")
                print("-" * 40)
                print()

            def on_live(reading):
                if args.live:
                    print(f"  [{reading.speed:.1f} {reading.unit}]", end="\r")

            monitor.start(shot_callback=on_shot, live_callback=on_live)

            try:
                while True:
                    time.sleep(0.1)
            except KeyboardInterrupt:
                print("\n")
                stats = monitor.get_session_stats()
                if stats["shot_count"] > 0:
                    print("Session Summary:")
                    print(f"  Shots: {stats['shot_count']}")
                    print(f"  Avg Ball Speed: {stats['avg_ball_speed']:.1f} mph")
                    print(f"  Max Ball Speed: {stats['max_ball_speed']:.1f} mph")
                    print(f"  Avg Est. Carry: {stats['avg_carry_est']:.0f} yards")
                print("\nGoodbye!")

    except ConnectionError as e:
        print(f"Error: {e}")
        print("\nMake sure the OPS243-A is connected via USB.")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
