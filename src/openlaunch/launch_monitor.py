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

from .ops243 import OPS243Radar, SpeedReading, Direction
from .session_logger import get_session_logger


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
        launch_angle_vertical: Vertical launch angle in degrees (from camera)
        launch_angle_horizontal: Horizontal launch angle in degrees (from camera)
        launch_angle_confidence: Confidence in launch angle measurement (0-1)
    """
    ball_speed_mph: float
    timestamp: datetime
    club_speed_mph: Optional[float] = None
    peak_magnitude: Optional[float] = None
    readings: List[SpeedReading] = field(default_factory=list)
    club: ClubType = ClubType.DRIVER
    launch_angle_vertical: Optional[float] = None
    launch_angle_horizontal: Optional[float] = None
    launch_angle_confidence: Optional[float] = None

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
        # Reduce to ±5% if we have launch angle data
        if self.has_launch_angle:
            return (base * 0.95, base * 1.05)
        return (base * 0.90, base * 1.10)

    @property
    def has_launch_angle(self) -> bool:
        """Check if launch angle data is available for this shot."""
        return self.launch_angle_vertical is not None


class LaunchMonitor:
    """
    Golf Launch Monitor using OPS243-A Doppler Radar.

    Detects club head speed and ball speed, providing shot analysis.

    The radar with multi-object reporting (O4) detects both club and ball
    in the same sample window. Club speed is detected first during downswing
    (slower, higher magnitude due to larger radar cross-section), followed
    by ball speed after impact (faster, lower magnitude).

    Separation uses three criteria:
    1. Temporal: Club appears 0-300ms before ball
    2. Speed ratio: Club is 50-85% of ball speed (smash factor 1.1-1.7)
    3. Magnitude: Club head has larger RCS = stronger signal

    Example:
        monitor = LaunchMonitor()
        monitor.start()

        shot = monitor.wait_for_shot(timeout=30)
        if shot:
            print(f"Club Speed: {shot.club_speed_mph:.1f} mph")
            print(f"Ball Speed: {shot.ball_speed_mph:.1f} mph")
            print(f"Smash Factor: {shot.smash_factor:.2f}")
    """

    # Speed thresholds
    MIN_CLUB_SPEED_MPH = 30      # Minimum club speed (allows short game)
    MAX_CLUB_SPEED_MPH = 140     # Maximum realistic club speed
    MIN_BALL_SPEED_MPH = 30      # Minimum ball speed (allows chips/pitches)
    MAX_BALL_SPEED_MPH = 220     # Maximum realistic ball speed

    # Signal filtering
    MIN_MAGNITUDE = 20           # Minimum signal strength to accept reading
    MIN_SHOT_MAGNITUDE = 100     # Minimum peak magnitude for valid shot (filters walking)

    # Shot detection timing
    SHOT_TIMEOUT_SEC = 0.5       # Gap to consider shot complete
    MIN_READINGS_FOR_SHOT = 3    # Minimum readings for valid shot
    MAX_SHOT_DURATION_SEC = 0.3  # Real shots complete within 300ms

    # Club/ball separation parameters
    CLUB_BALL_WINDOW_SEC = 0.3   # Max time window for club before ball
    CLUB_SPEED_MIN_RATIO = 0.50  # Club must be >= 50% of ball speed
    CLUB_SPEED_MAX_RATIO = 0.85  # Club must be <= 85% of ball speed
    SMASH_FACTOR_MIN = 1.1       # Minimum valid smash factor
    SMASH_FACTOR_MAX = 1.7       # Maximum valid smash factor

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
        logger = get_session_logger()

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
            print(f"[FILTER] Speed {reading.speed:.1f} outside range {min_speed}-{self.MAX_BALL_SPEED_MPH}")
            return

        # Only accept outbound readings (ball/club moving away from radar)
        if reading.direction != Direction.OUTBOUND:
            print(f"[FILTER] Direction {reading.direction.value} is not outbound")
            return

        # Filter by minimum magnitude (signal strength)
        if reading.magnitude is not None and reading.magnitude < self.MIN_MAGNITUDE:
            print(f"[FILTER] Magnitude {reading.magnitude:.1f} below minimum {self.MIN_MAGNITUDE}")
            return

        print(f"[ACCEPTED] {reading.speed:.1f} mph {reading.direction.value} mag={reading.magnitude:.1f} - buffered: {len(self._current_readings)}")
        if logger:
            logger.log_accepted_reading(reading)

        # Check if this is part of current shot or new shot
        if self._current_readings and (now - self._last_reading_time) > self.SHOT_TIMEOUT_SEC:
            # Previous shot complete, process it
            print(f"[TIMEOUT] Processing shot with {len(self._current_readings)} readings")
            self._process_shot()

        # Track shot start time
        if not self._current_readings:
            self._shot_start_time = now

        # Add to current readings
        self._current_readings.append(reading)
        self._last_reading_time = now

    def _find_club_speed(
        self,
        readings: List[SpeedReading],
        ball_speed: float,
        ball_time: float
    ) -> Optional[SpeedReading]:
        """
        Find club head reading using temporal and magnitude analysis.

        Args:
            readings: Sorted list of readings (by timestamp)
            ball_speed: Detected ball speed in mph
            ball_time: Timestamp of ball reading

        Returns:
            Club SpeedReading if found, None otherwise
        """
        if len(readings) < 2:
            return None

        # Speed range: club should be 50-85% of ball speed
        club_speed_min = max(self.MIN_CLUB_SPEED_MPH, ball_speed * self.CLUB_SPEED_MIN_RATIO)
        club_speed_max = min(self.MAX_CLUB_SPEED_MPH, ball_speed * self.CLUB_SPEED_MAX_RATIO)

        # Find candidate club readings (before ball, in speed range)
        club_candidates = []
        for r in readings:
            r_time = r.timestamp or 0

            # Must be before the ball reading
            if r_time >= ball_time:
                continue

            # Must be within time window (not too early)
            if ball_time - r_time > self.CLUB_BALL_WINDOW_SEC:
                continue

            # Must be in realistic club speed range
            if not (club_speed_min <= r.speed <= club_speed_max):
                continue

            # Must be less than ball speed
            if r.speed >= ball_speed:
                continue

            club_candidates.append(r)
            print(f"[CLUB CANDIDATE] {r.speed:.1f} mph, mag={r.magnitude}, "
                  f"dt={((ball_time - r_time) * 1000):.0f}ms before ball")

        if not club_candidates:
            return None

        # Select best candidate: prefer highest magnitude (larger RCS = club head)
        candidates_with_mag = [c for c in club_candidates if c.magnitude]

        if candidates_with_mag:
            club_reading = max(candidates_with_mag, key=lambda r: r.magnitude)
            print(f"[CLUB DETECTED] {club_reading.speed:.1f} mph selected by magnitude "
                  f"(mag={club_reading.magnitude})")
        else:
            # No magnitude data - use reading closest in time to ball
            club_reading = max(club_candidates, key=lambda r: r.timestamp or 0)
            print(f"[CLUB DETECTED] {club_reading.speed:.1f} mph selected by timing")

        # Validate smash factor
        smash = ball_speed / club_reading.speed
        if not (self.SMASH_FACTOR_MIN <= smash <= self.SMASH_FACTOR_MAX):
            print(f"[CLUB REJECTED] Smash factor {smash:.2f} outside range "
                  f"{self.SMASH_FACTOR_MIN}-{self.SMASH_FACTOR_MAX}")
            return None

        return club_reading

    def _process_shot(self):
        """
        Process accumulated readings into a shot.

        Uses temporal and magnitude-based analysis to separate club from ball:
        1. Ball speed = peak (maximum) speed in the shot window
        2. Club speed = detected BEFORE ball, lower speed, higher magnitude

        Validates that the readings represent a real golf shot:
        - Sufficient readings clustered in time (<300ms)
        - Peak magnitude above threshold (strong radar return)
        - Ball speed above minimum for golf shots
        """
        if len(self._current_readings) < self.MIN_READINGS_FOR_SHOT:
            print(f"[REJECTED] Only {len(self._current_readings)} readings "
                  f"(need {self.MIN_READINGS_FOR_SHOT})")
            self._current_readings = []
            return

        # Sort readings by timestamp for temporal analysis
        sorted_readings = sorted(self._current_readings, key=lambda r: r.timestamp or 0)

        # Check shot duration - real shots happen fast (<300ms)
        first_time = sorted_readings[0].timestamp or 0
        last_time = sorted_readings[-1].timestamp or 0
        shot_duration = last_time - first_time

        if shot_duration > self.MAX_SHOT_DURATION_SEC:
            print(f"[REJECTED] Shot duration {shot_duration*1000:.0f}ms exceeds "
                  f"max {self.MAX_SHOT_DURATION_SEC*1000:.0f}ms (likely not a golf shot)")
            self._current_readings = []
            return

        # Find ball: peak speed reading
        ball_reading = max(sorted_readings, key=lambda r: r.speed)
        ball_speed = ball_reading.speed
        ball_time = ball_reading.timestamp or 0

        # Get peak magnitude
        magnitudes = [r.magnitude for r in sorted_readings if r.magnitude]
        peak_mag = max(magnitudes) if magnitudes else None

        # Validate peak magnitude - real shots have strong radar returns
        if peak_mag is not None and peak_mag < self.MIN_SHOT_MAGNITUDE:
            print(f"[REJECTED] Peak magnitude {peak_mag:.0f} below minimum "
                  f"{self.MIN_SHOT_MAGNITUDE} (weak signal, likely not a golf shot)")
            self._current_readings = []
            return

        # Validate ball speed - must be a real golf shot speed
        if ball_speed < self.MIN_BALL_SPEED_MPH:
            print(f"[REJECTED] Ball speed {ball_speed:.1f} mph below minimum "
                  f"{self.MIN_BALL_SPEED_MPH} mph (too slow for golf shot)")
            self._current_readings = []
            return

        # Find club speed
        club_speed = None
        if self._detect_club_speed:
            club_reading = self._find_club_speed(sorted_readings, ball_speed, ball_time)
            if club_reading:
                club_speed = club_reading.speed

        print(f"[SHOT ANALYSIS] Ball={ball_speed:.1f} mph, Club={club_speed or 'N/A'}, "
              f"Readings={len(sorted_readings)}")

        shot = Shot(
            ball_speed_mph=ball_speed,
            timestamp=datetime.now(),
            club_speed_mph=club_speed,
            peak_magnitude=peak_mag,
            readings=self._current_readings.copy(),
            club=self._current_club
        )

        self._shots.append(shot)

        if club_speed:
            print(f"[SHOT CREATED] Ball: {ball_speed:.1f} mph, Club: {club_speed:.1f} mph, "
                  f"Smash: {shot.smash_factor:.2f}")
        else:
            print(f"[SHOT CREATED] Ball: {ball_speed:.1f} mph (club not detected)")

        # Log shot to session logger
        logger = get_session_logger()
        if logger:
            readings_data = [
                {"speed": r.speed, "direction": r.direction.value, "magnitude": r.magnitude,
                 "timestamp": r.timestamp}
                for r in self._current_readings
            ]
            logger.log_shot(
                ball_speed_mph=ball_speed,
                club_speed_mph=club_speed,
                smash_factor=shot.smash_factor,
                estimated_carry_yards=shot.estimated_carry_yards,
                club=self._current_club.value,
                peak_magnitude=peak_mag,
                readings_count=len(self._current_readings),
                readings=readings_data
            )

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
