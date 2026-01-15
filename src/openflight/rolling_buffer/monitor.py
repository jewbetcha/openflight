"""
Rolling Buffer Monitor - Alternative to LaunchMonitor for rolling buffer mode.

Provides the same interface as LaunchMonitor but uses rolling buffer capture
and post-processing for higher resolution speed data and spin detection.
"""

import logging
import statistics
import threading
import time
from datetime import datetime
from typing import Callable, List, Optional

from ..ops243 import OPS243Radar, SpeedReading, Direction
from ..launch_monitor import Shot, ClubType, estimate_carry_distance
from ..session_logger import get_session_logger
from .types import IQCapture, ProcessedCapture
from .processor import RollingBufferProcessor
from .trigger import TriggerStrategy, create_trigger

logger = logging.getLogger("openflight.rolling_buffer.monitor")


def get_optimal_spin_for_ball_speed(ball_speed_mph: float, club: ClubType = ClubType.DRIVER) -> float:
    """
    Get optimal spin rate for a given ball speed.

    Based on TrackMan/PING research data:
    - Higher ball speeds require LESS spin for optimal carry
    - Lower ball speeds need MORE spin to maintain lift

    Reference data points (driver):
    - 120 mph ball speed → ~2900 rpm optimal
    - 140 mph ball speed → ~2700 rpm optimal
    - 160 mph ball speed → ~2550 rpm optimal (Tour average zone)
    - 180 mph ball speed → ~2050 rpm optimal

    Args:
        ball_speed_mph: Ball speed in mph
        club: Club type (affects optimal spin)

    Returns:
        Optimal spin rate in RPM
    """
    # Driver optimal spin (baseline)
    if ball_speed_mph >= 180:
        optimal = 2050
    elif ball_speed_mph >= 170:
        # 2050 at 180, 2300 at 170 → 25 rpm per mph
        optimal = 2050 + (180 - ball_speed_mph) * 25
    elif ball_speed_mph >= 160:
        # 2300 at 170, 2550 at 160 → 25 rpm per mph
        optimal = 2300 + (170 - ball_speed_mph) * 25
    elif ball_speed_mph >= 140:
        # 2550 at 160, 2700 at 140 → 7.5 rpm per mph
        optimal = 2550 + (160 - ball_speed_mph) * 7.5
    elif ball_speed_mph >= 120:
        # 2700 at 140, 2900 at 120 → 10 rpm per mph
        optimal = 2700 + (140 - ball_speed_mph) * 10
    elif ball_speed_mph >= 100:
        # 2900 at 120, 3100 at 100 → 10 rpm per mph
        optimal = 2900 + (120 - ball_speed_mph) * 10
    else:
        # Below 100 mph, keep at 3200 rpm
        optimal = 3200

    # Adjust for club type - irons need more spin
    club_spin_multipliers = {
        ClubType.DRIVER: 1.0,
        ClubType.WOOD_3: 1.15,
        ClubType.WOOD_5: 1.25,
        ClubType.HYBRID: 1.4,
        ClubType.IRON_3: 1.6,
        ClubType.IRON_4: 1.8,
        ClubType.IRON_5: 2.0,
        ClubType.IRON_6: 2.2,
        ClubType.IRON_7: 2.5,
        ClubType.IRON_8: 2.8,
        ClubType.IRON_9: 3.2,
        ClubType.PW: 3.6,
        ClubType.UNKNOWN: 1.0,
    }

    multiplier = club_spin_multipliers.get(club, 1.0)
    return optimal * multiplier


