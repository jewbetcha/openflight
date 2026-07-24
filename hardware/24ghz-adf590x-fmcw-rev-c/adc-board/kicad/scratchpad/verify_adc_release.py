"""Verify the production ADC schematic/PCB connector contract."""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pcbnew


ADC_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ADC_DIR))
from adc_interface_contract import (  # noqa: E402
    COPPER_LAYER_ORDER,
    DNP_REFERENCES,
    PI_J2_REQUIRED_PIN_NETS,
    RF_ENABLE_NETS,
    RF_J1_PIN_NETS,
)


def schematic_pin_map(root: ET.Element, reference: str) -> dict[int, str]:
    result: dict[int, str] = {}
    for net in root.findall("./nets/net"):
        for node in net.findall("node"):
            if node.get("ref") == reference:
                result[int(node.get("pin", "0"))] = net.get("name", "")
    return result


def footprint(board: pcbnew.BOARD, reference: str) -> pcbnew.FOOTPRINT:
    matches = [item for item in board.GetFootprints() if item.GetReference() == reference]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {reference}, found {len(matches)}")
    return matches[0]


def pcb_pin_map(board: pcbnew.BOARD, reference: str) -> dict[int, str]:
    return {
        int(pad.GetNumber()): pad.GetNetname()
        for pad in footprint(board, reference).Pads()
    }


def require_pin_map(actual: dict[int, str], expected: dict[int, str], name: str) -> None:
    mismatches = {
        pin: {"expected": net, "actual": actual.get(pin)}
        for pin, net in expected.items()
        if actual.get(pin) != net
    }
    if mismatches:
        raise RuntimeError(f"{name} pin-map mismatch: {mismatches}")


def verify(netlist_path: Path, board_path: Path) -> dict[str, object]:
    root = ET.parse(netlist_path).getroot()
    board = pcbnew.LoadBoard(str(board_path))
    sch_j1 = schematic_pin_map(root, "J1")
    sch_j2 = schematic_pin_map(root, "J2")
    pcb_j1 = pcb_pin_map(board, "J1")
    pcb_j2 = pcb_pin_map(board, "J2")

    require_pin_map(sch_j1, RF_J1_PIN_NETS, "schematic J1")
    require_pin_map(pcb_j1, RF_J1_PIN_NETS, "PCB J1")
    require_pin_map(sch_j2, PI_J2_REQUIRED_PIN_NETS, "schematic J2")
    require_pin_map(pcb_j2, PI_J2_REQUIRED_PIN_NETS, "PCB J2")

    j2 = footprint(board, "J2")
    if not pcbnew.IsBackLayer(j2.GetLayer()):
        raise RuntimeError("J2 is not mounted on the PCB bottom side")

    for reference, expected_net in (("R6", "CE_RX"), ("R7", "TX_EN")):
        pins = pcb_pin_map(board, reference)
        require_pin_map(pins, {1: expected_net, 2: "GND"}, f"PCB {reference}")

    for reference in DNP_REFERENCES:
        if not footprint(board, reference).IsDNP():
            raise RuntimeError(f"{reference} is not marked DNP on the PCB")

    copper_layers = COPPER_LAYER_ORDER
    settings = board.GetDesignSettings()
    if settings.GetCopperLayerCount() != len(copper_layers):
        raise RuntimeError(
            f"expected {len(copper_layers)} copper layers, "
            f"found {settings.GetCopperLayerCount()}"
        )
    for layer_name in copper_layers:
        layer = board.GetLayerID(layer_name)
        if not pcbnew.IsCopperLayer(layer) or not settings.IsLayerEnabled(layer):
            raise RuntimeError(f"required copper layer is not enabled: {layer_name}")

    return {
        "status": "pass",
        "rf_header_pins_verified": len(RF_J1_PIN_NETS),
        "pi_required_pins_verified": len(PI_J2_REQUIRED_PIN_NETS),
        "rf_enable_nets": list(RF_ENABLE_NETS),
        "j2_side": "Bottom",
        "dnp_references": sorted(DNP_REFERENCES),
        "copper_layer_order": list(copper_layers),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("netlist", type=Path)
    parser.add_argument("board", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.netlist, args.board)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
