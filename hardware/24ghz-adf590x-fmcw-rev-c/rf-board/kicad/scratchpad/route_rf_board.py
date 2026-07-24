from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pcbnew

from rf_route_plan import (
    Point,
    build_loop_filter_routes,
    build_loop_filter_vias,
    build_rx_feed_routes,
    build_tx_feed_route,
)

HERE = Path(__file__).resolve().parent
BOARD_PATH = HERE.parent / "openflight-24ghz-fmcw-rf-rev-c.kicad_pcb"


@dataclass(frozen=True)
class PadRef:
    reference: str
    number: str


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def footprints_by_reference(board: pcbnew.BOARD) -> dict[str, pcbnew.FOOTPRINT]:
    return {footprint.GetReference(): footprint for footprint in board.GetFootprints()}


def find_pad(footprints: dict[str, pcbnew.FOOTPRINT], pad_ref: PadRef) -> pcbnew.PAD:
    pads = [
        pad for pad in footprints[pad_ref.reference].Pads() if pad.GetNumber() == pad_ref.number
    ]
    if len(pads) != 1:
        raise RuntimeError(f"expected one pad for {pad_ref}, found {len(pads)}")
    return pads[0]


def add_track(
    board: pcbnew.BOARD,
    start: pcbnew.VECTOR2I,
    end: pcbnew.VECTOR2I,
    net: pcbnew.NETINFO_ITEM,
    width_mm: float,
    layer: int,
) -> None:
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(start)
    track.SetEnd(end)
    track.SetWidth(mm(width_mm))
    track.SetLayer(layer)
    track.SetNet(net)
    board.Add(track)


def add_polyline(
    board: pcbnew.BOARD,
    points: list[Point],
    net: pcbnew.NETINFO_ITEM,
    width_mm: float,
    layer: int = pcbnew.F_Cu,
) -> None:
    for start, end in zip(points, points[1:]):
        add_track(
            board,
            vector(start),
            vector(end),
            net,
            width_mm,
            layer,
        )


def vector(point: Point) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(point.x_mm), mm(point.y_mm))


def net_by_name(board: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    net = board.FindNet(name)
    if net is None:
        raise RuntimeError(f"board has no net named {name}")
    return net


def add_named_polyline(
    board: pcbnew.BOARD,
    net_name: str,
    points: list[Point],
    width_mm: float,
    layer: int = pcbnew.F_Cu,
) -> None:
    add_polyline(board, points, net_by_name(board, net_name), width_mm, layer)


def add_necked_straight(
    board: pcbnew.BOARD,
    net_name: str,
    pad: Point,
    transition: Point,
    pin: Point,
) -> None:
    net = net_by_name(board, net_name)
    add_track(board, vector(pad), vector(transition), net, 0.556, pcbnew.F_Cu)
    add_track(board, vector(transition), vector(pin), net, 0.2, pcbnew.F_Cu)


def add_zone(
    board: pcbnew.BOARD,
    net_name: str,
    layer: int,
    points: list[Point],
    *,
    clearance_mm: float,
    priority: int = 0,
) -> pcbnew.ZONE:
    zone = pcbnew.ZONE(board)
    zone.SetLayer(layer)
    zone.SetNet(net_by_name(board, net_name))
    zone.SetLocalClearance(mm(clearance_mm))
    zone.SetAssignedPriority(priority)
    zone.SetMinThickness(mm(0.15))
    zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    outline = zone.Outline()
    outline_index = outline.NewOutline()
    for point in points:
        outline.Append(vector(point), outline_index)
    board.Add(zone)
    return zone


def add_via(
    board: pcbnew.BOARD,
    net_name: str,
    point: Point,
    *,
    diameter_mm: float = 0.6,
    drill_mm: float = 0.3,
) -> None:
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(vector(point))
    via.SetWidth(mm(diameter_mm))
    via.SetDrill(mm(drill_mm))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetNet(net_by_name(board, net_name))
    board.Add(via)


def add_planned_routes(board: pcbnew.BOARD, filename: str) -> None:
    route_data = json.loads((HERE / filename).read_text())
    layers = {
        "F.Cu": pcbnew.F_Cu,
        "B.Cu": pcbnew.B_Cu,
        "In2.Cu": pcbnew.In2_Cu,
    }
    net_entries = route_data["nets"]
    if isinstance(net_entries, dict):
        entries = (
            {"net_name": net_name, **net_data}
            for net_name, net_data in net_entries.items()
        )
    else:
        entries = iter(net_entries)
    for net_data in entries:
        net_name = net_data["net_name"]
        for route in net_data["routes"]:
            for segment in route["segments"]:
                start = segment["start"]
                end = segment["end"]
                add_named_polyline(
                    board,
                    net_name,
                    [Point(*start), Point(*end)],
                    net_data.get("width", 0.127),
                    layers[segment["layer"]],
                )
            for x, y in route["vias"]:
                add_via(
                    board,
                    net_name,
                    Point(x, y),
                    diameter_mm=net_data["via_diameter"],
                    drill_mm=net_data["via_drill"],
                )


def add_pad_stitch(
    board: pcbnew.BOARD,
    footprints: dict[str, pcbnew.FOOTPRINT],
    pad_ref: PadRef,
    via_point: Point,
    *,
    width_mm: float = 0.3,
    diameter_mm: float = 0.6,
    drill_mm: float = 0.3,
) -> None:
    pad = find_pad(footprints, pad_ref)
    add_track(
        board,
        pad.GetPosition(),
        vector(via_point),
        pad.GetNet(),
        width_mm,
        pcbnew.F_Cu,
    )
    add_via(
        board,
        pad.GetNetname(),
        via_point,
        diameter_mm=diameter_mm,
        drill_mm=drill_mm,
    )


def add_ground_zones(board: pcbnew.BOARD) -> None:
    board_outline = [
        Point(0.3, 0.3),
        Point(81.7, 0.3),
        Point(81.7, 49.7),
        Point(0.3, 49.7),
    ]
    add_zone(board, "GND", pcbnew.In1_Cu, board_outline, clearance_mm=0.15)
    add_zone(board, "GND", pcbnew.B_Cu, board_outline, clearance_mm=0.2)
    front_ground = add_zone(
        board,
        "GND",
        pcbnew.F_Cu,
        [
            Point(27.0, 0.4),
            Point(48.0, 0.4),
            Point(48.0, 19.0),
            Point(61.5, 19.0),
            Point(61.5, 0.4),
            Point(69.6, 0.4),
            Point(69.6, 49.6),
            Point(27.0, 49.6),
        ],
        clearance_mm=0.2,
    )
    front_ground.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)


