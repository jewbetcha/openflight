from __future__ import annotations

import argparse
import heapq
import json
import math
from dataclasses import dataclass
from pathlib import Path

import pcbnew


LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu, pcbnew.In2_Cu)
LAYER_NAMES = ("F.Cu", "B.Cu", "In2.Cu")
MOVES = (
    (-1, 0),
    (-1, -1),
    (0, -1),
    (1, -1),
    (1, 0),
    (1, 1),
    (0, 1),
    (-1, 1),
)


@dataclass(frozen=True)
class Terminal:
    reference: str
    pad_number: str
    x: float
    y: float
    route_x: float
    route_y: float
    lead: tuple[tuple[float, float], ...]
    layer: int


def mm(value: int) -> float:
    return value / 1_000_000.0


def iu(value: float) -> int:
    return pcbnew.FromMM(value)


def point_segment_distance(
    px: float, py: float, ax: float, ay: float, bx: float, by: float
) -> float:
    dx = bx - ax
    dy = by - ay
    if dx == 0.0 and dy == 0.0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class ClearanceMap:
    def __init__(
        self,
        board: pcbnew.BOARD,
        target_net: str,
        step: float,
        trace_width: float,
        clearance: float,
        via_diameter: float,
        edge_clearance: float,
    ) -> None:
        bbox = board.GetBoardEdgesBoundingBox()
        self.x0 = mm(bbox.GetX())
        self.y0 = mm(bbox.GetY())
        self.step = step
        self.nx = math.floor(mm(bbox.GetWidth()) / step) + 1
        self.ny = math.floor(mm(bbox.GetHeight()) / step) + 1
        size = self.nx * self.ny
        self.blocked = [bytearray(size) for _ in LAYERS]
        self.via_blocked = bytearray(size)
        self.trace_radius = trace_width / 2.0
        self.via_radius = via_diameter / 2.0
        self.clearance = clearance
        self._mark_edges(edge_clearance)
        self._mark_board(board, target_net)

    def index(self, x: int, y: int) -> int:
        return y * self.nx + x

    def coordinate(self, x: int, y: int) -> tuple[float, float]:
        return self.x0 + x * self.step, self.y0 + y * self.step

    def grid(self, x: float, y: float) -> tuple[int, int]:
        return round((x - self.x0) / self.step), round((y - self.y0) / self.step)

    def _mark_edges(self, edge_clearance: float) -> None:
        track_margin = edge_clearance + self.trace_radius
        via_margin = edge_clearance + self.via_radius
        for y in range(self.ny):
            for x in range(self.nx):
                px, py = self.coordinate(x, y)
                edge_distance = min(
                    px - self.x0,
                    py - self.y0,
                    self.x0 + (self.nx - 1) * self.step - px,
                    self.y0 + (self.ny - 1) * self.step - py,
                )
                idx = self.index(x, y)
                if edge_distance < track_margin:
                    for layer in self.blocked:
                        layer[idx] = 1
                if edge_distance < via_margin:
                    self.via_blocked[idx] = 1

    def _range(self, low: float, high: float, origin: float, count: int) -> range:
        first = max(0, math.floor((low - origin) / self.step))
        last = min(count - 1, math.ceil((high - origin) / self.step))
        return range(first, last + 1)

    def _mark_circle(self, layer_indexes: tuple[int, ...], cx: float, cy: float, radius: float) -> None:
        xs = self._range(cx - radius, cx + radius, self.x0, self.nx)
        ys = self._range(cy - radius, cy + radius, self.y0, self.ny)
        radius_sq = radius * radius
        for y in ys:
            for x in xs:
                px, py = self.coordinate(x, y)
                if (px - cx) ** 2 + (py - cy) ** 2 <= radius_sq:
                    idx = self.index(x, y)
                    for layer_index in layer_indexes:
                        self.blocked[layer_index][idx] = 1

    def _mark_via_circle(self, cx: float, cy: float, radius: float) -> None:
        xs = self._range(cx - radius, cx + radius, self.x0, self.nx)
        ys = self._range(cy - radius, cy + radius, self.y0, self.ny)
        radius_sq = radius * radius
        for y in ys:
            for x in xs:
                px, py = self.coordinate(x, y)
                if (px - cx) ** 2 + (py - cy) ** 2 <= radius_sq:
                    self.via_blocked[self.index(x, y)] = 1

    def _mark_segment(
        self,
        layer_index: int,
        ax: float,
        ay: float,
        bx: float,
        by: float,
        radius: float,
    ) -> None:
        xs = self._range(min(ax, bx) - radius, max(ax, bx) + radius, self.x0, self.nx)
        ys = self._range(min(ay, by) - radius, max(ay, by) + radius, self.y0, self.ny)
        for y in ys:
            for x in xs:
                px, py = self.coordinate(x, y)
                if point_segment_distance(px, py, ax, ay, bx, by) <= radius:
                    self.blocked[layer_index][self.index(x, y)] = 1

    def _mark_via_segment(
        self, ax: float, ay: float, bx: float, by: float, radius: float
    ) -> None:
        xs = self._range(min(ax, bx) - radius, max(ax, bx) + radius, self.x0, self.nx)
        ys = self._range(min(ay, by) - radius, max(ay, by) + radius, self.y0, self.ny)
        for y in ys:
            for x in xs:
                px, py = self.coordinate(x, y)
                if point_segment_distance(px, py, ax, ay, bx, by) <= radius:
                    self.via_blocked[self.index(x, y)] = 1

    def _mark_rect(
        self, layer_indexes: tuple[int, ...], x1: float, y1: float, x2: float, y2: float, margin: float
    ) -> None:
        xs = self._range(x1 - margin, x2 + margin, self.x0, self.nx)
        ys = self._range(y1 - margin, y2 + margin, self.y0, self.ny)
        for y in ys:
            for x in xs:
                idx = self.index(x, y)
                for layer_index in layer_indexes:
                    self.blocked[layer_index][idx] = 1

    def _mark_via_rect(self, x1: float, y1: float, x2: float, y2: float, margin: float) -> None:
        xs = self._range(x1 - margin, x2 + margin, self.x0, self.nx)
        ys = self._range(y1 - margin, y2 + margin, self.y0, self.ny)
        for y in ys:
            for x in xs:
                self.via_blocked[self.index(x, y)] = 1

    def _mark_board(self, board: pcbnew.BOARD, target_net: str) -> None:
        route_margin = self.clearance + self.trace_radius
        via_margin = self.clearance + self.via_radius

        for item in board.GetTracks():
            if item.GetNetname() == target_net:
                continue
            if isinstance(item, pcbnew.PCB_VIA):
                pos = item.GetPosition()
                radius = mm(item.GetWidth(LAYERS[0])) / 2.0
                cx, cy = mm(pos.x), mm(pos.y)
                self._mark_circle(tuple(range(len(LAYERS))), cx, cy, radius + route_margin)
                self._mark_via_circle(cx, cy, radius + via_margin)
                continue
            layer = item.GetLayer()
            if layer not in LAYERS:
                continue
            a = item.GetStart()
            b = item.GetEnd()
            track_radius = mm(item.GetWidth()) / 2.0
            layer_index = LAYERS.index(layer)
            self._mark_segment(
                layer_index,
                mm(a.x),
                mm(a.y),
                mm(b.x),
                mm(b.y),
                track_radius + route_margin,
            )
            self._mark_via_segment(
                mm(a.x),
                mm(a.y),
                mm(b.x),
                mm(b.y),
                track_radius + via_margin,
            )

        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                if pad.GetNetname() == target_net:
                    continue
                bbox = pad.GetBoundingBox()
                x1 = mm(bbox.GetX())
                y1 = mm(bbox.GetY())
                x2 = x1 + mm(bbox.GetWidth())
                y2 = y1 + mm(bbox.GetHeight())
                layer_indexes = tuple(
                    index for index, layer in enumerate(LAYERS) if pad.IsOnLayer(layer)
                )
                if layer_indexes:
                    self._mark_rect(layer_indexes, x1, y1, x2, y2, route_margin)
                    self._mark_via_rect(x1, y1, x2, y2, via_margin)


