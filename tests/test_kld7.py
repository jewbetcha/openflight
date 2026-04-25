"""Tests for K-LD7 angle radar integration."""

import pickle
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from openflight.kld7.tracker import KLD7Tracker
from openflight.kld7.types import KLD7Angle, KLD7Frame
from openflight.launch_monitor import Shot
from openflight.server import shot_to_dict

# Path to real captured K-LD7 data (golf swings + body movement)
CAPTURE_PATH = Path(__file__).parent.parent / "session_logs" / "kld7_capture_20260329_095614.pkl"


class TestKLD7Types:
    """Tests for K-LD7 data types."""

    def test_kld7_frame_defaults(self):
        frame = KLD7Frame(timestamp=1000.0)
        assert frame.timestamp == 1000.0
        assert frame.tdat is None
        assert frame.pdat == []

    def test_kld7_frame_radc_field(self):
        frame = KLD7Frame(timestamp=1000.0)
        assert frame.radc is None
        frame_with_radc = KLD7Frame(timestamp=1000.0, radc=b"\x00" * 3072)
        assert len(frame_with_radc.radc) == 3072

    def test_kld7_angle_vertical(self):
        angle = KLD7Angle(
            vertical_deg=12.5, distance_m=2.0, magnitude=5000, confidence=0.8, num_frames=3
        )
        assert angle.vertical_deg == 12.5
        assert angle.horizontal_deg is None

    def test_kld7_angle_horizontal(self):
        angle = KLD7Angle(
            horizontal_deg=-3.2, distance_m=1.5, magnitude=4000, confidence=0.7, num_frames=2
        )
        assert angle.horizontal_deg == -3.2
        assert angle.vertical_deg is None


class TestKLD7TrackerRingBuffer:
    """Tests for ring buffer and basic operations."""

    def _make_tracker(self, orientation="vertical"):
        tracker = KLD7Tracker.__new__(KLD7Tracker)
        tracker.orientation = orientation
        tracker.buffer_seconds = 2.0
        tracker.max_buffer_frames = 70
        tracker._init_ring_buffer()
        return tracker

    def test_ring_buffer_stores_frames(self):
        tracker = self._make_tracker()
        now = time.time()
        for i in range(5):
            tracker._add_frame(
                KLD7Frame(
                    timestamp=now + i * 0.03,
                    tdat=None,
                    pdat=[],
                )
            )
        assert len(tracker._ring_buffer) == 5

    def test_ring_buffer_max_size(self):
        tracker = self._make_tracker()
        tracker.max_buffer_frames = 10
        tracker._ring_buffer = __import__("collections").deque(maxlen=10)
        now = time.time()
        for i in range(20):
            tracker._add_frame(KLD7Frame(timestamp=now + i * 0.03, tdat=None, pdat=[]))
        assert len(tracker._ring_buffer) == 10

    def test_reset_clears_buffer(self):
        tracker = self._make_tracker()
        tracker._add_frame(KLD7Frame(timestamp=time.time(), tdat=None, pdat=[]))
        assert len(tracker._ring_buffer) == 1
        tracker.reset()
        assert len(tracker._ring_buffer) == 0

    def test_snapshot_buffer(self):
        tracker = self._make_tracker()
        now = time.time()
        tracker._add_frame(
            KLD7Frame(
                timestamp=now,
                tdat={"distance": 1.0, "speed": 5.0, "angle": 0.0, "magnitude": 3000},
                pdat=[],
            )
        )
        snap = tracker.snapshot_buffer()
        assert len(snap) == 1
        assert snap[0]["tdat"]["distance"] == 1.0

    def test_returns_none_when_no_detections(self):
        tracker = self._make_tracker()
        now = time.time()
        for i in range(5):
            tracker._add_frame(KLD7Frame(timestamp=now + i * 0.03, tdat=None, pdat=[]))
        assert tracker.get_angle_for_shot() is None


class TestKLD7RealData:
    """Tests against real captured K-LD7 data."""

    def _make_tracker(self, orientation="vertical"):
        tracker = KLD7Tracker.__new__(KLD7Tracker)
        tracker.orientation = orientation
        tracker.buffer_seconds = 2.0
        tracker.max_buffer_frames = 70
        tracker._init_ring_buffer()
        return tracker

    def _load_frames(self):
        if not CAPTURE_PATH.exists():
            pytest.skip(f"Capture file not found: {CAPTURE_PATH}")
        with open(CAPTURE_PATH, "rb") as f:
            data = pickle.load(f)
        return data["frames"]

    def test_rejects_body_movement_from_real_data(self):
        """Body movement window should produce no ball detection."""
        raw_frames = self._load_frames()
        tracker = self._make_tracker()
        t0 = raw_frames[0]["timestamp"]
        for f in raw_frames:
            t = f["timestamp"] - t0
            if 0.4 <= t <= 4.0:
                tracker._add_frame(
                    KLD7Frame(
                        timestamp=f["timestamp"],
                        tdat=f.get("tdat"),
                        pdat=f.get("pdat", []),
                    )
                )
        assert tracker.get_angle_for_shot() is None

    def test_quiet_period_produces_no_results(self):
        """A quiet period in real data should produce no results."""
        raw_frames = self._load_frames()
        tracker = self._make_tracker()
        t0 = raw_frames[0]["timestamp"]
        for f in raw_frames:
            t = f["timestamp"] - t0
            if 19.0 <= t <= 24.0:
                tracker._add_frame(
                    KLD7Frame(
                        timestamp=f["timestamp"],
                        tdat=f.get("tdat"),
                        pdat=f.get("pdat", []),
                    )
                )
        assert tracker.get_angle_for_shot() is None


