"""Tests for the Trackman ↔ OpenFlight comparison tool."""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "analysis"))

import compare_trackman as ct  # noqa: E402  pylint: disable=wrong-import-position

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_openflight_jsonl(path: Path, shots: list) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for shot in shots:
            fh.write(json.dumps({
                "type": "shot_detected",
                "timestamp": shot["timestamp"],
                "data": {k: v for k, v in shot.items() if k != "timestamp"},
            }) + "\n")


def _write_trackman_csv(path: Path, headers: list, rows: list) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


# ---------------------------------------------------------------------------
# Club name normalization
# ---------------------------------------------------------------------------

class TestNormalizeClub:
    @pytest.mark.parametrize("raw,expected", [
        ("7-iron", "7-iron"),
        ("7 iron", "7-iron"),
        ("7i",     "7-iron"),
        ("Iron 7", "7-iron"),
        ("Driver", "driver"),
        ("DRV",    "driver"),
        ("PW",     "pw"),
        ("Pitching Wedge", "pw"),
        ("3-wood", "3-wood"),
        ("3W",     "3-wood"),
    ])
    def test_aliases_normalize_to_canonical(self, raw, expected):
        assert ct.normalize_club(raw) == expected

    def test_empty_returns_empty(self):
        assert ct.normalize_club("") == ""
        assert ct.normalize_club(None) == ""


# ---------------------------------------------------------------------------
# Header alias map
# ---------------------------------------------------------------------------

class TestHeaderAliases:
    def test_standard_headers_resolve(self):
        headers = ["Shot Number", "Date/Time", "Club",
                   "Ball Speed (mph)", "Club Speed (mph)",
                   "Launch Angle", "Launch Direction",
                   "Spin Rate", "Carry Distance", "Smash Factor"]
        col_map = ct._build_column_map(headers)
        assert col_map["ball_speed_mph"] == "Ball Speed (mph)"
        assert col_map["club_speed_mph"] == "Club Speed (mph)"
        assert col_map["launch_angle_vertical"] == "Launch Angle"
        assert col_map["launch_angle_horizontal"] == "Launch Direction"
        assert col_map["spin_rpm"] == "Spin Rate"
        assert col_map["carry_yards"] == "Carry Distance"

    def test_alternate_headers_resolve(self):
        headers = ["Shot", "Time", "Club Type",
                   "BallSpeed", "ClubSpeed",
                   "Launch Angle V", "Side Angle",
                   "Total Spin", "Carry"]
        col_map = ct._build_column_map(headers)
        assert col_map["ball_speed_mph"] == "BallSpeed"
        assert col_map["launch_angle_vertical"] == "Launch Angle V"
        assert col_map["launch_angle_horizontal"] == "Side Angle"
        assert col_map["spin_rpm"] == "Total Spin"
        assert col_map["carry_yards"] == "Carry"

    def test_unit_detection_kph(self):
        headers = ["Ball Speed (kph)", "Club Speed (km/h)", "Carry (m)"]
        units = ct._detect_units(headers)
        assert units["speed"] == "kph"
        assert units["carry"] == "m"

    def test_date_header_beats_last_data_point_time(self):
        headers = ["Date", "Club", "Ball Speed", "Last data Point - Time"]
        col_map = ct._build_column_map(headers)
        assert col_map["timestamp"] == "Date"


# ---------------------------------------------------------------------------
# Trackman CSV loading + unit conversion
# ---------------------------------------------------------------------------