def terminals_for(board: pcbnew.BOARD, net_name: str, specs: list[str]) -> list[Terminal]:
    by_reference = {fp.GetReference(): fp for fp in board.GetFootprints()}
    terminals: list[Terminal] = []
    for spec in specs:
        if spec.startswith("@"):
            values = spec[1:].split(",")
            x, y = (float(value) for value in values[:2])
            layer = LAYER_NAMES.index(values[2]) if len(values) == 3 else 0
            terminals.append(Terminal("coordinate", spec[1:], x, y, x, y, (), layer))
            continue
        pad_spec, separator, route_spec = spec.partition("@")
        reference, pad_number = pad_spec.split(":", 1)
        footprint = by_reference[reference]
        pad = next(pad for pad in footprint.Pads() if pad.GetNumber() == pad_number)
        if pad.GetNetname() != net_name:
            raise ValueError(f"{spec} is on {pad.GetNetname()}, not {net_name}")
        pos = pad.GetPosition()
        pad_positions = [candidate.GetPosition() for candidate in footprint.Pads()]
        px = mm(pos.x)
        py = mm(pos.y)
        min_x = min(mm(candidate.x) for candidate in pad_positions)
        max_x = max(mm(candidate.x) for candidate in pad_positions)
        min_y = min(mm(candidate.y) for candidate in pad_positions)
        max_y = max(mm(candidate.y) for candidate in pad_positions)
        _, dx, dy = min(
            (px - min_x, -1.0, 0.0),
            (max_x - px, 1.0, 0.0),
            (py - min_y, 0.0, -1.0),
            (max_y - py, 0.0, 1.0),
        )
        escape = 0.8
        route_x = px + dx * escape
        route_y = py + dy * escape
        lead = ((route_x, route_y),)
        if separator:
            lead = tuple(
                tuple(float(value) for value in point.split(",", 1))
                for point in route_spec.split(";")
            )
            route_x, route_y = lead[-1]
        terminals.append(
            Terminal(reference, pad_number, px, py, route_x, route_y, lead, 0)
        )
    return terminals