class TestKLD7Integration:
    """Integration tests for K-LD7 angle data flowing through to Shot."""

    def test_angle_attaches_to_shot_vertical(self):
        shot = Shot(
            ball_speed_mph=150.0,
            timestamp=datetime.now(),
            launch_angle_vertical=12.5,
            launch_angle_confidence=0.8,
            angle_source="radar",
        )
        result = shot_to_dict(shot)
        assert result["launch_angle_vertical"] == 12.5
        assert result["angle_source"] == "radar"

    def test_angle_attaches_to_shot_horizontal(self):
        shot = Shot(
            ball_speed_mph=150.0,
            timestamp=datetime.now(),
            launch_angle_horizontal=-3.5,
            launch_angle_confidence=0.7,
            angle_source="radar",
        )
        result = shot_to_dict(shot)
        assert result["launch_angle_horizontal"] == -3.5

    def test_carry_adjusts_for_vertical_angle(self):
        shot_no_angle = Shot(ball_speed_mph=150.0, timestamp=datetime.now())
        shot_with_angle = Shot(
            ball_speed_mph=150.0,
            timestamp=datetime.now(),
            launch_angle_vertical=15.0,
            launch_angle_confidence=0.8,
            angle_source="radar",
        )
        assert shot_no_angle.estimated_carry_yards != shot_with_angle.estimated_carry_yards

    def test_club_angle_in_shot_dict(self):
        shot = Shot(
            ball_speed_mph=150.0,
            timestamp=datetime.now(),
            club_angle_deg=-5.5,
        )
        result = shot_to_dict(shot)
        assert result["club_angle_deg"] == -5.5

    def test_full_tracker_to_shot_flow(self):
        """Full flow: KLD7Angle manually attached to Shot appears in shot_to_dict."""
        angle = KLD7Angle(
            vertical_deg=18.0,
            horizontal_deg=None,
            confidence=0.85,
            num_frames=3,
            magnitude=5.2,
            detection_class="ball",
        )

        shot = Shot(ball_speed_mph=150.0, timestamp=datetime.now())
        shot.launch_angle_vertical = angle.vertical_deg
        shot.launch_angle_confidence = angle.confidence
        shot.angle_source = "radar"

        result = shot_to_dict(shot)
        assert result["launch_angle_vertical"] == 18.0
        assert result["angle_source"] == "radar"


