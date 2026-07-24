#!/usr/bin/env python3
"""Render F.Cu geometry of the Rev C RF board for expert-review mapping."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = Path(__file__).resolve().parent
DATA = HERE / "board-geometry.json"

RF_NETS = {
    "RX1", "RX2", "RX3", "RX4", "TX_ANT", "LO_OUT", "RFIN_DIV",
    "Net-(U6-LO_IN)", "Net-(U5-TXOUT1)", "Net-(U5-TXOUT2)", "Net-(U5-LOOUT)",
    "Net-(U4-RFinA)", "Net-(U4-RFinB)", "Net-(C53-Pad2)",
    "Net-(U6-RX1_RF)", "Net-(U6-RX2_RF)", "Net-(U6-RX3_RF)", "Net-(U6-RX4_RF)",
}


def main() -> int:
    data = json.loads(DATA.read_text())
    fig, ax = plt.subplots(figsize=(20, 12))

    # Board outline
    for seg in data["edge_cuts"]:
        ax.plot([seg["x0_mm"], seg["x1_mm"]], [seg["y0_mm"], seg["y1_mm"]], "k-", lw=2)

    # Antenna pads (F.Cu rects)
    for pad in data["pads"]:
        if "F.Cu" not in pad["layers"]:
            continue
        color = "red" if pad["ref"].startswith(("ANT", "A")) else "lightcoral"
        ax.add_patch(
            Rectangle(
                (pad["x_mm"] - pad["w_mm"] / 2, pad["y_mm"] - pad["h_mm"] / 2),
                pad["w_mm"],
                pad["h_mm"],
                facecolor=color,
                edgecolor="none",
                alpha=0.9,
            )
        )

    # F.Cu tracks
    for track in data["tracks"]:
        if track["kind"] != "track" or track["layer"] != "F.Cu":
            continue
        if track["net"] in RF_NETS:
            color, lw = "blue", 1.6
        elif track["net"] == "GND":
            color, lw = "green", 1.0
        else:
            color, lw = "gray", 0.5
        ax.plot(
            [track["x0_mm"], track["x1_mm"]],
            [track["y0_mm"], track["y1_mm"]],
            color=color,
            lw=lw,
            solid_capstyle="round",
        )

    # F.Cu zone outlines
    for zone in data["zones"]:
        if zone["layer"] != "F.Cu":
            continue
        for outline in zone["outlines"]:
            xs = [p[0] for p in outline] + [outline[0][0]]
            ys = [p[1] for p in outline] + [outline[0][1]]
            ax.plot(xs, ys, "g--", lw=1.0)

    # RF net labels at segment midpoints (only first segment per net)
    seen = set()
    for track in data["tracks"]:
        if track["kind"] != "track" or track["layer"] != "F.Cu" or track["net"] not in RF_NETS:
            continue
        if track["net"] in seen:
            continue
        seen.add(track["net"])
        ax.annotate(
            track["net"],
            ((track["x0_mm"] + track["x1_mm"]) / 2, (track["y0_mm"] + track["y1_mm"]) / 2),
            fontsize=6,
            color="blue",
        )

    ax.set_xlim(-2, 84)
    ax.set_ylim(52, -2)
    ax.set_aspect("equal")
    ax.set_title("Rev C RF board F.Cu: blue=RF tracks, red=pads, green=GND")
    ax.grid(True, alpha=0.3)
    fig.savefig(HERE / "fcu-map.png", dpi=110, bbox_inches="tight")

    # Zoom on antenna area (left ~0-35mm)
    ax.set_xlim(-1, 36)
    ax.set_ylim(51, -1)
    fig.savefig(HERE / "fcu-antenna-zoom.png", dpi=150, bbox_inches="tight")
    print(f"wrote {HERE/'fcu-map.png'} and fcu-antenna-zoom.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
