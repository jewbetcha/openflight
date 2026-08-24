"""Unit tests for MLM2 Pro CSV to TrackMan CSV adapter script."""

import csv
import importlib.util
import tempfile
from pathlib import Path

import pytest

_script_path = Path(__file__).resolve().parents[1] / "scripts" / "adapters" / "mlm2pro_adapter.py"
_spec = importlib.util.spec_from_file_location("mlm2pro_adapter", _script_path)
mlm2pro_adapter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mlm2pro_adapter)

METRES_TO_YARDS = mlm2pro_adapter.METRES_TO_YARDS
TRACKMAN_OUTPUT_HEADERS = mlm2pro_adapter.TRACKMAN_OUTPUT_HEADERS
adapt_mlm2pro_csv = mlm2pro_adapter.adapt_mlm2pro_csv
adapt_mlm2pro_row = mlm2pro_adapter.adapt_mlm2pro_row
convert_distance_to_yards = mlm2pro_adapter.convert_distance_to_yards
convert_speed_to_mph = mlm2pro_adapter.convert_speed_to_mph
detect_header_units = mlm2pro_adapter.detect_header_units
detect_mlm2pro_column_map = mlm2pro_adapter.detect_mlm2pro_column_map


class TestMlm2ProHeaderDetection:
    """Test header alias resolution and unit detection."""

    def test_detect_standard_mlm2pro_headers(self):
        headers = [
            "Date",
            "Shot Number",
            "Club",
            "Ball Speed (mph)",
            "Club Speed (mph)",
            "Smash Factor",
            "Launch Angle (deg)",
            "Launch Direction (deg)",
            "Spin Rate (rpm)",
            "Spin Axis (deg)",
            "Carry Distance (yds)",
            "Total Distance (yds)",
            "Apex (ft)",
            "Side Carry (yds)",
        ]
        col_map = detect_mlm2pro_column_map(headers)
        assert col_map["ball_speed"] == "Ball Speed (mph)"
        assert col_map["club_speed"] == "Club Speed (mph)"
        assert col_map["launch_angle"] == "Launch Angle (deg)"
        assert col_map["launch_direction"] == "Launch Direction (deg)"
        assert col_map["spin_rate"] == "Spin Rate (rpm)"
        assert col_map["spin_axis"] == "Spin Axis (deg)"
        assert col_map["carry_distance"] == "Carry Distance (yds)"
        assert col_map["club"] == "Club"

    def test_detect_alternate_aliases(self):
        headers = [
            "Timestamp",
            "Shot #",
            "Club Type",
            "Ball Velocity",
            "Club Head Speed",
            "Smash",
            "Vertical Launch",
            "Side Angle",
            "Total Spin",
            "Spin Tilt",
            "Carry",
            "Total",
            "Max Height",
            "Offline",
        ]
        col_map = detect_mlm2pro_column_map(headers)
        assert col_map["timestamp"] == "Timestamp"
        assert col_map["shot_number"] == "Shot #"
        assert col_map["club"] == "Club Type"
        assert col_map["ball_speed"] == "Ball Velocity"
        assert col_map["club_speed"] == "Club Head Speed"
        assert col_map["smash_factor"] == "Smash"
        assert col_map["launch_angle"] == "Vertical Launch"
        assert col_map["launch_direction"] == "Side Angle"
        assert col_map["spin_rate"] == "Total Spin"
        assert col_map["spin_axis"] == "Spin Tilt"
        assert col_map["carry_distance"] == "Carry"
        assert col_map["total_distance"] == "Total"
        assert col_map["apex"] == "Max Height"
        assert col_map["offline"] == "Offline"

    def test_detect_header_units_metric_kph_meters(self):
        headers = [
            "Date",
            "Ball Speed (km/h)",
            "Club Speed (km/h)",
            "Carry Distance (m)",
        ]
        units = detect_header_units(headers)
        assert units["speed"] == "kph"
        assert units["distance"] == "meters"

    def test_detect_header_units_metric_mps(self):
        headers = [
            "Date",
            "Ball Speed (m/s)",
            "Carry Distance (meters)",
        ]
        units = detect_header_units(headers)
        assert units["speed"] == "mps"
        assert units["distance"] == "meters"


class TestUnitConversions:
    """Test metric and imperial unit conversion routines."""

    def test_convert_speed_to_mph(self):
        assert convert_speed_to_mph(100.0, "mph") == 100.0
        assert convert_speed_to_mph(160.9344, "kph") == pytest.approx(100.0)
        assert convert_speed_to_mph(44.704, "mps") == pytest.approx(100.0)
        assert convert_speed_to_mph(None, "mph") is None

    def test_convert_distance_to_yards(self):
        assert convert_distance_to_yards(150.0, "yards") == 150.0
        assert convert_distance_to_yards(100.0, "meters") == pytest.approx(100.0 * METRES_TO_YARDS)
        assert convert_distance_to_yards(None, "yards") is None


