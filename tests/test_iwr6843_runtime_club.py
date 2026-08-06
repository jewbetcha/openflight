"""Runtime forwards per-shot geometry and club-path inputs."""

import math
from unittest.mock import patch

import pytest

from openflight.iwr6843.calibration import Calibration
from openflight.iwr6843.club import ClubPathResult
from openflight.iwr6843.runtime import IWR6843Runtime


class FakeCapture:
    valid = True
    raw = b"x" * 32
    path = None
    error = None
    trigger_timestamp = 1.0
    dump_duration_s = 5.3
    sequence = 1


class FakeMonitor:
    def capture_for_shot(self, _ts, timeout_s):
        return FakeCapture()

    def stop(self):
        pass


def _runtime(**kwargs):
    return IWR6843Runtime(
        capture_monitor=FakeMonitor(),
        calibration=object(),
        net_range_m=4.064,
        **kwargs,
    )


def test_club_path_receives_ball_tdm_sign():
    seen = {}

    def fake_club(raw, cal, **kw):
        seen.update(kw)
        return ClubPathResult(status="accepted", path_deg=2.0, confidence=0.8)

    class Measurement:
        tdm_sign_used = -1

    with (
        patch("openflight.iwr6843.runtime.estimate_lcmf_v1", return_value=Measurement()),
        patch("openflight.iwr6843.runtime.estimate_club_path", side_effect=fake_club),
    ):
        result = _runtime().process_shot(
            impact_timestamp=1.0, ball_speed_mph=100.0, club="7i", club_speed_mph=74.0
        )

    assert result.club_path.path_deg == 2.0
    assert seen["tdm_sign"] == -1
    assert seen["ops_club_speed_mph"] == 74.0


def test_club_path_receives_the_configured_azimuth_offset():
    """The aim offset must cross the runtime -> estimator boundary.

    Club path is an absolute angle and the offset enters additively, so a
    boresight that is not the target line shifts every reported path by that
    amount. Coverage stopped one step short on each side: test_server.py
    checks the CLI value reaches ``IWR6843Runtime.azimuth_offset_deg``, and the
    tests around this one check that ``tdm_sign`` and ``ops_club_speed_mph``
    reach ``estimate_club_path`` -- but nothing checked that *this* value
    crosses *that* boundary. Replacing ``aim_offset_deg=self.azimuth_offset_deg``
    with a literal ``0.0`` therefore left the entire suite green while silently
    reporting club path relative to boresight instead of the target line, which
    is precisely the error the flag exists to correct.

    A non-zero offset is required here: with 0.0 the assertion would pass
    against the hardcoded literal too.
    """
    seen = {}

    def fake_club(raw, cal, **kw):
        seen.update(kw)
        return ClubPathResult(status="accepted", path_deg=2.0, confidence=0.8)

    class Measurement:
        tdm_sign_used = 1

    with (
        patch("openflight.iwr6843.runtime.estimate_lcmf_v1", return_value=Measurement()),
        patch("openflight.iwr6843.runtime.estimate_club_path", side_effect=fake_club),
    ):
        _runtime(azimuth_offset_deg=1.5).process_shot(
            impact_timestamp=1.0, ball_speed_mph=100.0, club="7i", club_speed_mph=74.0
        )

    assert seen["aim_offset_deg"] == 1.5


def test_falls_back_to_policy_sign_when_ball_has_none():
    seen = {}

    def fake_club(raw, cal, **kw):
        seen.update(kw)
        return ClubPathResult(status="accepted", path_deg=1.0)

    class Measurement:
        tdm_sign_used = None

    with (
        patch("openflight.iwr6843.runtime.estimate_lcmf_v1", return_value=Measurement()),
        patch("openflight.iwr6843.runtime.estimate_club_path", side_effect=fake_club),
    ):
        result = _runtime().process_shot(
            impact_timestamp=1.0, ball_speed_mph=100.0, club="7i", club_speed_mph=74.0
        )

    assert seen["tdm_sign"] == 1, "policy default is positive"
    assert result.club_path.status.endswith("tdm_sign_fallback")


def test_no_club_speed_skips_the_estimate():
    """Without OPS club speed there is no identity gate, so do not guess."""
    with patch("openflight.iwr6843.runtime.estimate_lcmf_v1", return_value=None):
        result = _runtime().process_shot(
            impact_timestamp=1.0, ball_speed_mph=100.0, club="7i", club_speed_mph=None
        )
    assert result.club_path is None


def test_per_shot_tilt_uses_a_calibration_copy_without_mutating_runtime():
    calibration = Calibration.identity()
    runtime = IWR6843Runtime(
        capture_monitor=FakeMonitor(),
        calibration=calibration,
        net_range_m=4.064,
    )
    seen = {}

    def fake_lcmf(_raw, shot_calibration, **_kwargs):
        seen["calibration"] = shot_calibration
        return None

    with patch("openflight.iwr6843.runtime.estimate_lcmf_v1", side_effect=fake_lcmf):
        runtime.process_shot(
            impact_timestamp=1.0,
            ball_speed_mph=100.0,
            club="7i",
            tilt_deg=13.5,
        )

    assert seen["calibration"] is not calibration
    assert math.degrees(seen["calibration"].tilt_rad) == pytest.approx(13.5)
    assert calibration.tilt_rad == 0.0


def test_ball_estimate_receives_the_configured_tdm_sign_policy():
    """``tdm_sign_policy`` must cross the runtime -> LCMF boundary.

    Same trap as the azimuth-offset test above: the dataclass exposes a
    configurable ``tdm_sign_policy``, and the club-path fallback honors it,
    but the ball-estimate call passed a hardcoded ``"positive"`` literal.
    ``replay.replay_capture`` plumbs a caller-supplied policy end to end, so
    any non-default setting silently produced different live-vs-replay
    answers for the same capture. A non-default value is required here: with
    ``"positive"`` the assertion would pass against the literal too.
    """
    seen = {}

    def fake_lcmf(raw, cal, **kw):
        seen.update(kw)

        class Measurement:
            tdm_sign_used = 1

        return Measurement()

    with patch("openflight.iwr6843.runtime.estimate_lcmf_v1", side_effect=fake_lcmf):
        _runtime(tdm_sign_policy="auto").process_shot(
            impact_timestamp=1.0, ball_speed_mph=100.0, club="7i", club_speed_mph=None
        )

    assert seen["tdm_sign_policy"] == "auto"
