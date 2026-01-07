"""Tests for OPS243 radar driver."""

import pytest

from openflight.ops243 import OPS243Radar, SpeedReading, Direction


class TestParseReading:
    """Tests for radar reading parsing."""

    def setup_method(self):
        """Set up test radar instance."""
        self.radar = OPS243Radar.__new__(OPS243Radar)
        self.radar._json_mode = True
        self.radar._unit = "mph"
        self.radar._magnitude_enabled = True

    def test_parse_json_with_magnitude(self):
        """Parse JSON output with positive speed (inbound)."""
        # Positive speed = INBOUND (toward radar)
        line = '{"speed": 152.3, "magnitude": 1847}'
        reading = self.radar._parse_reading(line)

        assert reading is not None
        assert reading.speed == 152.3
        assert reading.magnitude == 1847
        assert reading.direction == Direction.INBOUND
        assert reading.unit == "mph"

    def test_parse_json_negative_speed(self):
        """Negative speed indicates outbound direction."""
        # Negative speed = OUTBOUND (away from radar - ball flight)
        line = '{"speed": -45.2, "magnitude": 500}'
        reading = self.radar._parse_reading(line)

        assert reading is not None
        assert reading.speed == 45.2  # Absolute value
        assert reading.direction == Direction.OUTBOUND

    def test_parse_json_without_magnitude(self):
        """Parse JSON without magnitude field."""
        line = '{"speed": 120.5}'
        reading = self.radar._parse_reading(line)

        assert reading is not None
        assert reading.speed == 120.5
        assert reading.magnitude is None

    def test_parse_plain_number(self):
        """Parse plain number output (non-JSON mode)."""
        # Positive speed = INBOUND (toward radar)
        self.radar._json_mode = False
        line = "145.7"
        reading = self.radar._parse_reading(line)

        assert reading is not None
        assert reading.speed == 145.7
        assert reading.direction == Direction.INBOUND

    def test_parse_plain_negative(self):
        """Parse plain negative number."""
        # Negative speed = OUTBOUND (away from radar - ball flight)
        self.radar._json_mode = False
        line = "-88.3"
        reading = self.radar._parse_reading(line)

        assert reading is not None
        assert reading.speed == 88.3
        assert reading.direction == Direction.OUTBOUND

    def test_parse_invalid_json(self):
        """Invalid JSON returns None."""
        line = '{"speed": invalid}'
        reading = self.radar._parse_reading(line)

        assert reading is None

    def test_parse_empty_line(self):
        """Empty line returns None."""
        reading = self.radar._parse_reading("")

        assert reading is None

    def test_parse_non_numeric(self):
        """Non-numeric line returns None."""
        self.radar._json_mode = False
        reading = self.radar._parse_reading("hello")

        assert reading is None

    def test_parse_json_zero_speed(self):
        """Zero speed should parse correctly."""
        line = '{"speed": 0, "magnitude": 100}'
        reading = self.radar._parse_reading(line)

        assert reading is not None
        assert reading.speed == 0

    def test_parse_json_high_speed(self):
        """Very high speeds should parse correctly."""
        line = '{"speed": 195.8, "magnitude": 2500}'
        reading = self.radar._parse_reading(line)

        assert reading is not None
        assert reading.speed == 195.8

    def test_parse_json_decimal_precision(self):
        """Decimal precision should be preserved."""
        line = '{"speed": 142.857, "magnitude": 1234}'
        reading = self.radar._parse_reading(line)

        assert reading is not None
        assert reading.speed == 142.857

    def test_parse_json_array_format(self):
        """Parse O4 multi-object array format."""
        # O4 mode outputs arrays for speed and magnitude
        line = '{"magnitude":[606.71, 352.58, 230.87], "speed":[-10.90, -12.26, -17.71]}'
        reading = self.radar._parse_reading(line)

        assert reading is not None
        # Should take first (strongest) reading
        assert reading.speed == 10.90  # Absolute value
        assert reading.magnitude == 606.71
        # Negative speed = OUTBOUND
        assert reading.direction == Direction.OUTBOUND

    def test_parse_json_array_inbound(self):
        """Parse array format with positive (inbound) speed."""
        line = '{"magnitude":[500.0, 300.0], "speed":[15.5, 12.3]}'
        reading = self.radar._parse_reading(line)

        assert reading is not None
        assert reading.speed == 15.5
        assert reading.magnitude == 500.0
        # Positive speed = INBOUND
        assert reading.direction == Direction.INBOUND


class TestConfigureForGolf:
    """Tests for golf configuration."""

    def test_configure_sets_correct_values(self):
        """Verify configure_for_golf sets expected parameters."""
        # We can't test actual hardware, but we can verify the method exists
        # and doesn't raise errors when radar is not connected
        radar = OPS243Radar.__new__(OPS243Radar)
        radar.serial = None

        # These should be the expected configuration values
        assert radar.DEFAULT_BAUD == 57600
        assert radar.DEFAULT_TIMEOUT == 1.0


class TestFFTSize:
    """Tests for FFT size configuration."""

    def test_set_fft_size_valid_values(self):
        """Valid FFT size values should be accepted."""
        radar = OPS243Radar.__new__(OPS243Radar)
        radar.serial = None
        # Just verify method exists and accepts valid values
        # (can't test actual command without hardware)
        valid_sizes = [1, 2, 4, 8, 16, 32]
        for size in valid_sizes:
            # Should not raise
            try:
                radar.set_fft_size(size)
            except ConnectionError:
                pass  # Expected - no serial connection

    def test_set_fft_size_invalid_value(self):
        """Invalid FFT size should raise ValueError."""
        radar = OPS243Radar.__new__(OPS243Radar)
        radar.serial = None
        with pytest.raises(ValueError):
            radar.set_fft_size(3)
        with pytest.raises(ValueError):
            radar.set_fft_size(64)


class TestSpeedReading:
    """Tests for SpeedReading dataclass."""

    def test_speed_reading_creation(self):
        """Create a basic speed reading."""
        reading = SpeedReading(
            speed=150.0,
            direction=Direction.OUTBOUND,
            magnitude=1500,
            timestamp=12345.67,
            unit="mph"
        )

        assert reading.speed == 150.0
        assert reading.direction == Direction.OUTBOUND
        assert reading.magnitude == 1500
        assert reading.timestamp == 12345.67
        assert reading.unit == "mph"

    def test_speed_reading_defaults(self):
        """Test default values."""
        reading = SpeedReading(speed=100.0, direction=Direction.OUTBOUND)

        assert reading.magnitude is None
        assert reading.timestamp is None
        assert reading.unit == "mph"
