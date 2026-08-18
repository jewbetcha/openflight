#!/usr/bin/env python3
"""Replay saved IWR6843 L3 captures through LCMF-v1."""

from __future__ import annotations

import argparse
from pathlib import Path

from openflight.iwr6843.monitor import tx_order_from_config
from openflight.iwr6843.replay import (
    build_replay_calibration,
    input_from_dump,
    inputs_from_session,
    replay_capture,
    replay_summary,
    write_records,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay a session JSONL or single .l3dump through IWR6843 LCMF-v1."
    )
    parser.add_argument("--input", required=True, type=Path, help="Session JSONL or .l3dump file")
    parser.add_argument("--ball-speed-mph", type=float, help="Required for a single .l3dump")
    parser.add_argument("--club", default=None, help="Club label, e.g. 9i, 7i, driver")
    parser.add_argument("--tee-m", type=float, required=True, help="Radar-to-ball slant range")
    parser.add_argument("--net-m", type=float, default=None, help="Radar-to-net/screen range")
    parser.add_argument(
        "--cal",
        default="config/iwr6843_calibration_reference.json",
        help="IWR6843 array calibration JSON",
    )
    parser.add_argument("--tilt-deg", type=float, default=None, help="Override mount tilt")
    parser.add_argument("--radar-height-m", type=float, default=None, help="Antenna-center height")
    parser.add_argument("--ball-height-m", type=float, default=0.040, help="Ball-center height")
    parser.add_argument(
        "--cfg",
        default="config/iwr6843_l3dump_wide_24f3ms_53bin_iq16.cfg",
        help="Cfg used to infer TX order when --tx-order auto",
    )
    parser.add_argument(
        "--tx-order",
        choices=("auto", "normal", "reversed"),
        default="auto",
        help="Physical TX order",
    )
    parser.add_argument(
        "--tdm-sign-policy",
        choices=("positive", "negative", "auto"),
        default="positive",
        help="TDM sign policy; positive matches server LCMF-v1",
    )
    parser.add_argument("--grid-step-deg", type=float, default=0.5)
    parser.add_argument("--out", type=Path, default=None, help="Optional CSV or JSONL output path")
    parser.add_argument(
        "--format",
        choices=("table", "csv", "jsonl"),
        default=None,
        help="Output format. Defaults from --out suffix, otherwise table.",
    )
    return parser


def _resolve_output_format(path: Path | None, requested: str | None) -> str:
    if requested:
        return requested
    if path is None:
        return "table"
    if path.suffix.lower() == ".jsonl":
        return "jsonl"
    return "csv"


def _resolve_tx_order(config_path: str, requested: str) -> str:
    configured = tx_order_from_config(config_path)
    if requested == "auto":
        return configured
    if requested != configured:
        raise ValueError(f"--tx-order {requested} conflicts with {Path(config_path).name}")
    return requested


def _inputs(args) -> list:
    if args.input.suffix.lower() == ".l3dump":
        if args.ball_speed_mph is None:
            raise ValueError("--ball-speed-mph is required when --input is a single .l3dump")
        return [
            input_from_dump(
                args.input,
                ball_speed_mph=args.ball_speed_mph,
                club=args.club,
            )
        ]
    return inputs_from_session(args.input, club=args.club)


def _print_table(records) -> None:
    print("shot  speed  club     status                         launch  rms   start_m  file")
    for record in records:
        launch = (
            f"{record.launch_angle_deg:6.2f}" if record.launch_angle_deg is not None else "  n/a "
        )
        rms = f"{record.track_rms_bins:4.2f}" if record.track_rms_bins is not None else " n/a"
        start = (
            f"{record.track_start_range_m:7.3f}"
            if record.track_start_range_m is not None
            else "   n/a "
        )
        shot = str(record.shot_number) if record.shot_number is not None else "-"
        print(
            f"{shot:>4}  {record.ball_speed_mph:5.1f}  "
            f"{(record.club or '')[:7]:<7}  {record.status[:30]:<30}  "
            f"{launch}  {rms}  {start}  {record.capture_path}"
        )


def main() -> int:
    args = _build_parser().parse_args()
    output_format = _resolve_output_format(args.out, args.format)
    tx_order = _resolve_tx_order(args.cfg, args.tx_order)
    replay_inputs = _inputs(args)
    if not replay_inputs:
        raise SystemExit(f"no replayable IWR6843 captures found in {args.input}")
    calibration = build_replay_calibration(
        args.cal,
        tee_range_m=args.tee_m,
        tilt_deg=args.tilt_deg,
        radar_height_m=args.radar_height_m,
        ball_height_m=args.ball_height_m,
    )
    records = [
        replay_capture(
            replay_input,
            calibration,
            net_range_m=args.net_m,
            tx_order=tx_order,
            tdm_sign_policy=args.tdm_sign_policy,
            grid_step_deg=args.grid_step_deg,
        )
        for replay_input in replay_inputs
    ]
    if args.out is not None:
        if output_format == "table":
            raise SystemExit("--format table cannot be used with --out")
        write_records(records, args.out, output_format)
        print(f"wrote {len(records)} replay rows to {args.out}")
    else:
        _print_table(records)
    summary = replay_summary(records)
    print(
        "summary: "
        f"{summary['accepted_shots']}/{summary['shots']} accepted "
        f"({100.0 * summary['coverage']:.0f}% coverage), "
        f"median LA {summary['median_launch_angle_deg']}, "
        f"median RMS {summary['median_track_rms_bins']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
