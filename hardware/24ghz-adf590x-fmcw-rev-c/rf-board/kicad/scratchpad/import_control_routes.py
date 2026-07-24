from __future__ import annotations

import sys
import os
from pathlib import Path

import pcbnew
from build_rf_board import CTRL_NET_NAMES

HERE = Path(__file__).resolve().parent
KICAD_DIR = HERE.parent
DEFAULT_BOARD = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c.kicad_pcb"
DEFAULT_SESSION = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c-control.ses"
DEFAULT_OUTPUT = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c-control-candidate.kicad_pcb"
LOW_SPEED_NET_NAMES = frozenset({"Net-(U1-PG)", "Net-(U2-PG)"})


def main() -> int:
    board_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BOARD
    session_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_SESSION
    output_path = Path(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_OUTPUT

    board = pcbnew.LoadBoard(str(board_path))
    if list(board.GetTracks()):
        raise RuntimeError("control route import requires a board with no existing tracks")
    if not pcbnew.ImportSpecctraSES(board, str(session_path)):
        raise RuntimeError(f"failed to import {session_path}")

    imported = list(board.GetTracks())
    requested_nets = os.environ.get("IMPORT_NETS")
    selected_nets = (
        frozenset(name for name in requested_nets.split(",") if name)
        if requested_nets
        else LOW_SPEED_NET_NAMES
    )
    remap_target = os.environ.get("REMAP_IN1_TO_LAYER")
    remap_layer = {"In2.Cu": pcbnew.In2_Cu, "B.Cu": pcbnew.B_Cu}.get(remap_target)
    remap_in1 = remap_layer is not None
    in1_nets = {
        item.GetNetname()
        for item in imported
        if not isinstance(item, pcbnew.PCB_VIA) and item.GetLayer() == pcbnew.In1_Cu
    }
    if remap_in1:
        for item in imported:
            if not isinstance(item, pcbnew.PCB_VIA) and item.GetLayer() == pcbnew.In1_Cu:
                item.SetLayer(remap_layer)
    for item in imported:
        if item.GetNetname() not in selected_nets or (
            item.GetNetname() in in1_nets and not remap_in1
        ):
            board.Remove(item)

    kept = list(board.GetTracks())
    layer_counts: dict[str, int] = {}
    for item in kept:
        layer_name = board.GetLayerName(item.GetLayer())
        layer_counts[layer_name] = layer_counts.get(layer_name, 0) + 1
    pcbnew.SaveBoard(str(output_path), board)
    print(
        f"Imported {len(imported)} route items; kept {len(kept)} control/baseband items "
        f"on {layer_counts}; "
        f"{'remapped to ' + remap_target if remap_in1 else 'rejected'} In1 nets "
        f"{sorted(in1_nets & selected_nets)} "
        f"-> {output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
