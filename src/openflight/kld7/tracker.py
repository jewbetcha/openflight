"""K-LD7 angle radar tracker with ring buffer for shot correlation."""

import logging
import threading
import time
from collections import deque
from typing import Optional

from .types import KLD7Angle, KLD7Frame

logger = logging.getLogger(__name__)


def _find_port():
    """Auto-detect K-LD7 EVAL board USB serial port."""
    try:
        from serial.tools.list_ports import comports
    except ImportError:
        return None
    for port in comports():
        desc = (port.description or "").lower()
        mfg = (port.manufacturer or "").lower()
        if any(kw in desc for kw in ["ftdi", "cp210", "usb-serial", "uart"]):
            return port.device
        if any(kw in mfg for kw in ["ftdi", "silicon labs"]):
            return port.device
    return None


class KLD7Tracker:
    """
    K-LD7 angle radar tracker.

    Streams RADC frames in a background thread into a ring buffer.
    When the OPS243 detects a shot, call get_angle_for_shot() to search
    the buffer for the ball pass and extract angle data via phase interferometry.
    """

    # Class-level defaults so __new__-constructed instances (tests) don't
    # fail with AttributeError when code accesses these.
    angle_offset_deg = 0.0
    base_freq = 0
    shot_window_seconds = 0.2

    def __init__(
        self,
        port: Optional[str] = None,
        range_m: int = 5,
        speed_kmh: int = 100,
        orientation: str = "vertical",
        buffer_seconds: float = 2.0,
        angle_offset_deg: float = 0.0,
        base_freq: int = 0,
    ):
        self.port = port
        self.range_m = range_m
        self.speed_kmh = speed_kmh
        self.orientation = orientation
        self.buffer_seconds = buffer_seconds
        self.angle_offset_deg = angle_offset_deg
        self.base_freq = base_freq
        self.max_buffer_frames = int(34 * buffer_seconds)

        self._radar = None
        self._stream_thread: Optional[threading.Thread] = None
        self._running = False
        self._init_ring_buffer()

    def _init_ring_buffer(self):
        """Initialize or reset the ring buffer."""
        self._ring_buffer: deque[KLD7Frame] = deque(maxlen=self.max_buffer_frames)

    def connect(self) -> bool:
        """Connect to K-LD7 and configure for golf."""
        try:
            from kld7 import KLD7
        except ImportError:
            logger.error("[KLD7] kld7 package not installed. Run: pip install kld7")
            return False

        port = self.port or _find_port()
        if not port:
            logger.error("[KLD7] No K-LD7 EVAL board detected")
            return False

        # The kld7 library always opens at 115200, sends INIT to negotiate
        # up to 3Mbaud, then switches. If a prior session left the K-LD7 at
        # 3Mbaud (crashed before GBYE), the 115200-baud INIT is garbled.
        #
        # Recovery: send a binary GBYE packet at 3Mbaud to cleanly close
        # the prior session, returning the K-LD7 to its idle state where
        # it accepts INIT at 115200 again.
        import struct

        import serial as pyserial

        # Binary GBYE packet: 4-byte command + 4-byte length (0)
        gbye_packet = struct.pack("<4sI", b"GBYE", 0)

        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                self._radar = KLD7(port, baudrate=3000000)
                actual_baud = (
                    getattr(self._radar._port, "baudrate", "unknown")
                    if hasattr(self._radar, "_port")
                    else "unknown"
                )
                logger.info(
                    "[KLD7] Connected on %s at %s baud (attempt %d/%d)",
                    port,
                    actual_baud,
                    attempt,
                    max_attempts,
                )
                break
            except Exception as e:
                logger.warning("[KLD7] Connect attempt %d/%d failed: %s", attempt, max_attempts, e)
                if attempt >= max_attempts:
                    logger.error(
                        "[KLD7] Connection failed after %d attempts — giving up",
                        max_attempts,
                        exc_info=True,
                    )
                    return False

                # Send binary GBYE at 3Mbaud to close a stuck prior session,
                # then drain. The K-LD7 will return to idle and accept INIT
                # at 115200 on the next attempt.
                try:
                    with pyserial.Serial(
                        port, 3000000, parity=pyserial.PARITY_EVEN, timeout=0.1
                    ) as ser:
                        ser.reset_input_buffer()
                        ser.write(gbye_packet)
                        ser.flush()
                        time.sleep(0.3)
                        # Drain any response
                        while ser.in_waiting:
                            ser.read(ser.in_waiting)
                            time.sleep(0.1)
                    logger.info("[KLD7] Sent GBYE at 3Mbaud to reset prior session")
                except Exception as flush_err:
                    logger.debug("[KLD7] GBYE flush failed: %s", flush_err)
                time.sleep(0.3)

        self._configure_for_golf()
        logger.info(
            "[KLD7] Ready: port=%s, baud=%s, range=%dm, speed=%dkm/h, orientation=%s",
            port,
            actual_baud,
            self.range_m,
            self.speed_kmh,
            self.orientation,
        )
        return True

    def _configure_for_golf(self):
        """Configure K-LD7 parameters for golf ball detection."""
        range_settings = {5: 0, 10: 1, 30: 2, 100: 3}
        speed_settings = {12: 0, 25: 1, 50: 2, 100: 3}

        params = self._radar.params
        params.RRAI = range_settings.get(self.range_m, 0)
        params.RSPI = speed_settings.get(self.speed_kmh, 3)
        params.RBFR = self.base_freq
        params.DEDI = 2
        params.THOF = 10
        params.TRFT = 1
        params.MIAN = -90
        params.MAAN = 90
        params.MIRA = 0
        params.MARA = 100
        params.MISP = 0
        params.MASP = 100
        params.VISU = 0

        freq_labels = {0: "Low/24.05GHz", 1: "Mid/24.15GHz", 2: "High/24.25GHz"}
        logger.info(
            "[KLD7] Configured: range=%dm, speed=%dkm/h, orientation=%s, RBFR=%d (%s)",
            self.range_m,
            self.speed_kmh,
            self.orientation,
            self.base_freq,
            freq_labels.get(self.base_freq, "unknown"),
        )

    def start(self):
        """Start the background streaming thread."""
        if self._running:
            return
        self._running = True
        self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._stream_thread.start()
        logger.info("[KLD7] Streaming started (orientation=%s)", self.orientation)

    def stop(self):
        """Stop streaming and close connection."""
        self._running = False
        if self._stream_thread:
            self._stream_thread.join(timeout=5)
            self._stream_thread = None
        if self._radar:
            try:
                self._radar.close()
            except Exception:
                pass
            try:
                self._radar._port = None
            except Exception:
                pass
            self._radar = None
        logger.info("[KLD7] Stopped")

    def _stream_loop(self):
        """Background thread: stream RADC into ring buffer.

        Retries on packet errors (common when two K-LD7s start simultaneously).
        The kld7 library's stream_frames generator can fail if a stray packet
        from the prior GNFD cycle is still in the serial buffer.
        """
        from kld7 import FrameCode, KLD7Exception

        frame_codes = FrameCode.RADC
        frame_count = 0
        errors = 0
        max_errors = 10

        logger.info("[KLD7] Stream started: RADC only (3Mbaud, %s)", self.orientation)

        # Monkey-patch the library's _read_packet to handle short reads.
        # At 12M USB Full Speed, the FTDI driver splits large packets across
        # USB microframes. serial.read(length) returns whatever's available,
        # giving a short read. The library prints "Failed to read all of reply"
        # and continues with a truncated packet, causing cascading errors.
        # This patch retries the read until we get all expected bytes.
        import struct

        def _robust_read_packet(device):
            if device._port is None:
                raise KLD7Exception("serial port has been closed")
            header = device._port.read(8)
            if len(header) == 0:
                raise KLD7Exception("Timeout waiting for reply")
            if len(header) != 8:
                raise KLD7Exception("Wrong length reply")
            reply, length = struct.unpack("<4sI", header)
            reply = reply.decode("ASCII")
            if length != 0:
                payload = b""
                remaining = length
                while remaining > 0:
                    chunk = device._port.read(remaining)
                    if not chunk:
                        break
                    payload += chunk
                    remaining -= len(chunk)
            else:
                payload = None
            return reply, payload

        self._radar._read_packet = lambda: _robust_read_packet(self._radar)

        while self._running and errors < max_errors:
            try:
                for code, payload in self._radar.stream_frames(frame_codes, max_count=-1):
                    if not self._running:
                        break

                    if code == "RADC":
                        # Validate payload — USB short reads can truncate packets
                        if not isinstance(payload, bytes) or len(payload) != 3072:
                            continue
                        frame = KLD7Frame(timestamp=time.time())
                        frame.radc = payload
                        self._add_frame(frame)
                        frame_count += 1
                        errors = 0  # reset on success

                        if frame_count == 1:
                            logger.info(
                                "[KLD7] First RADC frame received (%d bytes, %s)",
                                len(payload) if payload else 0,
                                self.orientation,
                            )
                        elif frame_count == 50:
                            logger.info(
                                "[KLD7] Stream health: %d RADC frames (%s)",
                                frame_count,
                                self.orientation,
                            )

                if not self._running:
                    break
                logger.warning(
                    "[KLD7] Stream generator exited (frames=%d, %s)", frame_count, self.orientation
                )

            except KLD7Exception as e:
                errors += 1
                logger.debug(
                    "[KLD7] Stream error %d/%d (%s): %s", errors, max_errors, self.orientation, e
                )
                if errors < max_errors:
                    # Drain serial and retry
                    try:
                        self._radar._drain_serial()
                    except Exception:
                        pass
                    time.sleep(0.1)

            except Exception as e:
                logger.error(
                    "[KLD7] Stream crashed after %d frames (%s): %s",
                    frame_count,
                    self.orientation,
                    e,
                    exc_info=True,
                )
                break

        if errors >= max_errors:
            logger.error(
                "[KLD7] Stream gave up after %d consecutive errors (%s)",
                max_errors,
                self.orientation,
            )

    def _add_frame(self, frame: KLD7Frame):
        """Add a frame to the ring buffer."""
        self._ring_buffer.append(frame)

    def _get_radc_frames(self, shot_timestamp: Optional[float] = None) -> list[dict]:
        """Collect RADC frames, optionally narrowed around the shot timestamp."""
        frames = [
            {"timestamp": frame.timestamp, "radc": frame.radc}
            for frame in self._ring_buffer
            if frame.radc is not None
        ]

        if shot_timestamp is None or not frames:
            return frames

        window_start = shot_timestamp - self.shot_window_seconds
        window_end = shot_timestamp + self.shot_window_seconds
        filtered = [frame for frame in frames if window_start <= frame["timestamp"] <= window_end]

        logger.info(
            "[KLD7] RADC: filtered %d/%d frames around shot timestamp %.3f (+/- %.0fms)",
            len(filtered),
            len(frames),
            shot_timestamp,
            self.shot_window_seconds * 1000,
        )
        return filtered

    def _extract_ball_radc(
        self,
        ball_speed_mph: float,
        shot_timestamp: Optional[float] = None,
    ) -> Optional[KLD7Angle]:
        """Extract ball launch angle via RADC phase interferometry.

        Uses the OPS243-measured ball speed to narrow the FFT velocity
        search band, then extracts angle from F1A/F2A phase difference.
        """
        from .radc import extract_launch_angle

        frames = self._get_radc_frames(shot_timestamp=shot_timestamp)

        if not frames:
            logger.info(
                "[KLD7] RADC: no frames with RADC data in buffer (%d total frames)",
                len(self._ring_buffer),
            )
            return None

        logger.info(
            "[KLD7] RADC: examining %d frames, ball_speed=%.1f mph", len(frames), ball_speed_mph
        )

        # Horizontal radar sees weaker ball returns (narrower beam in
        # the horizontal plane), so use a lower impact energy threshold.
        energy_threshold = 1.85 if self.orientation == "horizontal" else 3.0

        results = extract_launch_angle(
            frames,
            ops243_ball_speed_mph=ball_speed_mph,
            angle_offset_deg=self.angle_offset_deg,
            speed_tolerance_mph=10.0,
            impact_energy_threshold=energy_threshold,
            orientation=self.orientation,
        )

        if not results:
            logger.info(
                "[KLD7] RADC: no ball detections for %.1f mph (%s, %d frames examined)",
                ball_speed_mph,
                self.orientation,
                len(frames),
            )
            return None

        best = results[0]
        logger.info(
            "[KLD7] RADC: angle=%.1f° speed=%.1f mph snr=%.1f conf=%.2f frames=%d",
            best["launch_angle_deg"],
            best["ball_speed_mph"],
            best["avg_snr_db"],
            best["confidence"],
            best["frame_count"],
        )

        if self.orientation == "vertical":
            return KLD7Angle(
                vertical_deg=best["launch_angle_deg"],
                horizontal_deg=None,
                confidence=best["confidence"],
                num_frames=best["frame_count"],
                magnitude=best["avg_snr_db"],
                detection_class="ball",
            )
        return KLD7Angle(
            vertical_deg=None,
            horizontal_deg=best["launch_angle_deg"],
            confidence=best["confidence"],
            num_frames=best["frame_count"],
            magnitude=best["avg_snr_db"],
            detection_class="ball",
        )

    def get_angle_for_shot(
        self, shot_timestamp: Optional[float] = None, ball_speed_mph: Optional[float] = None
    ) -> Optional[KLD7Angle]:
        """Search the ring buffer for the ball launch angle using RADC phase interferometry.

        Requires ball_speed_mph from OPS243 to narrow the FFT velocity search.
        Returns None if RADC extraction fails or ball_speed_mph not provided.
        """
        logger.info(
            "[KLD7] Angle extraction: ball_speed=%s mph, buffer=%d frames",
            "%.1f" % ball_speed_mph if ball_speed_mph else "None",
            len(self._ring_buffer),
        )

        if ball_speed_mph is None:
            logger.info("[KLD7] No ball speed provided, cannot extract RADC angle")
            return None

        try:
            result = self._extract_ball_radc(
                ball_speed_mph,
                shot_timestamp=shot_timestamp,
            )
            if result is not None:
                return result
            logger.info(
                "[KLD7] RADC extraction returned None (no detections at %.1f mph)", ball_speed_mph
            )
        except Exception as e:
            logger.warning("[KLD7] RADC extraction failed: %s", e, exc_info=True)

        return None

    def get_club_angle(self, club_speed_mph: Optional[float] = None) -> Optional[KLD7Angle]:
        """Extract club head angle from RADC using OPS243 club speed.

        Same approach as ball extraction — uses club speed to find the
        club's aliased velocity bin in the FFT, then phase interferometry.
        """
        if club_speed_mph is None:
            return None

        try:
            result = self._extract_ball_radc(club_speed_mph)
            if result is not None:
                # Re-tag as club detection
                result.detection_class = "club"
                logger.info(
                    "[KLD7] Club angle: %.1f° at %.1f mph (%s)",
                    result.vertical_deg or result.horizontal_deg,
                    club_speed_mph,
                    self.orientation,
                )
                return result
        except Exception as e:
            logger.debug("[KLD7] Club angle extraction failed: %s", e)

        return None

    def snapshot_buffer(self) -> list:
        """Return a serializable snapshot of the current ring buffer.

        Call this BEFORE get_angle_for_shot/reset to capture raw data
        for offline analysis alongside OPS243 shot data.
        """
        frames = []
        for frame in self._ring_buffer:
            entry = {
                "timestamp": frame.timestamp,
                "tdat": frame.tdat,
                "pdat": frame.pdat,
            }
            if frame.radc is not None:
                entry["has_radc"] = True
            frames.append(entry)
        return frames

    def reset(self):
        """Clear the ring buffer after a shot is processed."""
        self._ring_buffer.clear()
