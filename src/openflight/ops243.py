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
    MPS = "UM"      # meters per second (default)
    MPH = "US"      # miles per hour
    KPH = "UK"      # kilometers per hour
    FPS = "UF"      # feet per second
    CMS = "UC"      # centimeters per second


class PowerMode(Enum):
    """Power modes for OPS243-A."""
    ACTIVE = "PA"   # Normal operating mode
    IDLE = "PI"     # Low power idle, waits for Active command
    PULSE = "PP"    # Single pulse mode (must be in IDLE first)


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
    timestamp: float      # When this block was received


class OPS243Radar:
    """
    Driver for OPS243-A Doppler radar sensor.

    Example usage:
        radar = OPS243Radar()
        radar.connect()
        radar.configure_for_golf()

        # Blocking read
        reading = radar.read_speed()
        print(f"Speed: {reading.speed} {reading.unit}")

        # Or use callback for continuous monitoring
        def on_speed(reading):
            print(f"Detected: {reading.speed} mph")

        radar.start_streaming(callback=on_speed)
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
        self._callback: Optional[Callable[[SpeedReading], None]] = None
        self._iq_callback: Optional[Callable[[IQBlock], None]] = None
        self._iq_error_callback: Optional[Callable[[str], None]] = None
        self._unit = "mph"
        self._json_mode = False
        self._magnitude_enabled = False

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
                stopbits=serial.STOPBITS_ONE
            )
            # Give sensor time to initialize
            time.sleep(0.5)
            # Flush any startup data
            self.serial.reset_input_buffer()
            return True
        except serial.SerialException as e:
            raise ConnectionError(f"Failed to connect to {self.port}: {e}") from e

    def disconnect(self):
        """Disconnect from the radar sensor."""
        self.stop_streaming()
        if self.serial and self.serial.is_open:
            self.serial.close()
            self.serial = None

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
        self.serial.write(cmd.encode('ascii'))

        # For commands that require carriage return
        if '=' in cmd or '>' in cmd or '<' in cmd:
            self.serial.write(b'\r')

        # Wait for response
        time.sleep(0.1)

        # Read response
        response = ""
        while self.serial.in_waiting:
            response += self.serial.read(self.serial.in_waiting).decode('ascii', errors='ignore')
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

        for line in response.split('\n'):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
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
            SpeedUnit.CMS: "cm/s"
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
            100000: "SC"
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
        size_commands = {
            128: "S(",
            256: "S[",
            512: "S<",
            1024: "S>"
        }
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

        logger.info("Setting direction filter: %s", cmd)
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

    def configure_for_golf(self):
        """
        Configure radar with optimal settings for golf ball detection.

        Based on OmniPreSense AN-027 Rolling Buffer and Sports Ball Detection docs:
        - 30ksps sample rate (max ~208 mph, sufficient for all golf shots)
        - 128 buffer size
        - FFT size 4096 (X=32) for ±0.1 mph resolution at ~56 Hz report rate
        - Peak averaging enabled (K+) for cleaner speed readings
        - Multi-object reporting (O4) to detect both club and ball
        - MPH units, magnitude reporting, both directions

        Direction filtering is done in software based on the sign of the speed.
        Per API docs AN-010-AD:
        - Positive speed = INBOUND (toward radar) - ignored (backswing)
        - Negative speed = OUTBOUND (away from radar) - recorded as shot

        Positioning: Place radar 6-8 feet behind ball, angled 10° upward.
        """
        # Set units to MPH
        self.set_units(SpeedUnit.MPH)

        # 30ksps sample rate per OmniPreSense golf recommendation
        # Max detectable speed ~208 mph (sufficient for golf, pros max ~190 mph)
        # Lower than 50ksps but better resolution tradeoff
        self.set_sample_rate(30000)
        logger.info("Sample rate: 30ksps")

        # 128 buffer per OmniPreSense recommendation
        # Combined with 30ksps gives good base for FFT
        self.set_buffer_size(128)
        logger.info("Buffer size: 128")

        # FFT size 4096 (X=32 multiplier with 128 buffer)
        # This gives: ~56 Hz report rate, ±0.1 mph resolution
        self.set_fft_size(32)
        logger.info("FFT size: 4096 (X=32) - ±0.1 mph resolution @ ~56 Hz")

        # Enable magnitude to help filter weak signals
        # Magnitude helps distinguish club (larger RCS, higher mag) from ball
        self.enable_magnitude_report(True)

        # Clear direction filter to get BOTH directions
        # Direction is determined by the SIGN of the speed value.
        # Per API docs: positive = inbound, negative = outbound
        # This allows us to filter inbound readings (backswing) in software
        self.set_direction_filter(None)

        # Minimum speed 10 mph to filter very slow movements
        # We filter higher speeds (backswing) in software based on direction
        self.set_min_speed_filter(10)

        # Minimum magnitude filter to reject weak signals (walking, noise)
        # Real golf shots have magnitude 100+, walking is typically 20-30
        self.set_magnitude_filter(min_mag=50)
        logger.info("Minimum magnitude filter: 50")

        # Max transmit power for best range
        self.set_transmit_power(0)

        # Enable JSON for easier parsing
        self.enable_json_output(True)

        # Enable multi-object reporting to detect both club head AND ball
        # O4 reports up to 4 objects per sample cycle, ordered by magnitude
        self.set_num_reports(4)
        logger.info("Multi-object reporting enabled (O4)")

        # Re-enable JSON output after O4 (in case it was reset)
        self.enable_json_output(True)

        # Enable peak speed averaging per OmniPreSense recommendation
        # Helps provide cleaner speed readings
        self.enable_peak_averaging(True)
        logger.info("Peak averaging enabled (K+)")

        # Verify settings were applied
        logger.info("Verifying configuration...")
        filter_settings = self.get_speed_filter()
        logger.info("Current filter settings: %s", filter_settings)

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

        logger.debug("Sending num_reports command: %s", cmd)
        self._send_command(cmd)

    def set_decimal_precision(self, places: int):
        """
        Set number of decimal places in speed output.

        Args:
            places: Number of decimal places (0-5)
        """
        if places < 0 or places > 5:
            raise ValueError("Decimal places must be 0-5")
        self._send_command(f"F{places}")

    def set_led(self, enabled: bool = True):
        """
        Enable/disable the onboard LEDs.

        Disabling LEDs saves ~10mA of power.

        Args:
            enabled: True to turn LEDs on, False to turn off
        """
        self._send_command("OL" if enabled else "Ol")

    def set_power_mode(self, mode: PowerMode):
        """
        Set the radar power mode.

        Args:
            mode: PowerMode.ACTIVE (normal), PowerMode.IDLE (low power),
                  or PowerMode.PULSE (single shot, must be IDLE first)
        """
        self._send_command(mode.value)

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

    def enable_time_report(self, enabled: bool = True):
        """
        Enable/disable timestamp reporting with each reading.

        When enabled, time since power-on is included with speed data.

        Args:
            enabled: True to include timestamps
        """
        self._send_command("OT" if enabled else "Ot")

    def read_speed(self) -> Optional[SpeedReading]:
        """
        Read a single speed measurement (blocking).

        Returns:
            SpeedReading object or None if no valid reading
        """
        if not self.serial or not self.serial.is_open:
            raise ConnectionError("Not connected to radar")

        try:
            # Read raw bytes first to see exactly what's coming in
            raw_bytes = self.serial.readline()

            if _show_raw_readings and raw_bytes:
                print(f"[BYTES] {raw_bytes!r}")

            line = raw_bytes.decode('ascii', errors='ignore').strip()
            if not line:
                return None

            # Log raw data for debugging
            raw_logger.debug(f"RAW: {line}")

            return self._parse_reading(line)
        except serial.SerialException as e:
            if _show_raw_readings:
                print(f"[SERIAL ERROR] {e}")
            return None

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
            if self._json_mode and line.startswith('{'):
                data = json.loads(line)
                speed_data = data.get('speed', 0)
                magnitude_data = data.get('magnitude')

                # Handle array format from O4 multi-object mode
                # Arrays are ordered by magnitude (strongest first)
                if isinstance(speed_data, list):
                    if not speed_data:
                        return None
                    speed = float(speed_data[0])
                    magnitude = float(magnitude_data[0]) if magnitude_data else None

                    if _show_raw_readings:
                        print(f"[MULTI] {len(speed_data)} objects: speeds={speed_data} mags={magnitude_data}")
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
                logger.debug(f"PARSED: raw_speed={speed:.2f} abs_speed={abs(speed):.2f} dir={direction.value} mag={magnitude}")

                return SpeedReading(
                    speed=abs(speed),
                    direction=direction,
                    magnitude=magnitude,
                    timestamp=time.time(),
                    unit=self._unit
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

            logger.debug(f"PARSED (plain): raw_speed={speed:.2f} abs_speed={abs(speed):.2f} dir={direction.value}")

            return SpeedReading(
                speed=abs(speed),
                direction=direction,
                timestamp=time.time(),
                unit=self._unit
            )
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to parse reading: {line!r} - {e}")
            return None

    def start_streaming(self, callback: Callable[[SpeedReading], None]):
        """
        Start continuous speed streaming with callback.

        Args:
            callback: Function called with each SpeedReading
        """
        if self._streaming:
            return

        self._callback = callback
        self._streaming = True
        self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._stream_thread.start()

    def stop_streaming(self):
        """Stop continuous speed or I/Q streaming."""
        self._streaming = False
        if self._stream_thread:
            self._stream_thread.join(timeout=2.0)
            self._stream_thread = None
        self._callback = None

        # If we were doing I/Q streaming, tell radar to stop
        if self._iq_callback is not None:
            self.disable_raw_iq_output()

        self._iq_callback = None
        self._iq_error_callback = None

    def _stream_loop(self):
        """Internal streaming loop."""
        while self._streaming:
            try:
                reading = self.read_speed()
                if reading and self._callback:
                    self._callback(reading)
            except Exception:
                if self._streaming:
                    time.sleep(0.1)

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

    def enable_rolling_buffer(self):
        """
        Enable rolling buffer mode for raw I/Q capture.

        Rolling buffer mode (GC) captures 4096 raw I/Q samples instead of
        processing them internally. This allows post-capture FFT processing
        with overlapping windows for higher temporal resolution and spin detection.

        Commands:
        - GC: Enable rolling buffer (Continuous Sampling Mode)
        - PA: Activate sampling (required to start data capture loop)

        After enabling, use trigger_capture() or hardware trigger (HOST_INT) to dump the buffer.
        """
        logger.info("Enabling rolling buffer mode...")

        # Enable rolling buffer mode
        response = self._send_command("GC")
        time.sleep(0.1)
        logger.info("GC response: %s", response if response else '(none)')

        # Activate sampling - puts sensor into active data capture loop
        self._send_command("PA")
        time.sleep(0.1)
        logger.info("Rolling buffer mode enabled and sampling activated")

    def disable_rolling_buffer(self):
        """
        Disable rolling buffer mode and return to normal streaming.

        After disabling, call configure_for_golf() to restore streaming settings.
        """
        logger.info("Disabling rolling buffer mode...")
        self._send_command("GS")  # Return to standard CW mode
        time.sleep(0.1)
        logger.info("Rolling buffer mode disabled (returned to CW mode)")

    def set_trigger_split(self, segments: int = 8):
        """
        Set the pre/post trigger data split for rolling buffer.

        The S#n command controls how much historical data is included:
        - n=0: Only new samples (0% pre-trigger)
        - n=8: Default (25% pre-trigger = 1024 samples)
        - n=32: All current samples (100% pre-trigger)

        Each segment = 128 samples. At 30ksps:
        - 8 segments = 1024 samples = ~34ms pre-trigger

        Args:
            segments: Number of pre-trigger segments (0-32)
        """
        segments = max(0, min(32, segments))
        self._send_command(f"S#{segments}")
        logger.info("Trigger split set to %s segments", segments)

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
                response_lines.append(chunk.decode('ascii', errors='ignore'))
                bytes_received += len(chunk)
                last_data_time = time.time()

                # Check if we have complete data (Q array ends the response)
                full_response = ''.join(response_lines)
                if '"Q"' in full_response:
                    # Look for closing bracket of Q array followed by newline or EOF
                    q_idx = full_response.rfind('"Q"')
                    remaining = full_response[q_idx:]
                    if ']}' in remaining or (remaining.rstrip().endswith(']') and remaining.count('[') == remaining.count(']')):
                        break

                time.sleep(0.01)  # Short sleep to accumulate data
            else:
                # No data available
                # If we've received some data and haven't gotten more in 0.5s, consider done
                if bytes_received > 100 and (time.time() - last_data_time) > 0.5:
                    full_response = ''.join(response_lines)
                    if '"Q"' in full_response:
                        break
                time.sleep(0.02)

        full_response = ''.join(response_lines)

        # Only log issues, not normal operation
        if not full_response:
            logger.info("S! returned empty response")
        elif len(full_response) < 1000:
            # Short response usually means mode not configured correctly
            logger.info("S! response too short (%s bytes): %s", len(full_response), repr(full_response[:100]))

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

        while (time.time() - start_time) < timeout:
            if self.serial.in_waiting:
                chunk = self.serial.read(self.serial.in_waiting)
                response_lines.append(chunk.decode('ascii', errors='ignore'))
                bytes_received += len(chunk)
                last_data_time = time.time()

                # Check if we have complete I/Q data
                full_response = ''.join(response_lines)
                if '"Q"' in full_response:
                    q_idx = full_response.rfind('"Q"')
                    remaining = full_response[q_idx:]
                    if ']}' in remaining or (
                        remaining.rstrip().endswith(']')
                        and remaining.count('[') == remaining.count(']')
                    ):
                        break

                time.sleep(0.01)
            else:
                # If we've started receiving data, use shorter timeout
                if last_data_time and (time.time() - last_data_time) > 0.5:
                    full_response = ''.join(response_lines)
                    if '"Q"' in full_response:
                        break
                time.sleep(0.02)

        full_response = ''.join(response_lines) if response_lines else ""

        if not full_response:
            logger.info("Hardware trigger: no data received within %ss", timeout)
        else:
            logger.info("Hardware trigger: received %d bytes", len(full_response))

        return full_response

    def rearm_rolling_buffer(self):
        """
        Re-arm rolling buffer for next capture.

        After trigger_capture() outputs data, the sensor pauses in Idle mode.
        Send GC again to restart sampling for next capture.
        """
        self._send_command("GC")  # Re-enable rolling buffer mode
        time.sleep(0.05)
        self._send_command("PA")  # Activate sampling
        time.sleep(0.05)

    def configure_for_rolling_buffer(self):
        """
        Configure radar optimally for rolling buffer mode.

        Similar to configure_for_golf() but sets up for rolling buffer mode:
        - 30ksps sample rate (max ~208 mph, required for golf)
        - Rolling buffer enabled (GC command)
        - Trigger split for ~34ms pre-trigger data

        Note: Sample rate must be set AFTER enabling rolling buffer mode
        as the GC command may reset to default 10ksps.

        Based on OmniPreSense reference implementation:
        1. PI - deactivate to reset state
        2. GC - enable rolling buffer mode
        3. S=30 - set sample rate (30ksps for golf)
        """
        # Set units to MPH first
        self.set_units(SpeedUnit.MPH)
        logger.info("Units: MPH")

        # Reduced transmit power to avoid ADC clipping on close targets
        # Level 0=max, 7=min. Level 3 is a good balance.
        self.set_transmit_power(3)
        logger.info("Transmit power: level 3 (reduced to avoid clipping)")

        # Per OmniPreSense reference: deactivate first to reset state
        self._send_command("PI")
        time.sleep(0.1)
        logger.info("Deactivated (PI) to reset state")

        # Enable rolling buffer mode
        self.enable_rolling_buffer()

        # IMPORTANT: Set sample rate AFTER enabling rolling buffer
        # GC mode defaults to 10ksps, we need 30ksps for golf
        self.set_sample_rate(30000)
        time.sleep(0.1)
        logger.info("Sample rate set to 30ksps")

        # Verify sample rate was set correctly
        response = self._send_command("S?")
        logger.info("Sample rate check: %s", response)

        # Parse and warn if not 30ksps
        try:
            if response:
                data = json.loads(response)
                rate = data.get("SampleRate", data.get("Sampling Rate", 0))
                if rate and rate != 30000:
                    logger.warning("Sample rate is %s, expected 30000!", rate)
        except (json.JSONDecodeError, ValueError):
            pass

        # Set trigger split (8 segments = ~34ms pre-trigger)
        self.set_trigger_split(8)

        # CRITICAL: Re-activate sampling after changing settings
        # Per API doc: "Use GC or PA to start a new round of sampling"
        # Settings changes (S=30, S#n) may interrupt the sampling loop
        self._send_command("PA")
        time.sleep(0.1)
        logger.info("Re-activated sampling with PA")

        logger.info("Rolling buffer mode configured")

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
        logger.info("Configuring for fast speed trigger mode...")

        # Start from clean state
        self._send_command("GS")  # Ensure CW mode (not rolling buffer)
        time.sleep(0.1)

        self._send_command("PI")  # Idle mode
        time.sleep(0.1)

        # Set units to MPH
        self.set_units(SpeedUnit.MPH)
        logger.info("Units: MPH")

        # Max transmit power for best detection range
        self.set_transmit_power(0)
        logger.info("Transmit power: max (P0)")

        # 30ksps sample rate
        self.set_sample_rate(30000)
        time.sleep(0.1)
        logger.info("Sample rate: 30ksps")

        # 128 buffer size for fast report rate
        self.set_buffer_size(128)
        time.sleep(0.1)
        logger.info("Buffer size: 128")

        # 256 FFT size (X=2) for ~150-200Hz report rate
        # Report rate = 30000 / 128 / 2 ≈ 117 Hz per spec, but empirically faster
        self.set_fft_size(2)
        time.sleep(0.1)
        logger.info("FFT size: 256 (X=2) for fast reports")

        # Outbound only - ignore backswing (R-)
        self._send_command("R-")
        time.sleep(0.05)
        logger.info("Direction filter: outbound only (R-)")

        # Minimum speed 20mph - ignore leg movement and slow movements
        self._send_command("R>20")
        time.sleep(0.05)
        logger.info("Min speed filter: 20 mph (R>20)")

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
        logger.info("Speed trigger mode ready (PA)")

        # Verify settings
        response = self._send_command("S?")
        logger.info("Settings: %s", response)

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
            line = raw_bytes.decode('ascii', errors='ignore').strip()

            if not line:
                return None

            # May have multiple lines - take the last complete one
            lines = line.split('\n')
            for candidate in reversed(lines):
                candidate = candidate.strip()
                if candidate.startswith('{'):
                    reading = self._parse_reading(candidate)
                    if reading:
                        return reading

            return None
        except Exception:
            return None

    # =========================================================================
    # Continuous I/Q Streaming Mode (OR command)
    # =========================================================================

    def enable_raw_iq_output(self):
        """
        Enable raw I/Q ADC output for continuous streaming.

        Uses the OR command per API doc AN-010-AD:
        - I and Q output buffers from the ADC will be sent
        - Data output alternates between I and Q buffers
        - Not recommended for UART at low baud rates (USB is fine)

        The output format is JSON with alternating I and Q arrays:
        {"I": [sample0, sample1, ...]}
        {"Q": [sample0, sample1, ...]}

        Note: After OR command, radar immediately starts streaming.
        We don't wait for a response as the output buffer fills with I/Q data.
        """
        logger.info("Enabling raw I/Q output (OR command)...")
        if not self.serial or not self.serial.is_open:
            raise ConnectionError("Not connected to radar")

        # Clear buffer before sending
        self.serial.reset_input_buffer()

        # Send OR command - radar starts streaming immediately after this
        # Don't use _send_command() as it would try to read a response
        # but the radar is now outputting continuous I/Q data
        self.serial.write(b"OR")

        # Brief pause to let command process
        time.sleep(0.05)

    def disable_raw_iq_output(self):
        """
        Disable raw I/Q ADC output.

        Note: Must send command directly without waiting for response,
        as radar may be actively streaming I/Q data.
        """
        if not self.serial or not self.serial.is_open:
            return

        # Send Or command directly - don't use _send_command as radar may be streaming
        self.serial.write(b"Or")
        time.sleep(0.1)

        # Clear any buffered I/Q data
        self.serial.reset_input_buffer()

    def configure_for_iq_streaming(self):
        """
        Configure radar for continuous raw I/Q streaming mode.

        This mode outputs raw I/Q ADC samples continuously, which we
        process locally with FFT to extract speed.

        Settings optimized for raw I/Q capture:
        - Maximum baud rate (I5 command) for fastest data transfer
        - 30ksps sample rate (max ~208 mph)
        - 128 buffer size for minimum latency (~31ms between blocks)
        - FFT multiplier X=1 (minimizes internal processing delay)
        - W0 = no inter-report delay
        - Raw I/Q output enabled (OR command)

        Serial bandwidth limits total throughput to ~4000 samples/sec.
        128-sample blocks give best temporal resolution (~32 blocks/sec).
        We do our own 4096-point FFT in software with zero-padding.
        """
        logger.info("Configuring for continuous I/Q streaming...")

        # First, stop any existing I/Q streaming (from previous run or crash)
        # This ensures _send_command won't hang on buffered I/Q data
        self.disable_raw_iq_output()

        # Ensure we're in standard CW mode (not rolling buffer mode)
        # This is critical - GC mode has different output behavior
        self._send_command("GS")
        time.sleep(0.1)
        logger.info("CW mode enabled (GS)")

        # Put radar in idle mode first to ensure clean state for settings
        self._send_command("PI")
        time.sleep(0.1)
        logger.info("Idle mode (PI) - preparing for configuration")

        # Set maximum baud rate for fastest data transfer
        self._send_command("I5")
        logger.info("Baud rate: maximum (I5)")

        # Set units to MPH (for any fallback modes)
        self.set_units(SpeedUnit.MPH)
        logger.info("Units: MPH")

        # Reduced transmit power to avoid ADC clipping on close targets
        self.set_transmit_power(3)
        logger.info("Transmit power: level 3 (reduced to avoid clipping)")

        # 30ksps sample rate - critical for golf speeds
        self.set_sample_rate(30000)
        time.sleep(0.1)  # Allow setting to apply
        logger.info("Sample rate: 30ksps")

        # Verify sample rate was set correctly
        response = self._send_command("S?")
        logger.info("Sample rate check: %s", response)
        try:
            if response:
                data = json.loads(response)
                rate = data.get("SampleRate", data.get("Sampling Rate", 0))
                if rate and rate != 30000:
                    logger.warning("Sample rate is %s, expected 30000!", rate)
        except (json.JSONDecodeError, ValueError):
            pass

        # 128 buffer for minimum latency - serial bandwidth is the bottleneck
        # Smaller blocks transmit faster, giving ~31ms gaps vs ~225ms with 1024
        # Total data rate is similar, but 128 gives better temporal resolution
        self.set_buffer_size(128)
        time.sleep(0.1)

        # Verify buffer size was set
        response = self._send_command("S?")
        logger.info("Buffer size check: %s", response)

        # For raw I/Q mode (OR command), use X=1 to maximize output rate
        # We do our own 4096-point FFT with zero-padding in software
        # X=32 would slow OR output to 136ms per block (4096/30000)
        # X=1 with 128 buffer gives ~4.3ms per block
        self.set_fft_size(1)
        time.sleep(0.1)

        # Verify FFT size
        response = self._send_command("X?")
        logger.info("FFT size check: %s", response)

        # Disable inter-report delay (W0 = 0ms delay between reports)
        # This is critical for continuous I/Q streaming - default may have delay
        self._send_command("W0")
        time.sleep(0.05)
        logger.info("Report delay disabled (W0)")

        # Verify delay setting
        response = self._send_command("W?")
        logger.info("Delay setting check: %s", response)

        # Activate continuous sampling mode (PA = Power Active)
        # This puts the radar into active data capture loop AFTER all settings
        self._send_command("PA")
        time.sleep(0.1)
        logger.info("Power Active mode enabled (PA)")

        # Note: Don't enable I/Q output here - do it in start_iq_streaming()
        # This allows get_radar_info() to be called after connect() but before streaming
        logger.info("I/Q streaming mode configured (call start_iq_streaming to begin)")

    def start_iq_streaming(
        self,
        callback: Callable[['IQBlock'], None],
        error_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Start continuous I/Q streaming with callback for each block.

        The radar outputs alternating I and Q JSON arrays. We pair them
        and call the callback with each complete I/Q block.

        Args:
            callback: Function called with each IQBlock (1024 I + 1024 Q samples)
            error_callback: Optional function called on parse errors
        """
        if self._streaming:
            return

        # Enable raw I/Q output - this starts the radar streaming
        self.enable_raw_iq_output()

        self._iq_callback = callback
        self._iq_error_callback = error_callback
        self._streaming = True
        self._stream_thread = threading.Thread(target=self._iq_stream_loop, daemon=True)
        self._stream_thread.start()

    def _iq_stream_loop(self):
        """
        Internal I/Q streaming loop - parses alternating I/Q buffers.

        Optimized for low latency:
        - Uses bytearray for O(1) append instead of string concatenation
        - Processes data in chunks to minimize syscalls
        - No blocking operations in the critical path
        """
        pending_i = None
        buffer = bytearray()
        error_count = 0

        while self._streaming:
            try:
                if not self.serial or not self.serial.is_open:
                    time.sleep(0.01)
                    continue

                # Read all available data at once
                waiting = self.serial.in_waiting
                if waiting > 0:
                    # Read directly into bytearray (efficient)
                    chunk = self.serial.read(waiting)
                    buffer.extend(chunk)

                    # Process complete lines
                    while b'\n' in buffer:
                        newline_idx = buffer.index(b'\n')
                        line_bytes = buffer[:newline_idx]
                        # Efficiently remove processed data
                        del buffer[:newline_idx + 1]

                        # Strip trailing \r (radar outputs \r\n line endings)
                        if line_bytes and line_bytes[-1:] == b'\r':
                            line_bytes = line_bytes[:-1]

                        # Skip empty lines
                        if not line_bytes:
                            continue

                        # Fast check for JSON object
                        if line_bytes[0:1] != b'{' or line_bytes[-1:] != b'}':
                            continue

                        try:
                            # Decode and parse only valid JSON lines
                            data = json.loads(line_bytes)

                            if "I" in data:
                                pending_i = data["I"]
                            elif "Q" in data and pending_i is not None:
                                q_samples = data["Q"]
                                if len(pending_i) == len(q_samples):
                                    block = IQBlock(
                                        i_samples=pending_i,
                                        q_samples=q_samples,
                                        timestamp=time.time()
                                    )
                                    if self._iq_callback:
                                        self._iq_callback(block)
                                pending_i = None

                        except (json.JSONDecodeError, UnicodeDecodeError):
                            error_count += 1

                    # Prevent buffer overflow (sync lost)
                    if len(buffer) > 8192:
                        buffer.clear()
                        pending_i = None
                else:
                    # No data - very brief sleep to avoid busy-waiting
                    time.sleep(0.0001)

            except serial.SerialException:
                time.sleep(0.01)
            except Exception as e:
                error_count += 1
                logger.error("%s", e)

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