def find_path(
    clearance_map: ClearanceMap, start: Terminal, goal: Terminal
) -> list[tuple[int, int, int]]:
    sx, sy = clearance_map.grid(start.route_x, start.route_y)
    gx, gy = clearance_map.grid(goal.route_x, goal.route_y)
    start_state = (start.layer, sx, sy, 8)
    heap: list[tuple[float, float, tuple[int, int, int, int]]] = []
    heapq.heappush(heap, (0.0, 0.0, start_state))
    costs = {start_state: 0.0}
    parents: dict[tuple[int, int, int, int], tuple[int, int, int, int]] = {}
    final_state: tuple[int, int, int, int] | None = None

    while heap:
        _, cost, state = heapq.heappop(heap)
        if cost != costs.get(state):
            continue
        layer, x, y, direction = state
        if layer == goal.layer and x == gx and y == gy:
            final_state = state
            break

        for next_direction, (dx, dy) in enumerate(MOVES):
            nx = x + dx
            ny = y + dy
            if nx < 0 or ny < 0 or nx >= clearance_map.nx or ny >= clearance_map.ny:
                continue
            idx = clearance_map.index(nx, ny)
            if clearance_map.blocked[layer][idx] and (nx, ny) != (gx, gy):
                continue
            if dx and dy:
                if (
                    clearance_map.blocked[layer][clearance_map.index(x + dx, y)]
                    or clearance_map.blocked[layer][clearance_map.index(x, y + dy)]
                ):
                    continue
            move_cost = math.sqrt(2.0) if dx and dy else 1.0
            turn_cost = 0.0 if direction in (8, next_direction) else 0.35
            next_cost = cost + move_cost + turn_cost
            next_state = (layer, nx, ny, next_direction)
            if next_cost >= costs.get(next_state, math.inf):
                continue
            costs[next_state] = next_cost
            parents[next_state] = state
            heuristic = math.hypot(nx - gx, ny - gy)
            heapq.heappush(heap, (next_cost + heuristic, next_cost, next_state))

        idx = clearance_map.index(x, y)
        if not clearance_map.via_blocked[idx]:
            for next_layer in range(len(LAYERS)):
                if next_layer == layer or clearance_map.blocked[next_layer][idx]:
                    continue
                next_state = (next_layer, x, y, 8)
                next_cost = cost + 18.0
                if next_cost >= costs.get(next_state, math.inf):
                    continue
                costs[next_state] = next_cost
                parents[next_state] = state
                heuristic = math.hypot(x - gx, y - gy)
                heapq.heappush(heap, (next_cost + heuristic, next_cost, next_state))

    if final_state is None:
        raise RuntimeError(f"no route found from {start.reference}:{start.pad_number} to {goal.reference}:{goal.pad_number}")

    states = [final_state]
    while states[-1] != start_state:
        states.append(parents[states[-1]])
    states.reverse()
    return [(layer, x, y) for layer, x, y, _ in states]


