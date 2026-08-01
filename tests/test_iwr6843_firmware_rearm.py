"""Regression checks for the HWA snapshot ring freeze/rearm sequence."""

from __future__ import annotations

from pathlib import Path

FIRMWARE = Path(__file__).parents[1] / "firmware" / "iwr6843" / "l3_dump.c"
FIRMWARE_MAKEFILE = Path(__file__).parents[1] / "firmware" / "Makefile"
WINDOW53_12L18F_CONFIG = (
    Path(__file__).parents[1] / "config" / "iwr6843_l3dump_vTX2_window53_12l18f.cfg"
)


def _function_source(source: str, name: str, next_name: str) -> str:
    start = source.rindex(name)
    end = source.index(next_name, start)
    return source[start:end]


def test_hwa_dump_stops_at_boundary_before_streaming():
    source = FIRMWARE.read_text(encoding="utf-8")
    dump = _function_source(source, "int32_t l3_cli_dump", "static int32_t l3_cli_stats")

    stop = dump.index("l3_stopCaptureAtBoundary")
    stream = dump.index("UART_writePolling")

    assert stop < stream


def test_hwa_chain_processes_and_rearms_one_frame_at_a_time():
    source = FIRMWARE.read_text(encoding="utf-8")
    common = _function_source(source, "static int32_t l3_configHwaCommon", "static void l3_drain")
    output = _function_source(
        source,
        "static int32_t l3_configHwaOutputEdma",
        "static int32_t l3_configHwaSignatureEdma",
    )

    assert "commonCfg.numLoops = CHIRPS_PER_FRAME / 2U" in common
    assert "param->cCount = (uint16_t)(CHIRPS_PER_FRAME / 2U)" in output


def test_completed_frame_advances_circular_ring_slot():
    source = FIRMWARE.read_text(encoding="utf-8")
    callback = _function_source(
        source,
        "static void l3_hwaOutputDoneCB",
        "static int32_t l3_hwaStartRing",
    )

    assert "gRingFrame++" in callback
    assert "gRingFrame % RING_FRAMES" in callback


def test_freeze_request_keeps_rearming_until_post_trigger_target():
    source = FIRMWARE.read_text(encoding="utf-8")
    queue = _function_source(
        source, "static void l3_hwaMaybeQueueRearm", "static void l3_hwaChainDoneCB"
    )
    freeze = _function_source(
        source,
        "static int32_t l3_freezeHwaAfterPostFrames",
        "static int32_t l3_armHwaChain",
    )

    assert "gHwaFreezeRequested" in queue
    assert "gRingFrame >= gHwaFreezeTargetFrame" in queue
    assert "Semaphore_post(gHwaFreezeSemaphore)" in queue
    assert "gHwaFreezeTargetFrame = gRingFrame + HWA_POST_TRIGGER_FRAMES" in freeze


def test_sensor_stop_uses_completed_frame_boundary_before_teardown():
    source = FIRMWARE.read_text(encoding="utf-8")
    stop_helper = _function_source(
        source,
        "static int32_t l3_stopCaptureAtBoundary",
        "static int32_t l3_armHwaChain",
    )
    sensor_stop = _function_source(
        source,
        "static int32_t l3_cli_sensorStop",
        "static void l3_initTask",
    )

    freeze = stop_helper.index("l3_freezeHwaAfterPostFrames")
    rf_stop = stop_helper.index("MMWave_stop")
    hwa_disable = stop_helper.index("HWA_enable(gHwaHandle, 0U)")
    inactive = stop_helper.index("gCaptureActive = 0U")

    assert freeze < rf_stop < hwa_disable < inactive
    assert "if (MMWave_stop(gMMWaveHandle, &errCode) < 0)" in stop_helper
    assert "if (!gCaptureActive)" in sensor_stop
    assert "return l3_stopCaptureAtBoundary()" in sensor_stop


def test_dump_header_rotates_from_oldest_completed_frame():
    source = FIRMWARE.read_text(encoding="utf-8")
    dump = _function_source(source, "int32_t l3_cli_dump", "static int32_t l3_cli_stats")

    assert "gRingFrame % RING_FRAMES" in dump


def test_production_build_uses_balanced_geometry_and_single_release():
    source = FIRMWARE_MAKEFILE.read_text(encoding="utf-8")
    target = _function_source(source, "build-native:", "clean:")

    assert "--define=N_TX=3" in target
    assert "--define=LOOPS=12" in target
    assert "--define=RING_FRAMES=18" in target
    assert "--define=HWA_POST_TRIGGER_FRAMES=12" in target
    assert "--define=SNAPSHOT_DYNAMIC_WINDOWS=1" in target
    assert "--define=SNAPSHOT_BIN_START=20" in target
    assert "--define=SNAPSHOT_MIDDLE_BIN_START=32" in target
    assert "--define=SNAPSHOT_LATE_BIN_START=47" in target
    assert "--define=SNAPSHOT_BINS=53" in target
    assert (
        "RELEASE_NAME ?= "
        "l3_dump_vTX2_hwa_window53_12loops_18frames_4ms_temperature_report_20260731.bin"
        in source
    )
    assert '"$(RELEASE_DIR)/$(RELEASE_NAME)"' in target
    assert source.count("\nbuild-native:") == 1


def test_window53_12_loop_18_frame_config_matches_firmware_geometry():
    lines = {
        line.strip()
        for line in WINDOW53_12L18F_CONFIG.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("%")
    }

    assert "frameCfg 0 2 12 0 4 1 0" in lines
    assert "chirpCfg 0 0 0 0 0 0 0 1" in lines
    assert "chirpCfg 1 1 0 0 0 0 0 2" in lines
    assert "chirpCfg 2 2 0 0 0 0 0 4" in lines


def test_dynamic_window_start_is_recorded_per_ring_slot():
    source = FIRMWARE.read_text(encoding="utf-8")
    output = _function_source(
        source,
        "static int32_t l3_configHwaFrameOutput",
        "static void l3_drainHwaRearmSemaphore",
    )
    dump = _function_source(source, "int32_t l3_cli_dump", "static int32_t l3_cli_stats")

    assert "gFrameBinStart[ringSlot % RING_FRAMES]" in output
    assert "UART_writePolling(gDataUart, gFrameBinStart" in dump
