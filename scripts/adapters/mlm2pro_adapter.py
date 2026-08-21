#!/usr/bin/env python3
"""Convert Rapsodo MLM2 Pro CSV export files to TrackMan-compatible CSV format.

This adapter transforms session CSV exports from the Rapsodo MLM2 Pro mobile
app into the TrackMan CSV layout expected by scripts/analysis/compare_trackman.py.

Usage::

    uv run python scripts/adapters/mlm2pro_adapter.py \\
        --input ~/Downloads/mlm2pro_session_2026-08-20.csv \\
        --output ~/openflight_sessions/mlm2pro_trackman_adapted.csv

Then feed directly into compare_trackman.py::

    uv run python scripts/analysis/compare_trackman.py \\
        --openflight ~/openflight_sessions/session_20260820_*.jsonl \\
        --trackman ~/openflight_sessions/mlm2pro_trackman_adapted.csv \\
        --output ~/openflight_sessions/comparison_20260820.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# Speed conversion constants
KMH_TO_MPH = 1.0 / 1.609344
MPS_TO_MPH = 2.2369362920544
METRES_TO_YARDS = 1.0936132983377

# Output TrackMan canonical CSV headers
TRACKMAN_OUTPUT_HEADERS = [
    "Date",
    "Shot Number",
    "Club",
    "Ball Speed",
    "Club Speed",
    "Smash Factor",
    "Launch Angle",
    "Launch Direction",
    "Spin Rate",
    "Spin Axis",
    "Carry Distance",
    "Total Distance",
    "Max Height - Height",
    "Carry Flat - Side",
]

# Field match alias table for MLM2 Pro headers
MLM2PRO_FIELD_ALIASES: Dict[str, List[str]] = {
    "timestamp": [
        "date & time",
        "date/time",
        "date time",
        "datetime",
        "timestamp",
        "date",
        "time",
    ],
    "shot_number": [
        "shot number",
        "shot #",
        "shot no",
        "shot_no",
        "shot",
        "tmd no",
        "index",
        "#",
    ],
    "club": [
        "club type",
        "club name",
        "club",
    ],
    "ball_speed": [
        "ball speed",
        "ballspeed",
        "ball_speed",
        "ball velocity",
    ],
    "club_speed": [
        "club speed",
        "clubspeed",
        "club_speed",
        "club head speed",
        "clubheadspeed",
    ],
    "smash_factor": [
        "smash factor",
        "smashfactor",
        "smash",
    ],
    "launch_angle": [
        "launch angle (deg)",
        "launch angle v",
        "launch angle",
        "vertical launch",
        "v. launch",
    ],
    "launch_direction": [
        "launch direction (deg)",
        "launch direction",
        "launch angle h",
        "horizontal launch",
        "side angle",
        "azimuth",
        "h. launch",
    ],
    "spin_rate": [
        "spin rate (rpm)",
        "total spin (rpm)",
        "spin rate",
        "total spin",
        "spinrate",
        "spin",
    ],
    "spin_axis": [
        "spin axis (deg)",
        "spin axis",
        "spin tilt",
    ],
    "carry_distance": [
        "carry distance (yds)",
        "carry distance (m)",
        "carry distance",
        "carry (yds)",
        "carry (m)",
        "carry",
    ],
    "total_distance": [
        "total distance (yds)",
        "total distance (m)",
        "total distance",
        "total (yds)",
        "total (m)",
        "total",
    ],
    "apex": [
        "max height (ft)",
        "max height (yds)",
        "max height",
        "apex (ft)",
        "apex (yds)",
        "apex",
        "height",
    ],
    "offline": [
        "side carry (yds)",
        "carry side (yds)",
        "carry flat - side",
        "offline (yds)",
        "side (yds)",
        "offline",
        "side",
    ],
}


def _clean_header(header: str) -> str:
    """Normalize a header string for alias matching."""
    return re.sub(r"[\s_]+", " ", header.strip().lower())


def detect_mlm2pro_column_map(headers: Iterable[str]) -> Dict[str, str]:
    """Map canonical field names to actual CSV header names."""
    mapping: Dict[str, str] = {}
    cleaned_to_raw = {_clean_header(h): h for h in headers}

    for canonical, aliases in MLM2PRO_FIELD_ALIASES.items():
        for alias in aliases:
            cleaned_alias = _clean_header(alias)
            # Check exact match first
            if cleaned_alias in cleaned_to_raw and canonical not in mapping:
                mapping[canonical] = cleaned_to_raw[cleaned_alias]
                break
            # Check substring match
            for cleaned_hdr, raw_hdr in cleaned_to_raw.items():
                if cleaned_alias in cleaned_hdr and canonical not in mapping:
                    mapping[canonical] = raw_hdr
                    break
            if canonical in mapping:
                break

    return mapping


def detect_header_units(headers: Iterable[str]) -> Dict[str, str]:
    """Detect units (speed, distance) from header suffixes."""
    units: Dict[str, str] = {"speed": "mph", "distance": "yards"}
    for h in headers:
        ch = _clean_header(h)
        if "ball" in ch or "club" in ch:
            if "km/h" in ch or "kph" in ch or "kmh" in ch:
                units["speed"] = "kph"
            elif "m/s" in ch or "mps" in ch:
                units["speed"] = "mps"
            elif "mph" in ch:
                units["speed"] = "mph"
        if "carry" in ch or "total" in ch:
            if "meter" in ch or "metre" in ch or "(m)" in ch or "[m]" in ch:
                units["distance"] = "meters"
            elif "yard" in ch or "(yd" in ch or "[yd" in ch:
                units["distance"] = "yards"
    return units


def _parse_float(val: Any) -> Optional[float]:
    """Safely parse float from string or number."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "-", "--", "n/a"):
        return None
    # Remove unit suffixes if embedded in value
    s = re.sub(r"[^\d.\-+]", "", s)
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def convert_speed_to_mph(val: Optional[float], unit: str) -> Optional[float]:
    """Convert speed value to mph."""
    if val is None:
        return None
    unit_lower = unit.lower()
    if unit_lower in ("kph", "km/h", "kmh"):
        return val * KMH_TO_MPH
    if unit_lower in ("mps", "m/s"):
        return val * MPS_TO_MPH
    return val


