from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
KICAD_DIR = HERE.parent
REV_DIR = KICAD_DIR.parents[1]
XML_PATH = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c.xml"
BOARD_PATH = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c.kicad_pcb"
PROJECT_PATH = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c.kicad_pro"
CUSTOM_LIBRARY = REV_DIR / "library" / "openflight-revc.pretty"
STANDARD_LIBRARIES = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
GRID_PATH = REV_DIR / "antenna" / "results" / "grid.json"

MAIN_WIDTH_MM = 70.0
COUPON_WIDTH_MM = 12.0
BOARD_WIDTH_MM = MAIN_WIDTH_MM + COUPON_WIDTH_MM
BOARD_HEIGHT_MM = 50.0


@dataclass(frozen=True)
class Placement:
    x_mm: float
    y_mm: float
    rotation_deg: float = 0.0


RX_GRID_CENTER = Placement(14.5, 25.0)
TX_ANTENNA_PLACEMENT = Placement(54.5, 5.5, 180.0)


MAJOR_PLACEMENTS = {
    "J1": Placement(43.0, 46.0, 90.0),
    "U1": Placement(64.0, 24.0),
    "U2": Placement(64.0, 32.0),
    "U3": Placement(64.0, 40.0),
    "U4": Placement(45.5, 30.0, 180.0),
    "U5": Placement(51.0, 23.0, 180.0),
    "U6": Placement(31.5, 25.0, 270.0),
    "U7": Placement(46.0, 38.0, 90.0),
    "U8": Placement(54.5, 40.0),
    "X1": Placement(55.5, 34.5),
}

