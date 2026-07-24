from __future__ import annotations

import importlib.util
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_module():
    path = HERE / "tx_array_2x2.py"
    spec = importlib.util.spec_from_file_location("revc_tx_array_2x2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def passing_subarray() -> dict:
    return {
        "port_s11_db": {"band_max_24.15_24.25": -16.5},
        "phase_balance_deg_max": 2.5,
        "gain_dbi_est": 10.5,
        "far_field_validation": {"valid": True},
        "far_field_pattern": {"beam_offset_deg": 1.0, "phi_peak_deg": 90.0},
        "acceptance": {"s11": True, "phase": True, "gain": True},
    }


def test_tx_result_uses_reciprocal_as_built_array_evidence() -> None:
    result = load_module().build_tx_result(passing_subarray(), pa_dbm=8.0)

    assert result["architecture"] == "as_built_2x2_corporate_fed_patch_array"
    assert result["validation_basis"] == "electromagnetic_reciprocity"
    assert result["gain_dbi_est"] == 10.5
    assert result["eirp_check"]["eirp_dbm"] == 18.5
    assert result["acceptance"] == {
        "s11": True,
        "gain": True,
        "beam": True,
        "eirp_review": True,
        "overall": True,
    }


def test_tx_result_fails_closed_without_valid_far_field() -> None:
    subarray = passing_subarray()
    subarray["far_field_validation"] = {"valid": False}

    result = load_module().build_tx_result(subarray, pa_dbm=8.0)

    assert result["acceptance"]["gain"] is False
    assert result["acceptance"]["beam"] is False
    assert result["acceptance"]["overall"] is False
