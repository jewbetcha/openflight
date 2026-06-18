"""Protocol-agnostic simulator-connector framework.

A *codec* owns one simulator's wire format; the shared transport, resolver, and
types are sim-neutral. Adding a simulator = one new codec + a registry entry in
``sim.codec``. See docs/simulator/ for the full pattern.
"""

from .codec import SimConnector, build_connector, build_connectors
from .config import ConnectorConfig, load_sim_config
from .resolver import resolve_shot
from .types import (
    ConnectionState,
    InboundEvent,
    IncompleteShotError,
    PlayerState,
    PlayerUpdate,
    ResolvedShot,
    ShotAck,
    SimError,
    StatusEvent,
)

__all__ = [
    "ConnectionState",
    "ConnectorConfig",
    "IncompleteShotError",
    "InboundEvent",
    "PlayerState",
    "PlayerUpdate",
    "ResolvedShot",
    "ShotAck",
    "SimConnector",
    "SimError",
    "StatusEvent",
    "build_connector",
    "build_connectors",
    "load_sim_config",
    "resolve_shot",
]
