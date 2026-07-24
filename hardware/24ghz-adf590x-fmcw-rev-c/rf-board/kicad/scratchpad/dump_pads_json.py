#!/usr/bin/env python3
"""Dump all F.Cu pad bboxes (rotation applied) to JSON for clearance checks."""
import json
import math

import pcbnew

BOARD = (
    "/Users/colemanrollins/code/openflight/hardware/24ghz-adf590x-fmcw-rev-c/"
    "rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_pcb"
)
OUT = (
    "/Users/colemanrollins/code/openflight/hardware/24ghz-adf590x-fmcw-rev-c/"
    "analysis/expert-review-2026-07-18/pads.json"
)


def mm(v):
    return v / 1e6


def main():
    board = pcbnew.LoadBoard(BOARD)
    pads = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            if not pad.IsOnLayer(pcbnew.F_Cu):
                continue
            pos = pad.GetPosition()
            sz = pad.GetSize()
            rad = math.radians(pad.GetOrientation().AsDegrees())
            c, s = abs(math.cos(rad)), abs(math.sin(rad))
            sx, sy = mm(sz.x), mm(sz.y)
            hx = (sx * c + sy * s) / 2
            hy = (sx * s + sy * c) / 2
            pads.append(
                {
                    "ref": ref,
                    "pad": str(pad.GetPadName()),
                    "net": pad.GetNetname(),
                    "x0": mm(pos.x) - hx,
                    "x1": mm(pos.x) + hx,
                    "y0": mm(pos.y) - hy,
                    "y1": mm(pos.y) + hy,
                }
            )
    with open(OUT, "w") as f:
        json.dump(pads, f, indent=1)
    print(f"wrote {len(pads)} pads to {OUT}")


main()