class TestLoadTrackman:
    def test_basic_load(self, tmp_path):
        path = tmp_path / "tm.csv"
        _write_trackman_csv(
            path,
            ["Shot Number", "Date/Time", "Club",
             "Ball Speed (mph)", "Club Speed (mph)",
             "Launch Angle", "Launch Direction", "Spin Rate", "Carry"],
            [{"Shot Number": "1", "Date/Time": "2026-05-06 10:00:00",
              "Club": "7-iron", "Ball Speed (mph)": "120.5",
              "Club Speed (mph)": "85.0", "Launch Angle": "17.5",
              "Launch Direction": "-1.2", "Spin Rate": "6800",
              "Carry": "165.3"}],
        )
        shots = ct.load_trackman(path)
        assert len(shots) == 1
        s = shots[0]
        assert s.club == "7-iron"
        assert s.ball_speed_mph == pytest.approx(120.5)
        assert s.launch_angle_horizontal == pytest.approx(-1.2)
        assert s.spin_rpm == pytest.approx(6800)
        assert s.timestamp == datetime(2026, 5, 6, 10, 0, 0)

    def test_kph_speeds_converted_to_mph(self, tmp_path):
        path = tmp_path / "tm.csv"
        _write_trackman_csv(
            path,
            ["Shot Number", "Date/Time", "Club", "Ball Speed (kph)"],
            [{"Shot Number": "1", "Date/Time": "2026-05-06 10:00:00",
              "Club": "driver", "Ball Speed (kph)": "240.0"}],
        )
        shots = ct.load_trackman(path)
        # 240 kph = 149.13 mph
        assert shots[0].ball_speed_mph == pytest.approx(149.13, abs=0.05)

    def test_handles_excel_sep_preamble_and_bom(self, tmp_path):
        """Trackman 'Normalized' exports start with ``sep=,`` and may
        have one or even two UTF-8 BOMs prefixed."""
        path = tmp_path / "tm_normalized.csv"
        # Two BOMs + sep= preamble + units row.
        content = (
            "\ufeff\ufeffsep=,\r\n"
            "Date,Club,Ball Speed,Launch Angle,Launch Direction\r\n"
            ",,[mph],[deg],[deg]\r\n"
            "5/6/2026 6:58:02 PM,7 Iron,118.5,17.2,-1.5\r\n"
            "5/6/2026 6:59:00 PM,Driver,165.0,11.0,0.5\r\n"
        )
        # newline="" keeps the CRLF content byte-exact; the default translates
        # "\n" to os.linesep, turning "\r\n" into "\r\r\n" on Windows.
        path.write_text(content, encoding="utf-8", newline="")
        shots = ct.load_trackman(path)
        assert len(shots) == 2
        assert shots[0].club == "7-iron"
        assert shots[0].ball_speed_mph == pytest.approx(118.5)
        assert shots[0].launch_angle_vertical == pytest.approx(17.2)
        # 12-hour timestamp parsed correctly.
        assert shots[0].timestamp == datetime(2026, 5, 6, 18, 58, 2)
        assert shots[1].club == "driver"

    def test_units_row_with_only_brackets_is_skipped(self, tmp_path):
        """The units row contains bracketed unit labels and no numeric
        values — must not appear as a shot."""
        path = tmp_path / "tm.csv"
        content = (
            "Club,Ball Speed\r\n"
            ",[mph]\r\n"
            "7 Iron,120.0\r\n"
        )
        path.write_text(content, encoding="utf-8", newline="")
        shots = ct.load_trackman(path)
        assert len(shots) == 1
        assert shots[0].ball_speed_mph == pytest.approx(120.0)

    def test_metres_carry_converted_to_yards(self, tmp_path):
        path = tmp_path / "tm.csv"
        _write_trackman_csv(
            path,
            ["Shot Number", "Date/Time", "Club", "Carry (m)"],
            [{"Shot Number": "1", "Date/Time": "2026-05-06 10:00:00",
              "Club": "7-iron", "Carry (m)": "150"}],
        )
        shots = ct.load_trackman(path)
        # 150 m = 164 yards
        assert shots[0].carry_yards == pytest.approx(164.04, abs=0.1)


# ---------------------------------------------------------------------------
# OpenFlight JSONL loading
# ---------------------------------------------------------------------------

class TestLoadOpenflight:
    def test_loads_only_shot_detected(self, tmp_path):
        path = tmp_path / "of.jsonl"
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "session_start"}) + "\n")
            fh.write(json.dumps({
                "type": "shot_detected",
                "timestamp": "2026-05-06T10:00:00",
                "data": {"shot_number": 1, "club": "7-iron",
                         "ball_speed_mph": 121.0,
                         "estimated_carry_yards": 160.0,
                         "launch_angle_vertical": 18.2,
                         "launch_angle_horizontal": 0.5},
            }) + "\n")
            fh.write(json.dumps({"type": "iq_reading"}) + "\n")
        shots = ct.load_openflight(path)
        assert len(shots) == 1
        assert shots[0].club == "7-iron"
        assert shots[0].ball_speed_mph == pytest.approx(121.0)
        assert shots[0].carry_yards == pytest.approx(160.0)


