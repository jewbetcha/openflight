#!/usr/bin/env python3
"""Run the grid model with one RX subarray to validate its port implementation."""

from __future__ import annotations

import json
import os

import numpy as np
import sim_grid_coupling as coupling


def main() -> int:
    coupling.GRID = dict(coupling.GRID)
    coupling.GRID["phase_centers"] = [coupling.GRID["phase_centers"][0]]

    sim_path = os.environ.get(
        "SIM_OUT_DIR",
        os.path.join(coupling.HERE, "results", "grid_single_sanity"),
    )
    os.makedirs(sim_path, exist_ok=True)
    fdtd, ports, domain = coupling.build()
    if not os.environ.get("SKIP_SIM"):
        fdtd.Run(sim_path, verbose=1, cleanup=True)

    frequencies_hz = np.linspace(coupling.F_START, coupling.F_STOP, 401)
    ports[0].CalcPort(sim_path, frequencies_hz, ref_impedance=50)
    s11_db = 20.0 * np.log10(np.abs(ports[0].uf_ref / ports[0].uf_inc))
    band = (frequencies_hz >= 24.150e9) & (frequencies_hz <= 24.250e9)
    band_max_s11_db = float(np.max(s11_db[band]))
    candidate_s11_db = {
        frequency: coupling.at(float(frequency) * 1e9, frequencies_hz, s11_db)
        for frequency in ("24.15", "24.20", "24.25")
    }
    source_s11_db = {
        frequency: float(coupling.SUBARRAY["port_s11_db"][frequency])
        for frequency in candidate_s11_db
    }
    max_point_delta_db = max(
        abs(candidate_s11_db[frequency] - source_s11_db[frequency])
        for frequency in candidate_s11_db
    )
    result = {
        "model": "grid_port_single_rx1_sanity",
        "band_max_s11_db": band_max_s11_db,
        "s11_db": candidate_s11_db,
        "source_subarray_s11_db": source_s11_db,
        "source_subarray_band_max_s11_db": coupling.SUBARRAY["port_s11_db"][
            "band_max_24.15_24.25"
        ],
        "max_point_delta_db": max_point_delta_db,
        "acceptance": {
            "s11": band_max_s11_db <= -10.0,
            "agrees_with_source_within_db": max_point_delta_db <= 3.0,
        },
        "simulation": {
            "reused_time_domain_data": bool(os.environ.get("SKIP_SIM")),
            "data_directory": os.path.relpath(sim_path, coupling.HERE),
            "mesh_div": coupling.MESH_DIV,
            "end_criteria": coupling.END_CRIT,
            "max_timesteps": coupling.MAX_TIMESTEPS,
            "domain": domain,
        },
    }
    output = os.path.join(coupling.HERE, "results", "grid_single_sanity.json")
    with open(output, "w", encoding="utf-8") as file:
        json.dump(result, file, indent=2)
        file.write("\n")
    print(f"single-grid-port S11 worst-band = {band_max_s11_db:.2f} dB")
    print(f"source subarray S11 worst-band = {result['source_subarray_band_max_s11_db']:.2f} dB")
    print(f"results -> {output}")
    return 0 if all(result["acceptance"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
