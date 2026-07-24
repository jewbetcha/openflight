import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ANTENNA_DIR = ROOT / "hardware" / "24ghz-adf590x-fmcw-rev-c" / "antenna"


def load_module(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ANTENNA_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def subarray_geometry():
    geometry = load_module("subarray_geometry.py", "revc_subarray_geometry_for_grid")
    element = geometry.load_default_element(ANTENNA_DIR)
    return geometry.build_fallback_geometry(element, l_trim_mm=-0.05)


def test_grid_phase_centers_and_rotations_are_frozen():
    grid = load_module("grid_geometry.py", "revc_grid_geometry")
    result = grid.build_grid_geometry(subarray_geometry())

    assert result["pitch_mm"] == 12.5
    assert result["phase_centers"] == [
        {"channel": "RX1", "x_mm": -6.25, "y_mm": -6.25, "rotation_deg": 0},
        {"channel": "RX2", "x_mm": 6.25, "y_mm": -6.25, "rotation_deg": 0},
        {"channel": "RX3", "x_mm": -6.25, "y_mm": 6.25, "rotation_deg": 180},
        {"channel": "RX4", "x_mm": 6.25, "y_mm": 6.25, "rotation_deg": 180},
    ]


def test_grid_routes_feeds_outward_without_copper_overlap():
    grid = load_module("grid_geometry.py", "revc_grid_geometry_outward")
    result = grid.build_grid_geometry(subarray_geometry(), clearance_mm=0.2)
    centers = {item["channel"]: item for item in result["phase_centers"]}
    ports = {item["channel"]: item for item in result["feed_ports"]}

    assert ports["RX1"]["y_mm"] < centers["RX1"]["y_mm"]
    assert ports["RX2"]["y_mm"] < centers["RX2"]["y_mm"]
    assert ports["RX3"]["y_mm"] > centers["RX3"]["y_mm"]
    assert ports["RX4"]["y_mm"] > centers["RX4"]["y_mm"]
    assert result["acceptance"]["geometry"]
    assert not result["acceptance"]["coupling"]


def test_grid_simulation_port_extents_are_ordered_for_both_rotations():
    grid = load_module("grid_geometry.py", "revc_grid_geometry_port_extents")
    subarray = subarray_geometry()
    geometry = grid.build_grid_geometry(subarray)

    extents = [
        grid.simulation_port_extent(subarray["root"], placement)
        for placement in geometry["phase_centers"]
    ]

    assert all(extent["y_start_mm"] < extent["y_stop_mm"] for extent in extents)
    assert all(extent["span_mm"] == pytest.approx(5.0) for extent in extents)
    assert extents[0]["feed_direction"] == 1
    assert extents[2]["feed_direction"] == -1


def test_grid_simulation_assigns_each_root_feed_only_to_its_port():
    grid = load_module("grid_geometry.py", "revc_grid_geometry_port_copper")
    subarray = subarray_geometry()
    geometry = grid.build_grid_geometry(subarray)

    shared_copper, port_feeds = grid.split_simulation_rectangles(
        subarray,
        geometry["phase_centers"],
    )

    assert all(rectangle.tag != "root_feed_50" for rectangle in shared_copper)
    assert set(port_feeds) == {"RX1", "RX2", "RX3", "RX4"}
    for placement in geometry["phase_centers"]:
        extent = grid.simulation_port_extent(subarray["root"], placement)
        assert port_feeds[placement["channel"]].bounds == pytest.approx(
            (
                extent["x_mm"] - subarray["patch"]["feed_w_mm"] / 2.0,
                extent["y_start_mm"],
                extent["x_mm"] + subarray["patch"]["feed_w_mm"] / 2.0,
                extent["y_stop_mm"],
            )
        )


def test_grid_simulation_overlaps_each_feed_into_its_patch_notch():
    grid = load_module("grid_geometry.py", "revc_grid_geometry_feed_overlap")
    subarray = subarray_geometry()
    base = {rectangle.tag: rectangle for rectangle in grid.subarray_rectangles(subarray)}
    simulated = {
        rectangle.tag: rectangle
        for rectangle in grid.simulation_subarray_rectangles(subarray)
    }
    overlap_mm = subarray["patch"]["feed_w_mm"] / 4.0

    for tag in ("feed_left_top", "feed_right_top", "feed_left_bottom", "feed_right_bottom"):
        assert simulated[tag].bounds[0] == pytest.approx(base[tag].bounds[0])
        assert simulated[tag].bounds[2] == pytest.approx(base[tag].bounds[2] + overlap_mm)

    assert simulated["patch_TL_body"] == base["patch_TL_body"]
    assert simulated["root_feed_50"] == base["root_feed_50"]


def test_grid_mesh_translation_is_sorted_and_deduplicated():
    grid = load_module("grid_geometry.py", "revc_grid_geometry_mesh_lines")
    placements = [
        {"x_mm": -6.25, "y_mm": -6.25, "rotation_deg": 0},
        {"x_mm": -6.25, "y_mm": 6.25, "rotation_deg": 180},
    ]

    assert grid.translated_mesh_lines([-1.0, 0.0, 1.0], placements, "x") == [
        -7.25,
        -6.25,
        -5.25,
    ]
    assert grid.translated_mesh_lines([-1.0, 0.0, 1.0], placements, "y") == [
        -7.25,
        -6.25,
        -5.25,
        5.25,
        6.25,
        7.25,
    ]


def test_grid_mesh_merges_only_sub_threshold_near_coincident_lines():
    grid = load_module("grid_geometry.py", "revc_grid_geometry_mesh_merge")

    assert grid.merge_close_mesh_lines(
        [0.0, 0.001, 0.004, 0.008], min_spacing_mm=0.0035
    ) == pytest.approx([0.0005, 0.004, 0.008])


def test_grid_coupling_gate_uses_worst_case_across_ports_and_band():
    grid = load_module("grid_geometry.py", "revc_grid_geometry_coupling")
    geometry = grid.build_grid_geometry(subarray_geometry(), clearance_mm=0.2)

    result = grid.apply_coupling_result(
        geometry,
        {
            "RX2": [-24.0, -22.0, -23.0],
            "RX3": [-27.0, -26.0, -25.0],
            "RX4": [-29.0, -28.0, -27.0],
        },
    )

    assert result["coupling_db_max"] == -22.0
    assert result["acceptance"]["coupling"] is True


def test_grid_coupling_gate_fails_at_less_than_twenty_db_isolation():
    grid = load_module("grid_geometry.py", "revc_grid_geometry_coupling_fail")
    geometry = grid.build_grid_geometry(subarray_geometry(), clearance_mm=0.2)

    result = grid.apply_coupling_result(
        geometry,
        {"RX2": [-21.0, -19.9], "RX3": [-25.0], "RX4": [-30.0]},
    )

    assert result["coupling_db_max"] == -19.9
    assert result["acceptance"]["coupling"] is False


def test_grid_convergence_compares_every_band_point_and_channel():
    grid = load_module("grid_geometry.py", "revc_grid_geometry_convergence")
    reference = {
        "port_s11_db": {"24.15": -15.0, "24.20": -16.0, "24.25": -17.0},
        "coupling_db_by_port": {
            "RX2": {"24.15": -30.0, "24.20": -31.0, "24.25": -32.0},
            "RX3": {"24.15": -25.0, "24.20": -26.0, "24.25": -27.0},
        },
    }
    candidate = {
        "port_s11_db": {"24.15": -14.0, "24.20": -17.5, "24.25": -17.0},
        "coupling_db_by_port": {
            "RX2": {"24.15": -31.0, "24.20": -30.0, "24.25": -32.5},
            "RX3": {"24.15": -27.5, "24.20": -26.0, "24.25": -27.0},
        },
    }

    result = grid.compare_grid_results(reference, candidate, max_delta_db=3.0)

    assert result == {
        "s11_max_delta_db": 1.5,
        "coupling_max_delta_db": 2.5,
        "max_delta_db": 3.0,
        "acceptance": True,
    }