# ---------------------------------------------------------------------------
# Pairing
# ---------------------------------------------------------------------------

def _of(num, club, ball, ts, **kw):
    return ct.Shot(source="of", shot_number=num,
                   timestamp=datetime.fromisoformat(ts),
                   club=ct.normalize_club(club), ball_speed_mph=ball, **kw)


def _tm(num, club, ball, ts, **kw):
    return ct.Shot(source="tm", shot_number=num,
                   timestamp=datetime.fromisoformat(ts),
                   club=ct.normalize_club(club), ball_speed_mph=ball, **kw)


class TestPairShots:
    def test_one_to_one_chronological(self):
        of = [_of(1, "7-iron", 120, "2026-05-06T10:00:00"),
              _of(2, "7-iron", 122, "2026-05-06T10:01:00")]
        tm = [_tm(1, "7-iron", 121, "2026-05-06T10:00:01"),
              _tm(2, "7-iron", 123, "2026-05-06T10:01:01")]
        pairs = ct.pair_shots(of, tm)
        assert len(pairs) == 2
        assert all(p.match_quality == "good" for p in pairs)
        assert pairs[0].of.shot_number == 1
        assert pairs[0].tm.shot_number == 1

    def test_ball_speed_mismatch_flagged(self):
        of = [_of(1, "7-iron", 120, "2026-05-06T10:00:00")]
        tm = [_tm(1, "7-iron", 90, "2026-05-06T10:00:01")]
        pairs = ct.pair_shots(of, tm, ball_speed_tol_mph=5.0)
        assert len(pairs) == 1
        assert pairs[0].match_quality == "ball_speed_mismatch"
        assert "30" in pairs[0].notes  # reports the delta

    def test_unmatched_openflight_extra(self):
        of = [_of(1, "7-iron", 120, "2026-05-06T10:00:00"),
              _of(2, "7-iron", 122, "2026-05-06T10:01:00")]
        tm = [_tm(1, "7-iron", 121, "2026-05-06T10:00:01")]
        pairs = ct.pair_shots(of, tm)
        assert len(pairs) == 2
        assert pairs[0].match_quality == "good"
        assert pairs[1].match_quality == "unmatched_openflight"
        assert pairs[1].tm is None

    def test_unmatched_trackman_extra(self):
        of = [_of(1, "7-iron", 120, "2026-05-06T10:00:00")]
        tm = [_tm(1, "7-iron", 121, "2026-05-06T10:00:01"),
              _tm(2, "7-iron", 123, "2026-05-06T10:01:01")]
        pairs = ct.pair_shots(of, tm)
        assert len(pairs) == 2
        assert pairs[1].match_quality == "unmatched_trackman"
        assert pairs[1].of is None

    def test_grouping_by_club_independent(self):
        # 7i and driver are paired independently — interleaved input
        # order shouldn't matter as long as per-club order is correct.
        of = [_of(1, "driver", 165, "2026-05-06T10:00:00"),
              _of(2, "7-iron", 120, "2026-05-06T10:01:00"),
              _of(3, "driver", 167, "2026-05-06T10:02:00")]
        tm = [_tm(1, "7-iron", 121, "2026-05-06T10:01:01"),
              _tm(2, "driver", 166, "2026-05-06T10:00:01"),
              _tm(3, "driver", 168, "2026-05-06T10:02:01")]
        pairs = ct.pair_shots(of, tm)
        # All 3 should pair as "good" (ball-speed deltas all ≤ 1 mph)
        assert len([p for p in pairs if p.match_quality == "good"]) == 3
        # No unmatched
        assert all(p.match_quality == "good" for p in pairs)
        # Driver pairs are sorted within the driver group
        driver_pairs = [p for p in pairs if p.of and p.of.club == "driver"]
        assert [p.of.ball_speed_mph for p in driver_pairs] == [165, 167]

    def test_club_filter_excludes_unwanted_clubs(self):
        of = [_of(1, "driver", 165, "2026-05-06T10:00:00"),
              _of(2, "7-iron", 120, "2026-05-06T10:01:00")]
        tm = [_tm(1, "driver", 166, "2026-05-06T10:00:01"),
              _tm(2, "7-iron", 121, "2026-05-06T10:01:01")]
        pairs = ct.pair_shots(of, tm, club_filter=["7-iron"])
        assert len(pairs) == 1
        assert pairs[0].of.club == "7-iron"


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

