"""
OPS243-A Doppler Radar Driver for Golf Launch Monitor.

This module provides a Python interface to the OmniPreSense OPS243-A
short-range radar sensor via USB/serial connection.

Key specs for golf application:
- Speed accuracy: +/- 0.5%
- Direction reporting (inbound/outbound)
- Detection range: 50-100m (RCS=10), ~4-5m for golf ball sized objects

Recommended golf configuration (per OmniPreSense AN-027):
- 30ksps sample rate (max ~208 mph, sufficient for all golf)
- 128 buffer size
- FFT 4096 (X=32) for ±0.1 mph resolution at ~56 Hz report rate
- Positioning: 6-8 feet behind ball, 10° upward angle

Speed limits by sample rate:
- 10kHz (SX): max 69.5 mph  - too slow for golf
- 20kHz (S2): max 139 mph   - marginal for fast shots
- 30kHz (S=30): max 208 mph - RECOMMENDED for golf
- 50kHz (SL): max 347 mph   - overkill, lower resolution
- 100kHz (SC): max 695 mph  - overkill
"""

import json
import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional

import serial
import serial.tools.list_ports

# Configure logging for raw radar data
logger = logging.getLogger("ops243")
raw_logger = logging.getLogger("ops243.raw")

# Global flag to control raw reading console output
_show_raw_readings = False


def set_show_raw_readings(enabled: bool):
    """Enable/disable printing raw radar readings to console."""
    global _show_raw_readings  # pylint: disable=global-statement
    _show_raw_readings = enabled


class SpeedUnit(Enum):
    """Speed units supported by OPS243-A."""

    MPS = "UM"  # meters per second (default)
    MPH = "US"  # miles per hour
    KPH = "UK"  # kilometers per hour
    FPS = "UF"  # feet per second
    CMS = "UC"  # centimeters per second


