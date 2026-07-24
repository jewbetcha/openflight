"""Route the added RF control bus without disturbing the existing ADC routes."""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew


HERE = Path(__file__).resolve().parent
KICAD_DIR = HERE.parent
DEFAULT_BOARD = KICAD_DIR / "openflight-adc-pi-interface-rev-c-connector-candidate.kicad_pcb"
DEFAULT_OUTPUT = KICAD_DIR / "openflight-adc-pi-interface-rev-c-routed-candidate.kicad_pcb"
TRACK_WIDTH_MM = 0.15
VIA_DIAMETER_MM = 0.5
VIA_DRILL_MM = 0.3


def point(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def net(board: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    item = board.FindNet(name)
    if not item:
        raise RuntimeError(f"missing PCB net {name}")
    return item


def segment(
    board: pcbnew.BOARD,
    net_name: str,
    start: tuple[float, float],
    end: tuple[float, float],
    layer: int,
) -> None:
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(point(*start))
    track.SetEnd(point(*end))
    track.SetWidth(pcbnew.FromMM(TRACK_WIDTH_MM))
    track.SetLayer(layer)
    track.SetNet(net(board, net_name))
    board.Add(track)


def via(board: pcbnew.BOARD, net_name: str, at: tuple[float, float]) -> None:
    item = pcbnew.PCB_VIA(board)
    item.SetPosition(point(*at))
    item.SetWidth(pcbnew.FromMM(VIA_DIAMETER_MM))
    item.SetDrill(pcbnew.FromMM(VIA_DRILL_MM))
    item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    item.SetNet(net(board, net_name))
    board.Add(item)


ODD_ESCAPES = {
    "SPI_SCLK": ((3.05, 33.81), (0.6, 52.0)),
    "SPI_SDO": ((3.05, 35.08), (1.2, 54.2)),
    "LE_5901": ((3.05, 36.35), (1.8, 55.2)),
    "LE_4159": ((3.05, 37.62), (2.4, 56.2)),
    "TX_EN": ((3.05, 38.89), (3.0, 57.2)),
}


def route_odd_escapes(board: pcbnew.BOARD) -> None:
    for net_name, (j1, escape_end) in ODD_ESCAPES.items():
        column = (escape_end[0], j1[1])
        via(board, net_name, j1)
        segment(board, net_name, j1, column, pcbnew.B_Cu)
        segment(board, net_name, column, escape_end, pcbnew.B_Cu)
        if net_name != "TX_EN":
            via(board, net_name, escape_end)

    # Clock and TX latch approach their Pi pins on B.Cu after crossing the
    # left-side +5 V route on In2.
    segment(board, "SPI_SCLK", (0.6, 52.0), (9.0, 58.8), pcbnew.In1_Cu)
    via(board, "SPI_SCLK", (9.0, 58.8))
    sclk = [(9.0, 58.8), (42.5, 58.8), (42.5, 34.94), (45.72, 34.94)]
    for start, end in zip(sclk, sclk[1:]):
        segment(board, "SPI_SCLK", start, end, pcbnew.B_Cu)

    le5901_escape = [
        (1.8, 55.2),
        (0.4, 55.2),
        (0.4, 53.5),
        (7.0, 53.5),
        (7.0, 57.8),
    ]
    for start, end in zip(le5901_escape, le5901_escape[1:]):
        segment(board, "LE_5901", start, end, pcbnew.F_Cu)
    via(board, "LE_5901", (7.0, 57.8))
    le5901 = [(7.0, 57.8), (52.0, 57.8)]
    for start, end in zip(le5901, le5901[1:]):
        segment(board, "LE_5901", start, end, pcbnew.In2_Cu)
    via(board, "LE_5901", (52.0, 57.8))
    segment(board, "LE_5901", (52.0, 57.8), (52.0, 34.94), pcbnew.F_Cu)
    segment(board, "LE_5901", (52.0, 34.94), (48.26, 34.94), pcbnew.F_Cu)

    # Remaining odd-row destinations stay on In2 and approach from the left.
    inner_routes = {
        "SPI_SDO": (
            (4.6, 57.2),
            (9.8, 57.2),
            (9.8, 56.4),
            (11.4, 56.4),
            (11.4, 57.2),
            (33.6, 57.2),
            (43.0, 32.4),
            (45.72, 32.4),
        ),
        "LE_4159": (
            (2.4, 56.2),
            (0.8, 56.2),
            (0.8, 59.4),
            (5.0, 59.4),
            (35.4, 59.4),
        ),
        "TX_EN": (
            (5.0, 60.6),
            (36.0, 60.6),
        ),
    }
    for net_name, points in inner_routes.items():
        for start, end in zip(points, points[1:]):
            segment(board, net_name, start, end, pcbnew.In2_Cu)

    # SDO and TX move away from adjacent escape vias before joining In2.
    segment(board, "SPI_SDO", (1.2, 54.2), (4.6, 54.2), pcbnew.F_Cu)
    segment(board, "SPI_SDO", (4.6, 54.2), (4.6, 57.2), pcbnew.F_Cu)
    via(board, "SPI_SDO", (4.6, 57.2))
    segment(board, "TX_EN", (3.0, 57.2), (5.0, 60.6), pcbnew.B_Cu)
    via(board, "TX_EN", (5.0, 60.6))

    # TX_EN changes to B.Cu before the right-side vertical so it does not cross
    # the long LE_5901 In2 route.
    via(board, "TX_EN", (36.0, 60.6))
    tx_finish = [(36.0, 60.6), (44.0, 60.6), (44.0, 52.72), (45.72, 52.72)]
    for start, end in zip(tx_finish, tx_finish[1:]):
        segment(board, "TX_EN", start, end, pcbnew.B_Cu)

    via(board, "LE_4159", (35.4, 59.4))
    le4159_finish = [(35.4, 59.4), (40.0, 59.4), (40.0, 42.56), (45.72, 42.56)]
    for start, end in zip(le4159_finish, le4159_finish[1:]):
        segment(board, "LE_4159", start, end, pcbnew.F_Cu)


def route_pulldowns(board: pcbnew.BOARD) -> None:
    segment(board, "CE_RX", (6.95, 37.62), (8.6, 37.62), pcbnew.F_Cu)
    segment(board, "CE_RX", (8.6, 37.62), (8.6, 42.5), pcbnew.F_Cu)
    segment(board, "CE_RX", (8.6, 42.5), (6.49, 42.5), pcbnew.F_Cu)
    segment(board, "CE_RX", (6.49, 42.5), (6.49, 41.5), pcbnew.F_Cu)
    segment(board, "TX_EN", (3.05, 38.89), (3.05, 40.5), pcbnew.F_Cu)
    segment(board, "TX_EN", (3.05, 40.5), (3.69, 41.5), pcbnew.F_Cu)


def route_receiver_enable(board: pcbnew.BOARD) -> None:
    via(board, "CE_RX", (6.95, 37.62))
    ce_back = [
        (6.95, 37.62),
        (9.4, 37.62),
        (9.4, 21.0),
        (8.2, 21.0),
        (8.2, 19.0),
        (9.4, 19.0),
        (9.4, 17.8),
    ]
    for start, end in zip(ce_back, ce_back[1:]):
        segment(board, "CE_RX", start, end, pcbnew.B_Cu)
    via(board, "CE_RX", (9.4, 17.8))
    ce_front = [
        (9.4, 17.8),
        (10.0, 17.8),
        (10.0, 0.7),
        (53.6, 0.7),
        (53.6, 32.4),
        (48.26, 32.4),
    ]
    for start, end in zip(ce_front, ce_front[1:]):
        segment(board, "CE_RX", start, end, pcbnew.F_Cu)


def route_top_paths(board: pcbnew.BOARD) -> None:
    sdata_points = [
        (6.95, 33.81),
        (12.0, 33.81),
        (12.0, 1.5),
        (43.0, 1.5),
        (43.0, 29.86),
        (45.72, 29.86),
    ]
    for start, end in zip(sdata_points, sdata_points[1:]):
        segment(board, "SPI_SDATA", start, end, pcbnew.F_Cu)

    le5904_points = [
        (6.95, 36.35),
        (13.0, 34.8),
    ]
    for start, end in zip(le5904_points, le5904_points[1:]):
        segment(board, "LE_5904", start, end, pcbnew.F_Cu)
    via(board, "LE_5904", (13.0, 34.8))
    le5904_inner = [(13.0, 34.8), (13.0, 0.7), (54.2, 0.7), (54.2, 37.48), (48.26, 37.48)]
    for start, end in zip(le5904_inner, le5904_inner[1:]):
        segment(board, "LE_5904", start, end, pcbnew.In2_Cu)


def main() -> int:
    board_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BOARD
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    board = pcbnew.LoadBoard(str(board_path))
    route_odd_escapes(board)
    route_pulldowns(board)
    route_receiver_enable(board)
    route_top_paths(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(output_path), board)
    print(f"Wrote routed control-bus candidate: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