class TestWriteCSV:
    def test_round_trip(self, tmp_path):
        of = [_of(1, "7-iron", 120, "2026-05-06T10:00:00",
                  launch_angle_vertical=18.0)]
        tm = [_tm(1, "7-iron", 121, "2026-05-06T10:00:01",
                  launch_angle_vertical=18.5)]
        pairs = ct.pair_shots(of, tm)
        out = tmp_path / "comparison.csv"
        ct.write_comparison_csv(pairs, out)

        with open(out, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 1
        assert rows[0]["match_quality"] == "good"
        assert float(rows[0]["ball_speed_of"]) == pytest.approx(120.0)
        assert float(rows[0]["ball_speed_tm"]) == pytest.approx(121.0)
        assert float(rows[0]["ball_speed_delta"]) == pytest.approx(-1.0)
        assert float(rows[0]["launch_v_delta"]) == pytest.approx(-0.5)


# ---------------------------------------------------------------------------
# End-to-end CLI
# ---------------------------------------------------------------------------

class TestBallSpeedCalibrationFit:
    """The calibration printout is purely for the human; the underlying
    fits need to be correct so the recommended constants are usable.
    """

    def test_linear_fit_recovers_known_slope_and_offset(self):
        # Synthetic: tm = 0.99 * of - 1.5 with no noise — the fit
        # should recover those constants exactly.
        of = [80.0, 100.0, 120.0, 140.0, 160.0]
        tm = [0.99 * v - 1.5 for v in of]
        slope, offset, sd = ct._fit_linear(of, tm)
        assert slope == pytest.approx(0.99, abs=1e-9)
        assert offset == pytest.approx(-1.5, abs=1e-9)
        assert sd == pytest.approx(0.0, abs=1e-9)

    def test_proportional_fit_recovers_known_slope(self):
        of = [80.0, 100.0, 120.0, 140.0, 160.0]
        tm = [0.985 * v for v in of]
        slope, sd = ct._fit_proportional(of, tm)
        assert slope == pytest.approx(0.985, abs=1e-9)
        assert sd == pytest.approx(0.0, abs=1e-9)

    def test_calibration_handles_too_few_pairs(self, capsys):
        # No pairs → should warn but not crash.
        ct.print_ball_speed_calibration([])
        out = capsys.readouterr().out
        assert "not enough good ball-speed pairs" in out

    def test_calibration_emits_both_models(self, capsys):
        of = [_of(i, "7-iron", 100 + 5 * i,
                  f"2026-05-06T10:0{i:01d}:00")
              for i in range(5)]
        tm = [_tm(i, "7-iron", (100 + 5 * i) * 1.02 + 1.0,
                  f"2026-05-06T10:0{i:01d}:01")
              for i in range(5)]
        pairs = ct.pair_shots(of, tm, ball_speed_tol_mph=20.0)
        ct.print_ball_speed_calibration(pairs)
        out = capsys.readouterr().out
        assert "BALL-SPEED CALIBRATION RECOMMENDATION" in out
        assert "Two-parameter model" in out
        assert "One-parameter model" in out


class TestLaunchAngleCalibration:
    def test_calibration_emits_vertical_and_horizontal_models(self, capsys):
        of = [
            _of(1, "7-iron", 120, "2026-05-06T10:00:00",
                launch_angle_vertical=10.0, launch_angle_horizontal=-2.0),
            _of(2, "7-iron", 121, "2026-05-06T10:01:00",
                launch_angle_vertical=12.0, launch_angle_horizontal=0.0),
            _of(3, "7-iron", 122, "2026-05-06T10:02:00",
                launch_angle_vertical=14.0, launch_angle_horizontal=2.0),
        ]
        tm = [
            _tm(1, "7-iron", 120, "2026-05-06T10:00:01",
                launch_angle_vertical=15.0, launch_angle_horizontal=-1.0),
            _tm(2, "7-iron", 121, "2026-05-06T10:01:01",
                launch_angle_vertical=17.0, launch_angle_horizontal=1.0),
            _tm(3, "7-iron", 122, "2026-05-06T10:02:01",
                launch_angle_vertical=19.0, launch_angle_horizontal=3.0),
        ]
        pairs = ct.pair_shots(of, tm)
        ct.print_launch_angle_calibration(pairs)
        out = capsys.readouterr().out
        assert "LAUNCH-ANGLE CALIBRATION DIAGNOSTICS" in out
        assert "Vertical launch" in out
        assert "Horizontal launch" in out
        assert "offset-only correction" in out

    def test_calibration_handles_too_few_pairs(self, capsys):
        pairs = ct.pair_shots(
            [_of(1, "driver", 150, "2026-05-06T10:00:00",
                 launch_angle_vertical=10.0)],
            [_tm(1, "driver", 150, "2026-05-06T10:00:01",
                 launch_angle_vertical=11.0)],
        )
        ct.print_launch_angle_calibration(pairs)
        out = capsys.readouterr().out
        assert "not enough good paired values" in out


class TestMainCLI:
    def test_full_pipeline(self, tmp_path, capsys):
        of_path = tmp_path / "session.jsonl"
        tm_path = tmp_path / "trackman.csv"
        out_path = tmp_path / "comparison.csv"

        _write_openflight_jsonl(of_path, [
            {"timestamp": "2026-05-06T10:00:00",
             "shot_number": 1, "club": "7-iron",
             "ball_speed_mph": 120.0, "club_speed_mph": 85.0,
             "launch_angle_vertical": 18.0,
             "launch_angle_horizontal": 0.5,
             "spin_rpm": 6500.0,
             "estimated_carry_yards": 160.0},
            {"timestamp": "2026-05-06T10:01:00",
             "shot_number": 2, "club": "driver",
             "ball_speed_mph": 165.0, "club_speed_mph": 110.0,
             "launch_angle_vertical": 12.0,
             "launch_angle_horizontal": -1.0,
             "spin_rpm": 2800.0,
             "estimated_carry_yards": 240.0},
        ])
        _write_trackman_csv(
            tm_path,
            ["Shot Number", "Date/Time", "Club",
             "Ball Speed (mph)", "Club Speed (mph)",
             "Launch Angle", "Launch Direction",
             "Spin Rate", "Carry"],
            [{"Shot Number": "1", "Date/Time": "2026-05-06 10:00:01",
              "Club": "7-iron", "Ball Speed (mph)": "121.0",
              "Club Speed (mph)": "85.5", "Launch Angle": "17.8",
              "Launch Direction": "0.7", "Spin Rate": "6600",
              "Carry": "163.0"},
             {"Shot Number": "2", "Date/Time": "2026-05-06 10:01:01",
              "Club": "Driver", "Ball Speed (mph)": "166.0",
              "Club Speed (mph)": "110.5", "Launch Angle": "11.5",
              "Launch Direction": "-0.8", "Spin Rate": "2750",
              "Carry": "242.0"}],
        )

        rc = ct.main([
            "--openflight", str(of_path),
            "--trackman", str(tm_path),
            "--output", str(out_path),
        ])
        assert rc == 0
        assert out_path.exists()

        with open(out_path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 2
        # Driver sorts before 7-iron in our friendly ordering
        assert rows[0]["club"] == "driver"
        assert rows[1]["club"] == "7-iron"
        assert rows[0]["match_quality"] == "good"
        assert rows[1]["match_quality"] == "good"

        # Summary printed
        out = capsys.readouterr().out
        assert "COMPARISON SUMMARY" in out
        assert "7-iron" in out
        assert "driver" in out
