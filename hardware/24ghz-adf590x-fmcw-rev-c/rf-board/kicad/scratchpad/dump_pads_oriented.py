#!/usr/bin/env python3
"""Dump pad bboxes with rotation applied, for a region of interest."""
import math
import sys

import pcbnew

BOARD = (
    "/Users/colemanrollins/code/openflight/hardware/24ghz-adf590x-fmcw-rev-c/"
    "rf-board/kicad/openflight-24ghz-fmcw-rf-rev-c.kicad_pcb"
)


def nm(v):
    return v / 1e6


def main():
    x0, x1, y0, y1 = (float(a) for a in sys.argv[1:5])
    board = pcbnew.LoadBoard(BOARD)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            if not pad.IsOnLayer(pcbnew.F_Cu):
                continue
            pos = pad.GetPosition()
            sz = pad.GetSize()
            deg = pad.GetOrientation().AsDegrees()
            rad = math.radians(deg)
            c, s = abs(math.cos(rad)), abs(math.sin(rad))
            hx = (sz.x * c + sz.y * s) / 2
            hy = (sz.x * s + sz.y * c) / 2
            xa, xb = nm(pos.x) - hx, nm(pos.x) + hx
            ya, yb = nm(pos.y) - hy, nm(pos.y) + hy
            if xb < x0 or xa > x1 or yb < y0 or ya > y1:
                continue
            shape = pad.GetShape()
            print(
                f"{ref:5s} pad {pad.GetPadName():3s} {pad.GetNetname():16s} "
                f"x[{xa:6.2f},{xb:6.2f}] y[{ya:6.2f},{yb:6.2f}] "
                f"shape={shape} size=({nm(sz.x):.2f},{nm(sz.y):.2f}) rot={deg}"
            )


main()