def estimate_carry_with_spin(
    ball_speed_mph: float,
    spin_rpm: float,
    club: ClubType = ClubType.DRIVER,
    club_speed_mph: Optional[float] = None,
) -> float:
    """
    Estimate carry distance using ball speed, spin rate, and optional club speed.

    Based on TrackMan/PING research data and physics:
    - Ball speed is primary factor (~85% of distance variance)
    - Spin rate affects trajectory via Magnus effect (lift)
    - Optimal spin varies inversely with ball speed
    - Smash factor validates contact quality

    Reference data points (driver, optimal conditions):
    - 120 mph ball speed → ~198 yards carry
    - 140 mph ball speed → ~231 yards carry
    - 160 mph ball speed → ~271 yards carry (Tour average: 167 mph → 275 yds)
    - 180 mph ball speed → ~310 yards carry

    Spin effects:
    - Too LOW: Ball "falls out of sky" - significant distance loss
    - Optimal: Maximum carry for given ball speed
    - Too HIGH: Ball "balloons" - moderate distance loss

    Args:
        ball_speed_mph: Ball speed in mph
        spin_rpm: Spin rate in RPM
        club: Club type for distance calculation
        club_speed_mph: Optional club head speed for smash factor validation

    Returns:
        Estimated carry distance in yards
    """
    # Get base carry from existing lookup table (TrackMan-derived)
    base_carry = estimate_carry_distance(ball_speed_mph, club)

    # Calculate optimal spin for this ball speed and club
    optimal_spin = get_optimal_spin_for_ball_speed(ball_speed_mph, club)

    # Calculate spin deviation
    spin_delta = spin_rpm - optimal_spin
    spin_delta_abs = abs(spin_delta)

    # Apply asymmetric spin adjustment
    # Low spin hurts MORE than high spin (ball falls out of sky vs balloons)
    if spin_delta < 0:
        # LOW SPIN: More severe penalty
        # Research shows ~1.2 yards lost per 100 rpm below optimal
        # Cap at 18% max penalty for extremely low spin
        penalty_per_100rpm = 0.012  # 1.2% per 100 rpm
        spin_factor = 1.0 - (spin_delta_abs / 100) * penalty_per_100rpm
        spin_factor = max(0.82, spin_factor)
    else:
        # HIGH SPIN: Less severe penalty (ball balloons but still carries)
        # Research shows ~0.8 yards lost per 100 rpm above optimal
        # Cap at 12% max penalty for extremely high spin
        penalty_per_100rpm = 0.008  # 0.8% per 100 rpm
        spin_factor = 1.0 - (spin_delta_abs / 100) * penalty_per_100rpm
        spin_factor = max(0.88, spin_factor)

    # Slight bonus for being very close to optimal (within 200 rpm)
    if spin_delta_abs < 200:
        spin_factor = min(1.02, spin_factor + 0.01)

    # Smash factor quality adjustment (if club speed available)
    smash_factor_adj = 1.0
    if club_speed_mph and club_speed_mph > 0:
        smash = ball_speed_mph / club_speed_mph

        # Optimal smash factors by club type
        optimal_smash = {
            ClubType.DRIVER: 1.48,
            ClubType.WOOD_3: 1.44,
            ClubType.WOOD_5: 1.42,
            ClubType.HYBRID: 1.38,
            ClubType.IRON_3: 1.35,
            ClubType.IRON_4: 1.33,
            ClubType.IRON_5: 1.31,
            ClubType.IRON_6: 1.29,
            ClubType.IRON_7: 1.27,
            ClubType.IRON_8: 1.25,
            ClubType.IRON_9: 1.23,
            ClubType.PW: 1.21,
            ClubType.UNKNOWN: 1.35,
        }

        target_smash = optimal_smash.get(club, 1.35)
        smash_delta = target_smash - smash

        if smash_delta > 0:
            # Below optimal smash = off-center hit = less efficient energy transfer
            # Penalize ~3% per 0.05 smash factor below optimal
            smash_factor_adj = max(0.94, 1.0 - (smash_delta / 0.05) * 0.03)
        elif smash_delta < -0.05:
            # Unusually high smash factor (>1.53 for driver) - might be measurement error
            # Or could indicate gear effect adding speed - slight penalty for uncertainty
            smash_factor_adj = 0.98

    # Final calculation
    adjusted_carry = base_carry * spin_factor * smash_factor_adj

    return adjusted_carry


