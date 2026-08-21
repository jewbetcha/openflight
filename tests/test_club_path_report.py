"""Separation report: ordering plus a gap wider than the within-group spread."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "iwr6843"))

import club_path_report  # noqa: E402


def _session(tmp_path, name, paths):
    target = tmp_path / name
    with target.open("w", encoding="utf-8") as handle:
        for index, value in enumerate(paths, 1):
            handle.write(
                json.dumps(
                    {
                        "type": "iwr6843_capture",
                        "shot_number": index,
                        "club_path": {"status": "accepted", "path_deg": value},
                    }
                )
                + "\n"
            )
    return target


def test_load_group_reads_accepted_paths_only(tmp_path):
    path = _session(tmp_path, "a.jsonl", [1.0, 2.0])
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "type": "iwr6843_capture",
                    "club_path": {"status": "rejected_no_club_track", "path_deg": None},
                }
            )
            + "\n"
        )
    assert club_path_report.load_group(path) == [1.0, 2.0]


def test_load_group_counts_tdm_sign_fallback_as_accepted(tmp_path):
    """runtime.py rewrites "accepted" to "accepted_tdm_sign_fallback" whenever
    the ball's LCMF estimate had no measured TDM sign -- the common case, not
    an edge case. ClubPathResult.accepted (club.py) and server.py both treat
    it as accepted, so the report must too, or every real session reads as
    total failure.
    """
    target = tmp_path / "fallback.jsonl"
    with target.open("w", encoding="utf-8") as handle:
        for index in range(1, 11):
            handle.write(
                json.dumps(
                    {
                        "type": "iwr6843_capture",
                        "shot_number": index,
                        "club_path": {
                            "status": "accepted_tdm_sign_fallback",
                            "path_deg": float(index),
                        },
                    }
                )
                + "\n"
            )
    assert club_path_report.load_group(target) == [float(i) for i in range(1, 11)]
    coverage = club_path_report.group_coverage(target)
    assert coverage == {"total": 10, "accepted": 10, "rejected": 0, "skipped": 0}


def test_group_coverage_separates_skipped_from_rejected(tmp_path):
    """A null club_path means there was no OPS club speed to gate against
    (runtime.py), so the estimator never ran -- that must not read as an
    estimator failure alongside real rejections.
    """
    target = tmp_path / "mixed.jsonl"
    entries = [
        {"status": "accepted", "path_deg": 1.0},
        {"status": "rejected_no_club_track", "path_deg": None},
        None,
        None,
    ]
    with target.open("w", encoding="utf-8") as handle:
        for entry in entries:
            handle.write(json.dumps({"type": "iwr6843_capture", "club_path": entry}) + "\n")
    coverage = club_path_report.group_coverage(target)
    assert coverage == {"total": 4, "accepted": 1, "rejected": 1, "skipped": 2}


def test_separation_passes_when_groups_order_and_clear():
    report = club_path_report.separation(
        {
            "out-to-in": [-6.0, -5.0, -7.0, -6.5, -5.5],
            "square": [0.0, 1.0, -1.0, 0.5, -0.5],
            "in-to-out": [6.0, 5.0, 7.0, 6.5, 5.5],
        }
    )
    assert report["ordered"] is True
    assert report["separated"] is True
    assert report["reasons"] == []


def test_separation_fails_when_groups_overlap():
    """n=5 in every group (so the sample-size guard does not mask the
    result) but the spread of values overlaps heavily -- the within-group
    stdev guard must be the thing that catches this.
    """
    report = club_path_report.separation(
        {
            "out-to-in": [-1.0, 3.0, -4.0, 2.0, -2.0],
            "square": [0.0, 1.0, -1.0, 0.5, -0.5],
            "in-to-out": [1.0, -2.0, 4.0, -1.0, 3.0],
        }
    )
    assert report["ordered"] is True
    assert report["separated"] is False
    assert any("within-group spread" in reason for reason in report["reasons"])


def test_separation_fails_when_groups_have_too_few_shots():
    """A single shot per group has zero measured spread by definition, which
    would let a hairline gap look like clean separation. The minimum group
    size gate must catch that even though ordering and the naive gap check
    would otherwise both pass.
    """
    report = club_path_report.separation(
        {
            "out-to-in": [-6.0],
            "square": [0.0],
            "in-to-out": [6.0],
        }
    )
    assert report["ordered"] is True
    assert report["separated"] is False
    assert any("n=1" in reason for reason in report["reasons"])


def test_separation_reports_insufficient_n_per_group():
    report = club_path_report.separation(
        {
            "out-to-in": [-6.0, -5.0],
            "square": [0.0, 1.0, -1.0, 0.5, -0.5],
            "in-to-out": [6.0, 5.0, 7.0, 6.5, 5.5],
        }
    )
    assert report["groups"]["out-to-in"]["insufficient_n"] is True
    assert report["groups"]["square"]["insufficient_n"] is False


def test_separation_reports_both_reasons_when_a_gap_fails_both_guards():
    """A gap can be simultaneously below the fixed measurement floor and
    below the neighbouring stdev -- these are independent failure modes, so
    an ``elif`` between them would silently drop whichever reason lost the
    race, hiding real information from a failing report.
    """
    report = club_path_report.separation(
        {
            "out-to-in": [0.0, 1.0, -1.0, 0.5, -0.5],
            "square": [0.1, 1.1, -0.9, 0.6, -0.4],
        }
    )
    gap_reasons = [r for r in report["reasons"] if r.startswith("out-to-in->square")]
    assert any("measurement floor" in r for r in gap_reasons)
    assert any("within-group spread" in r for r in gap_reasons)


def test_separation_fails_when_gaps_are_below_measurement_precision():
    """Every group meets the minimum sample size and is tightly, consistently
    ordered -- the sample-size guard alone would pass this. But the gaps
    (0.15 deg) are below the estimator's own measured residual (0.3 deg), so
    they are not physically meaningful regardless of how many shots back
    them. This is the case a future refactor is most likely to break if the
    two guards get collapsed into one.
    """
    report = club_path_report.separation(
        {
            "out-to-in": [-0.10, -0.10, -0.10, -0.10, -0.10],
            "square": [0.05, 0.05, 0.05, 0.05, 0.05],
            "in-to-out": [0.20, 0.20, 0.20, 0.20, 0.20],
        }
    )
    assert report["groups"]["out-to-in"]["insufficient_n"] is False
    assert report["groups"]["square"]["insufficient_n"] is False
    assert report["groups"]["in-to-out"]["insufficient_n"] is False
    assert report["ordered"] is True
    assert report["separated"] is False
    assert any("measurement floor" in reason for reason in report["reasons"])