def convert_distance_to_yards(val: Optional[float], unit: str) -> Optional[float]:
    """Convert distance value to yards."""
    if val is None:
        return None
    unit_lower = unit.lower()
    if unit_lower in ("meters", "meter", "m", "metres", "metre"):
        return val * METRES_TO_YARDS
    return val


def adapt_mlm2pro_row(
    row: Dict[str, Any],
    col_map: Dict[str, str],
    row_idx: int,
    speed_unit: str = "mph",
    distance_unit: str = "yards",
    club_override: Optional[str] = None,
) -> Dict[str, str]:
    """Transform a single MLM2 Pro CSV row into a TrackMan CSV record."""

    def get_val(key: str) -> Any:
        raw_key = col_map.get(key)
        return row.get(raw_key) if raw_key else None

    # Date / Timestamp
    ts_val = get_val("timestamp")
    date_str = str(ts_val).strip() if ts_val is not None else ""
    if not date_str:
        date_str = datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")

    # Shot number
    shot_no_raw = _parse_float(get_val("shot_number"))
    shot_num = int(shot_no_raw) if shot_no_raw is not None else row_idx

    # Club
    club_val = club_override or get_val("club")
    club_str = str(club_val).strip() if club_val is not None else ""

    # Metrics
    ball_speed_raw = _parse_float(get_val("ball_speed"))
    ball_speed = convert_speed_to_mph(ball_speed_raw, speed_unit)

    club_speed_raw = _parse_float(get_val("club_speed"))
    club_speed = convert_speed_to_mph(club_speed_raw, speed_unit)

    smash_raw = _parse_float(get_val("smash_factor"))
    if smash_raw is None and ball_speed and club_speed and club_speed > 0:
        smash_raw = ball_speed / club_speed

    la_v = _parse_float(get_val("launch_angle"))
    la_h = _parse_float(get_val("launch_direction"))
    spin = _parse_float(get_val("spin_rate"))
    spin_axis = _parse_float(get_val("spin_axis"))

    carry_raw = _parse_float(get_val("carry_distance"))
    carry = convert_distance_to_yards(carry_raw, distance_unit)

    total_raw = _parse_float(get_val("total_distance"))
    total = convert_distance_to_yards(total_raw, distance_unit)

    apex = _parse_float(get_val("apex"))
    offline = _parse_float(get_val("offline"))

    def fmt_num(v: Optional[float], decimals: int = 1) -> str:
        if v is None:
            return ""
        return f"{v:.{decimals}f}"

    return {
        "Date": date_str,
        "Shot Number": str(shot_num),
        "Club": club_str,
        "Ball Speed": fmt_num(ball_speed, 1),
        "Club Speed": fmt_num(club_speed, 1),
        "Smash Factor": fmt_num(smash_raw, 2),
        "Launch Angle": fmt_num(la_v, 1),
        "Launch Direction": fmt_num(la_h, 1),
        "Spin Rate": fmt_num(spin, 0),
        "Spin Axis": fmt_num(spin_axis, 1),
        "Carry Distance": fmt_num(carry, 1),
        "Total Distance": fmt_num(total, 1),
        "Max Height - Height": fmt_num(apex, 1),
        "Carry Flat - Side": fmt_num(offline, 1),
    }


