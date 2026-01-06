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
            self._send_command(f"S={ksps}\r")

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

        # Send command and log
        print(f"[RADAR CONFIG] Setting direction filter: {cmd}")
        response = self._send_command(cmd)
        if response:
            print(f"[RADAR CONFIG] Direction filter response: {response}")

        # Also try with explicit newline in case that's needed
        if self.serial and self.serial.is_open:
            self.serial.write(b'\r\n')
            time.sleep(0.05)

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

    def clear_direction_filter(self):
        """
        Clear direction filter to allow both directions.

        When the filter is cleared (R|), the sign of the speed value indicates direction.

        Per API documentation AN-010-AD (cosine error correction naming convention):
        - Positive speed = INBOUND (toward radar)
        - Negative speed = OUTBOUND (away from radar)

        This is required to determine direction in software.
        """
        cmd = "R|"
        print(f"[RADAR CONFIG] Clearing direction filter: {cmd} (both directions)")
        response = self._send_command(cmd)
        if response:
            print(f"[RADAR CONFIG] Direction filter response: {response}")

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
        print("[RADAR CONFIG] Sample rate: 30ksps")

        # 128 buffer per OmniPreSense recommendation
        # Combined with 30ksps gives good base for FFT
        self.set_buffer_size(128)
        print("[RADAR CONFIG] Buffer size: 128")

        # FFT size 4096 (X=32 multiplier with 128 buffer)
        # This gives: ~56 Hz report rate, ±0.1 mph resolution
        self.set_fft_size(32)
        print("[RADAR CONFIG] FFT size: 4096 (X=32) - ±0.1 mph resolution @ ~56 Hz")

        # Enable magnitude to help filter weak signals
        # Magnitude helps distinguish club (larger RCS, higher mag) from ball
        self.enable_magnitude_report(True)

        # Clear direction filter to get BOTH directions
        # Direction is determined by the SIGN of the speed value.
        # Per API docs: positive = inbound, negative = outbound
        # This allows us to filter inbound readings (backswing) in software
        self.clear_direction_filter()

        # Minimum speed 10 mph to filter very slow movements
        # We filter higher speeds (backswing) in software based on direction
        self.set_min_speed_filter(10)

        # Max transmit power for best range
        self.set_transmit_power(0)

        # Enable JSON for easier parsing
        self.enable_json_output(True)

        # Enable multi-object reporting to detect both club head AND ball
        # O4 reports up to 4 objects per sample cycle, ordered by magnitude
        self.set_num_reports(4)
        print("[RADAR CONFIG] Multi-object reporting enabled (O4)")

        # Re-enable JSON output after O4 (in case it was reset)
        self.enable_json_output(True)

        # Enable peak speed averaging per OmniPreSense recommendation
        # Helps provide cleaner speed readings
        self.enable_peak_averaging(True)
        print("[RADAR CONFIG] Peak averaging enabled (K+)")

        # Verify settings were applied
        print("[RADAR CONFIG] Verifying configuration...")
        filter_settings = self.get_speed_filter()
        print(f"[RADAR CONFIG] Current filter settings: {filter_settings}")

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

        print(f"[RADAR] Sending num_reports command: {cmd}")
        response = self._send_command(cmd)
        if response:
            print(f"[RADAR] Response: {response}")

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
        """Stop continuous speed streaming."""
        self._streaming = False
        if self._stream_thread:
            self._stream_thread.join(timeout=2.0)
            self._stream_thread = None

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

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
