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
from enum import Enum

from .ops243 import OPS243Radar, SpeedReading


class ClubType(Enum):
    """Golf club types for distance estimation."""
    DRIVER = "driver"
    WOOD_3 = "3-wood"
    WOOD_5 = "5-wood"
    HYBRID = "hybrid"
    IRON_3 = "3-iron"
    IRON_4 = "4-iron"
    IRON_5 = "5-iron"
    IRON_6 = "6-iron"
    IRON_7 = "7-iron"
    IRON_8 = "8-iron"
    IRON_9 = "9-iron"
    PW = "pw"
    UNKNOWN = "unknown"


def estimate_carry_distance(ball_speed_mph: float, club: ClubType = ClubType.DRIVER) -> float:
    """
    Estimate carry distance from ball speed using TrackMan-derived data.

    This uses interpolation from real-world data assuming optimal launch
    conditions (10-14° launch angle, appropriate spin for ball speed).

    Data sources:
    - TrackMan PGA Tour averages
    - pitchmarks.com ball speed to distance tables

    Args:
        ball_speed_mph: Ball speed in mph
        club: Club type (affects the model used)

    Returns:
        Estimated carry distance in yards

    Note:
        Without launch angle and spin rate, this is an approximation.
        Actual distance can vary ±10-15% based on:
        - Launch angle (optimal: 10-14° for driver)
        - Spin rate (optimal: 2000-3000 rpm for driver)
        - Weather conditions
        - Altitude
    """
    # Driver ball speed to carry distance lookup table
    # Based on TrackMan data assuming optimal launch conditions
    # Format: (ball_speed_mph, carry_yards_low, carry_yards_high)
    DRIVER_TABLE = [
        (100, 130, 142),
        (110, 157, 170),
        (120, 183, 197),
        (130, 207, 223),
        (140, 231, 249),
        (150, 254, 275),
        (160, 276, 301),
        (167, 275, 285),  # PGA Tour average
        (170, 298, 325),
        (180, 320, 349),
        (190, 342, 372),
        (200, 360, 389),
        (210, 383, 408),
    ]

    # Adjustment factors for different clubs (relative to driver)
    # Based on typical smash factors and launch conditions
    CLUB_FACTORS = {
        ClubType.DRIVER: 1.0,
        ClubType.WOOD_3: 0.96,    # Slightly less efficient
        ClubType.WOOD_5: 0.93,
        ClubType.HYBRID: 0.90,
        ClubType.IRON_3: 0.87,
        ClubType.IRON_4: 0.85,
        ClubType.IRON_5: 0.82,
        ClubType.IRON_6: 0.79,
        ClubType.IRON_7: 0.76,
        ClubType.IRON_8: 0.73,
        ClubType.IRON_9: 0.70,
        ClubType.PW: 0.67,
        ClubType.UNKNOWN: 1.0,
    }

    # Interpolate from driver table
    if ball_speed_mph <= DRIVER_TABLE[0][0]:
        # Below minimum - extrapolate linearly
        ratio = ball_speed_mph / DRIVER_TABLE[0][0]
        base_carry = (DRIVER_TABLE[0][1] + DRIVER_TABLE[0][2]) / 2
        carry = base_carry * ratio
    elif ball_speed_mph >= DRIVER_TABLE[-1][0]:
        # Above maximum - extrapolate conservatively
        # Use ~1.8 yards per mph above 210 mph
        base_carry = (DRIVER_TABLE[-1][1] + DRIVER_TABLE[-1][2]) / 2
        carry = base_carry + (ball_speed_mph - DRIVER_TABLE[-1][0]) * 1.8
    else:
        # Interpolate between table entries
        for i in range(len(DRIVER_TABLE) - 1):
            if DRIVER_TABLE[i][0] <= ball_speed_mph < DRIVER_TABLE[i + 1][0]:
                # Linear interpolation
                speed_low, carry_low_min, carry_low_max = DRIVER_TABLE[i]
                speed_high, carry_high_min, carry_high_max = DRIVER_TABLE[i + 1]

                # Use midpoint of ranges
                carry_low = (carry_low_min + carry_low_max) / 2
                carry_high = (carry_high_min + carry_high_max) / 2

                # Interpolate
                t = (ball_speed_mph - speed_low) / (speed_high - speed_low)
                carry = carry_low + t * (carry_high - carry_low)
                break
        else:
            # Fallback (shouldn't reach here)
            carry = ball_speed_mph * 1.65

    # Apply club factor
    factor = CLUB_FACTORS.get(club, 1.0)
    return carry * factor


