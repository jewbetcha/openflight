"""Tests for offline K-LD7 session review helpers."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "analysis"))

import review_kld7_session
from kld7_session_review_lib import analyze_session, load_session
from review_kld7_session import ensure_output_dir

SESSION_PATH = Path(__file__).parent.parent / "session_logs" / "session_20260403_133805_range.jsonl"
NO_KLD7_SESSION_PATH = (
    Path(__file__).parent.parent / "session_logs" / "session_20260310_150412_range.jsonl"
)

requires_session_data = pytest.mark.skipif(
    not SESSION_PATH.exists(), reason="session log fixtures not present"
)
requires_no_kld7_session = pytest.mark.skipif(
    not NO_KLD7_SESSION_PATH.exists(), reason="session log fixtures not present"
)


@requires_session_data
def test_load_session_indexes_shots():
    """Session loader should index the expected shot records."""
    session_meta, shots = load_session(SESSION_PATH)

    assert session_meta["type"] == "session_start"
    assert session_meta["mode"] == "rolling-buffer"
    assert len(shots) == 10
    assert sorted(shots) == list(range(1, 11))
    assert "buffer" in shots[1]
    assert "capture" in shots[1]
    assert "shot" in shots[1]


@requires_session_data
def test_analyze_session_finds_recoverable_profiles():
    """The angle-offset range session should yield multiple strong profiles."""
    _, results = analyze_session(SESSION_PATH)
    quality_by_shot = {result.shot_number: result.quality for result in results}

    assert len(results) == 10
    assert sum(result.quality == "strong" for result in results) >= 4
    assert quality_by_shot[2] == "strong"
    assert quality_by_shot[8] == "weak"


@requires_no_kld7_session
def test_analyze_session_rejects_logs_without_kld7_buffers():
    """Session review should fail clearly when the session has no K-LD7 buffers."""
    with pytest.raises(ValueError, match="no kld7_buffer entries"):
        analyze_session(NO_KLD7_SESSION_PATH)


def test_load_session_rejects_missing_file(tmp_path):
    """Missing session files should fail with a clear path-specific error."""
    missing_path = tmp_path / "missing.jsonl"

    with pytest.raises(ValueError, match="Session file not found"):
        load_session(missing_path)


def test_load_session_reports_invalid_json_line(tmp_path):
    """Malformed JSONL should identify the failing line."""
    session_path = tmp_path / "broken.jsonl"
    session_path.write_text(
        '{"type":"session_start","mode":"rolling-buffer"}\n{"type":"shot_detected"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid JSON on line 2"):
        load_session(session_path)


def test_load_session_rejects_kld7_rows_without_shot_number(tmp_path):
    """Relevant session rows should not be silently discarded without shot numbers."""
    session_path = tmp_path / "missing_shot_number.jsonl"
    session_path.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_start", "mode": "rolling-buffer"}),
                json.dumps({"type": "kld7_buffer", "frames": []}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="line 2 is missing shot_number"):
        load_session(session_path)


def test_analyze_session_rejects_missing_frames(tmp_path):
    """Shot review should fail loudly when a K-LD7 buffer omits frames."""
    session_path = tmp_path / "missing_frames.jsonl"
    session_path.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_start", "mode": "rolling-buffer"}),
                json.dumps({"type": "kld7_buffer", "shot_number": 1}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="shot 1 is missing a usable kld7_buffer.frames list"):
        analyze_session(session_path)


def test_analyze_session_rejects_non_list_pdat(tmp_path):
    """Frame pdat payloads must be lists so malformed buffers do not misparse silently."""
    session_path = tmp_path / "bad_pdat.jsonl"
    session_path.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_start", "mode": "rolling-buffer"}),
                json.dumps(
                    {
                        "type": "kld7_buffer",
                        "shot_number": 1,
                        "frames": [
                            {"timestamp": 1.0, "pdat": {"distance": 1.0, "magnitude": 2500}}
                        ],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="shot 1 frame 0 has non-list pdat data"):
        analyze_session(session_path)


def test_analyze_session_rejects_non_numeric_frame_timestamp(tmp_path):
    """Frame timestamps must be numeric so path timing does not miscompute silently."""
    session_path = tmp_path / "bad_timestamp.jsonl"
    session_path.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_start", "mode": "rolling-buffer"}),
                json.dumps(
                    {
                        "type": "kld7_buffer",
                        "shot_number": 1,
                        "frames": [{"timestamp": "not-a-number", "pdat": []}],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="shot 1 frame 0 has non-numeric timestamp"):
        analyze_session(session_path)


def test_ensure_output_dir_requires_safe_clean_target(tmp_path):
    """Cleanup should be opt-in and reject unsafe directories."""
    unsafe_dir = tmp_path / "unsafe"
    unsafe_dir.mkdir()
    (unsafe_dir / "keep.txt").write_text("keep", encoding="utf-8")

    ensure_output_dir(unsafe_dir, clean=False)
    assert (unsafe_dir / "keep.txt").exists()

    with pytest.raises(ValueError, match="Refusing to clean unsafe output directory"):
        ensure_output_dir(unsafe_dir, clean=True)


def test_ensure_output_dir_cleans_safe_review_directory(tmp_path):
    """Cleanup should work for normal session review output directories."""
    safe_dir = tmp_path / "shots" / "session_review_example"
    safe_dir.mkdir(parents=True)
    stale_file = safe_dir / "stale.txt"
    stale_file.write_text("stale", encoding="utf-8")

    original_repo_root = review_kld7_session.REPO_ROOT
    review_kld7_session.REPO_ROOT = tmp_path
    try:
        ensure_output_dir(safe_dir, clean=True)
    finally:
        review_kld7_session.REPO_ROOT = original_repo_root

    assert not stale_file.exists()


def test_ensure_output_dir_rejects_lookalike_directory_outside_repo(tmp_path):
    """A shots/session_review_* directory outside the repo should still be rejected."""
    lookalike_dir = tmp_path / "shots" / "session_review_example"
    lookalike_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="Refusing to clean unsafe output directory"):
        ensure_output_dir(lookalike_dir, clean=True)


def test_ensure_output_dir_rejects_nested_directories_when_cleaning(tmp_path):
    """Unexpected nested directories should fail loudly instead of surviving cleanup."""
    safe_dir = tmp_path / "shots" / "session_review_example"
    nested_dir = safe_dir / "nested"
    nested_dir.mkdir(parents=True)

    original_repo_root = review_kld7_session.REPO_ROOT
    review_kld7_session.REPO_ROOT = tmp_path
    try:
        with pytest.raises(ValueError, match="contains nested paths"):
            ensure_output_dir(safe_dir, clean=True)
    finally:
        review_kld7_session.REPO_ROOT = original_repo_root


def test_session_output_dir_is_repo_relative():
    """Default output should land in the repo shots directory, not caller cwd."""
    session_path = Path("session_logs") / "session_20260403_133805_range.jsonl"

    output_dir = review_kld7_session.session_output_dir(session_path)

    assert output_dir == (
        review_kld7_session.REPO_ROOT / "shots" / "session_review_session_20260403_133805_range"
    )