class RollingBufferMonitor:
    """
    Golf Launch Monitor using rolling buffer mode.

    Alternative to LaunchMonitor that captures raw I/Q data for post-processing.
    Provides higher temporal resolution (~937 Hz vs ~56 Hz) and optional spin
    detection.

    Interface matches LaunchMonitor for compatibility with existing code.

    Example:
        monitor = RollingBufferMonitor()
        monitor.connect()
        monitor.start(shot_callback=on_shot)

        # Wait for shots...

        monitor.stop()
        monitor.disconnect()
    """

    def __init__(
        self,
        port: Optional[str] = None,
        trigger_type: str = "polling",
        **trigger_kwargs,
    ):
        """
        Initialize rolling buffer monitor.

        Args:
            port: Serial port for radar. Auto-detect if None.
            trigger_type: Trigger strategy ("polling", "threshold", "manual")
            **trigger_kwargs: Arguments for trigger strategy
        """
        self.radar = OPS243Radar(port=port)
        self.processor = RollingBufferProcessor()
        self.trigger = create_trigger(trigger_type, **trigger_kwargs)

        self._running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._shot_callback: Optional[Callable[[Shot], None]] = None
        self._live_callback: Optional[Callable[[SpeedReading], None]] = None
        self._shots: List[Shot] = []
        self._current_club: ClubType = ClubType.DRIVER

    def connect(self) -> bool:
        """
        Connect to radar and configure for rolling buffer mode.

        Returns:
            True if successful
        """
        self.radar.connect()
        self.radar.configure_for_rolling_buffer()
        return True

    def disconnect(self):
        """Disconnect from radar."""
        self.stop()
        self.radar.disable_rolling_buffer()
        self.radar.disconnect()

    def get_radar_info(self) -> dict:
        """Get radar module information."""
        return self.radar.get_info()

    def start(
        self,
        shot_callback: Optional[Callable[[Shot], None]] = None,
        live_callback: Optional[Callable[[SpeedReading], None]] = None,
    ):
        """
        Start monitoring for shots.

        Args:
            shot_callback: Called when a complete shot is detected
            live_callback: Called for live readings (limited in rolling buffer mode)
        """
        self._shot_callback = shot_callback
        self._live_callback = live_callback
        self._running = True

        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
        )
        self._capture_thread.start()

        logger.info("Rolling buffer monitor started")

    def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=5.0)
            self._capture_thread = None
        logger.info("Rolling buffer monitor stopped")

    def _capture_loop(self):
        """Main capture loop - wait for trigger, process, emit shot."""
        while self._running:
            try:
                # Wait for trigger and capture
                capture = self.trigger.wait_for_trigger(
                    radar=self.radar,
                    processor=self.processor,
                    timeout=5.0,
                )

                if capture is None:
                    continue

                # Process capture
                processed = self.processor.process_capture(capture)

                if processed is None:
                    print("[DEBUG] process_capture returned None")
                    logger.warning("Failed to process capture")
                    continue

                print(f"[DEBUG] Processed: ball_speed={processed.ball_speed_mph:.1f} mph, "
                      f"club_speed={processed.club_speed_mph}")

                # Create shot
                shot = self._create_shot(processed)

                if shot:
                    self._shots.append(shot)
                    print(f"[SHOT CREATED] {shot.ball_speed_mph:.1f} mph ball, "
                          f"club: {shot.club_speed_mph}, spin: {shot.spin_rpm}")
                    logger.info(
                        f"Shot detected: {shot.ball_speed_mph:.1f} mph, "
                        f"spin: {shot.spin_rpm if shot.spin_rpm else 'N/A'}"
                    )

                    # Log to session logger
                    session_logger = get_session_logger()
                    if session_logger:
                        session_logger.log_shot(
                            ball_speed_mph=shot.ball_speed_mph,
                            club_speed_mph=shot.club_speed_mph,
                            smash_factor=shot.smash_factor,
                            estimated_carry_yards=shot.estimated_carry_yards,
                            club=self._current_club.value,
                            peak_magnitude=None,  # Not available in rolling buffer mode
                            readings_count=len(processed.timeline.readings),
                            readings=None,  # Raw readings not stored in rolling buffer mode
                            spin_rpm=shot.spin_rpm,
                            spin_confidence=shot.spin_confidence,
                            mode="rolling-buffer"
                        )

                    if self._shot_callback:
                        self._shot_callback(shot)
                else:
                    print("[DEBUG] _create_shot returned None")

                # Reset trigger for next capture
                self.trigger.reset()

            except Exception as e:
                logger.error(f"Capture loop error: {e}")
                time.sleep(1.0)

    def _create_shot(self, processed: ProcessedCapture) -> Optional[Shot]:
        """
        Create Shot object from processed capture.

        Args:
            processed: Fully processed capture data

        Returns:
            Shot object or None if invalid
        """
        # Validate ball speed (lowered for field testing - real shots are 80+ mph)
        if processed.ball_speed_mph < 15:
            print(f"[DEBUG] Ball speed too low: {processed.ball_speed_mph:.1f} mph (need >=15)")
            return None

        # Calculate carry distance
        if processed.has_spin and processed.spin:
            carry = estimate_carry_with_spin(
                processed.ball_speed_mph,
                processed.spin.spin_rpm,
                self._current_club,
                club_speed_mph=processed.club_speed_mph,  # Include for smash factor validation
            )
            spin_rpm = processed.spin.spin_rpm
            spin_confidence = processed.spin.confidence
        else:
            carry = estimate_carry_distance(processed.ball_speed_mph, self._current_club)
            spin_rpm = None
            spin_confidence = None

        # Create shot with extended fields
        shot = Shot(
            ball_speed_mph=processed.ball_speed_mph,
            timestamp=datetime.now(),
            club_speed_mph=processed.club_speed_mph,
            peak_magnitude=None,  # Not directly available in rolling buffer mode
            readings=[],  # Raw readings not stored (use ProcessedCapture instead)
            club=self._current_club,
            spin_rpm=spin_rpm,
            spin_confidence=spin_confidence,
            carry_spin_adjusted=carry if spin_rpm else None,
        )

        return shot

    def wait_for_shot(self, timeout: float = 60) -> Optional[Shot]:
        """
        Wait for a shot to be detected.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            Shot object or None if timeout
        """
        shot_detected: List[Shot] = []

        def on_shot(shot: Shot):
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
                "avg_carry_est": 0,
                "avg_spin_rpm": None,
                "mode": "rolling-buffer",
            }

        ball_speeds = [s.ball_speed_mph for s in self._shots]
        club_speeds = [s.club_speed_mph for s in self._shots if s.club_speed_mph]
        smash_factors = [s.smash_factor for s in self._shots if s.smash_factor]

        # Get spin data
        spin_rpms = [
            s.spin_rpm
            for s in self._shots
            if s.spin_rpm is not None
        ]

        return {
            "shot_count": len(self._shots),
            "avg_ball_speed": statistics.mean(ball_speeds),
            "max_ball_speed": max(ball_speeds),
            "min_ball_speed": min(ball_speeds),
            "std_dev": statistics.stdev(ball_speeds) if len(ball_speeds) > 1 else 0,
            "avg_club_speed": statistics.mean(club_speeds) if club_speeds else None,
            "avg_smash_factor": statistics.mean(smash_factors) if smash_factors else None,
            "avg_carry_est": statistics.mean([s.estimated_carry_yards for s in self._shots]),
            "avg_spin_rpm": statistics.mean(spin_rpms) if spin_rpms else None,
            "spin_detection_rate": len(spin_rpms) / len(self._shots) if self._shots else 0,
            "mode": "rolling-buffer",
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