FIXED_PASSIVE_PLACEMENTS = {
    # Power entry and regulators.
    "FB1": Placement(55.0, 46.0, 90.0),
    "D1": Placement(59.0, 47.0, 90.0),
    "C1": Placement(62.0, 46.0, 90.0),
    "C2": Placement(68.5, 20.0, 90.0),
    "C3": Placement(60.5, 19.5, 90.0),
    "R1": Placement(68.5, 24.0, 90.0),
    "C4": Placement(68.5, 28.0, 90.0),
    "C5": Placement(59.0, 29.5, 90.0),
    "R2": Placement(68.5, 32.0, 90.0),
    "C6": Placement(61.25, 40.0, 90.0),
    "C7": Placement(66.75, 40.0, 90.0),
    # ADF4159 reference, RF feedback, loop filter, and supply bypassing.
    "C30": Placement(61.5, 36.5, 180.0),
    "C31": Placement(58.5, 42.0, 90.0),
    "C32": Placement(59.0, 33.5, 90.0),
    "C33": Placement(49.25, 33.5, 90.0),
    "C34": Placement(52.0, 32.0, 90.0),
    "C35": Placement(52.5, 29.25, 90.0),
    "C36": Placement(49.0, 30.25, 180.0),
    "C37": Placement(48.75, 28.25, 180.0),
    "C38": Placement(40.0, 26.5, 180.0),
    "C39": Placement(42.0, 26.5),
    "C40": Placement(41.0, 28.0, 270.0),
    "C41": Placement(38.5, 31.0, 180.0),
    "C42": Placement(42.0, 33.0, 90.0),
    "C43": Placement(40.25, 31.0, 270.0),
    "C44": Placement(40.25, 33.0, 90.0),
    "C45": Placement(40.0, 35.0, 180.0),
    "C46": Placement(39.0, 37.0),
    "C47": Placement(42.0, 41.0),
    "C48": Placement(42.0, 36.0),
    "C49": Placement(52.0, 40.0, 90.0),
    "C59": Placement(57.0, 40.0, 90.0),
    "R20": Placement(59.5, 36.5, 180.0),
    "R21": Placement(47.5, 33.5, 180.0),
    "R22": Placement(50.5, 32.0, 270.0),
    "R23": Placement(50.5, 29.25, 270.0),
    "R24": Placement(51.5, 34.5, 90.0),
    # ADF5901 RF coupling, tuning support, and four supply bypass groups.
    "C15": Placement(58.5, 23.0, 270.0),
    "C16": Placement(57.0, 23.0, 270.0),
    "C17": Placement(54.5, 18.75, 90.0),
    "C18": Placement(47.5, 18.75, 90.0),
    "C19": Placement(49.0, 18.75, 90.0),
    "C20": Placement(50.5, 18.75, 90.0),
    "C22": Placement(44.5, 24.5, 90.0),
    "C23": Placement(44.5, 22.5, 90.0),
    "C24": Placement(44.5, 20.5, 90.0),
    "C27": Placement(58.5, 26.25, 90.0),
    "C28": Placement(56.5, 26.25, 90.0),
    "C29": Placement(54.5, 29.0, 90.0),
    "C50": Placement(55.0, 24.25, 180.0),
    "C51": Placement(55.0, 21.75, 180.0),
    "C52": Placement(51.75, 19.25, 270.0),
    "C53": Placement(48.75, 26.6, 90.0),
    "C55": Placement(50.25, 27.3, 270.0),
    "C56": Placement(53.0, 27.0, 270.0),
    "C57": Placement(54.5, 27.0, 270.0),
    "C58": Placement(47.0, 21.75),
    "R40": Placement(46.0, 24.0, 90.0),
    # ADF5904 RF ports, baseband output filters, and supply bypassing.
    "C70": Placement(32.75, 20.75, 270.0),
    "C71": Placement(30.75, 20.75, 270.0),
    "C72": Placement(32.75, 29.25, 90.0),
    "C73": Placement(30.75, 29.25, 90.0),
    "C74": Placement(42.0, 24.0, 180.0),
    "C75": Placement(37.25, 21.0, 270.0),
    "C76": Placement(37.25, 23.0, 270.0),
    "C77": Placement(39.25, 21.0, 90.0),
    "C78": Placement(39.25, 23.0, 90.0),
    "C79": Placement(37.25, 29.0, 90.0),
    "C80": Placement(37.25, 26.5, 270.0),
    "C81": Placement(34.5, 34.5, 90.0),
    "C82": Placement(39.25, 28.0, 90.0),
    "C83": Placement(29.0, 18.0, 90.0),
    "C84": Placement(31.0, 18.0, 90.0),
    "C85": Placement(33.0, 18.0, 90.0),
    "C86": Placement(29.0, 32.0, 90.0),
    "C87": Placement(31.0, 32.0, 90.0),
    "C88": Placement(33.0, 32.0, 90.0),
    "C89": Placement(35.5, 25.5, 180.0),
    "C90": Placement(37.0, 33.5, 90.0),
    "C91": Placement(39.5, 25.5, 180.0),
    "R60": Placement(35.75, 22.0, 180.0),
    "R61": Placement(35.75, 23.5, 180.0),
    "R62": Placement(27.5, 21.0),
    "R63": Placement(27.5, 22.5),
    "R64": Placement(35.75, 28.5, 180.0),
    "R65": Placement(35.75, 27.0, 180.0),
    "R66": Placement(27.5, 29.0),
    "R67": Placement(27.5, 27.5),
}

SHEET_REGIONS = {
    "/": (50.5, 40.5, 66.0, 48.0),
    "/PLL + Ramp Generator/": (35.5, 28.5, 63.5, 39.0),
    "/ADF5901 Transmitter/": (51.5, 9.0, 68.0, 27.0),
    "/ADF5904 Receiver/": (35.0, 9.0, 48.0, 27.0),
}

