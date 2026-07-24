#!/usr/bin/env python3
"""Freeze the as-built TX 2x2 array from reciprocal full-wave evidence."""

from __future__ import annotations

import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "results" / "subarray.json"
OUTPUT = HERE / "results" / "tx_array_2x2.json"


def build_tx_result(subarray: dict, *, pa_dbm: float = 8.0) -> dict:
    """Apply TX-specific gain, beam, and EIRP gates to the identical RX copper."""
    far_field_valid = bool(subarray.get("far_field_validation", {}).get("valid"))
    source_acceptance = subarray.get("acceptance", {})
    gain_dbi = subarray.get("gain_dbi_est")
    pattern = subarray.get("far_field_pattern", {})
    beam_offset_deg = pattern.get("beam_offset_deg")

    s11_accept = bool(source_acceptance.get("s11"))
    gain_accept = bool(
        far_field_valid
        and gain_dbi is not None
        and 10.0 <= float(gain_dbi) <= 12.0
    )
    beam_accept = bool(
        far_field_valid
        and beam_offset_deg is not None
        and float(beam_offset_deg) <= 3.0
    )
    eirp_dbm = None if gain_dbi is None else pa_dbm + float(gain_dbi)
    eirp_review = bool(eirp_dbm is not None and eirp_dbm <= 20.0)
    overall = s11_accept and gain_accept and beam_accept and eirp_review

    return {
        "architecture": "as_built_2x2_corporate_fed_patch_array",
        "validation_basis": "electromagnetic_reciprocity",
        "source_result": "subarray.json",
        "source_copper_identity": "TX_ARRAY_2X2 and RX_SUBARRAY_2X2 are generated from the same rectangles",
        "port_s11_db": subarray.get("port_s11_db"),
        "phase_balance_deg_max": subarray.get("phase_balance_deg_max"),
        "gain_dbi_est": gain_dbi,
        "far_field_validation": subarray.get("far_field_validation"),
        "far_field_pattern": pattern,
        "eirp_check": {
            "pa_dbm_typ": pa_dbm,
            "gain_dbi": gain_dbi,
            "eirp_dbm": eirp_dbm,
            "exceeds_20dbm": bool(eirp_dbm is not None and eirp_dbm > 20.0),
        },
        "acceptance": {
            "s11": s11_accept,
            "gain": gain_accept,
            "beam": beam_accept,
            "eirp_review": eirp_review,
            "overall": overall,
        },
    }


def main() -> int:
    subarray = json.loads(SOURCE.read_text(encoding="utf-8"))
    result = build_tx_result(subarray)
    OUTPUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT}")
    return 0 if result["acceptance"]["overall"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