def main() -> int:
    board_path = Path(sys.argv[1]) if len(sys.argv) > 1 else BOARD_PATH
    board = pcbnew.LoadBoard(str(board_path))
    if list(board.GetTracks()):
        raise RuntimeError("route_rf_board.py requires a freshly generated board with no tracks")
    footprints = footprints_by_reference(board)

    for net_name, points in build_rx_feed_routes().items():
        add_polyline(board, points, net_by_name(board, net_name), 0.556)

    add_named_polyline(board, "TX_ANT", build_tx_feed_route(), 0.556)

    for net_name, pad, transition, pin in (
        (
            "Net-(U6-RX1_RF)",
            Point(32.75, 21.23),
            Point(32.75, 22.1),
            Point(32.75, 22.75),
        ),
        (
            "Net-(U6-RX2_RF)",
            Point(30.75, 21.23),
            Point(30.75, 22.1),
            Point(30.75, 22.75),
        ),
        (
            "Net-(U6-RX3_RF)",
            Point(32.75, 28.77),
            Point(32.75, 27.9),
            Point(32.75, 27.25),
        ),
        (
            "Net-(U6-RX4_RF)",
            Point(30.75, 28.77),
            Point(30.75, 27.9),
            Point(30.75, 27.25),
        ),
    ):
        add_necked_straight(board, net_name, pad, transition, pin)

    add_named_polyline(
        board,
        "Net-(U5-TXOUT1)",
        [
            Point(54.52, 24.25),
            Point(54.0, 24.25),
        ],
        0.556,
    )
    add_named_polyline(
        board,
        "Net-(U5-TXOUT1)",
        [
            Point(54.0, 24.25),
            Point(53.25, 24.25),
        ],
        0.2,
    )
    add_named_polyline(
        board,
        "Net-(U5-TXOUT2)",
        [Point(54.52, 21.75), Point(54.0, 21.75)],
        0.556,
    )
    add_named_polyline(
        board,
        "Net-(U5-TXOUT2)",
        [Point(54.0, 21.75), Point(53.25, 21.75)],
        0.2,
    )
    add_necked_straight(
        board,
        "Net-(U5-LOOUT)",
        Point(51.75, 19.73),
        Point(51.75, 20.25),
        Point(51.75, 20.75),
    )

    add_named_polyline(
        board,
        "LO_OUT",
        [
            Point(51.75, 18.77),
            Point(51.75, 16.0),
            Point(43.0, 16.0),
            Point(43.0, 24.0),
            Point(42.48, 24.0),
        ],
        0.556,
    )
    add_named_polyline(
        board,
        "Net-(U6-LO_IN)",
        [Point(41.52, 24.0), Point(41.52, 24.6), Point(34.4, 24.6)],
        0.556,
    )
    add_named_polyline(
        board,
        "Net-(U6-LO_IN)",
        [Point(34.4, 24.6), Point(34.25, 24.75), Point(33.75, 24.75)],
        0.2,
    )

    add_named_polyline(
        board,
        "RFIN_DIV",
        [Point(48.75, 26.92), Point(49.23, 28.25)],
        0.556,
    )
    add_named_polyline(
        board,
        "Net-(C53-Pad2)",
        [
            Point(48.75, 26.28),
            Point(49.0, 26.1),
            Point(50.0, 26.1),
            Point(50.25, 25.85),
            Point(50.25, 25.25),
        ],
        0.127,
    )
    add_named_polyline(
        board,
        "Net-(U4-RFinA)",
        [
            Point(48.27, 28.25),
            Point(48.5, 28.25),
            Point(48.5, 29.25),
            Point(47.25, 29.25),
        ],
        0.2,
    )
    add_named_polyline(
        board,
        "Net-(U4-RFinB)",
        [
            Point(48.52, 30.25),
            Point(48.25, 30.25),
            Point(47.75, 29.75),
            Point(47.25, 29.75),
        ],
        0.2,
    )

    add_named_polyline(
        board,
        "Net-(U5-VREG)",
        [Point(47.48, 21.75), Point(48.75, 21.75)],
        0.2,
    )
    add_named_polyline(
        board,
        "Net-(C55-Pad1)",
        [
            Point(50.25, 26.82),
            Point(50.75, 26.32),
            Point(50.75, 25.25),
        ],
        0.127,
    )
    add_named_polyline(
        board,
        "Net-(U5-C1)",
        [
            Point(53.0, 26.52),
            Point(53.0, 26.1),
            Point(52.25, 25.6),
            Point(52.25, 25.25),
        ],
        0.127,
    )
    add_named_polyline(
        board,
        "Net-(U5-C2)",
        [
            Point(54.5, 26.52),
            Point(53.75, 25.8),
            Point(53.25, 25.6),
            Point(52.75, 25.6),
            Point(52.75, 25.25),
        ],
        0.127,
    )

    baseband_internal_routes = {
        "Net-(U6-RX1_O)": [
            Point(33.75, 23.25),
            Point(34.0, 23.25),
            Point(35.24, 22.01),
            Point(35.24, 22.0),
        ],
        "Net-(U6-RX1_OB)": [
            Point(33.75, 23.75),
            Point(34.99, 23.75),
            Point(35.24, 23.5),
        ],
        "Net-(U6-RX2_O)": [
            Point(29.75, 22.75),
            Point(29.25, 22.75),
            Point(28.01, 21.51),
            Point(28.01, 21.0),
        ],
        "Net-(U6-RX2_OB)": [
            Point(29.25, 23.25),
            Point(28.76, 23.25),
            Point(28.01, 22.5),
        ],
        "Net-(U6-RX3_O)": [
            Point(33.75, 26.75),
            Point(34.0, 26.75),
            Point(35.24, 27.99),
            Point(35.24, 28.5),
        ],
        "Net-(U6-RX3_OB)": [
            Point(33.75, 26.25),
            Point(34.49, 26.25),
            Point(35.24, 27.0),
        ],
        "Net-(U6-RX4_O)": [
            Point(29.75, 27.25),
            Point(29.25, 27.25),
            Point(28.01, 28.49),
            Point(28.01, 29.0),
        ],
        "Net-(U6-RX4_OB)": [
            Point(29.25, 26.75),
            Point(28.76, 26.75),
            Point(28.01, 27.5),
        ],
    }
    for net_name, points in baseband_internal_routes.items():
        add_named_polyline(board, net_name, points, 0.127)

    baseband_front_routes = {
        "BB1_P": [
            Point(36.26, 22.0),
            Point(36.75, 22.0),
            Point(37.25, 21.5),
            Point(37.25, 21.48),
            Point(38.2, 21.48),
        ],
        "BB1_N": [
            Point(36.26, 23.5),
            Point(37.25, 23.5),
            Point(37.25, 23.48),
            Point(38.2, 23.48),
        ],
        "BB3_P": [
            Point(36.26, 28.5),
            Point(37.25, 28.5),
            Point(37.25, 28.52),
            Point(38.2, 28.52),
        ],
        "BB3_N": [
            Point(36.26, 27.0),
            Point(37.25, 27.0),
            Point(37.25, 26.98),
            Point(38.2, 26.98),
        ],
        "BB2_P": [Point(26.99, 21.0), Point(26.0, 21.0)],
        "BB2_N": [Point(26.99, 22.5), Point(26.0, 22.5)],
        "BB4_P": [
            Point(26.99, 29.0),
            Point(27.2, 29.0),
            Point(27.2, 30.2),
        ],
        "BB4_N": [
            Point(26.99, 27.5),
            Point(27.2, 27.5),
            Point(27.2, 26.3),
        ],
    }
    baseband_branch_routes = {
        "BB2_P": [Point(39.25, 20.52), Point(40.2, 20.52)],
        "BB2_N": [Point(39.25, 22.52), Point(40.2, 22.52)],
        "BB4_P": [Point(34.5, 34.02), Point(33.5, 34.02)],
        "BB4_N": [Point(39.25, 27.52), Point(40.2, 27.52)],
    }
    for routes in (baseband_front_routes, baseband_branch_routes):
        for net_name, points in routes.items():
            add_named_polyline(board, net_name, points, 0.127)

    baseband_source_vias = {
        "BB1_P": Point(38.2, 21.48),
        "BB1_N": Point(38.2, 23.48),
        "BB2_P": Point(26.0, 21.0),
        "BB2_N": Point(26.0, 22.5),
        "BB3_P": Point(38.2, 28.52),
        "BB3_N": Point(38.2, 26.98),
        "BB4_P": Point(27.2, 30.2),
        "BB4_N": Point(27.2, 26.3),
    }
    baseband_branch_vias = {
        "BB2_P": Point(40.2, 20.52),
        "BB2_N": Point(40.2, 22.52),
        "BB4_P": Point(33.5, 34.02),
        "BB4_N": Point(40.2, 27.52),
    }
    for vias in (baseband_source_vias, baseband_branch_vias):
        for net_name, point in vias.items():
            add_via(board, net_name, point, diameter_mm=0.6, drill_mm=0.3)

    baseband_layer_routes = {
        "BB1_P": (
            pcbnew.B_Cu,
            [
                Point(38.2, 21.48),
                Point(35.9, 22.82),
                Point(35.9, 46.8),
                Point(36.65, 46.8),
            ],
        ),
        "BB1_N": (
            pcbnew.In2_Cu,
            [
                Point(38.2, 23.48),
                Point(36.7, 24.02),
                Point(36.7, 45.8),
                Point(37.2, 45.8),
                Point(37.2, 42.8),
                Point(36.65, 42.8),
            ],
        ),
        "BB2_P": (
            pcbnew.B_Cu,
            [
                Point(26.0, 21.0),
                Point(28.0, 19.0),
                Point(39.2, 19.0),
                Point(40.2, 20.0),
                Point(40.2, 20.52),
                Point(37.7, 23.02),
                Point(37.7, 46.8),
                Point(39.19, 46.8),
            ],
        ),
        "BB2_N": (
            pcbnew.B_Cu,
            [
                Point(26.0, 22.5),
                Point(24.5, 24.0),
                Point(24.5, 31.5),
                Point(22.5, 32.0),
                Point(22.5, 49.0),
                Point(40.0, 49.0),
                Point(40.0, 42.8),
                Point(39.19, 42.8),
            ],
        ),
        "BB3_P": (
            pcbnew.In2_Cu,
            [
                Point(38.2, 28.52),
                Point(41.1, 31.42),
                Point(41.1, 46.8),
                Point(41.73, 46.8),
            ],
        ),
        "BB3_N": (
            pcbnew.In2_Cu,
            [
                Point(38.2, 26.98),
                Point(40.7, 29.48),
                Point(42.1, 29.48),
                Point(42.1, 31.0),
                Point(41.9, 31.2),
                Point(41.9, 45.8),
                Point(42.4, 45.8),
                Point(42.4, 42.8),
                Point(41.73, 42.8),
            ],
        ),
        "BB4_P": (
            pcbnew.In2_Cu,
            [
                Point(27.2, 30.2),
                Point(24.5, 32.9),
                Point(24.5, 48.5),
                Point(44.27, 48.5),
                Point(44.27, 46.8),
            ],
        ),
        "BB4_N": (
            pcbnew.In2_Cu,
            [
                Point(27.2, 26.3),
                Point(27.2, 18.5),
                Point(48.4, 18.5),
                Point(48.4, 47.5),
                Point(44.95, 47.5),
                Point(44.95, 42.8),
                Point(44.27, 42.8),
            ],
        ),
    }
    baseband_connector_vias = {
        "BB1_P": Point(36.65, 46.8),
        "BB1_N": Point(36.65, 42.8),
        "BB2_P": Point(39.19, 46.8),
        "BB2_N": Point(39.19, 42.8),
        "BB3_P": Point(41.73, 46.8),
        "BB3_N": Point(41.73, 42.8),
        "BB4_P": Point(44.27, 46.8),
        "BB4_N": Point(44.27, 42.8),
    }
    connector_pads = {
        "BB1_P": Point(36.65, 47.95),
        "BB1_N": Point(36.65, 44.05),
        "BB2_P": Point(39.19, 47.95),
        "BB2_N": Point(39.19, 44.05),
        "BB3_P": Point(41.73, 47.95),
        "BB3_N": Point(41.73, 44.05),
        "BB4_P": Point(44.27, 47.95),
        "BB4_N": Point(44.27, 44.05),
    }
    for net_name, (layer, points) in baseband_layer_routes.items():
        add_named_polyline(board, net_name, points, 0.127, layer)
        via_point = baseband_connector_vias[net_name]
        add_via(board, net_name, via_point, diameter_mm=0.6, drill_mm=0.3)
        add_named_polyline(board, net_name, [via_point, connector_pads[net_name]], 0.127)

    add_named_polyline(
        board,
        "BB2_N",
        [
            Point(40.2, 22.52),
            Point(40.8, 22.52),
            Point(40.8, 42.8),
            Point(40.0, 42.8),
        ],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "BB4_P",
        [
            Point(33.5, 34.02),
            Point(24.5, 34.02),
            Point(24.5, 48.5),
        ],
        0.127,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "BB4_N",
        [
            Point(40.2, 27.52),
            Point(48.4, 27.52),
        ],
        0.127,
        pcbnew.In2_Cu,
    )

    layers = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    for route in build_loop_filter_routes():
        add_named_polyline(
            board,
            route.net_name,
            list(route.points),
            route.width_mm,
            layers[route.layer],
        )
    for via in build_loop_filter_vias():
        add_via(
            board,
            via.net_name,
            via.point,
            diameter_mm=via.diameter_mm,
            drill_mm=via.drill_mm,
        )

    add_named_polyline(
        board,
        "Net-(X1-OUT)",
        [
            Point(56.9, 36.22),
            Point(57.27, 36.22),
            Point(57.55, 36.5),
            Point(58.99, 36.5),
        ],
        0.2,
    )
    add_named_polyline(
        board,
        "Net-(C30-Pad2)",
        [Point(60.01, 36.5), Point(61.02, 36.5)],
        0.2,
    )

    refin_vias = (
        Point(62.7, 36.5),
        Point(49.75, 17.5),
        Point(44.5, 26.75),
    )
    add_named_polyline(board, "REFIN", [Point(61.98, 36.5), refin_vias[0]], 0.2)
    add_named_polyline(
        board,
        "REFIN",
        [
            refin_vias[0],
            Point(62.7, 10.0),
            Point(49.75, 10.0),
            refin_vias[1],
        ],
        0.2,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "REFIN",
        [Point(62.7, 26.75), refin_vias[2]],
        0.2,
        pcbnew.B_Cu,
    )
    for point in refin_vias:
        add_via(board, "REFIN", point)
    add_named_polyline(
        board,
        "REFIN",
        [refin_vias[1], Point(49.75, 20.75)],
        0.127,
    )

    add_named_polyline(
        board,
        "REFIN",
        [
            refin_vias[2],
            Point(44.8, 27.05),
            Point(45.75, 28.0),
            Point(45.75, 28.25),
        ],
        0.127,
    )

    add_zone(
        board,
        "+3V3_RX",
        pcbnew.In2_Cu,
        [Point(27.0, 5.0), Point(69.5, 5.0), Point(69.5, 44.0), Point(27.0, 44.0)],
        clearance_mm=0.15,
    )
    rx_power_stitches = {
        PadRef("C83", "2"): Point(29.0, 16.7),
        PadRef("C84", "2"): Point(31.0, 16.7),
        PadRef("C85", "2"): Point(33.0, 16.7),
        PadRef("C86", "2"): Point(29.0, 30.7),
        PadRef("C87", "2"): Point(31.0, 30.7),
        PadRef("C88", "2"): Point(33.0, 30.7),
        PadRef("C90", "2"): Point(38.5, 33.02),
        PadRef("C38", "2"): Point(38.5, 25.7),
        PadRef("C39", "2"): Point(43.25, 26.5),
        PadRef("C40", "2"): Point(39.9, 29.45),
        PadRef("C41", "2"): Point(38.5, 30.2),
        PadRef("C42", "2"): Point(43.0, 32.52),
        PadRef("C47", "2"): Point(42.48, 41.8),
        PadRef("C5", "1"): Point(59.0, 31.1),
        PadRef("C31", "1"): Point(58.5, 43.7),
        PadRef("C32", "1"): Point(59.0, 34.8),
        PadRef("C59", "2"): Point(57.0, 38.7),
        PadRef("R2", "1"): Point(68.5, 33.3),
        PadRef("TP3", "1"): Point(64.0, 13.0),
        PadRef("U2", "1"): Point(60.7, 30.095),
        PadRef("U2", "2"): Point(60.5, 31.365),
        PadRef("U4", "22"): Point(45.75, 33.0),
        PadRef("U4", "8"): Point(46.8, 25.5),
        PadRef("U6", "4"): Point(31.75, 22.0),
        PadRef("U6", "21"): Point(31.75, 28.0),
        PadRef("U7", "1"): Point(43.725, 41.8),
        PadRef("U8", "7"): Point(56.0, 39.8),
        PadRef("X1", "1"): Point(54.1, 31.9),
        PadRef("X1", "4"): Point(56.9, 31.9),
    }
    for pad_ref, via_point in rx_power_stitches.items():
        add_pad_stitch(board, footprints, pad_ref, via_point)

    add_pad_stitch(
        board,
        footprints,
        PadRef("C89", "2"),
        Point(35.02, 25.9),
        width_mm=0.127,
    )

    for points in (
        [Point(39.02, 25.5), Point(38.5, 25.7)],
        [Point(33.75, 25.75), Point(34.2, 25.9), Point(35.02, 25.5)],
        [Point(47.25, 28.75), Point(47.0, 28.0), Point(46.8, 27.8), Point(46.8, 25.5)],
        [Point(46.75, 28.25), Point(46.8, 27.8)],
        [Point(46.25, 28.25), Point(46.4, 27.8), Point(46.8, 27.8)],
        [Point(42.48, 41.8), Point(43.725, 41.8)],
        [Point(44.375, 40.8625), Point(44.375, 41.4), Point(43.725, 41.4)],
        [Point(45.025, 40.8625), Point(45.025, 41.4), Point(43.725, 41.4)],
    ):
        add_named_polyline(board, "+3V3_RX", points, 0.2)

    add_zone(
        board,
        "+3V3_TX",
        pcbnew.B_Cu,
        [Point(43.5, 5.0), Point(69.5, 5.0), Point(69.5, 30.5), Point(43.5, 30.5)],
        clearance_mm=0.15,
        priority=1,
    )
    tx_power_stitches = {
        PadRef("C15", "1"): Point(58.5, 21.7),
        PadRef("C16", "1"): Point(57.0, 21.7),
        PadRef("C17", "1"): Point(54.5, 20.0),
        PadRef("C18", "1"): Point(46.8, 20.0),
        PadRef("C19", "1"): Point(49.0, 20.0),
        PadRef("C20", "1"): Point(50.5, 20.0),
        PadRef("C22", "1"): Point(45.3, 24.98),
        PadRef("C23", "1"): Point(45.3, 22.98),
        PadRef("C24", "1"): Point(45.3, 20.98),
        PadRef("C27", "1"): Point(58.5, 27.55),
        PadRef("C28", "1"): Point(56.5, 27.55),
        PadRef("C29", "1"): Point(54.5, 30.3),
        PadRef("C3", "1"): Point(60.5, 21.2),
        PadRef("R1", "1"): Point(68.5, 25.3),
        PadRef("TP2", "1"): Point(64.0, 10.0),
        PadRef("U1", "1"): Point(60.6, 22.095),
        PadRef("U1", "2"): Point(60.6, 23.365),
        PadRef("U5", "30"): Point(51.75, 25.9),
    }
    for pad_ref, via_point in tx_power_stitches.items():
        add_pad_stitch(board, footprints, pad_ref, via_point)

    add_via(board, "+3V3_TX", Point(54.1, 23.0))
    for points in (
        [Point(50.25, 20.75), Point(50.5, 20.0)],
        [Point(49.25, 20.75), Point(49.0, 20.0)],
        [Point(48.75, 21.25), Point(48.3, 20.8), Point(46.8, 20.0)],
        [Point(53.25, 23.25), Point(54.1, 23.0)],
        [Point(53.25, 22.75), Point(54.1, 23.0)],
    ):
        add_named_polyline(board, "+3V3_TX", points, 0.2)

    add_zone(
        board,
        "+1V8_DIG",
        pcbnew.B_Cu,
        [Point(38.0, 31.0), Point(69.5, 31.0), Point(69.5, 44.5), Point(38.0, 44.5)],
        clearance_mm=0.15,
        priority=1,
    )
    digital_power_stitches = {
        PadRef("C43", "2"): Point(40.2, 32.2),
        PadRef("C44", "2"): Point(39.5, 32.52),
        PadRef("C45", "2"): Point(38.7, 35.0),
        PadRef("C46", "2"): Point(39.48, 37.8),
        PadRef("C48", "2"): Point(43.3, 36.0),
        PadRef("C49", "2"): Point(52.0, 38.7),
        PadRef("C7", "1"): Point(65.8, 41.7),
        PadRef("U4", "18"): Point(43.75, 32.2),
    }
    for pad_ref, via_point in digital_power_stitches.items():
        add_pad_stitch(board, footprints, pad_ref, via_point)

    add_named_polyline(
        board,
        "+1V8_DIG",
        [Point(43.725, 35.1375), Point(43.725, 35.5), Point(43.3, 36.0)],
        0.2,
    )

    add_pad_stitch(
        board,
        footprints,
        PadRef("U8", "6"),
        Point(56.0, 40.8),
        width_mm=0.127,
    )

    add_named_polyline(
        board,
        "+1V8_DIG",
        [Point(44.25, 31.75), Point(44.25, 32.2), Point(43.75, 32.2)],
        0.2,
    )
    digital_test_vias = (Point(64.0, 16.0), Point(64.0, 38.0))
    add_named_polyline(board, "+1V8_DIG", [Point(64.0, 15.0), digital_test_vias[0]], 0.3)
    add_named_polyline(
        board,
        "+1V8_DIG",
        [digital_test_vias[0], digital_test_vias[1]],
        0.3,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "+1V8_DIG",
        [digital_test_vias[1], Point(64.5, 38.5), Point(65.1375, 39.05)],
        0.3,
    )
    for point in digital_test_vias:
        add_via(board, "+1V8_DIG", point)

    add_named_polyline(
        board,
        "+1V8_DIG",
        [
            Point(38.7, 35.0),
            Point(38.0, 35.0),
            Point(38.0, 47.5),
            Point(43.1, 47.5),
            Point(43.1, 40.5),
            Point(43.2, 40.1),
            Point(43.2, 36.5),
            Point(43.3, 36.0),
        ],
        0.2,
        pcbnew.In2_Cu,
    )

    regulated_power_stitches = {
        PadRef("FB1", "2"): Point(56.0, 45.2125),
        PadRef("D1", "1"): Point(59.0, 47.7),
        PadRef("C1", "1"): Point(62.0, 47.7),
        PadRef("C2", "1"): Point(68.5, 21.7),
        PadRef("C4", "1"): Point(68.5, 29.6),
        PadRef("C6", "1"): Point(60.5, 40.775),
        PadRef("U1", "5"): Point(67.3, 25.905),
        PadRef("U1", "8"): Point(67.3, 22.095),
        PadRef("U2", "5"): Point(67.3, 33.905),
        PadRef("U2", "8"): Point(67.3, 30.095),
        PadRef("U3", "1"): Point(61.8, 38.3),
        PadRef("U3", "3"): Point(61.8, 40.95),
    }
    for pad_ref, via_point in regulated_power_stitches.items():
        add_pad_stitch(board, footprints, pad_ref, via_point, width_mm=0.4)

    add_named_polyline(
        board,
        "+5V_REG",
        [
            Point(56.0, 45.2125),
            Point(60.0, 45.2125),
            Point(60.0, 42.5),
            Point(67.3, 42.5),
            Point(67.3, 21.7),
            Point(68.5, 21.7),
        ],
        0.5,
        pcbnew.In2_Cu,
    )
    for points in (
        [Point(59.0, 47.7), Point(59.0, 45.2125)],
        [Point(62.0, 47.7), Point(62.0, 45.2125), Point(60.0, 45.2125)],
        [Point(60.5, 40.775), Point(60.5, 42.5)],
        [Point(61.8, 38.3), Point(61.8, 42.5)],
        [Point(61.8, 40.95), Point(61.8, 42.5)],
        [Point(67.3, 25.905), Point(67.3, 22.095)],
        [Point(67.3, 33.905), Point(67.3, 30.095)],
        [Point(68.5, 29.6), Point(67.3, 29.6)],
    ):
        add_named_polyline(board, "+5V_REG", points, 0.5, pcbnew.In2_Cu)

    add_named_polyline(
        board,
        "+5V",
        [
            Point(34.11, 44.05),
            Point(33.2, 44.05),
            Point(33.2, 47.8),
        ],
        0.4,
    )
    add_named_polyline(
        board,
        "+5V",
        [Point(34.11, 47.95), Point(33.2, 47.8)],
        0.4,
    )
    raw_power_vias = (Point(64.0, 7.0), Point(54.0, 46.12))
    add_named_polyline(board, "+5V", [Point(64.0, 6.0), raw_power_vias[0]], 0.4)
    add_named_polyline(
        board,
        "+5V",
        [
            raw_power_vias[0],
            Point(70.5, 7.0),
            Point(70.5, 44.5),
            Point(54.0, 44.5),
            raw_power_vias[1],
        ],
        0.4,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "+5V",
        [
            Point(33.2, 47.8),
            Point(33.2, 46.12),
            Point(53.5, 46.12),
            raw_power_vias[1],
        ],
        0.4,
    )
    add_named_polyline(
        board,
        "+5V",
        [raw_power_vias[1], Point(54.2, 46.8), Point(55.0, 46.7875)],
        0.4,
    )
    for point in raw_power_vias:
        add_via(board, "+5V", point)

    le_4159_vias = (Point(47.421, 42.1219), Point(50.62, 46.8))
    add_named_polyline(
        board,
        "LE_4159",
        [Point(46.975, 40.8625), Point(46.975, 41.6759), le_4159_vias[0]],
        0.2,
    )
    add_named_polyline(
        board,
        "LE_4159",
        [le_4159_vias[0], Point(49.0, 43.7), Point(50.62, 45.32), le_4159_vias[1]],
        0.2,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "LE_4159",
        [le_4159_vias[1], Point(50.62, 47.95)],
        0.2,
    )
    for point in le_4159_vias:
        add_via(board, "LE_4159", point)

    u4_rset_vias = (Point(44.8, 33.7), Point(49.142, 35.2155))
    add_named_polyline(
        board,
        "Net-(U4-RSET)",
        [
            Point(46.25, 31.75),
            Point(46.35, 32.0),
            Point(46.35, 33.45),
            u4_rset_vias[0],
        ],
        0.127,
    )
    add_named_polyline(
        board,
        "Net-(U4-RSET)",
        [
            u4_rset_vias[0],
            Point(44.8, 40.5),
            Point(49.142, 40.5),
            u4_rset_vias[1],
        ],
        0.2,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "Net-(U4-RSET)",
        [u4_rset_vias[1], Point(49.3475, 35.01), Point(51.5, 35.01)],
        0.2,
    )
    for point in u4_rset_vias:
        add_via(board, "Net-(U4-RSET)", point)

    add_named_polyline(
        board,
        "Net-(U5-RSET)",
        [
            Point(49.75, 25.25),
            Point(49.75, 25.75),
            Point(48.0, 25.75),
            Point(47.5, 25.25),
            Point(46.0, 24.51),
        ],
        0.127,
    )

    u4_clk_vias = (Point(42.4, 29.0), Point(45.675, 34.4))
    add_named_polyline(
        board,
        "Net-(U4-CLK)",
        [Point(43.75, 29.25), Point(43.25, 29.25), u4_clk_vias[0]],
        0.127,
    )
    add_named_polyline(
        board,
        "Net-(U4-CLK)",
        [u4_clk_vias[0], Point(42.4, 29.0), Point(42.4, 34.4), u4_clk_vias[1]],
        0.127,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "Net-(U4-CLK)",
        [u4_clk_vias[1], Point(45.675, 35.1375)],
        0.127,
    )
    for point in u4_clk_vias:
        add_via(board, "Net-(U4-CLK)", point)

    u4_data_vias = (Point(43.1, 29.75), Point(44.0, 36.7), Point(46.4, 34.0))
    add_named_polyline(
        board,
        "Net-(U4-DATA)",
        [Point(43.75, 29.75), u4_data_vias[0]],
        0.127,
    )
    add_named_polyline(
        board,
        "Net-(U4-DATA)",
        [
            u4_data_vias[0],
            Point(42.0, 30.4),
            Point(42.0, 36.7),
            u4_data_vias[1],
        ],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "Net-(U4-DATA)",
        [u4_data_vias[1], Point(46.4, 36.7), u4_data_vias[2]],
        0.127,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "Net-(U4-DATA)",
        [u4_data_vias[2], Point(46.325, 35.1375)],
        0.127,
    )
    for point in u4_data_vias:
        add_via(board, "Net-(U4-DATA)", point)

    u4_le_vias = (
        Point(41.5, 30.25),
        Point(42.6, 37.3),
        Point(42.6, 39.5),
        Point(44.0, 39.5),
        Point(46.975, 36.2),
    )
    add_named_polyline(
        board,
        "Net-(U4-LE)",
        [Point(43.75, 30.25), u4_le_vias[0]],
        0.127,
    )
    add_named_polyline(
        board,
        "Net-(U4-LE)",
        [
            u4_le_vias[0],
            Point(41.5, 37.3),
            u4_le_vias[1],
        ],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "Net-(U4-LE)",
        [u4_le_vias[1], u4_le_vias[2]],
        0.127,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "Net-(U4-LE)",
        [u4_le_vias[2], u4_le_vias[3]],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "Net-(U4-LE)",
        [u4_le_vias[3], Point(46.975, 39.5), u4_le_vias[4]],
        0.127,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "Net-(U4-LE)",
        [u4_le_vias[4], Point(46.975, 35.1375)],
        0.127,
    )
    for point in u4_le_vias:
        add_via(board, "Net-(U4-LE)", point)

    u4_ce_vias = (Point(43.2, 28.2), Point(47.8, 37.2))
    add_named_polyline(
        board,
        "Net-(U4-CE)",
        [Point(43.75, 28.75), Point(43.5, 28.75), u4_ce_vias[0]],
        0.127,
    )
    add_named_polyline(
        board,
        "Net-(U4-CE)",
        [u4_ce_vias[0], Point(47.9, 28.2), Point(47.9, 37.0), u4_ce_vias[1]],
        0.127,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "Net-(U4-CE)",
        [u4_ce_vias[1], Point(47.625, 35.1375)],
        0.127,
    )
    for point in u4_ce_vias:
        add_via(board, "Net-(U4-CE)", point)

    u4_muxout_vias = (Point(43.2, 30.75), Point(57.0, 41.5))
    add_named_polyline(
        board,
        "Net-(U4-MUXOUT)",
        [Point(43.75, 30.75), u4_muxout_vias[0]],
        0.127,
    )
    add_named_polyline(
        board,
        "Net-(U4-MUXOUT)",
        [
            u4_muxout_vias[0],
            Point(43.8, 30.75),
            Point(43.8, 28.5),
            Point(57.7, 28.5),
            Point(57.7, 41.5),
            u4_muxout_vias[1],
        ],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "Net-(U4-MUXOUT)",
        [u4_muxout_vias[1], Point(54.9, 41.5), Point(54.9, 40.85)],
        0.127,
    )
    for point in u4_muxout_vias:
        add_via(board, "Net-(U4-MUXOUT)", point)

    ramp_sync_vias = (Point(58.5, 37.7), Point(52.7633, 44.05))
    add_named_polyline(
        board,
        "RAMP_SYNC",
        [
            Point(54.9, 39.15),
            Point(54.9, 38.3),
            Point(55.5, 37.7),
            ramp_sync_vias[0],
        ],
        0.127,
    )
    add_named_polyline(
        board,
        "RAMP_SYNC",
        [
            ramp_sync_vias[0],
            Point(58.5, 43.0),
            Point(52.7633, 43.0),
            ramp_sync_vias[1],
        ],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "RAMP_SYNC",
        [ramp_sync_vias[1], Point(51.89, 44.05)],
        0.127,
    )
    for point in ramp_sync_vias:
        add_via(board, "RAMP_SYNC", point)

    le_5904_vias = (
        Point(28.0, 23.4),
        Point(48.5, 15.0),
        Point(72.0, 15.0),
        Point(49.35, 42.8),
    )
    add_named_polyline(
        board,
        "LE_5904",
        [Point(29.25, 23.75), le_5904_vias[0]],
        0.127,
    )
    add_named_polyline(
        board,
        "LE_5904",
        [
            le_5904_vias[0],
            Point(27.5, 22.7),
            Point(27.5, 21.7),
            Point(24.0, 21.7),
            Point(24.0, 15.0),
            le_5904_vias[1],
        ],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "LE_5904",
        [le_5904_vias[1], le_5904_vias[2]],
        0.127,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "LE_5904",
        [
            le_5904_vias[2],
            Point(72.0, 48.8),
            Point(52.1, 48.8),
            Point(52.1, 42.8),
            le_5904_vias[3],
        ],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "LE_5904",
        [le_5904_vias[3], Point(49.35, 44.05)],
        0.127,
    )
    for point in le_5904_vias:
        add_via(board, "LE_5904", point)

    spi_sclk_vias = (
        Point(28.0, 24.4),
        Point(47.7, 14.2),
        Point(72.8, 14.2),
        Point(72.8, 47.8),
        Point(46.81, 48.8),
        Point(46.6, 22.7),
        Point(46.0, 16.7),
        Point(45.675, 42.4),
    )
    add_named_polyline(
        board,
        "SPI_SCLK",
        [Point(29.25, 24.25), spi_sclk_vias[0]],
        0.127,
    )
    add_named_polyline(
        board,
        "SPI_SCLK",
        [
            spi_sclk_vias[0],
            Point(27.8, 25.2),
            Point(27.8, 26.8),
            Point(26.3, 27.0),
            Point(22.8, 25.0),
            Point(22.8, 14.2),
            spi_sclk_vias[1],
        ],
        0.127,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "SPI_SCLK",
        [spi_sclk_vias[1], spi_sclk_vias[2]],
        0.127,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "SPI_SCLK",
        [
            spi_sclk_vias[2],
            spi_sclk_vias[3],
        ],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "SPI_SCLK",
        [
            spi_sclk_vias[3],
            Point(72.8, 48.5),
            Point(46.81, 48.5),
            spi_sclk_vias[4],
        ],
        0.127,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "SPI_SCLK",
        [spi_sclk_vias[4], Point(46.81, 47.95)],
        0.127,
    )
    add_named_polyline(
        board,
        "SPI_SCLK",
        [
            Point(48.75, 23.25),
            Point(48.3, 23.25),
            Point(47.8, 23.2),
            Point(47.0, 23.2),
            spi_sclk_vias[5],
        ],
        0.127,
    )
    add_named_polyline(
        board,
        "SPI_SCLK",
        [spi_sclk_vias[5], Point(46.0, 21.6), spi_sclk_vias[6]],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "SPI_SCLK",
        [spi_sclk_vias[6], Point(46.0, 14.2), spi_sclk_vias[1]],
        0.127,
        pcbnew.In2_Cu,
    )
    add_named_polyline(
        board,
        "SPI_SCLK",
        [Point(45.675, 40.8625), spi_sclk_vias[7]],
        0.127,
    )
    add_named_polyline(
        board,
        "SPI_SCLK",
        [
            spi_sclk_vias[7],
            Point(45.3, 42.8),
            Point(45.3, 48.8),
            spi_sclk_vias[4],
        ],
        0.127,
        pcbnew.B_Cu,
    )
    for index, point in enumerate(spi_sclk_vias):
        if index == 1:
            continue
        add_via(board, "SPI_SCLK", point)

    spi_sdo_vias = (
        Point(28.6, 26.2),
        Point(34.745, 45.5),
        Point(46.175, 45.5),
        Point(48.08, 49.2),
    )
    add_named_polyline(
        board,
        "SPI_SDO",
        [Point(29.25, 25.75), spi_sdo_vias[0]],
        0.127,
    )
    add_named_polyline(
        board,
        "SPI_SDO",
        [
            spi_sdo_vias[0],
            Point(30.0, 27.6),
            Point(30.0, 44.9),
            spi_sdo_vias[1],
        ],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "SPI_SDO",
        [spi_sdo_vias[1], spi_sdo_vias[2]],
        0.127,
    )
    add_named_polyline(
        board,
        "SPI_SDO",
        [
            spi_sdo_vias[2],
            Point(47.5, 46.6),
            Point(48.08, 47.3),
            spi_sdo_vias[3],
        ],
        0.127,
        pcbnew.B_Cu,
    )
    add_named_polyline(
        board,
        "SPI_SDO",
        [
            spi_sdo_vias[3],
            Point(48.08, 47.95),
        ],
        0.127,
    )
    for index, point in enumerate(spi_sdo_vias):
        if index in (1, 2):
            add_via(board, "SPI_SDO", point, diameter_mm=0.5, drill_mm=0.3)
        else:
            add_via(board, "SPI_SDO", point)

    add_planned_routes(board, "planned_control_routes.json")
    add_planned_routes(board, "planned_power_routes.json")

    for pad, via_point in (
        (Point(47.5, 18.27), Point(47.5, 17.4)),
        (Point(54.5, 18.27), Point(54.5, 17.4)),
        (Point(49.0, 18.27), Point(49.0, 17.4)),
        (Point(50.5, 18.27), Point(50.5, 17.4)),
    ):
        add_named_polyline(board, "GND", [pad, via_point], 0.4)
        add_via(board, "GND", via_point)

    add_pad_stitch(
        board,
        footprints,
        PadRef("C89", "1"),
        Point(37.175, 25.5),
        diameter_mm=0.5,
    )
    add_pad_stitch(
        board,
        footprints,
        PadRef("C84", "1"),
        Point(31.0, 19.475),
        diameter_mm=0.5,
    )

    for point in (
        Point(28.0, 10.0),
        Point(28.0, 37.0),
        Point(40.0, 38.5),
        Point(55.0, 31.5),
        Point(68.0, 10.0),
        Point(68.0, 35.0),
        Point(30.925, 33.025),
        Point(45.825, 43.575),
    ):
        add_via(board, "GND", point)

    add_ground_zones(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    pcbnew.SaveBoard(str(board_path), board)
    print(f"Added matched RX feeds and primary TX/LO RF routes to {board_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
