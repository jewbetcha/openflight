import ast
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTING_DIR = (
    ROOT
    / "hardware"
    / "24ghz-adf590x-fmcw-rev-c"
    / "rf-board"
    / "kicad"
    / "scratchpad"
)


def load_route_plan():
    spec = importlib.util.spec_from_file_location(
        "revc_rf_route_plan", ROUTING_DIR / "rf_route_plan.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_rx_feed_routes_use_the_simulated_feed_endpoints():
    route_plan = load_route_plan()
    routes = route_plan.build_rx_feed_routes()

    assert routes["RX1"][0] == route_plan.Point(5.512, 5.547178)
    assert routes["RX2"][0] == route_plan.Point(18.012, 5.547178)
    assert routes["RX3"][0] == route_plan.Point(10.988, 44.452822)
    assert routes["RX4"][0] == route_plan.Point(23.488, 44.452822)


def test_rx_feed_routes_end_at_the_rf_dc_block_pads_and_are_length_matched():
    route_plan = load_route_plan()
    routes = route_plan.build_rx_feed_routes()

    assert routes["RX1"][-1] == route_plan.Point(32.75, 20.27)
    assert routes["RX2"][-1] == route_plan.Point(30.75, 20.27)
    assert routes["RX3"][-1] == route_plan.Point(32.75, 29.73)
    assert routes["RX4"][-1] == route_plan.Point(30.75, 29.73)

    lengths = {name: route_plan.polyline_length(points) for name, points in routes.items()}
    assert max(lengths.values()) - min(lengths.values()) <= 0.5


def test_rx_feed_routes_use_only_orthogonal_or_45_degree_segments():
    route_plan = load_route_plan()

    for points in route_plan.build_rx_feed_routes().values():
        for start, end in zip(points, points[1:]):
            delta_x = abs(end.x_mm - start.x_mm)
            delta_y = abs(end.y_mm - start.y_mm)
            assert delta_x == 0 or delta_y == 0 or abs(delta_x - delta_y) < 1e-6


def test_rx_feed_routes_hold_board_edge_clearance():
    route_plan = load_route_plan()

    for points in route_plan.build_rx_feed_routes().values():
        assert min(point.y_mm for point in points) >= 0.65
        assert max(point.y_mm for point in points) <= 49.35


def test_tx_feed_route_uses_the_simulated_feed_endpoint_and_dc_block_pad():
    route_plan = load_route_plan()
    route = route_plan.build_tx_feed_route()

    assert route[0] == route_plan.Point(57.238, 18.702822)
    assert route[-1] == route_plan.Point(55.48, 24.25)
    for start, end in zip(route, route[1:]):
        delta_x = abs(end.x_mm - start.x_mm)
        delta_y = abs(end.y_mm - start.y_mm)
        assert delta_x == 0 or delta_y == 0 or abs(delta_x - delta_y) < 1e-6


def test_loop_filter_route_plan_matches_validated_topology():
    route_plan = load_route_plan()
    routes = route_plan.build_loop_filter_routes()

    assert {route.net_name for route in routes} == {
        "Net-(U4-CP)",
        "Net-(C34-Pad2)",
        "Net-(C35-Pad1)",
        "VTUNE",
    }

    cp_route = next(route for route in routes if route.net_name == "Net-(U4-CP)")
    assert cp_route.points[0] == route_plan.Point(46.75, 31.75)  # U4.24
    assert route_plan.Point(46.99, 33.5) in cp_route.points  # R21.2
    assert route_plan.Point(49.25, 33.98) in cp_route.points  # C33.1
    assert cp_route.points[-1] == route_plan.Point(52.0, 32.48)  # C34.1

    final_node_routes = [
        route for route in routes if route.net_name == "Net-(C35-Pad1)"
    ]
    assert {route.layer for route in final_node_routes} == {"F.Cu", "B.Cu"}
    assert final_node_routes[0].points[0] == route_plan.Point(48.01, 33.5)  # R21.1
    assert final_node_routes[-1].points[-1] == route_plan.Point(52.5, 29.73)  # C35.1

    vias = route_plan.build_loop_filter_vias()
    assert vias == (
        route_plan.PlannedVia("Net-(C35-Pad1)", route_plan.Point(49.4, 32.2)),
        route_plan.PlannedVia("Net-(C35-Pad1)", route_plan.Point(51.5, 30.4)),
    )


def test_board_generator_classifies_current_loop_filter_nets():
    source = (ROUTING_DIR / "build_rf_board.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    pll_nets = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "pll_nets" for target in node.targets):
            continue
        pll_nets = {
            item.value
            for item in node.value.elts
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        }
        break

    assert pll_nets is not None
    assert "Net-(C34-Pad2)" in pll_nets
    assert "Net-(C35-Pad1)" in pll_nets
    assert "Net-(C33-Pad1)" not in pll_nets
    assert "Net-(C34-Pad1)" not in pll_nets


def test_board_generator_orients_c35_final_node_toward_r23():
    source = (ROUTING_DIR / "build_rf_board.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    c35_placement = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "FIXED_PASSIVE_PLACEMENTS"
            for target in node.targets
        ):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if isinstance(key, ast.Constant) and key.value == "C35":
                c35_placement = tuple(ast.literal_eval(argument) for argument in value.args)
                break

    assert c35_placement == (52.5, 29.25, 90.0)