def compress_path(path: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    result = [path[0]]
    for node in path[1:]:
        if node == result[-1]:
            continue
        if len(result) >= 2:
            a = result[-2]
            b = result[-1]
            if a[0] == b[0] == node[0]:
                first = (b[1] - a[1], b[2] - a[2])
                second = (node[1] - b[1], node[2] - b[2])
                if first[0] * second[1] == first[1] * second[0]:
                    result[-1] = node
                    continue
        result.append(node)
    return result


def add_route(
    board: pcbnew.BOARD,
    net_name: str,
    path: list[tuple[int, int, int]],
    clearance_map: ClearanceMap,
    start: Terminal,
    goal: Terminal,
    width: float,
    via_diameter: float,
    via_drill: float,
) -> dict[str, object]:
    net = board.FindNet(net_name)
    compressed = compress_path(path)
    coordinates = [clearance_map.coordinate(x, y) for _, x, y in compressed]
    segments: list[dict[str, object]] = []
    vias: list[list[float]] = []

    def add_segment(layer: int, ax: float, ay: float, bx: float, by: float) -> None:
        if ax == bx and ay == by:
            return
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(pcbnew.VECTOR2I(iu(ax), iu(ay)))
        track.SetEnd(pcbnew.VECTOR2I(iu(bx), iu(by)))
        track.SetWidth(iu(width))
        track.SetLayer(LAYERS[layer])
        track.SetNet(net)
        board.Add(track)
        segments.append(
            {
                "layer": LAYER_NAMES[layer],
                "start": [round(ax, 4), round(ay, 4)],
                "end": [round(bx, 4), round(by, 4)],
            }
        )

    start_lead = [(start.x, start.y), *start.lead, coordinates[0]]
    for (ax, ay), (bx, by) in zip(start_lead, start_lead[1:]):
        add_segment(start.layer, ax, ay, bx, by)

    for index in range(len(compressed) - 1):
        layer_a, _, _ = compressed[index]
        layer_b, _, _ = compressed[index + 1]
        ax, ay = coordinates[index]
        bx, by = coordinates[index + 1]
        if layer_a != layer_b:
            existing_via = None
            for item in board.GetTracks():
                if not isinstance(item, pcbnew.PCB_VIA) or item.GetNetname() != net_name:
                    continue
                position = item.GetPosition()
                vx = mm(position.x)
                vy = mm(position.y)
                if math.hypot(vx - ax, vy - ay) <= 0.55:
                    existing_via = (vx, vy)
                    break
            if existing_via is not None:
                vx, vy = existing_via
                add_segment(layer_a, ax, ay, vx, vy)
                add_segment(layer_b, ax, ay, vx, vy)
                continue
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I(iu(ax), iu(ay)))
            via.SetWidth(iu(via_diameter))
            via.SetDrill(iu(via_drill))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetNet(net)
            board.Add(via)
            vias.append([round(ax, 4), round(ay, 4)])
            continue
        add_segment(layer_a, ax, ay, bx, by)
    goal_lead = [coordinates[-1], *reversed(goal.lead), (goal.x, goal.y)]
    for (ax, ay), (bx, by) in zip(goal_lead, goal_lead[1:]):
        add_segment(goal.layer, ax, ay, bx, by)
    return {"segments": segments, "vias": vias}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("net")
    parser.add_argument("terminals", nargs="+")
    parser.add_argument("--step", type=float, default=0.2)
    parser.add_argument("--width", type=float, default=0.127)
    parser.add_argument("--clearance", type=float, default=0.18)
    parser.add_argument("--via-diameter", type=float, default=0.6)
    parser.add_argument("--via-drill", type=float, default=0.3)
    parser.add_argument("--edge-clearance", type=float, default=0.3)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    board = pcbnew.LoadBoard(str(args.board))
    terminals = terminals_for(board, args.net, args.terminals)
    clearance_map = ClearanceMap(
        board,
        args.net,
        args.step,
        args.width,
        args.clearance,
        args.via_diameter,
        args.edge_clearance,
    )
    routes: list[dict[str, object]] = []
    for start, goal in zip(terminals, terminals[1:]):
        path = find_path(clearance_map, start, goal)
        route = add_route(
            board,
            args.net,
            path,
            clearance_map,
            start,
            goal,
            args.width,
            args.via_diameter,
            args.via_drill,
        )
        route["from"] = f"{start.reference}:{start.pad_number}"
        route["to"] = f"{goal.reference}:{goal.pad_number}"
        routes.append(route)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(args.output), board)
    print(json.dumps({"net": args.net, "routes": routes}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
