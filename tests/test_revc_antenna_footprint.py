import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANTENNA_DIR = ROOT / "hardware" / "24ghz-adf590x-fmcw-rev-c" / "antenna"


def load_module(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ANTENNA_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def geometry_result():
    geometry = load_module("subarray_geometry.py", "revc_subarray_geometry_for_footprint")
    element = geometry.load_default_element(ANTENNA_DIR)
    return geometry.build_fallback_geometry(element, l_trim_mm=-0.05)


def test_generated_subarray_has_expected_copper_primitives():
    generator = load_module("geometry_to_footprint.py", "revc_geometry_to_footprint")
    rectangles = generator.subarray_rectangles(geometry_result())
    tags = {rectangle.tag for rectangle in rectangles}

    assert len(rectangles) == 28
    assert {f"patch_{patch}_body" for patch in ("TL", "TR", "BL", "BR")} <= tags
    assert "root_branch_left_0" in tags
    assert "root_branch_right_0" in tags
    assert "root_transformer_0" in tags
    assert "root_feed_50" in tags


def test_generated_patch_body_dimensions_match_geometry_to_one_micron():
    generator = load_module("geometry_to_footprint.py", "revc_geometry_to_footprint_dims")
    result = geometry_result()
    rectangles = {rectangle.tag: rectangle for rectangle in generator.subarray_rectangles(result)}
    top_left = result["patches"]["TL"]
    body = rectangles["patch_TL_body"]

    assert round(body.width_mm - (top_left["x_max"] - top_left["x_inset_end"]), 6) == 0.0
    assert round(body.height_mm - (top_left["y_max"] - top_left["y_min"]), 6) == 0.0


def test_rendered_footprint_emits_every_rectangle_as_exposed_copper():
    generator = load_module("geometry_to_footprint.py", "revc_geometry_to_footprint_render")
    result = geometry_result()
    rectangles = generator.subarray_rectangles(result)
    rendered = generator.render_footprint("RX_SUBARRAY_2X2", result)

    assert rendered.count('(pad "1" smd rect') == len(rectangles)
    assert rendered.count('(layers "F.Cu" "F.Mask")') == len(rectangles)
    assert rendered.count("(solder_mask_margin 0.08)") == len(rectangles)
    assert '(layer "F.CrtYd")' not in rendered


def test_failing_result_is_rejected_before_generation():
    generator = load_module("geometry_to_footprint.py", "revc_geometry_to_footprint_gate")
    result = json.loads((ANTENNA_DIR / "results" / "subarray.json").read_text(encoding="utf-8"))
    result["acceptance"]["phase"] = False

    try:
        generator.validate_result(result)
    except RuntimeError as error:
        assert "phase" in str(error)
    else:
        raise AssertionError("expected the synthetic phase failure to be rejected")


def test_result_with_invalid_far_field_is_rejected_before_generation():
    generator = load_module("geometry_to_footprint.py", "revc_geometry_to_footprint_pass")
    result = json.loads((ANTENNA_DIR / "results" / "subarray.json").read_text(encoding="utf-8"))
    result["far_field_validation"]["valid"] = False
    result["acceptance"]["gain"] = False

    try:
        generator.validate_result(result)
    except RuntimeError as error:
        assert "gain" in str(error)
    else:
        raise AssertionError("expected the invalid far-field gain gate to be rejected")
