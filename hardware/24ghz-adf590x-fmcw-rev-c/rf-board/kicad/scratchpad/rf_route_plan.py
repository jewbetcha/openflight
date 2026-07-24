"""Pure geometry for deterministic Rev C RF-board routes."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x_mm: float
    y_mm: float


@dataclass(frozen=True)
class PlannedRoute:
    net_name: str
    points: tuple[Point, ...]
    layer: str = "F.Cu"
    width_mm: float = 0.2


@dataclass(frozen=True)
class PlannedVia:
    net_name: str
    point: Point
    diameter_mm: float = 0.6
    drill_mm: float = 0.3


MITER_SETBACK_MM = 0.35


def polyline_length(points: list[Point]) -> float:
    return sum(
        math.hypot(end.x_mm - start.x_mm, end.y_mm - start.y_mm)
        for start, end in zip(points, points[1:])
    )


def _axis_unit(start: Point, end: Point) -> tuple[float, float]:
    delta_x = end.x_mm - start.x_mm
    delta_y = end.y_mm - start.y_mm
    if delta_x and delta_y:
        raise ValueError(f"raw route segment is not orthogonal: {start} -> {end}")
    if delta_x:
        return (math.copysign(1.0, delta_x), 0.0)
    if delta_y:
        return (0.0, math.copysign(1.0, delta_y))
    raise ValueError(f"raw route has a zero-length segment at {start}")


def miter_orthogonal_path(
    points: list[Point], setback_mm: float = MITER_SETBACK_MM
) -> list[Point]:
    """Replace orthogonal corners with fixed-setback 45-degree miters."""

    if len(points) < 2:
        raise ValueError("a route needs at least two points")
    result = [points[0]]
    for previous, corner, following in zip(points, points[1:], points[2:]):
        incoming = _axis_unit(previous, corner)
        outgoing = _axis_unit(corner, following)
        if incoming == outgoing:
            result.append(corner)
            continue
        if incoming == (-outgoing[0], -outgoing[1]):
            raise ValueError(f"route doubles back at {corner}")
        incoming_length = math.hypot(corner.x_mm - previous.x_mm, corner.y_mm - previous.y_mm)
        outgoing_length = math.hypot(following.x_mm - corner.x_mm, following.y_mm - corner.y_mm)
        if min(incoming_length, outgoing_length) <= setback_mm:
            raise ValueError(f"segments are too short to miter corner at {corner}")
        result.extend(
            (
                Point(
                    corner.x_mm - incoming[0] * setback_mm,
                    corner.y_mm - incoming[1] * setback_mm,
                ),
                Point(
                    corner.x_mm + outgoing[0] * setback_mm,
                    corner.y_mm + outgoing[1] * setback_mm,
                ),
            )
        )
    result.append(points[-1])
    return result


def _rx_raw_routes() -> dict[str, list[Point]]:
    # Each row is nested: the outside antenna reaches the outside RF input and
    # the inside antenna loops toward the inside input without a layer change.
    top_inner_x_mm = 8.611975
    bottom_outer_x_mm = 8.0
    bottom_inner_x_mm = 11.75
    return {
        "RX1": [
            Point(5.512, 5.547178),
            Point(5.512, 0.755),
            Point(32.0, 0.755),
            Point(32.0, 20.27),
            Point(32.75, 20.27),
        ],
        "RX2": [
            Point(18.012, 5.547178),
            Point(18.012, 5.0),
            Point(top_inner_x_mm, 5.0),
            Point(top_inner_x_mm, 2.7),
            Point(30.0, 2.7),
            Point(30.0, 20.27),
            Point(30.75, 20.27),
        ],
        "RX3": [
            Point(10.988, 44.452822),
            Point(10.988, 46.5),
            Point(bottom_outer_x_mm, 46.5),
            Point(bottom_outer_x_mm, 49.2),
            Point(32.0, 49.2),
            Point(32.0, 29.73),
            Point(32.75, 29.73),
        ],
        "RX4": [
            Point(23.488, 44.452822),
            Point(23.488, 47.7),
            Point(bottom_inner_x_mm, 47.7),
            Point(bottom_inner_x_mm, 45.0),
            Point(30.0, 45.0),
            Point(30.0, 29.73),
            Point(30.75, 29.73),
        ],
    }


def build_rx_feed_routes() -> dict[str, list[Point]]:
    return {name: miter_orthogonal_path(points) for name, points in _rx_raw_routes().items()}


def build_tx_feed_route() -> list[Point]:
    return miter_orthogonal_path(
        [
            Point(57.238, 18.702822),
            Point(59.5, 18.702822),
            Point(59.5, 24.25),
            Point(55.48, 24.25),
        ]
    )


def build_loop_filter_routes() -> tuple[PlannedRoute, ...]:
    """Return the routed form of the validated UG-866 Figure 12 loop filter."""

    return (
        PlannedRoute(
            "Net-(U4-CP)",
            (
                Point(46.75, 31.75),
                Point(46.75, 33.5),
                Point(46.99, 33.5),
                Point(46.99, 34.05),
                Point(48.6, 34.05),
                Point(49.25, 33.98),
                Point(49.8, 33.8),
                Point(50.0, 33.5),
                Point(50.0, 33.2),
                Point(51.3, 33.2),
                Point(52.0, 32.48),
            ),
        ),
        PlannedRoute(
            "Net-(C34-Pad2)",
            (Point(52.0, 31.52), Point(50.5, 31.49)),
        ),
        PlannedRoute(
            "Net-(C35-Pad1)",
            (Point(48.01, 33.5), Point(48.1, 32.3), Point(49.4, 32.2)),
        ),
        PlannedRoute(
            "Net-(C35-Pad1)",
            (Point(49.4, 32.2), Point(51.5, 30.4)),
            layer="B.Cu",
        ),
        PlannedRoute(
            "Net-(C35-Pad1)",
            (Point(51.5, 30.4), Point(50.5, 29.76), Point(52.5, 29.73)),
        ),
        PlannedRoute(
            "VTUNE",
            (
                Point(50.5, 28.74),
                Point(51.25, 28.74),
                Point(51.25, 28.45),
                Point(51.1, 28.2),
                Point(51.1, 25.9),
                Point(51.25, 25.65),
                Point(51.25, 25.25),
            ),
        ),
    )


def build_loop_filter_vias() -> tuple[PlannedVia, ...]:
    return (
        PlannedVia("Net-(C35-Pad1)", Point(49.4, 32.2)),
        PlannedVia("Net-(C35-Pad1)", Point(51.5, 30.4)),
    )