@dataclass
class Shot:
    """
    Represents a detected golf shot with ball and club data.

    Attributes:
        ball_speed_mph: Peak ball speed detected (mph)
        club_speed_mph: Peak club head speed detected (mph), if available
        smash_factor: Ratio of ball speed to club speed (typically 1.4-1.5 for driver)
        timestamp: When the shot was detected
        peak_magnitude: Signal strength of strongest reading
        readings: All raw speed readings for this shot
        club: Club type for distance estimation
    """
    ball_speed_mph: float
    timestamp: datetime
    club_speed_mph: Optional[float] = None
    peak_magnitude: Optional[float] = None
    readings: List[SpeedReading] = field(default_factory=list)
    club: ClubType = ClubType.DRIVER

    @property
    def ball_speed_ms(self) -> float:
        """Ball speed in meters per second."""
        return self.ball_speed_mph * 0.44704

    @property
    def club_speed_ms(self) -> Optional[float]:
        """Club speed in meters per second."""
        if self.club_speed_mph is None:
            return None
        return self.club_speed_mph * 0.44704

    @property
    def smash_factor(self) -> Optional[float]:
        """
        Smash factor: ratio of ball speed to club speed.

        Indicates quality of contact:
        - Driver: 1.44-1.50 (optimal)
        - Irons: 1.30-1.38
        - Wedges: 1.20-1.25

        Returns:
            Smash factor or None if club speed not available
        """
        if self.club_speed_mph is None or self.club_speed_mph == 0:
            return None
        return self.ball_speed_mph / self.club_speed_mph

    @property
    def estimated_carry_yards(self) -> float:
        """
        Estimated carry distance based on ball speed and club type.

        Uses TrackMan-derived lookup table with interpolation, assuming
        optimal launch conditions (10-14° launch angle for driver).

        Without launch angle and spin data, actual distance may vary ±10-15%.
        """
        return estimate_carry_distance(self.ball_speed_mph, self.club)

    @property
    def estimated_carry_range(self) -> tuple:
        """
        Return (min, max) carry distance estimate to show uncertainty.

        Returns:
            Tuple of (low_estimate, high_estimate) in yards
        """
        base = self.estimated_carry_yards
        # ±10% uncertainty without launch angle/spin data
        return (base * 0.90, base * 1.10)