class Direction(Enum):
    """Direction of detected object."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"
    UNKNOWN = "unknown"


@dataclass
class SpeedReading:
    """A single speed reading from the radar."""

    speed: float
    direction: Direction
    magnitude: Optional[float] = None
    timestamp: Optional[float] = None
    unit: str = "mph"


@dataclass
class IQBlock:
    """
    A block of raw I/Q samples from the radar.

    Each block contains 128 samples at 30ksps (~4.3ms of data).
    Blocks arrive every ~31ms due to serial bandwidth limits.
    Used for continuous I/Q streaming mode where we process
    the FFT locally instead of using the radar's internal processing.
    """

    i_samples: List[int]  # Raw I channel ADC values (0-4095)
    q_samples: List[int]  # Raw Q channel ADC values (0-4095)
    timestamp: float  # When this block was received


class OPS243Radar:
    """
    Driver for OPS243-A Doppler radar sensor.

    Production mode uses rolling buffer capture exclusively.

    Example usage:
        radar = OPS243Radar()
        radar.connect()
        radar.configure_for_rolling_buffer()

        # Wait for hardware trigger (sound trigger via HOST_INT)
        response = radar.wait_for_hardware_trigger()

        # Re-arm for next capture
        radar.rearm_rolling_buffer()
    """

    # Default serial settings per datasheet
    DEFAULT_BAUD = 57600
    DEFAULT_TIMEOUT = 1.0

    # Common USB identifiers for OPS243
    VENDOR_IDS = [0x0483]  # STMicroelectronics

    def __init__(self, port: Optional[str] = None, baud: int = DEFAULT_BAUD):
        """
        Initialize radar driver.

        Args:
            port: Serial port (e.g., '/dev/ttyACM0'). If None, auto-detect.
            baud: Baud rate (default 57600 per datasheet)
        """
        self.port = port
        self.baud = baud
        self.serial: Optional[serial.Serial] = None
        self._streaming = False
        self._stream_thread: Optional[threading.Thread] = None
        self._iq_callback: Optional[Callable[[IQBlock], None]] = None
        self._iq_error_callback: Optional[Callable[[str], None]] = None
        self._unit = "mph"
        self._json_mode = False
        self._magnitude_enabled = False
        self.last_hardware_trigger_time: Optional[float] = None

    @staticmethod
    def find_radar_ports() -> List[str]:
        """
        Find potential OPS243 radar ports.

        Returns:
            List of port names that might be OPS243 devices
        """
        ports = []
        for port in serial.tools.list_ports.comports():
            # OPS243 shows up as USB serial device
            if port.vid in OPS243Radar.VENDOR_IDS or "ACM" in port.device:
                ports.append(port.device)
            # Also check description for OmniPreSense
            elif port.description and "OmniPreSense" in port.description:
                ports.append(port.device)
        return ports

    def connect(self, timeout: float = DEFAULT_TIMEOUT) -> bool:
        """
        Connect to the radar sensor.

        Args:
            timeout: Serial read timeout in seconds

        Returns:
            True if connection successful
        """
        if self.port is None:
            ports = self.find_radar_ports()
            if not ports:
                raise ConnectionError(
                    "No OPS243 radar found. Check USB connection and try specifying port manually."
                )
            self.port = ports[0]

        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            # Drain any in-progress dump (e.g. radar triggered while no software was running).
            # Opening the port unblocks the radar's UART TX, so we read until silence.
            self._drain_serial()
            return True
        except serial.SerialException as e:
            raise ConnectionError(f"Failed to connect to {self.port}: {e}") from e

    def disconnect(self):
        """Disconnect from the radar sensor."""
        self.stop_streaming()
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.serial = None

    def _drain_serial(self, quiet_period: float = 0.5, max_wait: float = 5.0):
        """
        Drain serial port until no data arrives for quiet_period seconds.

        Handles the case where the radar was triggered while no software was
        running. The radar may be mid-dump (I/Q data streaming out) when we
        connect. We need to let it finish before sending any commands.

        Args:
            quiet_period: Seconds of silence before considering drain complete
            max_wait: Maximum total seconds to wait before giving up
        """
        start = time.monotonic()
        drained = 0
        old_timeout = self.serial.timeout
        self.serial.timeout = quiet_period

        while time.monotonic() - start < max_wait:
            chunk = self.serial.read(4096)
            if not chunk:
                break  # No data for quiet_period — drain complete
            drained += len(chunk)

        self.serial.timeout = old_timeout
        self.serial.reset_input_buffer()

        if drained > 0:
            logger.info("[OPS] Drained %d bytes of stale data from serial buffer", drained)

    def _send_command(self, cmd: str) -> str:
        """
        Send a command to the radar and return response.

        Args:
            cmd: Two-character command (e.g., "??", "US")

        Returns:
            Response string from radar
        """
        if not self.serial or not self.serial.is_open:
            raise ConnectionError("Not connected to radar")

        # Clear input buffer
        self.serial.reset_input_buffer()

        # Send command
        self.serial.write(cmd.encode("ascii"))

        # For commands that require carriage return
        # Note: S# commands (trigger split) also need \r
        if "=" in cmd or ">" in cmd or "<" in cmd or "#" in cmd:
            self.serial.write(b"\r")

        # Wait for response
        time.sleep(0.1)

        # Read response
        response = ""
        while self.serial.in_waiting:
            response += self.serial.read(self.serial.in_waiting).decode("ascii", errors="ignore")
            time.sleep(0.05)

        return response.strip()

    def get_info(self) -> dict:
        """
        Get radar module information.

        Returns:
            Dict with product, version, settings info
        """
        response = self._send_command("??")
        info = {}

        for line in response.split("\n"):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    info.update(data)
                except json.JSONDecodeError:
                    pass

        return info

    def get_firmware_version(self) -> str:
        """Get firmware version string."""
        response = self._send_command("?V")
        try:
            data = json.loads(response)
            return data.get("Version", "unknown")
        except json.JSONDecodeError:
            return response

    def set_units(self, unit: SpeedUnit):
        """
        Set speed output units.

        Args:
            unit: SpeedUnit enum value
        """
        self._send_command(unit.value)
        unit_names = {
            SpeedUnit.MPS: "m/s",
            SpeedUnit.MPH: "mph",
            SpeedUnit.KPH: "kph",
            SpeedUnit.FPS: "fps",
            SpeedUnit.CMS: "cm/s",
        }
        self._unit = unit_names[unit]

    def set_sample_rate(self, rate: int):
        """
        Set sampling rate for speed measurement.

        Higher rates allow detecting faster objects but reduce resolution.
        Max detectable speeds by rate:
        - 10kHz: 69.5 mph (too slow for golf)
        - 20kHz: 139.1 mph (marginal for fast shots)
        - 30kHz: 208.5 mph (RECOMMENDED for golf per OmniPreSense)
        - 50kHz: 347.7 mph (overkill, lower resolution)
        - 100kHz: 695.4 mph (overkill)

        Args:
            rate: Sample rate in samples/second
                  Common values: 10000, 20000, 30000 (recommended), 50000, 100000
        """
        rate_commands = {
            1000: "SI",
            5000: "SV",
            10000: "SX",
            20000: "S2",
            50000: "SL",
            100000: "SC",
        }

        if rate in rate_commands:
            self._send_command(rate_commands[rate])
        else:
            # Use configurable rate command (S=nn where nn is in ksps)
            # 30ksps is recommended for golf (S=30)
            ksps = rate // 1000
            self._send_command(f"S={ksps}")

    def set_buffer_size(self, size: int):
        """
        Set sample buffer size.

        Smaller buffers = faster updates but lower resolution.

        Args:
            size: Buffer size (128, 256, 512, or 1024)
        """
        size_commands = {128: "S(", 256: "S[", 512: "S<", 1024: "S>"}
        if size in size_commands:
            self._send_command(size_commands[size])

    def set_min_speed_filter(self, min_speed: float):
        """
        Set minimum speed filter - ignore speeds below this.

        Args:
            min_speed: Minimum speed to report (in current units)
        """
        self._send_command(f"R>{min_speed}")

    def set_max_speed_filter(self, max_speed: float):
        """
        Set maximum speed filter - ignore speeds above this.

        Args:
            max_speed: Maximum speed to report (in current units)
        """
        self._send_command(f"R<{max_speed}")

    def set_magnitude_filter(self, min_mag: int = 0, max_mag: int = 0):
        """
        Set magnitude (signal strength) filter.

        Higher magnitude = larger/closer/more reflective objects.

        Args:
            min_mag: Minimum magnitude to report (0 = no filter)
            max_mag: Maximum magnitude to report (0 = no filter)
        """
        if min_mag > 0:
            self._send_command(f"M>{min_mag}")
        if max_mag > 0:
            self._send_command(f"M<{max_mag}")

    def set_direction_filter(self, direction: Optional[Direction]):
        """
        Filter by direction at the hardware level.

        Per API doc AN-010-AD:
        - R+ = Inbound Only Direction (toward radar)
        - R- = Outbound Only Direction (away from radar)
        - R| = Both directions

        Args:
            direction: Direction.INBOUND, Direction.OUTBOUND, or None for both
        """
        if direction == Direction.INBOUND:
            cmd = "R+"
        elif direction == Direction.OUTBOUND:
            cmd = "R-"
        else:
            cmd = "R|"

        logger.info("[OPS] Setting direction filter: %s", cmd)
        self._send_command(cmd)

    def enable_json_output(self, enabled: bool = True):
        """
        Enable/disable JSON formatted output.

        Args:
            enabled: True for JSON, False for plain numbers
        """
        self._send_command("OJ" if enabled else "Oj")
        self._json_mode = enabled

    def enable_magnitude_report(self, enabled: bool = True):
        """
        Enable/disable magnitude reporting with speed.

        Args:
            enabled: True to include magnitude in readings
        """
        self._send_command("OM" if enabled else "Om")
        self._magnitude_enabled = enabled

    def set_transmit_power(self, level: int):
        """
        Set transmit power level.

        Args:
            level: 0-7, where 0 is max power and 7 is min power
        """
        if level < 0 or level > 7:
            raise ValueError("Power level must be 0-7")
        self._send_command(f"P{level}")

    def enable_peak_averaging(self, enabled: bool = True):
        """
        Enable/disable peak speed averaging.

        When enabled, filters out multiple speed reports from signal reflections
        and provides just the primary speed of the detected object. Recommended
        for golf to get cleaner ball speed readings.

        Args:
            enabled: True to enable averaging, False to disable
        """
        self._send_command("K+" if enabled else "K-")

    def set_fft_size(self, size: int):
        """
        Set FFT size for frequency analysis.

        FFT size affects speed resolution and report rate.
        The X= command sets FFT size as a multiplier of buffer size:
        - X=1: FFT = buffer size
        - X=2: FFT = 2x buffer size
        - X=32: FFT = 32x buffer size (4096 with 128 buffer)

        With 30ksps and buffer 128:
        - X=1 (128 FFT): ~234 Hz, ±1.6 mph resolution
        - X=2 (256 FFT): ~117 Hz, ±0.8 mph resolution
        - X=32 (4096 FFT): ~56 Hz, ±0.1 mph resolution (recommended for golf)

        Args:
            size: FFT multiplier (1, 2, 4, 8, 16, 32)
        """
        valid_sizes = [1, 2, 4, 8, 16, 32]
        if size not in valid_sizes:
            raise ValueError(f"FFT size must be one of {valid_sizes}")
        self._send_command(f"X={size}")

    def set_num_reports(self, num: int):
        """
        Set number of objects to report per sample cycle.

        For golf, setting this to 4+ allows detecting both club head and ball
        in the same sample window. The radar will report the N strongest
        signals detected.

        Args:
            num: Number of reports per cycle (1-9 with On, up to 16 with O=n)
        """
        if num < 1:
            num = 1
        if num <= 9:
            cmd = f"O{num}"
        else:
            cmd = f"O={num}"

        logger.debug("[OPS] Sending num_reports command: %s", cmd)
        self._send_command(cmd)

    def system_reset(self):
        """Perform a full system reset including the clock."""
        self._send_command("P!")
        time.sleep(1)

    def get_serial_number(self) -> str:
        """Get the radar's serial number."""
        response = self._send_command("?N")
        try:
            data = json.loads(response)
            return data.get("SerialNumber", "unknown")
        except json.JSONDecodeError:
            return response

    def get_speed_filter(self) -> dict:
        """
        Get current speed filter settings.

        Returns:
            Dict with min/max speed filter values
        """
        response = self._send_command("R?")
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"raw": response}

    def get_current_units(self) -> str:
        """Get the currently configured speed units."""
        response = self._send_command("U?")
        try:
            data = json.loads(response)
            return data.get("Units", "unknown")
        except json.JSONDecodeError:
            return response

    def _parse_reading(self, line: str) -> Optional[SpeedReading]:
        """
        Parse a reading from the radar output.

        Direction is determined by the SIGN of the speed value.

        With R| (both directions) mode:
        - Negative speed = OUTBOUND (away from radar - ball flight)
        - Positive speed = INBOUND (toward radar - backswing)

        With O4 (multi-object) mode, speed and magnitude are arrays.
        We return the first/strongest reading here; the full array is
        available via read_speed_multi().

        Args:
            line: Raw line from serial output

        Returns:
            SpeedReading or None if parse fails
        """
        # Always log raw line when debugging enabled (before any parsing)
        if _show_raw_readings:
            print(f"[SERIAL] {line!r}")

        try:
            if self._json_mode and line.startswith("{"):
                data = json.loads(line)
                speed_data = data.get("speed", 0)
                magnitude_data = data.get("magnitude")

                # Handle array format from O4 multi-object mode
                # Arrays are ordered by magnitude (strongest first)
                if isinstance(speed_data, list):
                    if not speed_data:
                        return None
                    speed = float(speed_data[0])
                    magnitude = float(magnitude_data[0]) if magnitude_data else None

                    if _show_raw_readings:
                        print(
                            f"[MULTI] {len(speed_data)} objects: speeds={speed_data} mags={magnitude_data}"
                        )
                else:
                    speed = float(speed_data)
                    magnitude = float(magnitude_data) if magnitude_data else None

                # Direction from sign of speed value
                # Negative = OUTBOUND (away from radar - golf ball flight)
                # Positive = INBOUND (toward radar - backswing)
                if speed > 0:
                    direction = Direction.INBOUND
                else:
                    direction = Direction.OUTBOUND

                # Debug: print raw reading to console (sign indicates direction)
                if _show_raw_readings:
                    print(f"[RAW] {speed:+.1f} mph -> {direction.value} (mag: {magnitude})")

                # Log parsed reading for debugging
                logger.debug(
                    "[OPS] PARSED: raw_speed=%.2f abs_speed=%.2f dir=%s mag=%s",
                    speed,
                    abs(speed),
                    direction.value,
                    magnitude,
                )

                return SpeedReading(
                    speed=abs(speed),
                    direction=direction,
                    magnitude=magnitude,
                    timestamp=time.time(),
                    unit=self._unit,
                )

            # Plain number format - direction from sign
            speed = float(line)
            if speed > 0:
                direction = Direction.INBOUND
            else:
                direction = Direction.OUTBOUND

            # Debug: print raw reading to console
            if _show_raw_readings:
                print(f"[RAW] {speed:+.1f} mph -> {direction.value}")

            logger.debug(
                "[OPS] PARSED (plain): raw_speed=%.2f abs_speed=%.2f dir=%s",
                speed,
                abs(speed),
                direction.value,
            )

            return SpeedReading(
                speed=abs(speed), direction=direction, timestamp=time.time(), unit=self._unit
            )
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("[OPS] Failed to parse reading: %r - %s", line, e)
            return None

    def stop_streaming(self):
        """Stop any active I/Q streaming."""
        self._streaming = False
        if self._stream_thread:
            self._stream_thread.join(timeout=2.0)
            self._stream_thread = None

        # If we were doing I/Q streaming, tell radar to stop
        if self._iq_callback is not None:
            self.disable_raw_iq_output()

        self._iq_callback = None
        self._iq_error_callback = None

    def save_config(self):
        """Save current configuration to persistent memory."""
        self._send_command("A!")
        time.sleep(1)  # Wait for flash write

    def reset_config(self):
        """Reset configuration to factory defaults."""
        self._send_command("AX")
        time.sleep(1)

    # =========================================================================
    # Rolling Buffer Mode (G1)
    # =========================================================================

    def enter_rolling_buffer_mode(self, pre_trigger_segments: int = 16, sample_rate_ksps: int = 30):
        """
        Enter rolling buffer mode using the verified working sequence.

        This is the SINGLE SOURCE OF TRUTH for entering rolling buffer mode.
        All other methods that need rolling buffer mode should call this.

        The sequence follows OmniPreSense API doc AN-010-AD exactly:
        1. PI - reset to idle (clean state)
        2. GC - enter rolling buffer mode
        3. PA - activate sampling
        4. S=30 - set sample rate (with \\r)
        5. S#n - set trigger split (with \\r)
        6. PA - reactivate (CRITICAL after settings changes)
        7. Wait for buffer to fill

        Args:
            pre_trigger_segments: Number of pre-trigger segments (0-32).
                Each segment = 128 samples = ~4.27ms at 30ksps.
                Default 12 gives ~51ms pre-trigger, ~85ms post-trigger.
        """
        if not self.serial or not self.serial.is_open:
            raise ConnectionError("Not connected to radar")

        print(
            f"[RADAR] Entering rolling buffer mode (S#{pre_trigger_segments}, S={sample_rate_ksps})..."
        )
        logger.info(
            "[OPS] Entering rolling buffer mode (pre_trigger_segments=%d)...", pre_trigger_segments
        )

        # Clear any stale data
        self.serial.reset_input_buffer()

        # Step 1: Reset to idle for clean state
        self.serial.write(b"PI")
        time.sleep(0.2)
        logger.debug("[OPS] PI: reset to idle")

        # Step 2: Enter rolling buffer mode
        self.serial.write(b"GC")
        time.sleep(0.1)
        logger.debug("[OPS] GC: rolling buffer mode")

        # Step 3: Activate sampling
        self.serial.write(b"PA")
        time.sleep(0.1)
        logger.debug("[OPS] PA: activate sampling")

        # Step 4: Set sample rate - requires \r
        self.serial.write(f"S={sample_rate_ksps}\r".encode())
        self.serial.flush()
        time.sleep(0.15)
        logger.debug("[OPS] S=%d: %dksps sample rate", sample_rate_ksps, sample_rate_ksps)

        # Step 5: Set trigger split - requires \r
        pre_trigger_segments = max(0, min(32, pre_trigger_segments))
        self.serial.write(f"S#{pre_trigger_segments}\r".encode())
        self.serial.flush()
        time.sleep(0.15)
        logger.debug("[OPS] S#%d: pre-trigger segments", pre_trigger_segments)

        # Step 6: CRITICAL - Reactivate after settings changes
        self.serial.write(b"PA")
        time.sleep(0.1)
        logger.debug("[OPS] PA: reactivate sampling")

        # Clear any response data from commands
        self.serial.reset_input_buffer()

        # Step 7: Wait for buffer to fill
        # At 30ksps, 4096 samples takes ~137ms, but we wait a bit longer
        # to ensure stable state before accepting triggers
        time.sleep(0.3)

        print(
            f"[RADAR] Rolling buffer mode ACTIVE (S#{pre_trigger_segments}, {sample_rate_ksps}ksps)"
        )
        logger.info(
            "[OPS] Rolling buffer mode active (S#%d, %dksps)",
            pre_trigger_segments,
            sample_rate_ksps,
        )

    def disable_rolling_buffer(self):
        """Disable rolling buffer mode and return to normal CW mode."""
        logger.info("[OPS] Disabling rolling buffer mode...")
        self._send_command("GS")  # Return to standard CW mode
        time.sleep(0.1)
        logger.info("[OPS] Rolling buffer mode disabled (returned to CW mode)")

    def persist_rolling_buffer_mode(
        self, pre_trigger_segments: int = 16, sample_rate_ksps: int = 30
    ):
        """
        Save rolling buffer mode to persistent memory.

        The OPS243-A has a bug where the HOST_INT pin mode switches
        unexpectedly when transitioning from normal mode (GS) to rolling
        buffer mode (GC) at runtime. OmniPreSense workaround:

        1. Enter rolling buffer mode (GC) with desired settings
        2. Save to persistent memory (A!)
        3. Power cycle the board

        After power cycle, the board starts in rolling buffer mode and
        HOST_INT works correctly. Re-arm after each capture with PA.

        This only needs to be done ONCE per radar board (or when changing
        sample rate / pre-trigger settings).

        Args:
            pre_trigger_segments: Number of pre-trigger segments (0-32).
            sample_rate_ksps: Sample rate in ksps (default: 30).
        """
        if not self.serial or not self.serial.is_open:
            raise ConnectionError("Not connected to radar")

        logger.info("[OPS] Persisting rolling buffer mode to flash memory...")

        # Enter rolling buffer mode with desired settings
        self.enter_rolling_buffer_mode(
            pre_trigger_segments=pre_trigger_segments, sample_rate_ksps=sample_rate_ksps
        )

        # Save to persistent memory
        self.serial.write(b"A!")
        time.sleep(0.5)

        logger.info(
            "[OPS] Rolling buffer mode saved to persistent memory. "
            "Power cycle the board for changes to take effect."
        )
        print("[RADAR] Settings saved to persistent memory.")
        print("[RADAR] Power cycle the board (unplug USB, wait 3s, replug).")

    def trigger_capture(self, timeout: float = 10.0) -> str:
        """
        Trigger buffer capture and return raw I/Q data.

        Sends S! command to dump the rolling buffer contents.
        The response contains:
        - {"sample_time": "xxx.xxx"}
        - {"trigger_time": "xxx.xxx"}
        - {"I": [4096 integers...]}
        - {"Q": [4096 integers...]}

        Note: The I/Q data can be 20-30KB of JSON. At 57600 baud (~5.7KB/s),
        this takes 4-5 seconds to transmit. Default timeout is 10 seconds.

        Args:
            timeout: Maximum time to wait for response (default 10s)

        Returns:
            Raw response string containing JSON lines
        """
        if not self.serial or not self.serial.is_open:
            raise ConnectionError("Not connected to radar")

        # Clear input buffer
        self.serial.reset_input_buffer()

        # Send trigger command
        self.serial.write(b"S!\r")
        self.serial.flush()

        response_lines = []
        start_time = time.time()
        last_data_time = start_time
        bytes_received = 0

        # Read data until timeout or complete response
        while (time.time() - start_time) < timeout:
            if self.serial.in_waiting:
                chunk = self.serial.read(self.serial.in_waiting)
                response_lines.append(chunk.decode("ascii", errors="ignore"))
                bytes_received += len(chunk)
                last_data_time = time.time()

                # Check if we have complete data (Q array ends the response)
                full_response = "".join(response_lines)
                if '"Q"' in full_response:
                    # Look for closing bracket of Q array followed by newline or EOF
                    q_idx = full_response.rfind('"Q"')
                    remaining = full_response[q_idx:]
                    if "]}" in remaining or (
                        remaining.rstrip().endswith("]")
                        and remaining.count("[") == remaining.count("]")
                    ):
                        break

                time.sleep(0.01)  # Short sleep to accumulate data
            else:
                # No data available
                # If we've received some data and haven't gotten more in 0.5s, consider done
                if bytes_received > 100 and (time.time() - last_data_time) > 0.5:
                    full_response = "".join(response_lines)
                    if '"Q"' in full_response:
                        break
                time.sleep(0.02)

        full_response = "".join(response_lines)

        # Only log issues, not normal operation
        if not full_response:
            logger.warning(
                "[OPS] S! trigger returned empty response after %.1fs", time.time() - start_time
            )
        else:
            logger.info(
                "[OPS] S! trigger: %d bytes in %.1fs", len(full_response), time.time() - start_time
            )
            if len(full_response) < 1000:
                # Short response usually means mode not configured correctly
                logger.info(
                    "[OPS] S! response too short (%s bytes): %s",
                    len(full_response),
                    repr(full_response[:100]),
                )

        return full_response

    def wait_for_hardware_trigger(self, timeout: float = 30.0) -> str:
        """
        Wait for hardware trigger to fire and read the buffer dump.

        Unlike trigger_capture() which sends S!, this method just waits
        for data to appear on serial — triggered externally via J3 pin 3
        (HOST_INT). Used with SoundTrigger (SparkFun SEN-14262).

        Args:
            timeout: Maximum time to wait for trigger data

        Returns:
            Raw response string containing JSON lines, or empty string on timeout
        """
        if not self.serial or not self.serial.is_open:
            raise ConnectionError("Not connected to radar")

        # Clear any stale data
        self.serial.reset_input_buffer()

        response_lines = []
        start_time = time.time()
        last_data_time = None
        bytes_received = 0
        self.last_hardware_trigger_time = None

        while (time.time() - start_time) < timeout:
            if self.serial.in_waiting:
                chunk = self.serial.read(self.serial.in_waiting)
                response_lines.append(chunk.decode("ascii", errors="ignore"))
                bytes_received += len(chunk)
                if last_data_time is None:
                    last_data_time = time.time()
                    self.last_hardware_trigger_time = last_data_time
                    logger.debug(
                        "[OPS] Hardware trigger: first byte after %.1fs",
                        last_data_time - start_time,
                    )
                else:
                    last_data_time = time.time()

                # Check if we have complete I/Q data
                full_response = "".join(response_lines)
                if '"Q"' in full_response:
                    q_idx = full_response.rfind('"Q"')
                    remaining = full_response[q_idx:]
                    if "]}" in remaining or (
                        remaining.rstrip().endswith("]")
                        and remaining.count("[") == remaining.count("]")
                    ):
                        break

                time.sleep(0.01)
            else:
                # If we've started receiving data, use shorter timeout
                if last_data_time and (time.time() - last_data_time) > 0.5:
                    full_response = "".join(response_lines)
                    if '"Q"' in full_response:
                        break
                time.sleep(0.02)

        full_response = "".join(response_lines) if response_lines else ""

        if not full_response:
            logger.info("[OPS] Hardware trigger: no data received within %.0fs", timeout)
        else:
            logger.info(
                "[OPS] Hardware trigger: %d bytes in %.1fs",
                len(full_response),
                time.time() - start_time,
            )

        return full_response

    def rearm_rolling_buffer(self, pre_trigger_segments: int = 16):
        """
        Re-arm rolling buffer for next capture.

        After a hardware trigger dumps data, the sensor pauses in Idle mode.
        Per OmniPreSense: "do a PA or GC to start the Rolling Buffer
        sampling again" after each capture.

        We also re-send S#n to ensure the pre/post trigger split is
        correct, then PA again to activate with the new setting.

        Args:
            pre_trigger_segments: Number of pre-trigger segments (0-32).
                Each segment = 128 samples = ~4.27ms at 30ksps.
        """
        if not self.serial or not self.serial.is_open:
            raise ConnectionError("Not connected to radar")

        # Drain the serial buffer until no new bytes arrive for 200ms.
        # A full I/Q dump is ~41KB at 57600 baud (~7s). If the previous
        # capture wasn't fully read, bytes are still streaming in.
        # A single reset_input_buffer() only clears what's arrived so far.
        drain_start = time.time()
        total_drained = 0
        while True:
            total_drained += self.serial.in_waiting
            self.serial.reset_input_buffer()
            time.sleep(0.2)
            if self.serial.in_waiting == 0:
                break
        logger.info(
            "[OPS] Re-arm drain: %d bytes in %.1fs", total_drained, time.time() - drain_start
        )

        # Restart sampling
        self.serial.write(b"PA")
        self.serial.flush()
        time.sleep(0.1)

        # Re-send trigger split (may reset after capture dump)
        pre_trigger_segments = max(0, min(32, pre_trigger_segments))
        self.serial.write(f"S#{pre_trigger_segments}\r".encode())
        self.serial.flush()
        time.sleep(0.1)

        # Reactivate after settings change
        self.serial.write(b"PA")
        self.serial.flush()
        time.sleep(0.15)

        self.serial.reset_input_buffer()
        logger.info("[OPS] Rolling buffer re-armed (S#%d)", pre_trigger_segments)

    def configure_for_rolling_buffer(
        self, pre_trigger_segments: int = 16, sample_rate_ksps: int = 30
    ):
        """
        Configure radar optimally for rolling buffer mode.

        This is the high-level API for entering rolling buffer mode.
        Internally calls enter_rolling_buffer_mode() which uses the
        verified working sequence.

        Settings:
        - Units: MPH
        - Transmit power: Level 3 (reduced to avoid ADC clipping)
        - Sample rate: 30ksps (max ~208 mph, required for golf)
        - Rolling buffer enabled (GC command)
        - Trigger split: Configurable pre-trigger segments

        Args:
            pre_trigger_segments: Number of pre-trigger segments (0-32).
                Each segment = 128 samples = ~4.27ms at 30ksps.
                Default 12 gives ~51ms pre-trigger, ~85ms post-trigger.
        """
        # Set units to MPH first
        self.set_units(SpeedUnit.MPH)
        logger.info("[OPS] Units: MPH")

        # Reduced transmit power to avoid ADC saturation on close targets.
        # Level 0=max, 7=min. Rolling buffer captures raw I/Q at short range,
        # so max power clips the 12-bit ADC.
        self.set_transmit_power(3)
        logger.info("[OPS] Transmit power: level 3 (reduced to avoid clipping)")

        # Enter rolling buffer mode using the single source of truth
        self.enter_rolling_buffer_mode(
            pre_trigger_segments=pre_trigger_segments, sample_rate_ksps=sample_rate_ksps
        )

        logger.info("[OPS] Rolling buffer mode configured")

    def configure_for_speed_trigger(self):
        """
        Configure radar for fast speed detection to trigger rolling buffer capture.

        Per OmniPreSense manufacturer recommendation for golf:
        - 30ksps sample rate
        - 128 buffer size
        - 256 FFT size (X=2) for ~150-200Hz report rate (5-6ms between reports)
        - R>20 = minimum 20mph filter (eliminates leg movement, backswing noise)
        - R- = outbound only (ball/club going away from radar)

        This mode is used to detect the initial club swing, then we switch
        to rolling buffer mode (GC) to capture high-resolution ball data.

        Expected timing:
        - Club detected in speed mode
        - ~5-6ms to switch to rolling buffer
        - Club to ball impact is 20-40ms, so we capture the ball
        """
        logger.info("[OPS] Configuring for fast speed trigger mode...")

        # Start from clean state
        self._send_command("GS")  # Ensure CW mode (not rolling buffer)
        time.sleep(0.1)

        self._send_command("PI")  # Idle mode
        time.sleep(0.1)

        # Set units to MPH
        self.set_units(SpeedUnit.MPH)
        logger.info("[OPS] Units: MPH")

        # Max transmit power for best detection range
        self.set_transmit_power(0)
        logger.info("[OPS] Transmit power: max (P0)")

        # 30ksps sample rate
        self.set_sample_rate(30000)
        time.sleep(0.1)
        logger.info("[OPS] Sample rate: 30ksps")

        # 128 buffer size for fast report rate
        self.set_buffer_size(128)
        time.sleep(0.1)
        logger.info("[OPS] Buffer size: 128")

        # 256 FFT size (X=2) for ~150-200Hz report rate
        # Report rate = 30000 / 128 / 2 ≈ 117 Hz per spec, but empirically faster
        self.set_fft_size(2)
        time.sleep(0.1)
        logger.info("[OPS] FFT size: 256 (X=2) for fast reports")

        # Outbound only - ignore backswing (R-)
        self._send_command("R-")
        time.sleep(0.05)
        logger.info("[OPS] Direction filter: outbound only (R-)")

        # Minimum speed 20mph - ignore leg movement and slow movements
        self._send_command("R>20")
        time.sleep(0.05)
        logger.info("[OPS] Min speed filter: 20 mph (R>20)")

        # Enable JSON output for parsing
        self.enable_json_output(True)

        # Enable magnitude reporting
        self.enable_magnitude_report(True)

        # No inter-report delay
        self._send_command("W0")
        time.sleep(0.05)

        # Activate
        self._send_command("PA")
        time.sleep(0.1)
        logger.info("[OPS] Speed trigger mode ready (PA)")

        # Verify settings
        response = self._send_command("S?")
        logger.info("[OPS] Settings: %s", response)

    def switch_to_rolling_buffer(self):
        """
        Quickly switch from speed detection mode to rolling buffer capture.

        Called immediately when a speed trigger is detected. Uses S#0 to
        capture only new data (no pre-trigger history) since we want the
        ball impact which happens AFTER the club detection.

        Per manufacturer: "have it report all the immediate data captured
        with no history (S#0 API command)"
        """
        # Switch to rolling buffer mode - radar goes active immediately
        self._send_command("GC")
        time.sleep(0.02)  # Brief delay for mode switch

        # S#0 = no pre-trigger history, only capture new samples
        self._send_command("S#0")
        time.sleep(0.02)

        # 30ksps sample rate (GC may reset to default)
        self.set_sample_rate(30000)
        time.sleep(0.02)

    def read_speed_nonblocking(self) -> Optional[SpeedReading]:
        """
        Non-blocking speed read for trigger detection.

        Returns immediately with a reading if one is available,
        or None if no complete line in buffer.
        """
        if not self.serial or not self.serial.is_open:
            return None

        if self.serial.in_waiting == 0:
            return None

        try:
            # Read available data
            raw_bytes = self.serial.read(self.serial.in_waiting)
            line = raw_bytes.decode("ascii", errors="ignore").strip()

            if not line:
                return None

            # May have multiple lines - take the last complete one
            lines = line.split("\n")
            for candidate in reversed(lines):
                candidate = candidate.strip()
                if candidate.startswith("{"):
                    reading = self._parse_reading(candidate)
                    if reading:
                        return reading

            return None
        except Exception:
            return None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
