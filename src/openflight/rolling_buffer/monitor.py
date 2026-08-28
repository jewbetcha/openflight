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

from ..launch_monitor import ClubType, Shot, estimate_carry_distance
from ..ops243 import OPS243Radar, SpeedReading
from ..session_logger import get_session_logger, log_session_error
from .processor import RollingBufferProcessor
from .trigger import create_trigger
from .types import ProcessedCapture

logger = logging.getLogger("openflight.rolling_buffer.monitor")


def get_optimal_spin_for_ball_speed(
    ball_speed_mph: float, club: ClubType = ClubType.DRIVER
) -> float:
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
    # Driver optimal spin (baseline) - interpolated from TrackMan/PING data
    # Table: (min_speed, base_rpm_at_upper_bound, rpm_per_mph_below_upper, upper_bound)
    _spin_table = [
        (180, 2050, 0, 999),
        (170, 2050, 25, 180),
        (160, 2300, 25, 170),
        (140, 2550, 7.5, 160),
        (120, 2700, 10, 140),
        (100, 2900, 10, 120),
    ]

    optimal = 3200  # Default for speeds below 100 mph
    for min_speed, base_rpm, rpm_per_mph, upper in _spin_table:
        if ball_speed_mph >= min_speed:
            optimal = base_rpm + (upper - ball_speed_mph) * rpm_per_mph
            break

    # Adjust for club type - irons need more spin
    club_spin_multipliers = {
        ClubType.DRIVER: 1.0,
        ClubType.WOOD_3: 1.15,
        ClubType.WOOD_5: 1.25,
        ClubType.WOOD_7: 1.32,
        ClubType.HYBRID_3: 1.45,
        ClubType.HYBRID_5: 1.55,
        ClubType.HYBRID_7: 1.65,
        ClubType.HYBRID_9: 1.75,
        ClubType.IRON_2: 1.5,
        ClubType.IRON_3: 1.6,
        ClubType.IRON_4: 1.8,
        ClubType.IRON_5: 2.0,
        ClubType.IRON_6: 2.2,
        ClubType.IRON_7: 2.5,
        ClubType.IRON_8: 2.8,
        ClubType.IRON_9: 3.2,
        ClubType.PW: 3.6,
        ClubType.GW: 4.1,
        ClubType.SW: 4.3,
        ClubType.LW: 4.6,
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
            ClubType.WOOD_7: 1.41,
            ClubType.HYBRID_3: 1.39,
            ClubType.HYBRID_5: 1.37,
            ClubType.HYBRID_7: 1.35,
            ClubType.HYBRID_9: 1.33,
            ClubType.IRON_2: 1.36,
            ClubType.IRON_3: 1.35,
            ClubType.IRON_4: 1.33,
            ClubType.IRON_5: 1.31,
            ClubType.IRON_6: 1.29,
            ClubType.IRON_7: 1.27,
            ClubType.IRON_8: 1.25,
            ClubType.IRON_9: 1.23,
            ClubType.PW: 1.21,
            ClubType.GW: 1.19,
            ClubType.SW: 1.18,
            ClubType.LW: 1.17,
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

    Recommended configuration uses "speed" trigger (default):
    - Fast speed detection mode (~150-200Hz) watches for club swing
    - Automatically switches to rolling buffer when speed detected
    - Captures ball impact with high temporal resolution
    - Per OmniPreSense manufacturer recommendation

    Interface matches LaunchMonitor for compatibility with existing code.

    Example:
        monitor = RollingBufferMonitor()  # Uses speed trigger by default
        monitor.connect()
        monitor.start(shot_callback=on_shot)

        # Wait for shots...

        monitor.stop()
        monitor.disconnect()
    """

    def __init__(
        self,
        port: Optional[str] = None,
        trigger_type: str = "speed",
        sample_rate_ksps: int = 30,
        ops_baud: Optional[int] = None,
        **trigger_kwargs,
    ):
        """
        Initialize rolling buffer monitor.

        Args:
            port: Serial port for radar. Auto-detect if None. Pass the UART
                device (e.g. /dev/ttyAMA0) when the OPS243 is wired to the
                Pi GPIO header instead of USB.
            ops_baud: Target UART baud to negotiate to. None uses the
                driver default (230400). Ignored over USB, where the rate
                is nominal.
            trigger_type: Trigger strategy:
                - "speed" (default, recommended): Fast speed trigger per manufacturer
                - "polling": Continuous capture polling (slower, simpler)
                - "threshold": Speed threshold trigger
                - "manual": External trigger for testing
            **trigger_kwargs: Arguments for trigger strategy
        """
        radar_kwargs = {} if ops_baud is None else {"uart_baud": ops_baud}
        self.radar = OPS243Radar(port=port, **radar_kwargs)
        self.processor = RollingBufferProcessor(sample_rate=sample_rate_ksps * 1000)
        self.trigger_type = trigger_type
        self.sample_rate_ksps = sample_rate_ksps
        self.trigger = create_trigger(trigger_type, **trigger_kwargs)

        self._running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._shot_callback: Optional[Callable[[Shot], None]] = None
        self._live_callback: Optional[Callable[[SpeedReading], None]] = None
        self._diagnostic_callback: Optional[Callable[[dict], None]] = None
        self._processing_callback: Optional[Callable[[str], None]] = None
        self._shots: List[Shot] = []
        self._shot_sequence_number = 0
        self._current_club: ClubType = ClubType.DRIVER

    def connect(self) -> bool:
        """
        Connect to radar and configure based on trigger type.

        For "speed" trigger: Configuration is handled by the trigger strategy
        For other triggers: Configure for rolling buffer mode with appropriate
        pre_trigger_segments from the trigger.

        Returns:
            True if successful
        """
        self.radar.connect()

        # Speed trigger handles its own configuration (starts in speed mode)
        # Other triggers need rolling buffer mode configured upfront
        if self.trigger_type != "speed":
            # Get pre_trigger_segments from the trigger if available
            pre_trigger_segments = getattr(self.trigger, "pre_trigger_segments", 12)
            if self.trigger_type == "sound":
                self.radar.prepare_persisted_rolling_buffer(
                    pre_trigger_segments=pre_trigger_segments,
                    sample_rate_ksps=self.sample_rate_ksps,
                )
            else:
                self.radar.configure_for_rolling_buffer(
                    pre_trigger_segments=pre_trigger_segments,
                    sample_rate_ksps=self.sample_rate_ksps,
                )
            logger.info(
                "[MONITOR] Rolling buffer mode configured with S#%d, S=%d",
                pre_trigger_segments,
                self.sample_rate_ksps,
            )
        else:
            logger.info("[MONITOR] Using speed trigger — configuration deferred to trigger")

        return True

    def disconnect(self):
        """Disconnect from radar.

        Intentionally does NOT send a "GS" (return-to-CW) to the radar.
        The OPS243-A firmware has a documented bug where the HOST_INT
        pin mode flips when the radar transitions between modes at
        runtime — see ops243.py:enter_rolling_buffer_mode and
        CLAUDE.md "Radar Setup". The whole project relies on the radar
        being in *persistent* rolling-buffer mode (saved to flash, see
        scripts/hardware-test/test_rolling_buffer_persist.py).

        If we send GS on shutdown:
          1. The Python process exits, but the radar is now in CW mode.
          2. start-kiosk.sh re-runs and configure_for_rolling_buffer()
             sends the runtime GS→GC sequence, which trips the HOST_INT
             firmware bug.
          3. The sound trigger silently never fires again until the
             OPS243-A is power-cycled (USB unplug + replug).

        Leaving the radar in rolling-buffer mode at process exit is
        therefore the correct steady-state behaviour. The OS will
        release the serial port via radar.disconnect(), and the next
        start-kiosk.sh starts cleanly because no mode transition is
        required.
        """
        self.stop()
        self.radar.disconnect()

    def get_radar_info(self) -> dict:
        """Get radar module information."""
        return self.radar.get_info()

    def start(
        self,
        shot_callback: Optional[Callable[[Shot], None]] = None,
        live_callback: Optional[Callable[[SpeedReading], None]] = None,
        diagnostic_callback: Optional[Callable[[dict], None]] = None,
        processing_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Start monitoring for shots.

        Args:
            shot_callback: Called when a complete shot is detected
            live_callback: Called for live readings (limited in rolling buffer mode)
            diagnostic_callback: Called with trigger diagnostic data for UI display
            processing_callback: Called with "started" or "failed" around shot processing
        """
        self._shot_callback = shot_callback
        self._live_callback = live_callback
        self._diagnostic_callback = diagnostic_callback
        self._processing_callback = processing_callback
        self._stop_event.clear()
        self._running = True

        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            daemon=True,
        )
        self._capture_thread.start()

        logger.info("[MONITOR] Rolling buffer monitor started (trigger: %s)", self.trigger_type)

    def stop(self):
        """Stop monitoring."""
        self._running = False
        self._stop_event.set()
        if self._capture_thread:
            capture_thread = self._capture_thread
            # Idle sound waits are cancelled immediately. If bytes are
            # already arriving, let the bounded radar dump and re-arm
            # finish before the serial port is closed.
            capture_thread.join(timeout=5.0)
            if capture_thread.is_alive():
                logger.warning("[MONITOR] Capture thread still active during shutdown")
            else:
                self._capture_thread = None
        logger.info("[MONITOR] Rolling buffer monitor stopped")

    def _notify_processing(self, state: str) -> None:
        """Report shot-processing lifecycle without letting UI errors break capture."""
        if not self._processing_callback:
            return
        try:
            self._processing_callback(state)
        except Exception:
            logger.warning("[MONITOR] Processing status callback failed", exc_info=True)

    def _emit_diagnostics(self, wall_clock_ms: float = 0):
        """Drain trigger diagnostics and emit them to logger and UI."""
        diagnostics = self.trigger.drain_diagnostics()
        session_logger = get_session_logger()

        for diag in diagnostics:
            diag["trigger_type"] = self.trigger_type
            # Use trigger's own edge-to-S! latency if measured,
            # otherwise fall back to wall-clock (includes idle wait + serial transfer)
            latency = diag.pop("trigger_latency_ms", None) or wall_clock_ms
            diag["latency_ms"] = latency

            # Log to session JSONL
            if session_logger:
                session_logger.log_trigger_diagnostic(
                    trigger_type=self.trigger_type,
                    accepted=diag["accepted"],
                    reason=diag.get("reason", ""),
                    response_bytes=diag.get("response_bytes", 0),
                    total_readings=diag.get("total_readings", 0),
                    outbound_readings=diag.get("outbound_readings", 0),
                    inbound_readings=diag.get("inbound_readings", 0),
                    peak_outbound_mph=diag.get("peak_outbound_mph", 0),
                    peak_inbound_mph=diag.get("peak_inbound_mph", 0),
                    all_outbound_speeds=diag.get("all_outbound_speeds"),
                    all_inbound_speeds=diag.get("all_inbound_speeds"),
                    latency_ms=latency,
                )

            # Emit to UI via WebSocket
            if self._diagnostic_callback:
                self._diagnostic_callback(diag)

    def _capture_loop(self):
        """Main capture loop - wait for trigger, process, emit shot."""
        while self._running:
            try:
                trigger_start = time.time()

                # Wait for trigger and capture
                # Use a long timeout so sound/hardware triggers can wait
                # for the next swing without noisy timeout-restart cycles.
                trigger_kwargs = {
                    "radar": self.radar,
                    "processor": self.processor,
                    "timeout": 30.0,
                }
                capture_started = False

                def on_capture_started() -> None:
                    nonlocal capture_started
                    capture_started = True
                    self._notify_processing("capturing")

                if self.trigger_type == "sound":
                    trigger_kwargs["cancel_event"] = self._stop_event
                    trigger_kwargs["capture_started_callback"] = on_capture_started
                capture = self.trigger.wait_for_trigger(**trigger_kwargs)

                if not self._running:
                    break

                trigger_latency_ms = (time.time() - trigger_start) * 1000

                # Always drain trigger diagnostics (captures in-loop rejections)
                self._emit_diagnostics(trigger_latency_ms)

                if capture is None:
                    if capture_started:
                        self._notify_processing("failed")
                    continue

                # Process capture (FFT + speed/spin extraction)
                self._notify_processing("calculating")
                process_start = time.time()
                processed = self.processor.process_capture(
                    capture,
                    expected_spin_for_ball_speed=lambda ball_speed_mph: (
                        get_optimal_spin_for_ball_speed(
                            ball_speed_mph,
                            self._current_club,
                        )
                    ),
                    club_type=self._current_club,
                )
                process_ms = (time.time() - process_start) * 1000
                logger.info("[MONITOR] process_capture: %.1fms", process_ms)

                if processed is None:
                    self._notify_processing("failed")
                    logger.warning("[MONITOR] Failed to process capture")
                    # Emit diagnostic for processing failure
                    diag = {
                        "timestamp": capture.trigger_time if capture else 0,
                        "accepted": False,
                        "reason": "processing_failed",
                        "trigger_type": self.trigger_type,
                        "latency_ms": trigger_latency_ms,
                        "response_bytes": 0,
                        "total_readings": 0,
                        "outbound_readings": 0,
                        "inbound_readings": 0,
                        "peak_outbound_mph": 0,
                        "peak_inbound_mph": 0,
                        "all_outbound_speeds": [],
                        "all_inbound_speeds": [],
                    }
                    session_logger = get_session_logger()
                    if session_logger:
                        session_logger.log_trigger_diagnostic(
                            trigger_type=self.trigger_type,
                            accepted=False,
                            reason="processing_failed",
                            latency_ms=trigger_latency_ms,
                        )
                    if self._diagnostic_callback:
                        self._diagnostic_callback(diag)
                    continue

                # For speed trigger, use the trigger speed as club speed if not found in capture
                if (
                    self.trigger_type == "speed"
                    and processed.club_speed_mph is None
                    and hasattr(self.trigger, "last_trigger_speed")
                ):
                    trigger_speed = self.trigger.last_trigger_speed
                    if trigger_speed > 0:
                        processed.club_speed_mph = trigger_speed
                        logger.info(
                            "[MONITOR] Using trigger speed as club speed: %.1f mph", trigger_speed
                        )

                logger.debug(
                    "[MONITOR] Processed: ball=%.1f mph, club=%s",
                    processed.ball_speed_mph,
                    processed.club_speed_mph,
                )

                # Create shot
                shot = self._create_shot(processed)

                if shot:
                    self._shot_sequence_number += 1
                    shot.shot_number = self._shot_sequence_number
                    self._shots.append(shot)
                    logger.info(
                        "[MONITOR] Shot detected: ball=%.1f mph, club=%s, spin=%s",
                        shot.ball_speed_mph,
                        "%.1f" % shot.club_speed_mph if shot.club_speed_mph else "N/A",
                        "%.0f" % shot.spin_rpm if shot.spin_rpm else "N/A",
                    )
                    if shot.spin_rejection_reason:
                        logger.info(
                            "[MONITOR] Spin unavailable: %s (snr=%s, candidate=%s rpm)",
                            shot.spin_rejection_reason,
                            "%.2f" % shot.spin_snr if shot.spin_snr is not None else "N/A",
                            "%.0f" % (shot.spin_peak_freq_hz * 60)
                            if shot.spin_peak_freq_hz is not None
                            else "N/A",
                        )

                    # Log raw I/Q data and trigger events to session logger
                    session_logger = get_session_logger()
                    if session_logger:
                        # Log raw I/Q data for offline analysis
                        session_logger.log_rolling_buffer_capture(
                            shot_number=shot.shot_number,
                            sample_time=capture.sample_time,
                            trigger_time=capture.trigger_time,
                            i_samples=capture.i_samples,
                            q_samples=capture.q_samples,
                            ball_speed_mph=shot.ball_speed_mph,
                            club_speed_mph=shot.club_speed_mph,
                            ball_timestamp_ms=processed.ball_timestamp_ms,
                            club_timestamp_ms=processed.club_timestamp_ms,
                            impact_timestamp_ms=processed.impact_timestamp_ms,
                            impact_source=processed.impact_source,
                            impact_reason=(processed.impact.reason if processed.impact else None),
                            impact_speed_delta_mph=(
                                processed.impact.speed_delta_mph if processed.impact else None
                            ),
                            impact_transition_gap_ms=(
                                processed.impact.transition_gap_ms if processed.impact else None
                            ),
                            impact_last_club_speed_mph=(
                                processed.impact.last_club_speed_mph if processed.impact else None
                            ),
                            impact_last_club_timestamp_ms=(
                                processed.impact.last_club_timestamp_ms
                                if processed.impact
                                else None
                            ),
                            impact_last_club_center_ms=(
                                processed.impact.last_club_center_ms if processed.impact else None
                            ),
                            impact_first_ball_speed_mph=(
                                processed.impact.first_ball_speed_mph if processed.impact else None
                            ),
                            impact_first_ball_timestamp_ms=(
                                processed.impact.first_ball_timestamp_ms
                                if processed.impact
                                else None
                            ),
                            impact_first_ball_center_ms=(
                                processed.impact.first_ball_center_ms if processed.impact else None
                            ),
                            impact_min_transition_delta_mph=(
                                processed.impact.min_transition_delta_mph
                                if processed.impact
                                else None
                            ),
                            trigger_latency_ms=trigger_latency_ms,
                            first_byte_timestamp=capture.first_byte_timestamp,
                            trigger_timestamp=capture.trigger_timestamp,
                            trigger_timestamp_source=capture.trigger_timestamp_source,
                            clock_sync_offset_s=capture.clock_sync_offset_s,
                            post_trigger_duration_ms=capture.post_trigger_duration_ms,
                            smash_factor=processed.smash_factor,
                            spin_rpm=processed.spin.spin_rpm if processed.spin else None,
                            spin_confidence=processed.spin.confidence if processed.spin else None,
                            spin_method=processed.spin.method if processed.spin else None,
                            spin_quality=processed.spin.quality if processed.spin else None,
                            spin_multipath_fade_hz=(
                                processed.spin.multipath_fade_hz if processed.spin else None
                            ),
                            spin_snr=processed.spin.snr if processed.spin else None,
                            spin_modulation_depth=(
                                processed.spin.modulation_depth if processed.spin else None
                            ),
                            spin_peak_freq_hz=(
                                processed.spin.peak_freq_hz if processed.spin else None
                            ),
                            spin_seam_cycles=(
                                processed.spin.seam_cycles if processed.spin else None
                            ),
                            spin_at_lower_rail=(
                                processed.spin.at_lower_rail if processed.spin else None
                            ),
                            spin_at_upper_rail=(
                                processed.spin.at_upper_rail if processed.spin else None
                            ),
                            spin_candidates=(
                                [candidate.to_dict() for candidate in processed.spin.candidates]
                                if processed.spin
                                else None
                            ),
                            spin_phase_method=(
                                processed.spin.phase_method if processed.spin else None
                            ),
                            spin_phase_rpm=(processed.spin.phase_rpm if processed.spin else None),
                            spin_phase_snr=(processed.spin.phase_snr if processed.spin else None),
                            spin_phase_agreement_pct=(
                                processed.spin.phase_agreement_pct if processed.spin else None
                            ),
                            spin_phase_confirmed=(
                                processed.spin.phase_confirmed if processed.spin else False
                            ),
                            spin_rejection_reason=shot.spin_rejection_reason,
                        )

                        # Log accepted trigger event
                        session_logger.log_trigger_event(
                            trigger_type=self.trigger_type,
                            accepted=True,
                            peak_speed_mph=shot.ball_speed_mph,
                            readings_count=len(processed.timeline.readings),
                            latency_ms=trigger_latency_ms,
                        )

                        # Log detailed trigger diagnostic
                        all_outbound = [r for r in processed.timeline.readings if r.is_outbound]
                        all_inbound = [r for r in processed.timeline.readings if not r.is_outbound]
                        session_logger.log_trigger_diagnostic(
                            trigger_type=self.trigger_type,
                            accepted=True,
                            reason="accepted",
                            total_readings=len(processed.timeline.readings),
                            outbound_readings=len(all_outbound),
                            inbound_readings=len(all_inbound),
                            peak_outbound_mph=max((r.speed_mph for r in all_outbound), default=0),
                            peak_inbound_mph=max((r.speed_mph for r in all_inbound), default=0),
                            all_outbound_speeds=[r.speed_mph for r in all_outbound],
                            all_inbound_speeds=[r.speed_mph for r in all_inbound],
                            latency_ms=trigger_latency_ms,
                            ball_speed_mph=shot.ball_speed_mph,
                            club_speed_mph=shot.club_speed_mph,
                            spin_rpm=shot.spin_rpm,
                            carry_yards=shot.estimated_carry_yards,
                        )

                    # Emit diagnostic to UI
                    if self._diagnostic_callback:
                        self._diagnostic_callback(
                            {
                                # Correlation key used when the slower IWR6843
                                # result enriches this same UI history row.
                                "timestamp": shot.timestamp.isoformat(),
                                "accepted": True,
                                "reason": "accepted",
                                "trigger_type": self.trigger_type,
                                "latency_ms": trigger_latency_ms,
                                "response_bytes": 0,
                                "total_readings": len(processed.timeline.readings),
                                "outbound_readings": 0,
                                "inbound_readings": 0,
                                "peak_outbound_mph": shot.ball_speed_mph,
                                "peak_inbound_mph": 0,
                                "all_outbound_speeds": [],
                                "all_inbound_speeds": [],
                                "ball_speed_mph": shot.ball_speed_mph,
                                "club_speed_mph": shot.club_speed_mph,
                                "spin_rpm": shot.spin_rpm,
                                "spin_snr": shot.spin_snr,
                                "spin_candidate_rpm": (
                                    round(shot.spin_peak_freq_hz * 60)
                                    if shot.spin_peak_freq_hz is not None
                                    else None
                                ),
                                "spin_rejection_reason": shot.spin_rejection_reason,
                                "spin_candidates": shot.spin_candidates,
                                "spin_phase_method": shot.spin_phase_method,
                                "spin_phase_rpm": shot.spin_phase_rpm,
                                "spin_phase_snr": shot.spin_phase_snr,
                                "spin_phase_agreement_pct": shot.spin_phase_agreement_pct,
                                "spin_phase_confirmed": shot.spin_phase_confirmed,
                                "carry_yards": shot.estimated_carry_yards,
                            }
                        )

                    if self._shot_callback:
                        callback_start = time.time()
                        self._shot_callback(shot)
                        callback_ms = (time.time() - callback_start) * 1000
                        total_ms = (time.time() - trigger_start) * 1000
                        logger.info(
                            "[SHOT] #%d: ball=%.1f mph, club=%s, carry=%s yds | "
                            "trigger=%.0fms, process=%.0fms, callback=%.0fms, total=%.0fms",
                            shot.shot_number,
                            shot.ball_speed_mph,
                            "%.1f" % shot.club_speed_mph if shot.club_speed_mph else "N/A",
                            "%.0f" % shot.estimated_carry_yards
                            if shot.estimated_carry_yards
                            else "N/A",
                            trigger_latency_ms,
                            process_ms,
                            callback_ms,
                            total_ms,
                        )
                else:
                    self._notify_processing("failed")
                    logger.info(
                        "[MONITOR] Shot validation failed: ball=%.1f mph (min 15 mph)",
                        processed.ball_speed_mph if processed else 0,
                    )
                    # Emit diagnostic for shot validation failure
                    diag = {
                        "timestamp": datetime.now().isoformat(),
                        "accepted": False,
                        "reason": "shot_validation_failed",
                        "trigger_type": self.trigger_type,
                        "latency_ms": trigger_latency_ms,
                        "response_bytes": 0,
                        "total_readings": len(processed.timeline.readings) if processed else 0,
                        "outbound_readings": 0,
                        "inbound_readings": 0,
                        "peak_outbound_mph": processed.ball_speed_mph if processed else 0,
                        "peak_inbound_mph": 0,
                        "all_outbound_speeds": [],
                        "all_inbound_speeds": [],
                        "ball_speed_mph": processed.ball_speed_mph if processed else None,
                    }
                    session_logger = get_session_logger()
                    if session_logger:
                        session_logger.log_trigger_diagnostic(
                            trigger_type=self.trigger_type,
                            accepted=False,
                            reason="shot_validation_failed",
                            peak_outbound_mph=processed.ball_speed_mph if processed else 0,
                            total_readings=len(processed.timeline.readings) if processed else 0,
                            latency_ms=trigger_latency_ms,
                            ball_speed_mph=processed.ball_speed_mph if processed else None,
                        )
                    if self._diagnostic_callback:
                        self._diagnostic_callback(diag)

                # Reset trigger for next capture
                self.trigger.reset()

            except Exception as e:
                self._notify_processing("failed")
                logger.error("[MONITOR] Capture loop error: %s", e, exc_info=True)
                log_session_error(
                    "Rolling buffer capture loop error",
                    component="rolling_buffer_monitor",
                    context={"trigger_type": self.trigger_type},
                    exc=e,
                )
                time.sleep(1.0)

    def _create_shot(self, processed: ProcessedCapture) -> Optional[Shot]:
        """
        Create Shot object from processed capture.

        Args:
            processed: Fully processed capture data

        Returns:
            Shot object or None if invalid
        """
        # Validate ball speed
        if processed.ball_speed_mph < 15:
            logger.debug("[MONITOR] Ball speed too low: %.1f mph", processed.ball_speed_mph)
            return None

        spin = processed.spin
        spin_rejection_reason = spin.rejection_reason if spin else None
        is_ungated_multitaper = bool(spin is not None and spin.method == "multitaper_ungated")
        club_spin_rejection_reason = (
            None if is_ungated_multitaper else self._club_spin_rejection_reason(processed)
        )
        if club_spin_rejection_reason:
            spin_rejection_reason = club_spin_rejection_reason
            logger.warning(
                "[MONITOR] Spin rejected by club plausibility: %s "
                "(club=%s, ball=%.1f mph, candidate=%s rpm)",
                club_spin_rejection_reason,
                self._current_club.value,
                processed.ball_speed_mph,
                "%.0f" % spin.spin_rpm if spin else "N/A",
            )

        # Calculate carry distance.
        # Use spin-adjusted carry only for reliable, plausible spin readings.
        has_reliable_spin = bool(
            processed.has_spin
            and club_spin_rejection_reason is None
            and spin is not None
            and not spin.at_lower_rail
            and not spin.at_upper_rail
        )
        has_reportable_spin = bool(
            spin is not None
            and spin.spin_rpm > 0
            and (
                is_ungated_multitaper
                or (
                    club_spin_rejection_reason is None
                    and not spin.at_lower_rail
                    and not spin.at_upper_rail
                )
            )
        )
        if (
            spin is not None
            and spin.spin_rpm > 0
            and club_spin_rejection_reason is None
            and not is_ungated_multitaper
            and not has_reportable_spin
        ):
            if spin.at_lower_rail:
                spin_rejection_reason = (
                    f"Lower-rail spin candidate {spin.spin_rpm:.0f} RPM kept as diagnostic only"
                )
            elif spin.at_upper_rail:
                spin_rejection_reason = (
                    f"Upper-rail spin candidate {spin.spin_rpm:.0f} RPM kept as diagnostic only"
                )

        if has_reliable_spin:
            carry = estimate_carry_with_spin(
                processed.ball_speed_mph,
                spin.spin_rpm,
                self._current_club,
                club_speed_mph=processed.club_speed_mph,
            )
        else:
            carry = estimate_carry_distance(processed.ball_speed_mph, self._current_club)

        spin_rpm = spin.spin_rpm if has_reportable_spin else None
        spin_confidence = spin.confidence if has_reportable_spin else None
        spin_result_quality = spin.quality if has_reportable_spin else None
        capture = processed.capture
        impact_timestamp = None
        impact_timestamp_kld7: Optional[float] = None
        if capture is not None:
            trigger_epoch = (
                capture.trigger_timestamp
                if capture.trigger_timestamp is not None
                else capture.first_byte_timestamp
            )
            impact_timestamp = trigger_epoch

            impact_timestamp_kld7 = self._impact_epoch_from_processed(processed)
            if impact_timestamp_kld7 is None:
                impact_timestamp_kld7 = trigger_epoch

        # Create shot with extended fields
        shot = Shot(
            ball_speed_mph=processed.ball_speed_mph,
            timestamp=datetime.now(),
            impact_timestamp=impact_timestamp,
            impact_timestamp_kld7=impact_timestamp_kld7,
            club_speed_mph=processed.club_speed_mph,
            peak_magnitude=None,  # Not directly available in rolling buffer mode
            readings=[],  # Raw readings not stored (use ProcessedCapture instead)
            club=self._current_club,
            spin_rpm=spin_rpm,
            spin_confidence=spin_confidence,
            spin_method=spin.method if spin else None,
            spin_result_quality=spin_result_quality,
            spin_multipath_fade_hz=spin.multipath_fade_hz if spin else None,
            spin_snr=spin.snr if spin else None,
            spin_modulation_depth=spin.modulation_depth if spin else None,
            spin_peak_freq_hz=spin.peak_freq_hz if spin else None,
            spin_seam_cycles=spin.seam_cycles if spin else None,
            spin_at_lower_rail=spin.at_lower_rail if spin else None,
            spin_at_upper_rail=spin.at_upper_rail if spin else None,
            spin_candidates=(
                [candidate.to_dict() for candidate in spin.candidates] if spin else None
            ),
            spin_phase_method=spin.phase_method if spin else None,
            spin_phase_rpm=spin.phase_rpm if spin else None,
            spin_phase_snr=spin.phase_snr if spin else None,
            spin_phase_agreement_pct=spin.phase_agreement_pct if spin else None,
            spin_phase_confirmed=spin.phase_confirmed if spin else False,
            spin_rejection_reason=spin_rejection_reason,
            carry_spin_adjusted=carry if has_reliable_spin else None,
            mode="rolling-buffer",
        )

        return shot

    @staticmethod
    def _impact_epoch_from_processed(processed: ProcessedCapture) -> Optional[float]:
        """Convert the capture-relative impact estimate into host epoch time."""
        capture = processed.capture
        if capture is None or capture.trigger_timestamp is None:
            return None

        if processed.impact_timestamp_ms is None:
            return capture.trigger_timestamp

        impact_delta_ms = processed.impact_timestamp_ms - capture.trigger_offset_ms
        return capture.trigger_timestamp + impact_delta_ms / 1000.0

    def _club_spin_rejection_reason(
        self,
        processed: ProcessedCapture,
    ) -> Optional[str]:
        """Reject lower-rail spin candidates that are implausible for the
        selected club.

        The OPS envelope FFT can lock onto the low edge of the search band
        around 3300-3500 RPM. That can be real for a driver, but in real
        Trackman comparison sessions the same rail value showed up as false
        spin for 7-irons and wedges. Keep the raw DSP diagnostics, but do
        not expose those rail picks as measured spin for high-spin clubs.
        """
        spin = processed.spin
        if not spin or spin.spin_rpm <= 0 or not spin.at_lower_rail:
            return None

        high_spin_clubs = {
            ClubType.IRON_6,
            ClubType.IRON_7,
            ClubType.IRON_8,
            ClubType.IRON_9,
            ClubType.PW,
            ClubType.GW,
            ClubType.SW,
            ClubType.LW,
        }
        if self._current_club not in high_spin_clubs:
            return None

        optimal_spin = get_optimal_spin_for_ball_speed(
            processed.ball_speed_mph,
            self._current_club,
        )
        floor_rpm = optimal_spin * 0.60
        if spin.spin_rpm >= floor_rpm:
            return None

        return (
            f"Lower-rail spin candidate {spin.spin_rpm:.0f} RPM is below "
            f"the {self._current_club.value} plausibility floor "
            f"({floor_rpm:.0f} RPM)"
        )

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
        spin_rpms = [s.spin_rpm for s in self._shots if s.spin_rpm is not None]

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
