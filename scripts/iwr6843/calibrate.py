#!/usr/bin/env python3
"""Run an OPS+IWR6843 calibration session from the terminal."""

from __future__ import annotations

import argparse
import logging
import signal
import threading
from datetime import datetime
from pathlib import Path

from openflight.iwr6843 import Calibration
from openflight.iwr6843.calibration_session import (
    CalibrationSummary,
    JsonlWriter,
    build_record,
    clone_calibration,
    parse_club,
    tilt_consistency_sweep,
)
from openflight.iwr6843.monitor import IWR6843CaptureMonitor, tx_order_from_config
from openflight.iwr6843.runtime import IWR6843Runtime
from openflight.iwr6843.shot import process_dump
from openflight.rolling_buffer.monitor import RollingBufferMonitor

LOGGER = logging.getLogger("openflight.iwr6843.calibrate")


def _default_outdir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path.home() / "openflight_sessions" / "iwr6843_calibration" / stamp


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a production-shaped calibration session: OPS sound trigger/speed "
            "plus matched IWR6843 L3 capture and LCMF-v1 diagnostics."
        )
    )
    parser.add_argument("--shots", type=int, default=20, help="Accepted OPS shots to record")
    parser.add_argument("--ops-port", default=None, help="OPS243 serial port (auto if omitted)")
    parser.add_argument("--iwr6843-port", default=None, help="IWR6843 CLI serial port")
    parser.add_argument("--trigger-pin", type=int, default=17, help="BCM GPIO for sound trigger")
    parser.add_argument(
        "--cfg",
        default="config/iwr6843_l3dump_wide_24f3ms_53bin_iq16.cfg",
        help="IWR6843 L3 dump cfg file",
    )
    parser.add_argument(
        "--cal",
        default="config/iwr6843_calibration_reference.json",
        help="IWR6843 array calibration JSON",
    )
    parser.add_argument("--outdir", type=Path, default=None, help="Directory for dumps/logs")
    parser.add_argument("--tee-m", type=float, required=True, help="Radar-to-ball slant range")
    parser.add_argument("--net-m", type=float, default=None, help="Radar-to-net range")
    parser.add_argument("--tilt-deg", type=float, default=None, help="Measured mount tilt")
    parser.add_argument("--radar-height-m", type=float, default=None, help="Antenna center height")
    parser.add_argument("--ball-height-m", type=float, default=0.040, help="Ball center height")
    parser.add_argument(
        "--tx-order",
        choices=("auto", "normal", "reversed"),
        default="auto",
        help="Physical TX order; auto validates from cfg chirp masks",
    )
    parser.add_argument(
        "--club",
        default="unknown",
        help="Club label used for OPS spin plausibility and LCMF speed floor",
    )
    parser.add_argument(
        "--sound-pre-trigger",
        type=int,
        default=12,
        help="OPS rolling-buffer pre-trigger segments, matching server default",
    )
    parser.add_argument(
        "--capture-timeout-s",
        type=float,
        default=12.0,
        help="Seconds to wait for the matched TI dump after an OPS shot",
    )
    parser.add_argument(
        "--no-tilt-sweep",
        action="store_true",
        help="Skip radar-consistency tilt estimate for faster shot turnaround",
    )
    parser.add_argument("--tilt-sweep-half-width-deg", type=float, default=3.0)
    parser.add_argument("--tilt-sweep-step-deg", type=float, default=1.0)
    parser.add_argument("--debug", action="store_true", help="Verbose logs")
    return parser


def _resolve_tx_order(config_path: str, requested: str) -> str:
    configured = tx_order_from_config(config_path)
    if requested == "auto":
        return configured
    if requested != configured:
        raise ValueError(
            f"--tx-order {requested} conflicts with {Path(config_path).name} ({configured})"
        )
    return requested


def _print_record(summary: CalibrationSummary) -> None:
    record = summary.shots[-1]
    if record.accepted:
        print(
            f"[{record.shot_number:02d}] OPS {record.ball_speed_mph:5.1f} mph | "
            f"TI LA {record.launch_angle_deg:5.2f} deg | "
            f"rms {record.track_rms_bins:.2f} | "
            f"start {record.track_start_range_m:.2f} m"
        )
    else:
        print(
            f"[{record.shot_number:02d}] OPS {record.ball_speed_mph:5.1f} mph | "
            f"TI withheld: {record.lcmf_status or record.iwr_capture_error or 'no measurement'}"
        )
    data = summary.to_dict()
    print(
        "     coverage "
        f"{data['accepted_shots']}/{data['shots']} "
        f"({100.0 * data['coverage']:.0f}%), "
        f"median LA {data['median_launch_angle_deg']}, "
        f"median start {data['median_track_start_range_m']} m, "
        f"tilt candidate {data['median_tilt_candidate_deg']} deg"
    )