class TestAdaptMlm2ProRow:
    """Test transforming individual dictionary rows."""

    def test_adapt_complete_row(self):
        row = {
            "Date": "5/6/2026 7:00:00 PM",
            "Shot Number": "5",
            "Club": "7-Iron",
            "Ball Speed (mph)": "120.5",
            "Club Speed (mph)": "85.2",
            "Smash Factor": "1.41",
            "Launch Angle (deg)": "16.5",
            "Launch Direction (deg)": "-1.2",
            "Spin Rate (rpm)": "5500",
            "Spin Axis (deg)": "4.5",
            "Carry Distance (yds)": "165.2",
            "Total Distance (yds)": "175.0",
            "Apex (ft)": "85.0",
            "Side Carry (yds)": "-3.5",
        }
        col_map = detect_mlm2pro_column_map(row.keys())
        adapted = adapt_mlm2pro_row(row, col_map, row_idx=1)

        assert adapted["Date"] == "5/6/2026 7:00:00 PM"
        assert adapted["Shot Number"] == "5"
        assert adapted["Club"] == "7-Iron"
        assert adapted["Ball Speed"] == "120.5"
        assert adapted["Club Speed"] == "85.2"
        assert adapted["Smash Factor"] == "1.41"
        assert adapted["Launch Angle"] == "16.5"
        assert adapted["Launch Direction"] == "-1.2"
        assert adapted["Spin Rate"] == "5500"
        assert adapted["Spin Axis"] == "4.5"
        assert adapted["Carry Distance"] == "165.2"
        assert adapted["Total Distance"] == "175.0"
        assert adapted["Max Height - Height"] == "85.0"
        assert adapted["Carry Flat - Side"] == "-3.5"

    def test_adapt_row_calculates_missing_smash_factor(self):
        row = {
            "Ball Speed": "150.0",
            "Club Speed": "100.0",
            "Club": "Driver",
        }
        col_map = detect_mlm2pro_column_map(row.keys())
        adapted = adapt_mlm2pro_row(row, col_map, row_idx=3)
        assert adapted["Smash Factor"] == "1.50"
        assert adapted["Shot Number"] == "3"

    def test_adapt_row_with_club_override(self):
        row = {
            "Ball Speed": "150.0",
            "Club": "Unknown",
        }
        col_map = detect_mlm2pro_column_map(row.keys())
        adapted = adapt_mlm2pro_row(row, col_map, row_idx=1, club_override="Driver")
        assert adapted["Club"] == "Driver"


class TestAdaptMlm2ProCsvEndToEnd:
    """Test full file conversion and integration with compare_trackman expectations."""

    def test_convert_csv_file_with_preamble(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_csv = tmp_path / "raw_mlm2pro.csv"
            output_csv = tmp_path / "adapted_trackman.csv"

            raw_content = (
                "sep=,\n"
                "# Rapsodo MLM2 Pro Session Export\n"
                "Date,Shot #,Club,Ball Speed (mph),Club Speed (mph),Smash Factor,Launch Angle (deg),Launch Direction (deg),Spin Rate (rpm),Spin Axis (deg),Carry Distance (yds),Total Distance (yds)\n"
                "5/6/2026 6:58:02 PM,1,7 Iron,123.8,85.4,1.45,15.4,-1.2,5492,11.5,177.2,184.1\n"
                "5/6/2026 6:58:43 PM,2,7 Iron,110.2,83.4,1.32,15.5,-0.3,5419,7.2,153.2,164.5\n"
                "\n"
            )
            input_csv.write_text(raw_content, encoding="utf-8")

            count = adapt_mlm2pro_csv(input_csv, output_csv)
            assert count == 2
            assert output_csv.exists()

            with output_csv.open("r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                assert reader.fieldnames == TRACKMAN_OUTPUT_HEADERS
                rows = list(reader)
                assert len(rows) == 2
                assert rows[0]["Club"] == "7 Iron"
                assert rows[0]["Ball Speed"] == "123.8"
                assert rows[0]["Spin Rate"] == "5492"
                assert rows[1]["Ball Speed"] == "110.2"

    def test_adapted_csv_matches_compare_trackman_aliases(self):
        """Verify that adapted CSV is successfully parsed by compare_trackman._build_column_map."""
        from scripts.analysis.compare_trackman import _build_column_map

        col_map = _build_column_map(TRACKMAN_OUTPUT_HEADERS)
        assert "ball_speed_mph" in col_map
        assert "club_speed_mph" in col_map
        assert "smash_factor" in col_map
        assert "launch_angle_vertical" in col_map
        assert "launch_angle_horizontal" in col_map
        assert "spin_rpm" in col_map
        assert "carry_yards" in col_map
        assert "club" in col_map
        assert "shot_number" in col_map
        assert "timestamp" in col_map

    def test_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            adapt_mlm2pro_csv("nonexistent_path_12345.csv", "out.csv")

    def test_empty_file_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_csv = Path(tmpdir) / "empty.csv"
            empty_csv.write_text("", encoding="utf-8")
            with pytest.raises(ValueError, match="No valid CSV data found"):
                adapt_mlm2pro_csv(empty_csv, Path(tmpdir) / "out.csv")

    def test_cli_execution(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_csv = tmp_path / "mlm2.csv"
            output_csv = tmp_path / "out.csv"

            input_csv.write_text(
                "Date,Club,Ball Speed,Club Speed,Total Spin\n"
                "5/6/2026 7:00 PM,Driver,150.0,100.0,2500\n",
                encoding="utf-8",
            )

            monkeypatch.setattr(
                "sys.argv",
                [
                    "mlm2pro_adapter.py",
                    "--input",
                    str(input_csv),
                    "--output",
                    str(output_csv),
                ],
            )
            mlm2pro_adapter.main()
            assert output_csv.exists()
            with output_csv.open("r", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
                assert len(rows) == 1
                assert rows[0]["Club"] == "Driver"
                assert rows[0]["Ball Speed"] == "150.0"
                assert rows[0]["Club Speed"] == "100.0"
                assert rows[0]["Spin Rate"] == "2500"
