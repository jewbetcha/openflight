"""Tests for the IWR6843 CLI and dump serial contract."""

from __future__ import annotations

import numpy as np
import pytest

from openflight.iwr6843.driver import IWR6843Radar
from openflight.iwr6843.dump import TEMP_REPORT_KEYS, pack_dump


def test_send_config_rejects_missing_cli_acknowledgement(tmp_path, monkeypatch):
    """A wedged board must not be reported as configured and armed."""
    config = tmp_path / "radar.cfg"
    config.write_text("sensorStart\n", encoding="utf-8")
    radar = IWR6843Radar.__new__(IWR6843Radar)
    monkeypatch.setattr(radar, "drain_stale_output", lambda: 0)
    monkeypatch.setattr(radar, "cmd", lambda *_args, **_kwargs: "")

    with pytest.raises(RuntimeError, match="did not acknowledge"):
        radar.send_config(str(config))


class FakeSerial:
    """Serial double that exposes the in_waiting/read/write pieces read_dump uses."""

    def __init__(self, payload: bytes):
        self.payload = bytearray(payload)
        self.writes = []

    @property
    def in_waiting(self):
        return len(self.payload)

    def reset_input_buffer(self):
        pass

    def write(self, data: bytes):
        self.writes.append(data)

    def read(self, nbytes: int):
        nbytes = min(nbytes, len(self.payload))
        chunk = self.payload[:nbytes]
        del self.payload[:nbytes]
        return bytes(chunk)


def test_read_dump_sizes_v5_header_extension():
    report = {key: index + 40 for index, key in enumerate(TEMP_REPORT_KEYS)}
    raw = pack_dump(
        np.zeros((2, 4, 4, 8), dtype=complex),
        n_tx=2,
        version=5,
        temperature_report=report,
    )
    serial = FakeSerial(b"cli echo\r\n" + raw + b"trailing cli noise")
    radar = IWR6843Radar.__new__(IWR6843Radar)
    radar.ser = serial

    dump = radar.read_dump(timeout_s=0.1)

    assert dump == raw
    assert serial.writes == [b"l3dump\n"]