def main() -> int:
    args = _build_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    if args.shots <= 0:
        raise SystemExit("--shots must be positive")

    outdir = (args.outdir or _default_outdir()).expanduser()
    outdir.mkdir(parents=True, exist_ok=True)
    writer = JsonlWriter(outdir / "calibration_session.jsonl")
    tx_order = _resolve_tx_order(args.cfg, args.tx_order)
    club = parse_club(args.club)

    calibration = clone_calibration(
        Calibration.load(args.cal),
        tee_range_m=args.tee_m,
        tilt_deg=args.tilt_deg,
        radar_height_m=args.radar_height_m,
        ball_height_m=args.ball_height_m,
    )
    center_tilt_deg = (
        args.tilt_deg if args.tilt_deg is not None else float(calibration.meta.get("tilt_deg", 0.0))
    )

    writer.write(
        {
            "type": "iwr6843_calibration_start",
            "outdir": str(outdir),
            "shots_requested": args.shots,
            "club": club.value,
            "cfg": args.cfg,
            "cal": args.cal,
            "tee_m": args.tee_m,
            "net_m": args.net_m,
            "tilt_deg": center_tilt_deg,
            "radar_height_m": calibration.radar_height_m,
            "ball_height_m": calibration.tee_ball_height_m,
            "tx_order": tx_order,
            "tilt_sweep": not args.no_tilt_sweep,
            "raw_dump_saved": args.debug,
        }
    )

    iwr_monitor = IWR6843CaptureMonitor(
        config_path=args.cfg,
        output_dir=outdir / "iwr6843",
        port=args.iwr6843_port,
        gpio_pin=args.trigger_pin,
        save_dumps=args.debug,
    )
    runtime = IWR6843Runtime(
        capture_monitor=iwr_monitor,
        calibration=calibration,
        net_range_m=args.net_m,
        tx_order=tx_order,
        capture_timeout_s=args.capture_timeout_s,
    )
    ops_monitor = RollingBufferMonitor(
        port=args.ops_port,
        trigger_type="sound",
        pre_trigger_segments=args.sound_pre_trigger,
    )

    done = threading.Event()
    summary = CalibrationSummary()

    def on_shot(shot):
        shot.club = club
        shot_number = len(summary.shots) + 1
        result = runtime.process_shot(
            impact_timestamp=shot.impact_timestamp,
            ball_speed_mph=shot.ball_speed_mph,
            club=shot.club.value,
        )
        capture = result.capture
        track_measurement = None
        tilt_candidate = (None, None)
        if capture is not None and capture.valid and capture.raw is not None:
            track_measurement = process_dump(
                capture.raw,
                calibration,
                club=shot.club.value,
                net_range_m=args.net_m,
                tx_order=tx_order,
                tdm_sign_policy="positive",
            )
            if not args.no_tilt_sweep and result.measurement and result.measurement.accepted:
                tilt_candidate = tilt_consistency_sweep(
                    raw=capture.raw,
                    base_calibration=calibration,
                    ball_speed_mph=shot.ball_speed_mph,
                    club=shot.club.value,
                    net_range_m=args.net_m,
                    tx_order=tx_order,
                    center_tilt_deg=center_tilt_deg,
                    half_width_deg=args.tilt_sweep_half_width_deg,
                    step_deg=args.tilt_sweep_step_deg,
                )
        record = build_record(
            shot_number=shot_number,
            shot=shot,
            capture_path=str(capture.path) if capture and capture.path else None,
            capture_error=(
                capture.error
                if capture is not None
                else "no capture matched the OPS impact timestamp"
            ),
            measurement=result.measurement,
            track_measurement=track_measurement,
            calibration=calibration,
            tilt_candidate=tilt_candidate,
        )
        summary.shots.append(record)
        writer.write(record.to_dict())
        writer.write(summary.to_dict())
        _print_record(summary)
        if len(summary.shots) >= args.shots:
            done.set()

    def stop(_signum=None, _frame=None):
        done.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    print("Starting OPS+IWR6843 calibration session")
    print(f"Output: {outdir}")
    print(f"Raw .l3dump files: {'enabled' if args.debug else 'disabled'}")
    print(f"Club: {club.value}; TX order: {tx_order}; target shots: {args.shots}")
    print("Hit shots when ready. Press Ctrl+C to stop early.")

    try:
        iwr_monitor.start()
        ops_monitor.connect()
        ops_monitor.set_club(club)
        ops_monitor.start(shot_callback=on_shot)
        done.wait()
    finally:
        LOGGER.info("Stopping calibration session")
        ops_monitor.disconnect()
        runtime.stop()
        writer.write(summary.to_dict())

    print("Calibration session complete")
    print(f"JSONL: {outdir / 'calibration_session.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