def adapt_mlm2pro_csv(
    input_file: str | Path,
    output_file: str | Path,
    speed_unit: Optional[str] = None,
    distance_unit: Optional[str] = None,
    club_override: Optional[str] = None,
) -> int:
    """Read an MLM2 Pro CSV file, transform to TrackMan format, and save.

    Returns the number of shots converted.
    """
    input_path = Path(input_file)
    output_path = Path(output_file)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    # Read lines and skip any metadata preamble (e.g. sep=,)
    content = input_path.read_text(encoding="utf-8-sig", errors="replace")
    lines = content.splitlines()
    cleaned_lines = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("sep=") or s.startswith("#"):
            continue
        cleaned_lines.append(line)

    if not cleaned_lines:
        raise ValueError(f"No valid CSV data found in {input_path}")

    reader = csv.DictReader(cleaned_lines)
    if not reader.fieldnames:
        raise ValueError(f"Could not parse CSV headers from {input_path}")

    col_map = detect_mlm2pro_column_map(reader.fieldnames)
    detected_units = detect_header_units(reader.fieldnames)

    effective_speed_unit = speed_unit or detected_units["speed"]
    effective_dist_unit = distance_unit or detected_units["distance"]

    adapted_rows: List[Dict[str, str]] = []
    row_counter = 1
    for row in reader:
        # Check if row has any values
        if not any(str(v).strip() for v in row.values() if v is not None):
            continue
        adapted = adapt_mlm2pro_row(
            row=row,
            col_map=col_map,
            row_idx=row_counter,
            speed_unit=effective_speed_unit,
            distance_unit=effective_dist_unit,
            club_override=club_override,
        )
        adapted_rows.append(adapted)
        row_counter += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKMAN_OUTPUT_HEADERS)
        writer.writeheader()
        writer.writerows(adapted_rows)

    return len(adapted_rows)


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Adapt Rapsodo MLM2 Pro CSV export into TrackMan CSV format.",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to MLM2 Pro CSV export file.",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Path to output TrackMan-compatible CSV.",
    )
    parser.add_argument(
        "--speed-unit",
        choices=["mph", "kph", "mps"],
        default=None,
        help="Override input speed unit (default: auto-detect from header or mph).",
    )
    parser.add_argument(
        "--distance-unit",
        choices=["yards", "meters"],
        default=None,
        help="Override input distance unit (default: auto-detect from header or yards).",
    )
    parser.add_argument(
        "--club-override",
        default=None,
        help="Override club name for all shots in the file.",
    )

    args = parser.parse_args()
    try:
        count = adapt_mlm2pro_csv(
            input_file=args.input,
            output_file=args.output,
            speed_unit=args.speed_unit,
            distance_unit=args.distance_unit,
            club_override=args.club_override,
        )
        print(f"Successfully converted {count} shots from {args.input} to {args.output}")
    except Exception as e:
        print(f"Error converting MLM2 Pro CSV: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
