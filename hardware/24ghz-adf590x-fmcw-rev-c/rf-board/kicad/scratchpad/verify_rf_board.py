from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
KICAD_DIR = HERE.parent
DEFAULT_BOARD = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c.kicad_pcb"
XML_PATH = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c.xml"
PROJECT_PATH = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c.kicad_pro"

EXPECTED_SCHEMATIC_FOOTPRINTS = 98
EXPECTED_TOTAL_FOOTPRINTS = 114
EXPECTED_COPPER_LAYERS = 4
EXPECTED_BOARD_ONLY_REFS = {
    *(f"H{index}" for index in range(1, 5)),
    *(f"FID{index}" for index in range(1, 4)),
    *(f"TP{index}" for index in range(1, 5)),
    *(f"ANT_RX{index}" for index in range(1, 5)),
    "ANT_TX1",
}
EXPECTED_ANTENNA_NETS = {
    **{f"ANT_RX{index}": f"RX{index}" for index in range(1, 5)},
    "ANT_TX1": "TX_ANT",
}
EXPECTED_NETCLASSES = {"Default", "RF", "BB_DIFF", "PWR", "PLL", "CTRL"}


def schematic_nodes() -> tuple[set[str], dict[tuple[str, str], str]]:
    root = ET.parse(XML_PATH).getroot()
    references = {component.get("ref", "") for component in root.findall("./components/comp")}
    nodes: dict[tuple[str, str], str] = {}
    for net in root.findall("./nets/net"):
        net_name = net.get("name", "")
        for node in net.findall("node"):
            key = (node.get("ref", ""), node.get("pin", ""))
            if key in nodes:
                raise RuntimeError(f"duplicate schematic node {key}")
            nodes[key] = net_name
    return references, nodes


def edge_bounds(board: pcbnew.BOARD) -> tuple[float, float, float, float]:
    points: list[tuple[float, float]] = []
    for drawing in board.GetDrawings():
        if drawing.GetLayer() != pcbnew.Edge_Cuts:
            continue
        points.extend(
            [
                (pcbnew.ToMM(drawing.GetStart().x), pcbnew.ToMM(drawing.GetStart().y)),
                (pcbnew.ToMM(drawing.GetEnd().x), pcbnew.ToMM(drawing.GetEnd().y)),
            ]
        )
    if not points:
        raise RuntimeError("board has no Edge.Cuts geometry")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def main() -> int:
    board_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BOARD
    board = pcbnew.LoadBoard(str(board_path))
    references, nodes = schematic_nodes()
    footprints = {footprint.GetReference(): footprint for footprint in board.GetFootprints()}

    if len(references) != EXPECTED_SCHEMATIC_FOOTPRINTS:
        raise RuntimeError(f"expected {EXPECTED_SCHEMATIC_FOOTPRINTS} schematic footprints")
    if len(footprints) != EXPECTED_TOTAL_FOOTPRINTS:
        raise RuntimeError(
            f"expected {EXPECTED_TOTAL_FOOTPRINTS} board footprints, found {len(footprints)}"
        )
    missing = references - footprints.keys()
    if missing:
        raise RuntimeError(f"board missing schematic footprints: {sorted(missing)}")
    missing_board_only = EXPECTED_BOARD_ONLY_REFS - footprints.keys()
    if missing_board_only:
        raise RuntimeError(f"board missing fixtures: {sorted(missing_board_only)}")

    for reference, expected_net in EXPECTED_ANTENNA_NETS.items():
        actual_nets = {pad.GetNetname() for pad in footprints[reference].Pads() if pad.GetNumber()}
        if actual_nets != {expected_net}:
            raise RuntimeError(
                f"{reference}: expected all copper on {expected_net}, found {sorted(actual_nets)}"
            )

    for (reference, pin), expected_net in nodes.items():
        pads = [pad for pad in footprints[reference].Pads() if pad.GetNumber() == pin]
        if not pads:
            raise RuntimeError(f"{reference} has no board pad {pin}")
        actual_nets = {pad.GetNetname() for pad in pads}
        if actual_nets != {expected_net}:
            raise RuntimeError(
                f"{reference}.{pin}: expected {expected_net}, found {sorted(actual_nets)}"
            )

    if board.GetCopperLayerCount() != EXPECTED_COPPER_LAYERS:
        raise RuntimeError(
            f"expected {EXPECTED_COPPER_LAYERS} copper layers, found {board.GetCopperLayerCount()}"
        )
    bounds = edge_bounds(board)
    if bounds != (0.0, 0.0, 82.0, 50.0):
        raise RuntimeError(f"unexpected board outline bounds: {bounds}")

    board_text = board_path.read_text(encoding="utf-8")
    if "Rogers RO4350B - INTERIM PCBWay confirmation required" not in board_text:
        raise RuntimeError("interim Rogers stackup metadata missing from board")

    project = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))
    class_names = {item["name"] for item in project["net_settings"]["classes"]}
    if class_names != EXPECTED_NETCLASSES:
        raise RuntimeError(f"unexpected net classes: {sorted(class_names)}")

    print(
        f"PASS: {len(references)} schematic + {len(EXPECTED_BOARD_ONLY_REFS)} fixture "
        f"footprints, {len(nodes)} pad-net assignments, 4 layers, 82x50 mm outline"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
