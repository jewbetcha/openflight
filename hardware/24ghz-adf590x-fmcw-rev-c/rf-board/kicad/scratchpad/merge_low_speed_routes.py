from __future__ import annotations

import os
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
KICAD_DIR = HERE.parent
DEFAULT_BOARD = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c.kicad_pcb"
DEFAULT_CANDIDATE = KICAD_DIR / "openflight-24ghz-fmcw-rf-rev-c-low-speed-candidate.kicad_pcb"


def main() -> int:
    board_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BOARD
    candidate_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_CANDIDATE

    board = pcbnew.LoadBoard(str(board_path))
    candidate = pcbnew.LoadBoard(str(candidate_path))
    requested_nets = os.environ.get("MERGE_NETS")
    selected_nets = (
        frozenset(name for name in requested_nets.split(",") if name)
        if requested_nets
        else None
    )
    existing_nets = {item.GetNetname() for item in board.GetTracks()}
    candidate_nets = {
        item.GetNetname()
        for item in candidate.GetTracks()
        if selected_nets is None or item.GetNetname() in selected_nets
    }
    duplicate_nets = existing_nets & candidate_nets
    if duplicate_nets:
        raise RuntimeError(f"target already contains candidate nets: {sorted(duplicate_nets)}")

    added = 0
    for item in candidate.GetTracks():
        if selected_nets is not None and item.GetNetname() not in selected_nets:
            continue
        clone = item.Duplicate()
        net = board.FindNet(item.GetNetname())
        if net is None:
            raise RuntimeError(f"target has no net named {item.GetNetname()}")
        clone.SetNet(net)
        if (
            item.GetNetname() == "LE_4159"
            and not isinstance(item, pcbnew.PCB_VIA)
            and item.GetLayer() == pcbnew.In2_Cu
        ):
            clone.SetLayer(pcbnew.B_Cu)
        board.Add(clone)
        added += 1

    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(board_path), board)
    print(f"Merged {added} route items for {len(candidate_nets)} low-speed nets into {board_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
