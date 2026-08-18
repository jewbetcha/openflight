#!/usr/bin/env python3
"""Evaluate calibrated IWR6843 horizontal estimators against TrackMan truth.

The first wide-IQ16 session calibrates one setup-level phase reference. The
later wide session is the primary holdout; dense-IQ8 shots are reported as a
separate format-robustness cohort. No club-specific fitting is performed.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from openflight.iwr6843 import doa
from openflight.iwr6843.calibration import Calibration
from openflight.iwr6843.dump import is_range_snapshot, parse_dump
from openflight.iwr6843.lcmf import estimate_lcmf_v1
from openflight.iwr6843.shot import TX2_LOOP_PERIOD_S, geometry_from_header

MPH_PER_MS = 2.23694
WINDOWS = (3, 4, 5, 6, 8, 10)
RANGE_BANDS_M = ((1.8, 3.8), (2.0, 4.0), (2.2, 4.2), (2.4, 4.4))


def _event_data(session_path: str, shot_number: int) -> tuple[dict, dict]:
    start = None
    capture = None
    with Path(session_path).open(encoding="utf-8") as handle:
        for line in handle:
            event = json.loads(line)
            if event.get("type") == "session_start":
                start = event
            elif (
                event.get("type") == "iwr6843_capture"
                and int(event.get("shot_number", -1)) == shot_number
            ):
                capture = event
    if start is None or capture is None:
        raise ValueError(f"missing session metadata for shot {shot_number}")
    return start, capture


def _circular_mean(phases: np.ndarray, weights: np.ndarray | None = None) -> tuple[float, float]:
    if weights is None:
        weights = np.ones(phases.size)
    vector = np.sum(weights * np.exp(1j * phases))
    total = float(np.sum(weights))
    return float(np.angle(vector)), float(abs(vector) / total)


def _circular_median(phases: np.ndarray) -> float:
    distances = np.abs(np.angle(np.exp(1j * (phases[:, None] - phases[None, :]))))
    return float(phases[int(np.argmin(np.median(distances, axis=1)))])


def _frame_fusions(
    samples: list[tuple[int, float, float, float, float, float]],
    window: int,
) -> dict[str, tuple[float, float]]:
    observed = sorted({sample[0] for sample in samples})[-window:]
    return _fusions_for_frames(samples, observed, str(window))


def _fusions_for_frames(
    samples: list[tuple[int, float, float, float, float, float]],
    observed: list[int],
    label: str,
) -> dict[str, tuple[float, float]]:
    """Fuse snapshots while giving every selected radar frame equal influence."""
    selected = [sample for sample in samples if sample[0] in observed]
    result: dict[str, tuple[float, float]] = {}
    for name, phase_index in (("combined", 1), ("tx1", 2), ("tx3", 3)):
        phases = np.asarray([sample[phase_index] for sample in selected])
        weights = np.asarray([sample[4] for sample in selected])
        result[f"{name}_weighted_{label}"] = _circular_mean(phases, weights)

        frame_means = []
        frame_coherence = []
        frame_medians = []
        for frame in observed:
            frame_samples = [sample for sample in selected if sample[0] == frame]
            frame_phases = np.asarray([sample[phase_index] for sample in frame_samples])
            frame_weights = np.asarray([sample[4] for sample in frame_samples])
            phase, coherence = _circular_mean(frame_phases, frame_weights)
            frame_means.append(phase)
            frame_coherence.append(max(coherence, 0.05))
            frame_medians.append(_circular_median(frame_phases))
        result[f"{name}_frame_equal_{label}"] = _circular_mean(np.asarray(frame_means))
        result[f"{name}_frame_coherent_{label}"] = _circular_mean(
            np.asarray(frame_means), np.asarray(frame_coherence)
        )
        result[f"{name}_frame_median_{label}"] = _circular_mean(np.asarray(frame_medians))
    return result


def _range_fusions(
    samples: list[tuple[int, float, float, float, float, float]],
    low_m: float,
    high_m: float,
) -> dict[str, tuple[float, float]]:
    frame_ranges = {
        frame: float(np.median([sample[5] for sample in samples if sample[0] == frame]))
        for frame in {sample[0] for sample in samples}
    }
    observed = sorted(
        frame for frame, range_m in frame_ranges.items() if low_m <= range_m <= high_m
    )
    if len(observed) < 3:
        return {}
    label = f"range_{int(10 * low_m):02d}_{int(10 * high_m):02d}"
    return _fusions_for_frames(samples, observed, label)


def _extract(row: dict[str, str]) -> dict[str, object]:
    """Extract truth-independent horizontal phase features for one shot."""
    shot_number = int(row["of_shot_number"])
    start, capture = _event_data(row["session_log_path"], shot_number)
    radar_config = start["config"]["iwr6843"]
    raw = Path(row["iwr_dump_path"]).read_bytes()
    calibration = Calibration.load("config/iwr6843_calibration_reference.json")
    calibration.tee_range_m = float(radar_config["tee_slant_range_m"])
    calibration.tee_ball_height_m = float(radar_config["ball_height_m"])
    calibration.meta["radar_height_m"] = float(radar_config["radar_height_m"])
    calibration.tilt_rad = math.radians(float(row["of_effective_tilt_deg"]))
    ball_speed_mph = float(capture["ball_speed_mph"])
    radar = estimate_lcmf_v1(
        raw,
        calibration,
        ball_speed_mph=ball_speed_mph,
        club=row["of_club"],
        net_range_m=float(radar_config["net_range_m"]),
        tx_order=radar_config.get("tx_order", "normal"),
        horizontal_phase_reference_rad=0.0,
    )
    evidence = radar.range_evidence
    if evidence is None:
        raise ValueError(f"no ball range evidence for shot {shot_number}")

    meta, cube = parse_dump(raw)
    geometry = geometry_from_header(meta, loop_period_s=TX2_LOOP_PERIOD_S)
    n_frames, chirps_per_frame, n_rx, n_samples = cube.shape
    loops = chirps_per_frame // meta["n_tx"]
    tdm = cube.reshape(n_frames, loops, meta["n_tx"], n_rx, n_samples)
    range_cube = tdm if is_range_snapshot(meta) else np.fft.fft(tdm, axis=-1)
    mti = range_cube - range_cube.mean(axis=1, keepdims=True)
    phase_speed_mph = (
        float(row["tm_ball_speed_mph"])
        if row.get("_phase_speed_source") == "trackman"
        else ball_speed_mph
    )
    velocity_ms = phase_speed_mph / MPH_PER_MS
    samples: list[tuple[int, float, float, float, float, float]] = []
    neighborhood_samples: list[tuple[int, float, float, float, float, float]] = []
    track = evidence.track
    for frame in range(geometry.n_frames):
        for loop in range(geometry.n_loops):
            time_s = geometry.loop_time(frame, loop)
            if not track.t_first - 2e-3 <= time_s <= track.t_last + 2e-3:
                continue
            range_bin = int(round(track.bin_at(time_s)))
            if not geometry.contains_bin(range_bin, margin=1, frame=frame):
                continue
            local_bin = geometry.local_bin(range_bin, frame)
            range_m = calibration.true_range(track.range_at(time_s, geometry.range_res_m))
            candidate_bins = [local_bin]
            candidate_bins.extend(
                local_bin + offset
                for offset in (-1, 1)
                if 0 <= local_bin + offset < geometry.frame_bin_count(frame)
            )
            candidate_power = [
                float(np.sum(np.abs(mti[frame, loop, :, :, index]) ** 2))
                for index in candidate_bins
            ]
            neighborhood = candidate_bins[int(np.argmax(candidate_power))]
            for target, index in ((samples, local_bin), (neighborhood_samples, neighborhood)):
                combined = doa.tx2_phase_at(
                    mti,
                    frame,
                    loop,
                    index,
                    velocity_ms=velocity_ms,
                    tdm_sign=1,
                    n_rx=n_rx,
                )
                separate = doa.tx2_reference_phases_at(
                    mti,
                    frame,
                    loop,
                    index,
                    velocity_ms=velocity_ms,
                    tdm_sign=1,
                    n_rx=n_rx,
                )
                if combined is not None and separate is not None:
                    phase, weight = combined
                    tx1_phase, tx3_phase, separate_weight = separate
                    target.append(
                        (
                            frame,
                            phase,
                            tx1_phase,
                            tx3_phase,
                            math.sqrt(weight * separate_weight),
                            range_m,
                        )
                    )

    features: dict[str, tuple[float, float]] = {}
    for window in WINDOWS:
        if len({sample[0] for sample in samples}) >= window:
            features.update(_frame_fusions(samples, window))
        if len({sample[0] for sample in neighborhood_samples}) >= window:
            features.update(
                {
                    f"neighbor_{name}": value
                    for name, value in _frame_fusions(neighborhood_samples, window).items()
                }
            )
    for low_m, high_m in RANGE_BANDS_M:
        features.update(_range_fusions(samples, low_m, high_m))
        features.update(
            {
                f"neighbor_{name}": value
                for name, value in _range_fusions(neighborhood_samples, low_m, high_m).items()
            }
        )
    return {
        "tm_sequence": int(row["tm_sequence"]),
        "session_id": row["of_session_id"],
        "profile": "dense_iq8" if "dense" in row["iwr_config"] else "wide_iq16",
        "club": row["tm_club"],
        "truth_deg": float(row["tm_launch_direction_deg"]),
        "features": features,
    }


def _phase_reference(rows: list[dict[str, object]], model: str) -> float:
    references = np.asarray(
        [
            float(row["features"][model][0]) + np.pi * np.sin(np.radians(float(row["truth_deg"])))
            for row in rows
            if model in row["features"]
        ]
    )
    return _circular_median(references)


def _estimate(phase: float, reference: float) -> float:
    residual = float(np.angle(np.exp(1j * (phase - reference))))
    return -float(np.degrees(np.arcsin(np.clip(residual / np.pi, -1.0, 1.0))))


def _metrics(rows: list[dict[str, object]], model: str, reference: float) -> dict[str, float]:
    errors = np.asarray(
        [
            _estimate(float(row["features"][model][0]), reference) - float(row["truth_deg"])
            for row in rows
            if model in row["features"]
        ]
    )
    absolute = np.abs(errors)
    return {
        "coverage": float(errors.size / len(rows)),
        "n": int(errors.size),
        "mae": float(absolute.mean()),
        "bias": float(errors.mean()),
        "p50": float(np.percentile(absolute, 50)),
        "p75": float(np.percentile(absolute, 75)),
        "p90": float(np.percentile(absolute, 90)),
    }


def main() -> int:
    """Run the calibration/holdout sweep and persist summary diagnostics."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("aligned_csv", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--phase-speed-source",
        choices=("ops", "trackman"),
        default="ops",
        help="Use TrackMan speed only to isolate OPS speed-correction error offline",
    )
    args = parser.parse_args()
    with args.aligned_csv.open(newline="", encoding="utf-8") as handle:
        source = [
            row
            for row in csv.DictReader(handle)
            if row["match_status"] == "matched" and row["iwr_dump_path"]
        ]
    for row in source:
        row["_phase_speed_source"] = args.phase_speed_source
    with ProcessPoolExecutor(max_workers=args.workers) as executor:
        rows = list(executor.map(_extract, source))
    rows.sort(key=lambda row: int(row["tm_sequence"]))

    wide_sessions = sorted({row["session_id"] for row in rows if row["profile"] == "wide_iq16"})
    train = [row for row in rows if row["session_id"] == wide_sessions[0]]
    holdout = [row for row in rows if row["session_id"] in wide_sessions[1:]]
    dense = [row for row in rows if row["profile"] == "dense_iq8"]
    all_wide = train + holdout
    models = sorted(set.intersection(*(set(row["features"]) for row in train)))
    summaries = []
    for model in models:
        reference = _phase_reference(train, model)
        full_reference = _phase_reference(all_wide, model)
        summary = {
            "model": model,
            "train_reference_rad": reference,
            "all_wide_reference_rad": full_reference,
        }
        for name, cohort in (("train", train), ("holdout", holdout), ("dense", dense)):
            for key, value in _metrics(cohort, model, reference).items():
                summary[f"{name}_{key}"] = value
        for key, value in _metrics(all_wide, model, full_reference).items():
            summary[f"all_wide_fit_{key}"] = value
        summaries.append(summary)
    summaries.sort(key=lambda row: (row["holdout_mae"], row["holdout_p90"]))

    print(f"Calibration: {wide_sessions[0]} ({len(train)} shots)")
    print(f"Holdout:     {', '.join(wide_sessions[1:])} ({len(holdout)} shots)")
    print(f"Dense check: {len(dense)} shots\n")
    for row in summaries[:20]:
        print(
            f"{row['model']:<36} ref={row['train_reference_rad']:+.4f} "
            f"holdout MAE={row['holdout_mae']:.3f} bias={row['holdout_bias']:+.3f} "
            f"p90={row['holdout_p90']:.3f} dense={row['dense_mae']:.3f}"
        )

    print("\nPrimary holdout by club")
    for summary in summaries[:3]:
        model = str(summary["model"])
        reference = float(summary["train_reference_rad"])
        print(f"  {model}")
        for club in sorted({str(row["club"]) for row in holdout}):
            club_rows = [row for row in holdout if row["club"] == club]
            metrics = _metrics(club_rows, model, reference)
            print(
                f"    {club:<8} n={metrics['n']:2d} MAE={metrics['mae']:.3f} "
                f"bias={metrics['bias']:+.3f} p90={metrics['p90']:.3f}"
            )

    output = args.output or args.aligned_csv.with_name("iwr_horizontal_model_sweep.csv")
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    print(f"\nSaved {output}")

    detail_models = list(dict.fromkeys([summary["model"] for summary in summaries[:10]]))
    if "combined_weighted_3" not in detail_models:
        detail_models.append("combined_weighted_3")
    references = {
        str(summary["model"]): float(summary["train_reference_rad"]) for summary in summaries
    }
    detail_output = output.with_name(f"{output.stem}_per_shot.csv")
    detail_rows = []
    for row in rows:
        detail = {
            key: row[key] for key in ("tm_sequence", "session_id", "profile", "club", "truth_deg")
        }
        for model in detail_models:
            feature = row["features"].get(model)
            detail[f"{model}_deg"] = (
                _estimate(float(feature[0]), references[model]) if feature is not None else None
            )
            detail[f"{model}_coherence"] = float(feature[1]) if feature is not None else None
        detail_rows.append(detail)
    with detail_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(detail_rows[0]))
        writer.writeheader()
        writer.writerows(detail_rows)
    print(f"Saved {detail_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