class TestRADCAngleExtraction:
    """Tests for RADC-based phase-interferometry launch angle extraction."""

    def _make_tracker(self, orientation="vertical"):
        tracker = KLD7Tracker.__new__(KLD7Tracker)
        tracker.orientation = orientation
        tracker.buffer_seconds = 2.0
        tracker.max_buffer_frames = 70
        tracker.angle_offset_deg = 0.0
        tracker._init_ring_buffer()
        return tracker

    def _make_radc_payload_with_tone(self, velocity_kmh, angle_deg=10.0, amplitude=5000):
        """Create a synthetic RADC payload with a tone at the given velocity."""
        from openflight.kld7.radc import ANTENNA_SPACING_M, SAMPLES_PER_CHANNEL, WAVELENGTH_M

        n = SAMPLES_PER_CHANNEL  # 256
        max_speed_kmh = 100.0

        # Velocity to normalized frequency
        if velocity_kmh >= 0:
            norm_freq = velocity_kmh / (2 * max_speed_kmh)
        else:
            norm_freq = 1.0 + velocity_kmh / (2 * max_speed_kmh)

        t = np.arange(n)
        phase_per_sample = 2 * np.pi * norm_freq

        # F1A channel: reference (compute in float, then convert to uint16 with DC offset)
        f1a_i = (amplitude * np.cos(phase_per_sample * t) + 32768).astype(np.uint16)
        f1a_q = (amplitude * np.sin(phase_per_sample * t) + 32768).astype(np.uint16)

        # F2A channel: same tone shifted by angle-dependent phase
        angle_rad = np.radians(angle_deg)
        steering_phase = 2 * np.pi * ANTENNA_SPACING_M * np.sin(angle_rad) / WAVELENGTH_M
        f2a_i = (amplitude * np.cos(phase_per_sample * t + steering_phase) + 32768).astype(
            np.uint16
        )
        f2a_q = (amplitude * np.sin(phase_per_sample * t + steering_phase) + 32768).astype(
            np.uint16
        )

        # F1B channel: zeros (not used for angle)
        zeros = np.full(n, 32768, dtype=np.uint16)

        payload = b""
        for ch in [f1a_i, f1a_q, f2a_i, f2a_q, zeros, zeros]:
            payload += ch.astype(np.uint16).tobytes()
        return payload

    def _make_quiet_radc_payload(self, rng=None):
        """Create a quiet RADC payload (DC + small noise, no velocity tone)."""
        from openflight.kld7.radc import SAMPLES_PER_CHANNEL

        if rng is None:
            rng = np.random.default_rng(42)
        n = SAMPLES_PER_CHANNEL
        payload = b""
        for _ in range(6):
            noise = (32768 + rng.integers(-50, 50, size=n)).astype(np.uint16)
            payload += noise.tobytes()
        return payload

    def test_extracts_angle_from_radc_with_ball_speed(self):
        """RADC extraction should find the angle at the OPS-anchored velocity bin."""
        tracker = self._make_tracker()
        now = time.time()

        ball_speed_mph = 72.0
        ball_kmh = ball_speed_mph * 1.609
        aliased_kmh = ball_kmh % 200.0
        if aliased_kmh > 100.0:
            aliased_kmh -= 200.0
        target_angle = 12.0

        radc = self._make_radc_payload_with_tone(aliased_kmh, angle_deg=target_angle)
        quiet = self._make_quiet_radc_payload()

        for i in range(10):
            tracker._add_frame(KLD7Frame(timestamp=now + i * 0.056, radc=quiet))
        tracker._add_frame(KLD7Frame(timestamp=now + 0.56, radc=radc))
        for i in range(10):
            tracker._add_frame(KLD7Frame(timestamp=now + 0.62 + i * 0.056, radc=quiet))

        result = tracker.get_angle_for_shot(ball_speed_mph=ball_speed_mph)
        assert result is not None
        assert result.detection_class == "ball"
        assert result.vertical_deg == pytest.approx(target_angle, abs=3.0)
        assert result.confidence > 0.0

    def test_returns_none_without_ball_speed(self):
        """When ball_speed_mph is None, should return None (RADC requires speed anchor)."""
        tracker = self._make_tracker()
        now = time.time()

        for i in range(3):
            tracker._add_frame(
                KLD7Frame(
                    timestamp=now + i * 0.033,
                    pdat=[{"distance": 4.2, "speed": 25.0, "angle": 15.0, "magnitude": 2500}],
                )
            )

        result = tracker.get_angle_for_shot(ball_speed_mph=None)
        assert result is None

    def test_angle_offset_applied_to_radc(self):
        """Angle offset should be applied to RADC-extracted angle."""
        tracker = self._make_tracker()
        tracker.angle_offset_deg = 5.0
        now = time.time()

        ball_speed_mph = 72.0
        ball_kmh = ball_speed_mph * 1.609
        aliased_kmh = ball_kmh % 200.0
        if aliased_kmh > 100.0:
            aliased_kmh -= 200.0

        radc = self._make_radc_payload_with_tone(aliased_kmh, angle_deg=10.0)
        quiet = self._make_quiet_radc_payload()

        for i in range(10):
            tracker._add_frame(KLD7Frame(timestamp=now + i * 0.056, radc=quiet))
        tracker._add_frame(KLD7Frame(timestamp=now + 0.56, radc=radc))
        for i in range(10):
            tracker._add_frame(KLD7Frame(timestamp=now + 0.62 + i * 0.056, radc=quiet))

        result = tracker.get_angle_for_shot(ball_speed_mph=ball_speed_mph)
        assert result is not None
        assert result.vertical_deg == pytest.approx(15.0, abs=3.0)

    def test_shot_timestamp_filters_to_nearby_frames(self, monkeypatch):
        """A provided shot timestamp should narrow RADC extraction to the nearby burst."""
        tracker = self._make_tracker()
        tracker._add_frame(KLD7Frame(timestamp=100.00, radc=b"early-1"))
        tracker._add_frame(KLD7Frame(timestamp=100.03, radc=b"early-2"))
        tracker._add_frame(KLD7Frame(timestamp=100.80, radc=b"late-1"))
        tracker._add_frame(KLD7Frame(timestamp=100.83, radc=b"late-2"))

        captured_frames = []

        def fake_extract_launch_angle(frames, **kwargs):
            captured_frames.append(frames)
            return [
                {
                    "launch_angle_deg": 12.0,
                    "ball_speed_mph": kwargs["ops243_ball_speed_mph"],
                    "avg_snr_db": 8.0,
                    "confidence": 0.8,
                    "frame_count": len(frames),
                }
            ]

        monkeypatch.setattr(
            "openflight.kld7.radc.extract_launch_angle",
            fake_extract_launch_angle,
        )

        result = tracker.get_angle_for_shot(shot_timestamp=100.82, ball_speed_mph=72.0)

        assert result is not None
        assert len(captured_frames) == 1
        assert captured_frames[0] == [
            {"timestamp": 100.80, "radc": b"late-1"},
            {"timestamp": 100.83, "radc": b"late-2"},
        ]