class LaunchMonitor:
    """
    Golf Launch Monitor using OPS243-A Doppler Radar.

    Detects club head speed and ball speed, providing shot analysis.

    The radar detects both club and ball as they move away (outbound direction).
    Club speed is detected first (slower, 70-130 mph), followed by ball speed
    (faster, 100-190+ mph). The system separates these based on timing and
    speed characteristics.

    Example:
        monitor = LaunchMonitor()
        monitor.start()

        # Wait for a shot
        shot = monitor.wait_for_shot(timeout=30)
        if shot:
            print(f"Club Speed: {shot.club_speed_mph:.1f} mph")
            print(f"Ball Speed: {shot.ball_speed_mph:.1f} mph")
            print(f"Smash Factor: {shot.smash_factor:.2f}")
            print(f"Est. Carry: {shot.estimated_carry_yards:.0f} yards")
    """

    # Detection parameters
    MIN_CLUB_SPEED_MPH = 40      # Minimum realistic club head speed
    MAX_CLUB_SPEED_MPH = 140     # Maximum realistic club speed (long drive pros)
    MIN_BALL_SPEED_MPH = 60      # Minimum realistic golf ball speed
    MAX_BALL_SPEED_MPH = 220     # Maximum realistic ball speed
    SHOT_TIMEOUT_SEC = 0.5       # Gap between readings to consider shot complete
    MIN_READINGS_FOR_SHOT = 2    # Minimum readings to validate a shot
    CLUB_BALL_GAP_SEC = 0.05     # Min gap between club and ball detection (50ms)
    CLUB_BALL_WINDOW_SEC = 0.3   # Max time window for club+ball to be same shot

    def __init__(self, port: Optional[str] = None, detect_club_speed: bool = True):
        """
        Initialize launch monitor.

        Args:
            port: Serial port for radar. Auto-detect if None.
            detect_club_speed: If True, attempt to detect club head speed
                              before ball speed. Requires radar to see club.
        """
        self.radar = OPS243Radar(port=port)
        self._running = False
        self._detect_club_speed = detect_club_speed
        self._current_readings: List[SpeedReading] = []
        self._last_reading_time: float = 0
        self._shot_start_time: float = 0
        self._shots: List[Shot] = []
        self._shot_callback: Optional[Callable[[Shot], None]] = None
        self._live_callback: Optional[Callable[[SpeedReading], None]] = None
        self._current_club: ClubType = ClubType.DRIVER

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
        # Process any pending readings
        if self._current_readings:
            self._process_shot()

    def _on_reading(self, reading: SpeedReading):
        """Process incoming speed readings."""
        now = time.time()

        # Call live callback if set
        if self._live_callback:
            self._live_callback(reading)

        # Determine valid speed range based on detection mode
        if self._detect_club_speed:
            # Accept club speeds (40-140 mph) and ball speeds (60-220 mph)
            min_speed = self.MIN_CLUB_SPEED_MPH
        else:
            # Only accept ball speeds
            min_speed = self.MIN_BALL_SPEED_MPH

        # Filter by realistic speeds
        if not min_speed <= reading.speed <= self.MAX_BALL_SPEED_MPH:
            return

        # Check if this is part of current shot or new shot
        if self._current_readings and (now - self._last_reading_time) > self.SHOT_TIMEOUT_SEC:
            # Previous shot complete, process it
            self._process_shot()

        # Track shot start time
        if not self._current_readings:
            self._shot_start_time = now

        # Add to current readings
        self._current_readings.append(reading)
        self._last_reading_time = now

    def _process_shot(self):
        """
        Process accumulated readings into a shot.

        Separates club speed from ball speed based on:
        1. Ball speed is always higher than club speed (smash factor ~1.5)
        2. Club is detected first, ball immediately after
        3. Typical club: 70-130 mph, ball: 100-190 mph
        """
        if len(self._current_readings) < self.MIN_READINGS_FOR_SHOT:
            self._current_readings = []
            return

        speeds = [r.speed for r in self._current_readings]
        peak_speed = max(speeds)

        # Get peak magnitude if available
        magnitudes = [r.magnitude for r in self._current_readings if r.magnitude]
        peak_mag = max(magnitudes) if magnitudes else None

        # Try to separate club speed from ball speed
        club_speed = None

        if self._detect_club_speed and len(speeds) >= 2:
            # Strategy: Ball speed is the max, club speed is likely in the
            # lower range detected before the ball.
            #
            # Look for readings that could be club head:
            # - Below typical ball speed threshold
            # - Occurred before the peak ball speed reading
            #
            # Heuristic: Club speed should be roughly ball_speed / 1.45
            # (smash factor), so we look for speeds in that range.

            expected_club_speed = peak_speed / 1.45  # Expected based on smash factor
            club_speed_tolerance = 20  # mph tolerance

            # Find readings that could be club (within expected range)
            club_speed_min = expected_club_speed - club_speed_tolerance
            club_speed_max = expected_club_speed + club_speed_tolerance
            potential_club_speeds = [
                s for s in speeds
                if club_speed_min <= s <= club_speed_max
                and s < peak_speed * 0.85  # Must be significantly less than ball speed
            ]

            if potential_club_speeds:
                # Use the highest reading in the club speed range
                club_speed = max(potential_club_speeds)

                # Validate: club speed should be realistic
                if not self.MIN_CLUB_SPEED_MPH <= club_speed <= self.MAX_CLUB_SPEED_MPH:
                    club_speed = None

        # Ball speed is the peak
        ball_speed = peak_speed

        shot = Shot(
            ball_speed_mph=ball_speed,
            timestamp=datetime.now(),
            club_speed_mph=club_speed,
            peak_magnitude=peak_mag,
            readings=self._current_readings.copy(),
            club=self._current_club
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
                "avg_club_speed": None,
                "avg_smash_factor": None,
                "avg_carry_est": 0
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
            "avg_carry_est": statistics.mean([s.estimated_carry_yards for s in self._shots])
        }

    def get_shots(self) -> List[Shot]:
        """Get all detected shots."""
        return self._shots.copy()

    def clear_session(self):
        """Clear all recorded shots."""
        self._shots = []

    def set_club(self, club: ClubType):
        """Set the current club for future shots."""
        self._current_club = club

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
                return 0

            print("Ready! Swing when ready...")
            print("Press Ctrl+C to stop")
            print()

            def on_shot(shot):
                carry_low, carry_high = shot.estimated_carry_range
                print("-" * 40)
                if shot.club_speed_mph:
                    print(f"  Club Speed:   {shot.club_speed_mph:.1f} mph")
                print(f"  Ball Speed:   {shot.ball_speed_mph:.1f} mph")
                if shot.smash_factor:
                    print(f"  Smash Factor: {shot.smash_factor:.2f}")
                print(f"  Est. Carry:   {shot.estimated_carry_yards:.0f} yards")
                print(f"  Range:        {carry_low:.0f}-{carry_high:.0f} yards")
                if shot.peak_magnitude:
                    print(f"  Signal:       {shot.peak_magnitude:.0f}")
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
                    print(f"  Shots:          {stats['shot_count']}")
                    if stats["avg_club_speed"]:
                        print(f"  Avg Club Speed: {stats['avg_club_speed']:.1f} mph")
                    print(f"  Avg Ball Speed: {stats['avg_ball_speed']:.1f} mph")
                    print(f"  Max Ball Speed: {stats['max_ball_speed']:.1f} mph")
                    if stats["avg_smash_factor"]:
                        print(f"  Avg Smash:      {stats['avg_smash_factor']:.2f}")
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
    import sys
    sys.exit(main())
