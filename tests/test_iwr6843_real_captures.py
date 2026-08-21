"""Frozen regression baselines against real captures, when present locally.

session_logs/ is gitignored, so this skips on CI and runs on the machine that
recorded the 2026-07-25 sessions. It is the only test that exercises the
channel selection on live data rather than synthetic data.

**These baselines are the estimator's own output, not independent
measurements.** No independent reference -- no TrackMan pairing, no optical
capture -- exists in this repo for session 20260725_140533; the numbers below
were produced by running this estimator on these captures and rounding. For
one shot the figure is the mean of that shot's own two channels.

So this file detects CHANGE, not ERROR. It will catch a regression that
reintroduces the collapsed-channel behavior, a coverage drop, or an
unintended shift in the estimator's output. It cannot tell you the estimator
is accurate, and passing it is not evidence that it is: if the estimator is
systematically wrong today, these baselines are wrong by exactly the same
amount and the test still passes. Validating accuracy needs a paired session
against a reference instrument, which is separate outstanding work.
"""

import json
from pathlib import Path

import pytest

SESSION = Path("session_logs/session_20260725_140533_range.jsonl")
DUMPS = Path("session_logs/iwr")

pytestmark = pytest.mark.skipif(
    not SESSION.is_file() or not DUMPS.is_dir(),
    reason="local 2026-07-25 captures not present (session_logs is gitignored)",
)


def _captures():
    rows = [json.loads(line) for line in SESSION.read_text().splitlines() if line.strip()]
    return sorted(
        [r for r in rows if r.get("type") == "iwr6843_capture" and r.get("capture_path")],
        key=lambda r: r["shot_number"],
    )


def _estimate(capture):
    from openflight.iwr6843.lcmf import estimate_lcmf_v1
    from openflight.iwr6843.replay import build_replay_calibration

    raw = (DUMPS / Path(capture["capture_path"]).name).read_bytes()
    cal = build_replay_calibration(
        "config/iwr6843_calibration_reference.json",
        tee_range_m=1.372,
        tilt_deg=5.5,
        radar_height_m=0.229,
        ball_height_m=0.040,
    )
    return estimate_lcmf_v1(
        raw,
        cal,
        ball_speed_mph=capture["ball_speed_mph"],
        club="7i",
        net_range_m=4.064,
        tx_order="normal",
    )


def test_all_seven_captures_accepted():
    """15 ms span floor takes this session to 7/7.

    Before the span-floor fix, shot 1 (17.3 ms span) was rejected outright by
    the old 18 ms gate, leaving 6/7. Coverage is a regression target in its
    own right: a future tightening of the span floor would silently drop
    shot 1 again without ever touching the angle assertions below.
    """
    results = [_estimate(capture) for capture in _captures()]
    accepted = [r for r in results if r.accepted]
    assert len(accepted) == 7, [r.status for r in results]


def test_collapsed_channel_no_longer_drags_the_answer():
    """Seven 7-irons stay near the frozen 18 deg baseline, not the old 10.9 deg.

    The baseline for this session is this estimator's own output, not a
    measurement of the real launch angles (see the module docstring):
    per-shot 19.25, 17.71, 24.32, 19.23, 16.02, 15.28, 16.48 deg, mean
    18.3 deg -- and the 24.32 figure is itself the mean of that shot's two
    channels. What IS independent is the operator's report that the balls
    flew like normal 7-irons, which is why the pre-fix output is known to be
    wrong: one channel collapsed to ~0 deg and the plain mean dragged the
    session average to 10.9 deg (and shot 1 was rejected outright, see the
    coverage test above). That gives the bounds a direction to defend, but
    not a number to check against.

    Bounds sit clearly between the two known outcomes rather than tight
    around the current output, so the test tracks stability without pinning
    the estimator in place:
    - Mean [14.0, 22.0]: the midpoint between 10.9 and 18.3 is ~14.6, so the
      floor at 14.0 is just below that midpoint -- a regression to the old
      collapsed-channel behavior (mean ~10.9) fails by a wide margin, while
      the ceiling at 22.0 gives ~3.7 deg of headroom above the current 18.3
      for legitimate estimator refinement without becoming a no-op gate.
    - Per-shot [12.0, 26.0]: wide enough to allow shot-to-shot variance (the
      current range is 15.28-24.32 deg) and future estimator tweaks, but
      still well above the ~0 deg a collapsed channel produces on any single
      shot, so a single reintroduced bad channel is still caught.
    """
    angles = [r.angle_deg for r in (_estimate(c) for c in _captures()) if r.accepted]
    mean_angle = sum(angles) / len(angles)
    assert 14.0 <= mean_angle <= 22.0, f"7-iron mean {mean_angle:.1f} deg is implausible"
    assert all(12.0 <= angle <= 26.0 for angle in angles), angles
