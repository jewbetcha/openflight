"""Tests for sim.codec — SimConnector wiring and the codec registry."""
import json
import time

import pytest

from openflight.gspro.codec import GSProCodec
from openflight.launch_monitor import ClubType
from openflight.sim.codec import build_connector, SimConnector
from openflight.sim.config import ConnectorConfig
from openflight.sim.types import ConnectionState, PlayerUpdate, ResolvedShot


def _resolved() -> ResolvedShot:
    return ResolvedShot(
        shot_number=3, ball_speed_mph=120.0, vla=14.0, hla=0.0,
        total_spin_rpm=3000.0, spin_axis_deg=0.0, back_spin_rpm=3000.0,
        side_spin_rpm=0.0, carry_yards=210.0, club_path_deg=0.0,
        club=ClubType.IRON_7, club_speed_mph=90.0, provenance={},
    )


def _wait(connector, state, deadline=3.0):
    end = time.time() + deadline
    while time.time() < end:
        if connector.state == state:
            return True
        time.sleep(0.05)
    return False


def test_connector_routes_status_with_target(mock_sim):
    statuses = []
    c = SimConnector(GSProCodec(), mock_sim.host, mock_sim.port,
                     on_status=lambda name, evt: statuses.append((name, evt)))
    c.start()
    try:
        assert _wait(c, ConnectionState.CONNECTED)
        assert statuses
        assert all(name == "gspro" for name, _ in statuses)
    finally:
        c.stop()


def test_connector_routes_inbound_with_target(mock_sim):
    inbound = []
    c = SimConnector(GSProCodec(), mock_sim.host, mock_sim.port,
                     on_inbound=lambda name, evt: inbound.append((name, evt)))
    mock_sim.queue_reply({"Code": 201, "Player": {"Club": "I7"}})
    c.start()
    try:
        deadline = time.time() + 1.5
        while time.time() < deadline and not inbound:
            time.sleep(0.05)
        assert inbound
        name, evt = inbound[0]
        assert name == "gspro"
        assert isinstance(evt, PlayerUpdate)
        assert evt.club is ClubType.IRON_7
    finally:
        c.stop()


def test_connector_send_shot_serializes(mock_sim):
    c = SimConnector(GSProCodec(), mock_sim.host, mock_sim.port)
    c.start()
    try:
        assert _wait(c, ConnectionState.CONNECTED)
        c.send_shot(_resolved())
        deadline = time.time() + 1.0
        while time.time() < deadline and not mock_sim.received:
            time.sleep(0.05)
        assert mock_sim.received
        assert json.loads(mock_sim.received[0])["ShotNumber"] == 3
    finally:
        c.stop()


def test_build_connector_gspro():
    c = build_connector(ConnectorConfig(
        type="gspro", host="127.0.0.1", port=921, device_id="Bay7", units="Yards"))
    assert isinstance(c, SimConnector)
    assert c.name == "gspro"
    assert c.codec.device_id == "Bay7"


def test_build_connector_opengolfsim_uses_shared_codec_named_ogs():
    from openflight.gspro.codec import GSProCodec

    c = build_connector(ConnectorConfig(type="opengolfsim", host="127.0.0.1", port=3111))
    # OpenGolfSim reuses the shared OpenConnect (GSPro) codec, named "opengolfsim".
    assert isinstance(c.codec, GSProCodec)
    assert c.name == "opengolfsim"


def test_build_connector_unknown_type_raises():
    with pytest.raises(ValueError):
        build_connector(ConnectorConfig(type="nope", port=1))
