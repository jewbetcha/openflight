"""Apply the production RF/Pi connector contract to an ADC PCB candidate."""

from __future__ import annotations

import sys
from pathlib import Path

import pcbnew


HERE = Path(__file__).resolve().parent
KICAD_DIR = HERE.parent
ADC_DIR = KICAD_DIR.parent
DEFAULT_BOARD = KICAD_DIR / "openflight-adc-pi-interface-rev-c.kicad_pcb"
DEFAULT_OUTPUT = KICAD_DIR / "openflight-adc-pi-interface-rev-c-connector-candidate.kicad_pcb"
KICAD_FOOTPRINTS = Path(
    "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
)

sys.path.insert(0, str(ADC_DIR))
from adc_interface_contract import (  # noqa: E402
    DNP_REFERENCES,
    PI_J2_REQUIRED_PIN_NETS,
    PI_SOCKET_MPN,
    RF_J1_PIN_NETS,
)


def mm(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def find_footprint(board: pcbnew.BOARD, reference: str) -> pcbnew.FOOTPRINT:
    matches = [fp for fp in board.GetFootprints() if fp.GetReference() == reference]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {reference} footprint, found {len(matches)}")
    return matches[0]


def get_or_add_net(board: pcbnew.BOARD, name: str) -> pcbnew.NETINFO_ITEM:
    existing = board.FindNet(name)
    if existing:
        return existing
    net = pcbnew.NETINFO_ITEM(board, name)
    board.Add(net)
    return net


def set_pad_nets(
    board: pcbnew.BOARD,
    footprint: pcbnew.FOOTPRINT,
    pin_nets: dict[int, str],
) -> None:
    pads = {int(pad.GetNumber()): pad for pad in footprint.Pads()}
    missing = sorted(set(pin_nets) - set(pads))
    if missing:
        raise RuntimeError(f"{footprint.GetReference()} is missing pads {missing}")
    for pin, net_name in pin_nets.items():
        pads[pin].SetNet(get_or_add_net(board, net_name))


def replace_pi_socket(board: pcbnew.BOARD) -> None:
    old = find_footprint(board, "J2")
    old_position = old.GetPosition()
    old_pad_positions = {
        int(pad.GetNumber()): (pad.GetPosition().x, pad.GetPosition().y)
        for pad in old.Pads()
    }
    old_pin_nets = {
        int(pad.GetNumber()): pad.GetNetname()
        for pad in old.Pads()
        if not pad.GetNetname().startswith("unconnected-")
    }
    old_pin_nets.update(PI_J2_REQUIRED_PIN_NETS)

    socket = pcbnew.FootprintLoad(
        str(KICAD_FOOTPRINTS / "Connector_PinSocket_2.54mm.pretty"),
        "PinSocket_2x20_P2.54mm_Vertical",
    )
    if socket is None:
        raise RuntimeError("could not load the KiCad 2x20 pin-socket footprint")
    board.Add(socket)
    socket.SetReference("J2")
    socket.SetValue("RaspberryPi_GPIO")
    socket.SetPosition(old_position)
    socket.Flip(old_position, False)
    socket.Reference().SetLayer(pcbnew.B_Fab)
    socket.Value().SetLayer(pcbnew.B_Fab)
    for item in list(socket.GraphicalItems()):
        if item.GetLayer() == pcbnew.B_SilkS:
            item.SetLayer(pcbnew.B_Fab)
    set_pad_nets(board, socket, old_pin_nets)
    board.Remove(old)

    new_pad_positions = {
        int(pad.GetNumber()): (pad.GetPosition().x, pad.GetPosition().y)
        for pad in socket.Pads()
    }
    if new_pad_positions != old_pad_positions:
        raise RuntimeError("J2 replacement moved or renumbered Raspberry Pi pins")
    if not pcbnew.IsBackLayer(socket.GetLayer()):
        raise RuntimeError("J2 must be mounted on the bottom side")


def add_pulldown(
    board: pcbnew.BOARD,
    reference: str,
    net_name: str,
    position: tuple[float, float],
) -> None:
    resistor = pcbnew.FootprintLoad(
        str(KICAD_FOOTPRINTS / "Resistor_SMD.pretty"),
        "R_0402_1005Metric",
    )
    if resistor is None:
        raise RuntimeError("could not load the KiCad 0402 resistor footprint")
    board.Add(resistor)
    resistor.SetReference(reference)
    resistor.SetValue("10k")
    resistor.SetPosition(mm(*position))
    resistor.Reference().SetLayer(pcbnew.F_Fab)
    resistor.Value().SetLayer(pcbnew.F_Fab)
    set_pad_nets(board, resistor, {1: net_name, 2: "GND"})


def name_mechanical_footprints(board: pcbnew.BOARD) -> None:
    expected = {
        (3.0, 3.5): ("H1", "MountingHole_2.7mm"),
        (52.0, 3.5): ("H2", "MountingHole_2.7mm"),
        (3.0, 61.5): ("H3", "MountingHole_2.7mm"),
        (52.0, 61.5): ("H4", "MountingHole_2.7mm"),
        (49.5, 4.5): ("FID1", "Fiducial_1mm"),
        (49.5, 60.5): ("FID2", "Fiducial_1mm"),
        (5.0, 62.0): ("FID3", "Fiducial_1mm"),
    }
    found: set[tuple[float, float]] = set()
    for item in list(board.GetFootprints()):
        if item.GetReference():
            continue
        location = (
            round(pcbnew.ToMM(item.GetPosition().x), 2),
            round(pcbnew.ToMM(item.GetPosition().y), 2),
        )
        if location not in expected:
            continue
        reference, value = expected[location]
        item.SetReference(reference)
        item.SetValue(value)
        item.SetExcludedFromBOM(True)
        item.SetExcludedFromPosFiles(True)
        item.Reference().SetVisible(False)
        item.Value().SetVisible(False)
        found.add(location)
    if found != set(expected):
        raise RuntimeError(f"mechanical footprint mismatch: found {sorted(found)}")


def apply_contract(board: pcbnew.BOARD) -> None:
    j1 = find_footprint(board, "J1")
    set_pad_nets(board, j1, RF_J1_PIN_NETS)
    replace_pi_socket(board)

    for reference in ("R6", "R7"):
        existing = [fp for fp in board.GetFootprints() if fp.GetReference() == reference]
        if existing:
            raise RuntimeError(f"{reference} already exists")
    add_pulldown(board, "R6", "CE_RX", (7.0, 41.5))
    add_pulldown(board, "R7", "TX_EN", (4.2, 41.5))

    for reference in DNP_REFERENCES:
        find_footprint(board, reference).SetDNP(True)

    name_mechanical_footprints(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())


def main() -> int:
    board_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BOARD
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    board = pcbnew.LoadBoard(str(board_path))
    apply_contract(board)
    pcbnew.SaveBoard(str(output_path), board)
    print(f"Wrote production connector candidate: {output_path}")
    print("J2: bottom-mounted ESQ-120-58-S-D; all 40 pad coordinates preserved")
    print("J1: all 30 RF pins assigned; R6/R7 hold CE_RX and TX_EN low")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