BOARD_ONLY_TESTPOINTS = {
    "TP1": ("+5V", Placement(64.0, 6.0)),
    "TP2": ("+3V3_TX", Placement(64.0, 9.0)),
    "TP3": ("+3V3_RX", Placement(64.0, 12.0)),
    "TP4": ("+1V8_DIG", Placement(64.0, 15.0)),
}
BACKSIDE_TESTPOINTS: set[str] = set()
CTRL_NET_NAMES = frozenset(
    {
        "CE_RX",
        "LE_4159",
        "LE_5901",
        "LE_5904",
        "Net-(U1-PG)",
        "Net-(U2-PG)",
        "Net-(U4-CE)",
        "Net-(U4-CLK)",
        "Net-(U4-DATA)",
        "Net-(U4-LE)",
        "Net-(U4-MUXOUT)",
        "RAMP_SYNC",
        "SPI_SCLK",
        "SPI_SDATA",
        "SPI_SDO",
        "TX_EN",
    }
)


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def vector(x_mm: float, y_mm: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(mm(x_mm), mm(y_mm))


def antenna_placements() -> dict[str, Placement]:
    grid = json.loads(GRID_PATH.read_text(encoding="utf-8"))
    if not grid.get("acceptance", {}).get("geometry"):
        raise RuntimeError("grid.json does not have passing geometry acceptance")
    centers = grid.get("phase_centers", [])
    if {center.get("channel") for center in centers} != {"RX1", "RX2", "RX3", "RX4"}:
        raise RuntimeError("grid.json must define exactly RX1 through RX4")
    return {
        center["channel"]: Placement(
            RX_GRID_CENTER.x_mm + float(center["x_mm"]),
            RX_GRID_CENTER.y_mm + float(center["y_mm"]),
            float(center["rotation_deg"]),
        )
        for center in centers
    }


def parse_netlist() -> tuple[list[dict[str, str]], dict[str, list[tuple[str, str]]]]:
    root = ET.parse(XML_PATH).getroot()
    components: list[dict[str, str]] = []
    for component in root.findall("./components/comp"):
        sheetpath = component.find("sheetpath")
        components.append(
            {
                "ref": component.get("ref", ""),
                "value": component.findtext("value", ""),
                "footprint": component.findtext("footprint", ""),
                "sheet": sheetpath.get("names", "/") if sheetpath is not None else "/",
            }
        )

    nets: dict[str, list[tuple[str, str]]] = {}
    for net in root.findall("./nets/net"):
        nets[net.get("name", "")] = [
            (node.get("ref", ""), node.get("pin", "")) for node in net.findall("node")
        ]
    return components, nets


def load_footprint(identifier: str) -> pcbnew.FOOTPRINT:
    library, name = identifier.split(":", 1)
    library_path = (
        CUSTOM_LIBRARY if library == "openflight-revc" else STANDARD_LIBRARIES / f"{library}.pretty"
    )
    footprint = pcbnew.FootprintLoad(str(library_path), name)
    if footprint is None:
        raise RuntimeError(f"could not load footprint {identifier} from {library_path}")
    return footprint


def add_net(board: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    net = pcbnew.NETINFO_ITEM(board, name)
    board.Add(net)
    return net


def add_outline_segment(
    board: pcbnew.BOARD,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    layer: int = pcbnew.Edge_Cuts,
    width_mm: float = 0.05,
) -> None:
    segment = pcbnew.PCB_SHAPE(board)
    segment.SetShape(pcbnew.SHAPE_T_SEGMENT)
    segment.SetStart(vector(*start))
    segment.SetEnd(vector(*end))
    segment.SetLayer(layer)
    segment.SetWidth(mm(width_mm))
    board.Add(segment)


def set_text_size(text: pcbnew.PCB_TEXT, size_mm: float, thickness_mm: float) -> None:
    text.SetTextSize(vector(size_mm, size_mm))
    text.SetTextThickness(mm(thickness_mm))


def add_text(
    board: pcbnew.BOARD,
    value: str,
    placement: Placement,
    *,
    layer: int = pcbnew.F_SilkS,
    size_mm: float = 0.8,
) -> None:
    text = pcbnew.PCB_TEXT(board)
    text.SetText(value)
    text.SetPosition(vector(placement.x_mm, placement.y_mm))
    text.SetTextAngle(pcbnew.EDA_ANGLE(placement.rotation_deg, pcbnew.DEGREES_T))
    text.SetLayer(layer)
    set_text_size(text, size_mm, 0.12)
    board.Add(text)


def lattice(region: tuple[float, float, float, float], step_mm: float = 2.25) -> list[Placement]:
    x0, y0, x1, y1 = region
    points: list[Placement] = []
    y = y0
    row = 0
    while y <= y1 + 1e-6:
        xs: list[float] = []
        x = x0
        while x <= x1 + 1e-6:
            xs.append(x)
            x += step_mm
        if row % 2:
            xs.reverse()
        points.extend(Placement(x_value, y, 90.0 if row % 2 else 0.0) for x_value in xs)
        y += step_mm
        row += 1
    return points


def major_exclusion(ref: str) -> tuple[float, float]:
    if ref == "J1":
        return (12.0, 3.5)
    if ref in {"U5", "U6"}:
        return (4.0, 4.0)
    if ref == "U4":
        return (3.5, 3.5)
    if ref == "U7":
        return (4.5, 4.5)
    if ref == "X1":
        return (4.0, 3.5)
    return (2.5, 2.5)


def collides_with_major(point: Placement, sheet: str) -> bool:
    for ref, major in MAJOR_PLACEMENTS.items():
        if sheet == "/ADF5904 Receiver/" and ref != "U6":
            continue
        if sheet == "/ADF5901 Transmitter/" and ref != "U5":
            continue
        if sheet == "/PLL + Ramp Generator/" and ref not in {"U4", "U7", "U8", "X1"}:
            continue
        if sheet == "/" and ref not in {"J1", "U1", "U2", "U3"}:
            continue
        dx, dy = major_exclusion(ref)
        if abs(point.x_mm - major.x_mm) < dx and abs(point.y_mm - major.y_mm) < dy:
            return True
    fixed_exclusions = [
        *((placement, 1.25, 1.25) for _net, placement in BOARD_ONLY_TESTPOINTS.values()),
        (Placement(3.5, 3.5), 3.0, 3.0),
        (Placement(68.0, 3.5), 3.0, 3.0),
        (Placement(3.5, 46.5), 3.0, 3.0),
        (Placement(68.0, 46.5), 3.0, 3.0),
        (Placement(38.0, 4.0), 1.75, 1.75),
        (Placement(43.0, 4.0), 1.75, 1.75),
        (Placement(67.0, 15.0), 1.75, 1.75),
    ]
    for fixed, dx, dy in fixed_exclusions:
        if abs(point.x_mm - fixed.x_mm) < dx and abs(point.y_mm - fixed.y_mm) < dy:
            return True
    return False


def passive_placements(components: list[dict[str, str]]) -> dict[str, Placement]:
    by_sheet: dict[str, list[dict[str, str]]] = defaultdict(list)
    for component in components:
        if component["ref"] not in MAJOR_PLACEMENTS:
            by_sheet[component["sheet"]].append(component)

    result: dict[str, Placement] = {}
    for sheet, sheet_components in by_sheet.items():
        candidates = [
            point
            for point in lattice(SHEET_REGIONS[sheet])
            if not collides_with_major(point, sheet)
        ]
        if len(candidates) < len(sheet_components):
            raise RuntimeError(
                f"placement region for {sheet} has {len(candidates)} sites for "
                f"{len(sheet_components)} components"
            )
        for component, point in zip(
            sorted(sheet_components, key=lambda item: item["ref"]), candidates
        ):
            result[component["ref"]] = point
    return result


def place_footprint(
    board: pcbnew.BOARD,
    footprint: pcbnew.FOOTPRINT,
    ref: str,
    value: str,
    placement: Placement,
) -> None:
    footprint.SetReference(ref)
    footprint.SetValue(value)
    footprint.SetPosition(vector(placement.x_mm, placement.y_mm))
    footprint.SetOrientationDegrees(placement.rotation_deg)
    reference = footprint.Reference()
    reference.SetVisible(True)
    reference.SetLayer(pcbnew.F_Fab)
    reference.SetTextSize(vector(0.8, 0.8))
    reference.SetTextThickness(mm(0.1))
    footprint.Value().SetVisible(False)
    board.Add(footprint)


def add_board_only_footprint(
    board: pcbnew.BOARD,
    identifier: str,
    ref: str,
    value: str,
    placement: Placement,
    net: pcbnew.NETINFO_ITEM | None = None,
    *,
    back_side: bool = False,
) -> None:
    footprint = load_footprint(identifier)
    place_footprint(board, footprint, ref, value, placement)
    if back_side:
        footprint.Flip(footprint.GetPosition(), False)
    if net is not None:
        for pad in footprint.Pads():
            if pad.GetNumber():
                pad.SetNet(net)


def apply_stackup(path: Path) -> None:
    stackup = """\
\t\t(stackup
\t\t\t(layer \"F.Mask\" (type \"Top Solder Mask\") (color \"Green\") (thickness 0.01))
\t\t\t(layer \"F.Cu\" (type \"copper\") (thickness 0.017))
\t\t\t(layer \"dielectric 1\" (type \"core\") (thickness 0.254) (material \"Rogers RO4350B - INTERIM PCBWay confirmation required\") (epsilon_r 3.66) (loss_tangent 0.0037))
\t\t\t(layer \"In1.Cu\" (type \"copper\") (thickness 0.017))
\t\t\t(layer \"dielectric 2\" (type \"prepreg\") (thickness 0.5) (material \"FR4 - INTERIM PCBWay confirmation required\") (epsilon_r 4.2) (loss_tangent 0.02))
\t\t\t(layer \"In2.Cu\" (type \"copper\") (thickness 0.017))
\t\t\t(layer \"dielectric 3\" (type \"core\") (thickness 0.744) (material \"FR4 - INTERIM PCBWay confirmation required\") (epsilon_r 4.2) (loss_tangent 0.02))
\t\t\t(layer \"B.Cu\" (type \"copper\") (thickness 0.017))
\t\t\t(layer \"B.Mask\" (type \"Bottom Solder Mask\") (color \"Green\") (thickness 0.01))
\t\t\t(copper_finish \"ENIG\")
\t\t\t(dielectric_constraints no)
\t\t)
"""
    text = path.read_text(encoding="utf-8")
    marker = "\t(setup\n"
    if text.count(marker) != 1:
        raise RuntimeError("could not locate unique board setup block")
    path.write_text(text.replace(marker, marker + stackup, 1), encoding="utf-8")


def apply_project_settings() -> None:
    project = json.loads(PROJECT_PATH.read_text(encoding="utf-8"))

    def netclass(
        name: str,
        *,
        clearance: float,
        track_width: float,
        via_diameter: float,
        via_drill: float,
        diff_pair_width: float = 0.2,
        diff_pair_gap: float = 0.25,
    ) -> dict:
        return {
            "bus_width": 12,
            "clearance": clearance,
            "diff_pair_gap": diff_pair_gap,
            "diff_pair_via_gap": 0.25,
            "diff_pair_width": diff_pair_width,
            "line_style": 0,
            "microvia_diameter": 0.3,
            "microvia_drill": 0.1,
            "name": name,
            "pcb_color": "rgba(0, 0, 0, 0.000)",
            "priority": 2147483647 if name == "Default" else 0,
            "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": track_width,
            "tuning_profile": "",
            "via_diameter": via_diameter,
            "via_drill": via_drill,
            "wire_width": 6,
        }

    classes = [
        netclass("Default", clearance=0.1, track_width=0.2, via_diameter=0.5, via_drill=0.3),
        netclass("RF", clearance=0.1, track_width=0.556, via_diameter=0.5, via_drill=0.3),
        netclass(
            "BB_DIFF",
            clearance=0.127,
            track_width=0.127,
            via_diameter=0.45,
            via_drill=0.25,
            diff_pair_width=0.127,
            diff_pair_gap=0.127,
        ),
        netclass("PWR", clearance=0.15, track_width=0.4, via_diameter=0.6, via_drill=0.3),
        netclass("PLL", clearance=0.1, track_width=0.2, via_diameter=0.5, via_drill=0.3),
        netclass("CTRL", clearance=0.1, track_width=0.2, via_diameter=0.5, via_drill=0.3),
    ]

    rf_nets = {
        "RX1",
        "RX2",
        "RX3",
        "RX4",
        "TX_ANT",
        "LO_OUT",
        "RFIN_DIV",
        "Net-(C53-Pad2)",
        "Net-(C55-Pad1)",
        "Net-(U4-RFinA)",
        "Net-(U4-RFinB)",
        "Net-(U5-LOOUT)",
        "Net-(U5-TXOUT1)",
        "Net-(U5-TXOUT2)",
        "Net-(U6-LO_IN)",
        "Net-(U6-RX1_RF)",
        "Net-(U6-RX2_RF)",
        "Net-(U6-RX3_RF)",
        "Net-(U6-RX4_RF)",
    }
    bb_nets = {
        *(f"BB{channel}_{polarity}" for channel in range(1, 5) for polarity in ("P", "N")),
        *(f"Net-(U6-RX{channel}_{suffix})" for channel in range(1, 5) for suffix in ("O", "OB")),
    }
    power_nets = {"+5V", "+5V_REG", "+3V3_TX", "+3V3_RX", "+1V8_DIG", "GND"}
    pll_nets = {
        "Net-(C30-Pad2)",
        "Net-(C34-Pad2)",
        "Net-(C35-Pad1)",
        "Net-(U4-CP)",
        "Net-(U4-RSET)",
        "Net-(U5-C1)",
        "Net-(U5-C2)",
        "Net-(U5-RSET)",
        "Net-(U5-VREG)",
        "Net-(X1-OUT)",
        "REFIN",
        "VTUNE",
    }
    ctrl_nets = set(CTRL_NET_NAMES)
    known_nets = set(parse_netlist()[1])
    classified_nets = rf_nets | bb_nets | power_nets | pll_nets | ctrl_nets
    unknown_patterns = classified_nets - known_nets
    if unknown_patterns:
        raise RuntimeError(f"netclass patterns do not exist in netlist: {sorted(unknown_patterns)}")
    patterns = [
        *({"netclass": "RF", "pattern": name} for name in sorted(rf_nets)),
        *({"netclass": "BB_DIFF", "pattern": name} for name in sorted(bb_nets)),
        *({"netclass": "PWR", "pattern": name} for name in sorted(power_nets)),
        *({"netclass": "PLL", "pattern": name} for name in sorted(pll_nets)),
        *({"netclass": "CTRL", "pattern": name} for name in sorted(ctrl_nets)),
    ]
    project["net_settings"] = {
        "classes": classes,
        "meta": {"version": 5},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": patterns,
    }
    project["openflight"] = {
        "fabricator": "PCBWay",
        "generated_review_model": False,
        "material": "Rogers RO4350B over FR-4 (PCBWay 4-layer hybrid)",
        "fabrication_blocker": (
            "Exact PCBWay hybrid stackup and final passing antenna simulations are required "
            "before release."
        ),
    }
    PROJECT_PATH.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")


def build_board() -> pcbnew.BOARD:
    components, net_nodes = parse_netlist()
    if len(components) != 98 or len(net_nodes) != 80:
        raise RuntimeError(
            f"unexpected netlist size: {len(components)} components, {len(net_nodes)} nets"
        )

    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    settings = board.GetDesignSettings()
    settings.SetBoardThickness(mm(1.6))
    settings.m_CopperEdgeClearance = mm(0.3)
    settings.m_MinClearance = mm(0.1)
    settings.m_TrackMinWidth = mm(0.127)
    settings.m_SolderMaskExpansion = mm(0.02)
    settings.m_SolderMaskMinWidth = mm(0.04)
    settings.m_SilkClearance = mm(0.15)
    settings.m_MinSilkTextHeight = mm(0.6)
    settings.m_MinSilkTextThickness = mm(0.1)

    nets = {name: add_net(board, name) for name in net_nodes}
    node_to_net = {node: nets[name] for name, nodes in net_nodes.items() for node in nodes}

    placements = {
        **passive_placements(components),
        **FIXED_PASSIVE_PLACEMENTS,
        **MAJOR_PLACEMENTS,
    }
    footprints: dict[str, pcbnew.FOOTPRINT] = {}
    for component in components:
        ref = component["ref"]
        footprint = load_footprint(component["footprint"])
        place_footprint(board, footprint, ref, component["value"], placements[ref])
        footprints[ref] = footprint

    for (ref, pin), net in node_to_net.items():
        pads = [pad for pad in footprints[ref].Pads() if pad.GetNumber() == pin]
        if not pads:
            raise RuntimeError(f"{ref} footprint has no pad {pin}")
        for pad in pads:
            pad.SetNet(net)

    for start, end in (
        ((0.0, 0.0), (BOARD_WIDTH_MM, 0.0)),
        ((BOARD_WIDTH_MM, 0.0), (BOARD_WIDTH_MM, BOARD_HEIGHT_MM)),
        ((BOARD_WIDTH_MM, BOARD_HEIGHT_MM), (0.0, BOARD_HEIGHT_MM)),
        ((0.0, BOARD_HEIGHT_MM), (0.0, 0.0)),
    ):
        add_outline_segment(board, start, end)
    add_outline_segment(
        board,
        (MAIN_WIDTH_MM, 0.0),
        (MAIN_WIDTH_MM, BOARD_HEIGHT_MM),
        layer=pcbnew.Cmts_User,
        width_mm=0.2,
    )

    for index, placement in enumerate(
        (Placement(3.5, 3.5), Placement(68.0, 3.5), Placement(3.5, 46.5), Placement(68.0, 46.5)),
        start=1,
    ):
        add_board_only_footprint(
            board,
            "MountingHole:MountingHole_2.7mm",
            f"H{index}",
            "M2.5",
            placement,
        )

    for index, placement in enumerate(
        (Placement(38.0, 4.0), Placement(43.0, 4.0), Placement(67.0, 15.0)), start=1
    ):
        add_board_only_footprint(
            board,
            "Fiducial:Fiducial_1mm_Mask2mm",
            f"FID{index}",
            "Fiducial",
            placement,
        )

    for ref, (net_name, placement) in BOARD_ONLY_TESTPOINTS.items():
        add_board_only_footprint(
            board,
            "TestPoint:TestPoint_Pad_D1.0mm",
            ref,
            net_name,
            placement,
            nets[net_name],
            back_side=ref in BACKSIDE_TESTPOINTS,
        )

    for channel, placement in antenna_placements().items():
        add_board_only_footprint(
            board,
            "openflight-revc:RX_SUBARRAY_2X2",
            f"ANT_{channel}",
            channel,
            placement,
            nets[channel],
        )
    add_board_only_footprint(
        board,
        "openflight-revc:TX_ARRAY_2X2",
        "ANT_TX1",
        "TX_ANT",
        TX_ANTENNA_PLACEMENT,
        nets["TX_ANT"],
    )

    add_text(board, "OPENFLIGHT RF REV C", Placement(15.0, 46.0), size_mm=1.0)
    add_text(
        board,
        "INTERIM STACKUP - VERIFY BEFORE FAB",
        Placement(35.0, 1.5),
        layer=pcbnew.Cmts_User,
        size_mm=0.65,
    )
    add_text(board, "V-SCORE / COUPON", Placement(70.8, 25.0, 90.0), layer=pcbnew.Cmts_User)
    add_text(board, "RF COUPON", Placement(76.0, 48.0), size_mm=0.8)
    return board


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else BOARD_PATH
    board = build_board()
    pcbnew.SaveBoard(str(output), board)
    apply_stackup(output)
    apply_project_settings()
    print(
        f"Wrote {output}: {len(list(board.GetFootprints()))} footprints, "
        f"{len(list(board.GetNetsByNetcode())) - 1} nets"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
