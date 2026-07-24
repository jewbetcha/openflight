"""Dump F.Cu geometry from the authoritative Rev C RF board as JSON.

Run with KiCad's bundled Python (pcbnew), not the project venv:

    PYTHONPATH="$KICAD_SITE" "$KICAD_PY" dump_board_geometry.py [board] [out.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
DEFAULT_BOARD = HERE.parent / "openflight-24ghz-fmcw-rf-rev-c.kicad_pcb"


def to_mm(nm: int) -> float:
    return pcbnew.ToMM(nm)


def main() -> int:
    board_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_BOARD
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    board = pcbnew.LoadBoard(str(board_path))

    tracks = []
    for track in board.GetTracks():
        is_via = isinstance(track, pcbnew.PCB_VIA)
        item = {
            "kind": "via" if is_via else "track",
            "net": track.GetNetname(),
            "layer": board.GetLayerName(track.GetLayer()),
            "width_mm": to_mm(track.GetWidth(pcbnew.F_Cu) if is_via else track.GetWidth()),
        }
        if is_via:
            item["x_mm"] = to_mm(track.GetPosition().x)
            item["y_mm"] = to_mm(track.GetPosition().y)
            item["drill_mm"] = to_mm(track.GetDrill())
        else:
            item["x0_mm"] = to_mm(track.GetStart().x)
            item["y0_mm"] = to_mm(track.GetStart().y)
            item["x1_mm"] = to_mm(track.GetEnd().x)
            item["y1_mm"] = to_mm(track.GetEnd().y)
        tracks.append(item)

    zones = []
    for zone in board.Zones():
        outline = zone.Outline()
        polygons = []
        for poly_index in range(outline.OutlineCount()):
            points = []
            poly = outline.Outline(poly_index)
            for vertex_index in range(poly.PointCount()):
                vertex = poly.GetPoint(vertex_index)
                points.append([to_mm(vertex.x), to_mm(vertex.y)])
            polygons.append(points)
        zones.append(
            {
                "net": zone.GetNetname(),
                "layer": board.GetLayerName(zone.GetFirstLayer()),
                "priority": zone.GetAssignedPriority(),
                "clearance_mm": to_mm(zone.GetLocalClearance()),
                "outlines": polygons,
            }
        )

    pads = []
    for footprint in board.GetFootprints():
        reference = footprint.GetReference()
        fp_pos = footprint.GetPosition()
        for pad in footprint.Pads():
            pos = pad.GetPosition()
            size = pad.GetSize()
            pads.append(
                {
                    "ref": reference,
                    "pad": pad.GetNumber(),
                    "net": pad.GetNetname(),
                    "x_mm": to_mm(pos.x),
                    "y_mm": to_mm(pos.y),
                    "w_mm": to_mm(size.x),
                    "h_mm": to_mm(size.y),
                    "layers": [board.GetLayerName(layer) for layer in pad.GetLayerSet().Seq()],
                    "fp_x_mm": to_mm(fp_pos.x),
                    "fp_y_mm": to_mm(fp_pos.y),
                }
            )

    # Board outline from Edge.Cuts
    edge_segments = []
    for drawing in board.GetDrawings():
        if drawing.GetLayerName() != "Edge.Cuts":
            continue
        edge_segments.append(
            {
                "shape": drawing.GetShape() if hasattr(drawing, "GetShape") else None,
                "x0_mm": to_mm(drawing.GetStart().x),
                "y0_mm": to_mm(drawing.GetStart().y),
                "x1_mm": to_mm(drawing.GetEnd().x),
                "y1_mm": to_mm(drawing.GetEnd().y),
            }
        )

    data = {
        "board": str(board_path),
        "tracks": tracks,
        "zones": zones,
        "pads": pads,
        "edge_cuts": edge_segments,
    }
    text = json.dumps(data)
    if out_path:
        out_path.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out_path}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
