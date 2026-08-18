#!/usr/bin/env python3
"""Batch-replay rejected IWR6843 captures through experimental recovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from openflight.iwr6843.lcmf import LCMFResult, estimate_lcmf_v1
from openflight.iwr6843.monitor import tx_order_from_config
from openflight.iwr6843.recovery import (
    RecoveryPrior,
    find_recovery_candidates,
    select_recovery_candidate,
    track_impact_time_s,
)
from openflight.iwr6843.replay import build_replay_calibration, inputs_from_session
from openflight.iwr6843.shot import process_dump


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Learn truth-free track priors from accepted captures, then replay "
            "rejected captures as experimental low-confidence candidates."
        )
    )
    parser.add_argument("sessions", nargs="+", type=Path, help="Session JSONL files")
    parser.add_argument("--tee-m", required=True, type=float)
    parser.add_argument("--net-m", type=float, default=None)
    parser.add_argument("--tilt-deg", type=float, default=None)
    parser.add_argument("--radar-height-m", type=float, default=None)
    parser.add_argument("--ball-height-m", type=float, default=0.040)
    parser.add_argument("--club", default=None)
    parser.add_argument(
        "--cal",
        default="config/iwr6843_calibration_reference.json",
    )
    parser.add_argument(
        "--cfg",
        default="config/iwr6843_l3dump_wide_24f3ms_53bin_iq16.cfg",
    )
    parser.add_argument(
        "--tdm-sign-policy",
        choices=("positive", "negative"),
        default="positive",
    )
    parser.add_argument("--min-prior-shots", type=int, default=8)
    parser.add_argument("--out", type=Path, default=None)
    return parser


def _learn_prior(results, calibration) -> RecoveryPrior:
    observations = []
    for replay, result, measurement in results:
        if not result.accepted or measurement.track is None:
            continue
        impact_s = track_impact_time_s(
            measurement.track,
            measurement.geometry,
            calibration,
        )
        if impact_s is None:
            continue
        observations.append((replay, measurement, impact_s))
    return RecoveryPrior.fit(
        [
            measurement.track.speed_mph / replay.ball_speed_mph
            for replay, measurement, _impact_s in observations
        ],
        [impact_s for _replay, _measurement, impact_s in observations],
        [
            measurement.track.t_last - measurement.track.t_first
            for _replay, measurement, _impact_s in observations
        ],
    )


def _row(replay, baseline: LCMFResult, recovered: LCMFResult | None, candidate) -> dict:
    return {
        "shot_number": replay.shot_number,
        "capture_path": str(replay.capture_path),
        "ball_speed_mph": replay.ball_speed_mph,
        "baseline_status": baseline.status,
        "baseline_launch_angle_deg": baseline.angle_deg,
        "recovery_status": recovered.status if recovered is not None else "not_recovered",
        "recovered_launch_angle_deg": recovered.angle_deg if recovered is not None else None,
        "recovery_track_speed_mph": candidate.track.speed_mph if candidate else None,
        "recovery_speed_ratio": candidate.speed_ratio if candidate else None,
        "recovery_track_rms_bins": candidate.track.rms_bins if candidate else None,
        "recovery_track_inliers": candidate.track.n_inliers if candidate else None,
        "recovery_track_span_s": (
            candidate.track.t_last - candidate.track.t_first if candidate else None
        ),
        "recovery_impact_s": candidate.impact_s if candidate else None,
        "recovery_score": candidate.score if candidate else None,
        "recovery_scope": candidate.scope if candidate else None,
        "recovery_components_deg": recovered.components_deg if recovered is not None else {},
        "recovery_n_frames": recovered.n_frames if recovered is not None else 0,
        "recovery_n_snapshots": recovered.n_snapshots if recovered is not None else 0,
    }


def main() -> int:
    """Run baseline replay, learn priors, and evaluate rejected captures."""
    args = _parser().parse_args()
    inputs = [
        replay
        for session in args.sessions
        for replay in inputs_from_session(session, club=args.club)
    ]
    if not inputs:
        raise SystemExit("no replayable IWR6843 captures found")
    calibration = build_replay_calibration(
        args.cal,
        tee_range_m=args.tee_m,
        tilt_deg=args.tilt_deg,
        radar_height_m=args.radar_height_m,
        ball_height_m=args.ball_height_m,
    )
    tx_order = tx_order_from_config(args.cfg)
    baseline = []
    for replay in inputs:
        raw = replay.capture_path.read_bytes()
        result = estimate_lcmf_v1(
            raw,
            calibration,
            ball_speed_mph=replay.ball_speed_mph,
            club=replay.club,
            net_range_m=args.net_m,
            tx_order=tx_order,
            tdm_sign_policy=args.tdm_sign_policy,
        )
        measurement = process_dump(
            raw,
            calibration,
            club=replay.club,
            net_range_m=args.net_m,
            tx_order=tx_order,
            tdm_sign_policy=args.tdm_sign_policy,
        )
        baseline.append((replay, result, measurement))
    accepted_count = sum(result.accepted for _replay, result, _measurement in baseline)
    if accepted_count < args.min_prior_shots:
        raise SystemExit(
            f"need {args.min_prior_shots} accepted captures to learn recovery prior; "
            f"found {accepted_count}"
        )
    prior = _learn_prior(baseline, calibration)

    rows = []
    recovered_count = 0
    for replay, result, _measurement in baseline:
        if result.accepted:
            rows.append(_row(replay, result, None, None))
            continue
        raw = replay.capture_path.read_bytes()
        candidates = find_recovery_candidates(
            raw,
            calibration,
            ball_speed_mph=replay.ball_speed_mph,
            net_range_m=args.net_m,
        )
        candidate = select_recovery_candidate(candidates, prior)
        recovered = None
        if candidate is not None:
            measurement = estimate_lcmf_v1(
                raw,
                calibration,
                ball_speed_mph=replay.ball_speed_mph,
                club=replay.club,
                net_range_m=args.net_m,
                tx_order=tx_order,
                tdm_sign_policy=args.tdm_sign_policy,
                track_override=candidate.track,
                track_override_scope=candidate.scope,
            )
            # A recovery needs both independently conditioned vertical models.
            if (
                measurement.accepted
                and not measurement.single_channel
                and measurement.n_frames >= 4
            ):
                recovered = measurement
                recovered_count += 1
        rows.append(_row(replay, result, recovered, candidate))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
        print(f"wrote {len(rows)} rows to {args.out}")
    for row in rows:
        if row["baseline_status"].startswith("accepted"):
            continue
        print(
            f"shot {row['shot_number']}: {row['baseline_status']} -> "
            f"{row['recovery_status']} ({row['recovered_launch_angle_deg']})"
        )
    print(
        f"summary: {accepted_count}/{len(rows)} baseline accepted; "
        f"{recovered_count} additional experimental recoveries"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
