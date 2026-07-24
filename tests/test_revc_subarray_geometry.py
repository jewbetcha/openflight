import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANTENNA_DIR = ROOT / "hardware" / "24ghz-adf590x-fmcw-rev-c" / "antenna"


def load_geometry_module():
    spec = importlib.util.spec_from_file_location(
        "revc_subarray_geometry",
        ANTENNA_DIR / "subarray_geometry.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_fallback_feed_removes_column_transformers_and_meander():
    geometry = load_geometry_module()
    element = geometry.load_default_element(ANTENNA_DIR)

    design = geometry.build_fallback_geometry(element, l_trim_mm=-0.05)
    segment_names = {segment["seg"] for segment in design["feed_tree"]}

    assert "root_qw" in segment_names
    assert "col_qw_left" not in segment_names
    assert "col_qw_right" not in segment_names
    assert "right_meander_50" not in segment_names
    assert design["element_target_z_ohm"] == 100.0


def test_fallback_root_launch_is_clear_of_patch_copper():
    geometry = load_geometry_module()
    element = geometry.load_default_element(ANTENNA_DIR)

    design = geometry.build_fallback_geometry(element, l_trim_mm=-0.05)

    assert max(design["path_length_mm"].values()) - min(design["path_length_mm"].values()) < 0.01
    assert design["clearance_checks"]["root_qw_clear_of_patch_copper"]
    assert design["clearance_checks"]["root_feed_clear_of_patch_copper"]
    assert design["clearance_checks"]["root_branches_clear_of_patch_copper"]


def test_fallback_uses_symmetric_root_below_array():
    geometry = load_geometry_module()
    element = geometry.load_default_element(ANTENNA_DIR)

    design = geometry.build_fallback_geometry(element, l_trim_mm=-0.05)

    assert design["delay_routes"]["right_column"] is None
    assert design["root"]["y_mm"] < min(patch["y_min"] for patch in design["patches"].values())
    assert max(design["path_length_mm"].values()) - min(design["path_length_mm"].values()) < 0.01


def test_fallback_column_routes_are_mirrored_below_patch_copper():
    geometry = load_geometry_module()
    element = geometry.load_default_element(ANTENNA_DIR)

    design = geometry.build_fallback_geometry(element, l_trim_mm=-0.05)
    root = design["root"]
    left = design["root_branch_routes"]["left"]
    right = design["root_branch_routes"]["right"]
    bottom_patch_edge = min(patch["y_min"] for patch in design["patches"].values())
    feed_half_width = design["patch"]["feed_w_mm"] / 2.0

    assert left[0] == [design["column_junctions"]["left"]["x_mm"], 0.0]
    assert right[0] == [design["column_junctions"]["right"]["x_mm"], 0.0]
    assert left[-1] == right[-1] == [root["x_mm"], root["y_mm"]]
    assert root["y_mm"] + feed_half_width < bottom_patch_edge
    assert root["qw_route"] == [
        [root["x_mm"], root["y_mm"]],
        [root["x_mm"], root["y_qw_end_mm"]],
    ]
    assert root["x_port_mm"] == root["x_mm"]
    assert design["root"]["y_port_mm"] < design["root"]["y_qw_end_mm"]


def test_root_routes_leave_column_junctions_without_overlapping_element_trunks():
    geometry = load_geometry_module()
    element = geometry.load_default_element(ANTENNA_DIR)

    design = geometry.build_fallback_geometry(element, l_trim_mm=-0.05)
    left_x = design["column_junctions"]["left"]["x_mm"]
    right_x = design["column_junctions"]["right"]["x_mm"]
    left = design["root_branch_routes"]["left"]
    right = design["root_branch_routes"]["right"]

    assert left[1][1] == right[1][1] == 0.0
    assert left[1][0] != left_x
    assert right[1][0] != right_x

    def route_length(points):
        return sum(abs(x1 - x0) + abs(y1 - y0) for (x0, y0), (x1, y1) in zip(points, points[1:]))

    left_length = route_length(left)
    right_length = route_length(right)
    assert abs(left_length - right_length) < 0.01
    assert design["root_branch_length_mm"] == {
        "left": left_length,
        "right": right_length,
    }


def test_far_field_rejects_near_zero_radiated_power():
    geometry = load_geometry_module()

    result = geometry.assess_far_field(
        radiated_power_w=1.76659621e-27,
        accepted_power_w=0.5,
        directivity_linear=190.06836444,
        angular_grid_complete=True,
    )

    assert not result["valid"]
    assert result["radiation_efficiency"] < 1e-20
    assert "radiated power" in result["reason"]


def test_far_field_accepts_plausible_power_balance():
    geometry = load_geometry_module()

    result = geometry.assess_far_field(
        radiated_power_w=0.35,
        accepted_power_w=0.5,
        directivity_linear=12.0,
        angular_grid_complete=True,
    )

    assert result["valid"]
    assert result["radiation_efficiency"] == 0.7
