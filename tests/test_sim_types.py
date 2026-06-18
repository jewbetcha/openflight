"""Tests for sim.types — ConnectionState, PlayerState, inbound events."""
from openflight.launch_monitor import ClubType
from openflight.sim.types import (
    ConnectionState, PlayerState, PlayerUpdate,
)


def test_connection_state_values():
    assert ConnectionState.DISABLED.value == "disabled"
    assert ConnectionState.CONNECTING.value == "connecting"
    assert ConnectionState.CONNECTED.value == "connected"
    assert ConnectionState.RECONNECT_BACKOFF.value == "reconnecting"
    assert ConnectionState.STOPPED.value == "stopped"


def test_player_state_defaults():
    p = PlayerState()
    assert p.handed == "RH"
    assert p.club == ClubType.DRIVER
    assert p.shot_counter == 0


def test_next_shot_number_increments():
    p = PlayerState()
    assert p.next_shot_number() == 1
    assert p.next_shot_number() == 2
    assert p.shot_counter == 2


def test_apply_updates_handed_and_club():
    p = PlayerState()
    p.apply(PlayerUpdate(handed="LH", club=ClubType.IRON_7))
    assert p.handed == "LH"
    assert p.club == ClubType.IRON_7


def test_apply_ignores_none_fields():
    p = PlayerState(handed="LH", club=ClubType.IRON_7)
    p.apply(PlayerUpdate(handed=None, club=None))
    assert p.handed == "LH"
    assert p.club == ClubType.IRON_7


def test_apply_partial_update():
    p = PlayerState(handed="RH", club=ClubType.DRIVER)
    p.apply(PlayerUpdate(club=ClubType.PW))
    assert p.handed == "RH"
    assert p.club == ClubType.PW
