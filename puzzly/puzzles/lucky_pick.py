from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import heapq
import math
import random
from typing import Any

from ..config import (LUCKY_APPEARANCE_DURATION, LUCKY_SELECTION_DURATION, LUCKY_WINNER_HOLD,
                      PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION)
from ..models import RoundSpec, VideoSpec
from .memory_challenge import SHAPES

TARGET_COUNT = 7
# Neon maze (current). Every video gets its own seeded maze; targets sit in dead-end pockets.
MAP_VERSION = "neon_maze_v1"
MAZE_COLUMNS = (150, 345, 540, 735, 930)
MAZE_ROWS = (430, 618, 806, 994, 1182, 1370)
MAZE_ENTRANCE = (540, 1515)
MAZE_MIN_POCKETS = 9
MAZE_LOOPS = 2
TARGET_SIZE = 100
CORRIDOR_WIDTH = 118
POCKET_RADIUS = 76
BOARD_BOUNDS = (60, 340, 1020, 1600)
TRAVEL_SPEED = 680.0
TRAVEL_RAMP = 0.16  # seconds to speed up and to slow down; the cruise speed is constant
STOP_GAP = 92.0  # the character halts this far before a target, then lunges for it
EAT_ANTICIPATION = 0.16
EAT_BITE = 0.36
POST_EAT = 0.30
EAT_DURATION = 0.82
CHOMP_AT = 0.70  # fraction of the bite at which the jaws close and the target is gone
COLORS = {"red": "#FF5A5F", "blue": "#4D9DFF", "yellow": "#FFD93D", "green": "#4ADE80",
          "purple": "#B388FF", "orange": "#FF9F1C", "pink": "#FF6FB5"}
# Legacy corridor templates (older manifests only).
LEGACY_TARGET_SIZE = 136
LEGACY_BOARD_BOUNDS = (90, 245, 990, 1595)
LEGACY_TRAVEL_SPEED = 600.0
LEGACY_EAT_DURATION = 0.58
LEGACY_COLORS = {"red": "#D9434E", "blue": "#2874C6", "yellow": "#DCA915", "green": "#319457",
                 "purple": "#7654C5", "orange": "#E86F27", "pink": "#D94F8A"}

Point = tuple[int, int]
Path = tuple[Point, ...]


@dataclass(frozen=True)
class CorridorTemplate:
    id: str
    entrance: Point
    route_edges: tuple[tuple[Point, Point], ...]
    target_nodes: tuple[Point, ...]


def _edges(*paths: Path) -> tuple[tuple[Point, Point], ...]:
    result: list[tuple[Point, Point]] = []
    seen: set[tuple[Point, Point]] = set()
    for path in paths:
        for first, second in zip(path, path[1:]):
            key = (first, second) if first <= second else (second, first)
            if key not in seen:
                seen.add(key)
                result.append((first, second))
    return tuple(result)


_ENTRANCE = (540, 1510)
_CENTER = ((540, 1510), (540, 1400), (540, 1120), (540, 850), (540, 580), (540, 330))
_LEFT_BOTTOM = ((540, 1400), (360, 1400), (170, 1400), (170, 1180), (360, 1180), (360, 1120), (540, 1120))
_RIGHT_BOTTOM = ((540, 1400), (720, 1400), (910, 1400), (910, 1180), (720, 1180), (720, 1120), (540, 1120))
_LEFT_MIDDLE = ((540, 1120), (360, 1120), (180, 1120), (180, 910), (360, 910), (360, 850), (540, 850))
_RIGHT_MIDDLE = ((540, 1120), (720, 1120), (900, 1120), (900, 930), (720, 930), (720, 850), (540, 850))
_LEFT_UPPER = ((540, 850), (360, 850), (170, 850), (170, 640), (360, 640), (360, 580), (540, 580))
_RIGHT_UPPER = ((540, 850), (720, 850), (910, 850), (910, 660), (720, 660), (720, 580), (540, 580))
_LEFT_TOP = ((540, 580), (360, 580), (180, 580), (180, 390), (360, 390), (360, 330), (540, 330))
_RIGHT_TOP = ((540, 580), (720, 580), (900, 580), (900, 410), (720, 410), (720, 330), (540, 330))
_TARGET_NODES = (
    (170, 1400), (360, 1180), (910, 1400), (720, 1180),
    (180, 1120), (180, 910), (900, 1120), (900, 930),
    (360, 640), (720, 660),
    (180, 580), (180, 390), (360, 330), (900, 580), (900, 410), (720, 330),
    (540, 1120), (540, 850), (540, 580), (540, 330),
)
TEMPLATES = (
    CorridorTemplate(
        "sketch_house", _ENTRANCE,
        _edges(_CENTER, _LEFT_BOTTOM, _RIGHT_BOTTOM, _LEFT_MIDDLE, _RIGHT_MIDDLE,
               _LEFT_UPPER, _RIGHT_UPPER, _LEFT_TOP, _RIGHT_TOP),
        _TARGET_NODES,
    ),
)


def _mirror_point(point: Point) -> Point:
    return 1080 - point[0], point[1]


def _axis_aligned(a: Point | list[int], b: Point | list[int]) -> bool:
    return (a[0] == b[0]) != (a[1] == b[1])


def _segment_key(a: Point, b: Point) -> tuple[Point, Point]:
    return (a, b) if a <= b else (b, a)


def template_geometry(template: CorridorTemplate, mirrored: bool) -> dict[str, Any]:
    segments = [[list(_mirror_point(first) if mirrored else first),
                 list(_mirror_point(second) if mirrored else second)]
                for first, second in template.route_edges]
    entrance = list(_mirror_point(template.entrance) if mirrored else template.entrance)
    target_nodes = [list(_mirror_point(point) if mirrored else point) for point in template.target_nodes]
    return {"entrance": entrance, "corridors": segments, "target_nodes": target_nodes}


def _segment_intersection(a: tuple[Point, Point], b: tuple[Point, Point]) -> bool:
    (p1, p2), (q1, q2) = a, b
    p_vertical, q_vertical = p1[0] == p2[0], q1[0] == q2[0]
    if p_vertical == q_vertical:
        if p_vertical and p1[0] == q1[0]:
            return max(min(p1[1],p2[1]),min(q1[1],q2[1])) <= min(max(p1[1],p2[1]),max(q1[1],q2[1]))
        if not p_vertical and p1[1] == q1[1]:
            return max(min(p1[0],p2[0]),min(q1[0],q2[0])) <= min(max(p1[0],p2[0]),max(q1[0],q2[0]))
        return False
    vertical, horizontal = (a, b) if p_vertical else (b, a)
    return (min(vertical[0][1],vertical[1][1]) <= horizontal[0][1] <= max(vertical[0][1],vertical[1][1]) and
            min(horizontal[0][0],horizontal[1][0]) <= vertical[0][0] <= max(horizontal[0][0],horizontal[1][0]))


def template_errors(template: CorridorTemplate, mirrored: bool = False) -> list[str]:
    result: list[str] = []
    geometry = template_geometry(template, mirrored)
    target_nodes = geometry["target_nodes"]
    if len(target_nodes) < TARGET_COUNT or len(set(map(tuple, target_nodes))) != len(target_nodes):
        result.append("corridor map must contain unique target nodes")
    x1, y1, x2, y2 = LEGACY_BOARD_BOUNDS
    entrance = geometry["entrance"]
    if not (x1 <= entrance[0] <= x2 and y1 <= entrance[1] <= y2):
        result.append("corridor entrance is outside the board")
    segments = [(tuple(a), tuple(b)) for a, b in geometry["corridors"]]
    if any(not _axis_aligned(a, b) for a, b in segments):
        result.append("corridor contains diagonal or zero-length travel")
    if any(not (x1 <= point[0] <= x2 and y1 <= point[1] <= y2)
           for segment in geometry["corridors"] for point in segment):
        result.append("corridor point is outside safe bounds")
    if any(math.dist(a, b) < LEGACY_TARGET_SIZE + 28
           for index, a in enumerate(target_nodes) for b in target_nodes[index+1:]):
        result.append("valid target nodes overlap")
    radius = LEGACY_TARGET_SIZE / 2
    if any(not (x1+radius <= point[0] <= x2-radius and y1+radius <= point[1] <= y2-radius)
           for point in target_nodes):
        result.append("target region leaves safe bounds")
    nodes: dict[Point, set[Point]] = {}
    for a, b in segments:
        nodes.setdefault(a, set()).add(b); nodes.setdefault(b, set()).add(a)
    visited: set[Point] = set()
    stack = [tuple(entrance)]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node); stack.extend(nodes.get(node, set()) - visited)
    if visited != set(nodes):
        result.append("corridor network must be connected")
    if any(tuple(point) not in nodes for point in target_nodes):
        result.append("every target node must sit on the route network")
    for index, first in enumerate(segments):
        for second in segments[index+1:]:
            shared = set(first) & set(second)
            if _segment_intersection(first, second) and not shared:
                result.append("corridor segments cross outside a junction")
    return list(dict.fromkeys(result))


for _template_item in TEMPLATES:
    for _mirrored in (False, True):
        _errors = template_errors(_template_item, _mirrored)
        if _errors:
            raise ValueError(f"Invalid Lucky Pick template {_template_item.id}: {_errors}")


def path_length(path: list[list[int]]) -> float:
    return sum(math.dist(a, b) for a, b in zip(path, path[1:]))


def point_on_path(path: list[list[int]], amount: float) -> tuple[tuple[float, float], int]:
    lengths = [math.dist(a, b) for a, b in zip(path, path[1:])]
    target = max(0.0, min(1.0, amount)) * sum(lengths)
    for index, (a, b, length) in enumerate(zip(path, path[1:], lengths)):
        if target <= length or index == len(lengths)-1:
            fraction = 0 if length == 0 else target / length
            return ((a[0] + (b[0]-a[0])*fraction, a[1] + (b[1]-a[1])*fraction), index)
        target -= length
    return (tuple(path[-1]), len(path)-2)  # type: ignore[return-value]


def shortest_route(
    corridors: list[list[list[int]]], start: Point | list[int], destination: Point | list[int],
) -> list[list[int]]:
    start_node, destination_node = tuple(start), tuple(destination)
    graph: dict[Point, list[tuple[Point, float]]] = {}
    for first, second in corridors:
        a, b = tuple(first), tuple(second)
        distance = math.dist(a, b)
        graph.setdefault(a, []).append((b, distance))
        graph.setdefault(b, []).append((a, distance))
    queue: list[tuple[float, Point]] = [(0.0, start_node)]
    distances = {start_node: 0.0}
    previous: dict[Point, Point] = {}
    while queue:
        distance, node = heapq.heappop(queue)
        if node == destination_node:
            break
        if distance > distances.get(node, math.inf):
            continue
        for neighbor, edge_length in sorted(graph.get(node, [])):
            candidate = distance + edge_length
            if candidate + 1e-9 < distances.get(neighbor, math.inf):
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(queue, (candidate, neighbor))
    if destination_node not in distances:
        raise ValueError("Lucky Pick target is disconnected from the route network")
    route = [destination_node]
    while route[-1] != start_node:
        route.append(previous[route[-1]])
    route.reverse()
    return [list(point) for point in route]


def _balanced_order(
    rng: random.Random, geometry: dict[str, Any], targets: list[dict[str, Any]], losers: list[int],
) -> list[int]:
    candidates: dict[tuple[int, ...], float] = {}
    for _ in range(96):
        order = list(losers); rng.shuffle(order)
        lengths = [path_length(shortest_route(
            geometry["corridors"],
            geometry["entrance"] if index == 0 else targets[order[index-1]]["position"],
            targets[target]["position"],
        )) for index, target in enumerate(order)]
        score = sum(abs(length - 1050) for length in lengths) + max(lengths) * .22
        if min(lengths) < 420:
            score += (420 - min(lengths)) * 3
        key = tuple(order)
        candidates[key] = min(score, candidates.get(key, score))
    ranked = sorted(candidates, key=candidates.get)
    pool = ranked[:min(12, len(ranked))]
    return list(rng.choice(pool))


def _legacy_movement_steps(
    geometry: dict[str, Any], targets: list[dict[str, Any]], order: list[int],
) -> tuple[list[dict[str, Any]], float]:
    steps: list[dict[str, Any]] = []
    total = LUCKY_APPEARANCE_DURATION + LUCKY_SELECTION_DURATION
    previous: int | None = None
    for target in order:
        route = shortest_route(
            geometry["corridors"], geometry["entrance"] if previous is None else targets[previous]["position"],
            targets[target]["position"],
        )
        travel_duration = path_length(route) / LEGACY_TRAVEL_SPEED
        step = {"target_index": target, "travel_path": route, "travel_duration": round(travel_duration, 4),
                "hesitation_duration": 0.0, "eat_duration": LEGACY_EAT_DURATION,
                "start_time": round(total, 4)}
        total += travel_duration + LEGACY_EAT_DURATION
        step["end_time"] = round(total, 4)
        steps.append(step); previous = target
    return steps, round(total + LUCKY_WINNER_HOLD, 4)


def _legacy_errors(data: dict[str, Any], answer: Any) -> list[str]:
    result: list[str] = []
    template = next((item for item in TEMPLATES if item.id == data.get("corridor_template_id")), None)
    if template is None:
        return ["lucky corridor template is unknown"]
    mirrored = data.get("mirrored")
    if not isinstance(mirrored, bool):
        result.append("lucky mirror state is invalid"); mirrored = False
    geometry = template_geometry(template, mirrored); result.extend(template_errors(template, mirrored))
    if (data.get("entrance") != geometry["entrance"] or data.get("corridors") != geometry["corridors"]
            or data.get("valid_target_positions") != geometry["target_nodes"]):
        result.append("lucky corridor geometry does not match its template")
    targets = data.get("targets", []); shape_id = data.get("shape_id")
    colors = [target.get("color_id") for target in targets]
    if len(targets) != TARGET_COUNT or data.get("target_count") != TARGET_COUNT:
        result.append("lucky pick must contain exactly seven targets")
    if shape_id not in SHAPES or any(target.get("shape_id") != shape_id for target in targets):
        result.append("lucky targets must use one supported shape")
    if len(set(colors)) != TARGET_COUNT or set(colors) != set(LEGACY_COLORS):
        result.append("lucky pick must use seven distinct curated colors")
    target_positions = [target.get("position") for target in targets]
    valid_positions = geometry["target_nodes"]
    if (len({tuple(position) for position in target_positions if isinstance(position, list)}) != len(target_positions)
            or any(position not in valid_positions for position in target_positions)):
        result.append("lucky targets must occupy unique valid route nodes")
    if any(target.get("index") != index
           or target.get("color_value") != LEGACY_COLORS.get(target.get("color_id")) for index, target in enumerate(targets)):
        result.append("lucky target mapping is invalid")
    winner, order = data.get("winner_index"), data.get("elimination_order", [])
    if not isinstance(winner, int) or winner not in range(TARGET_COUNT) or answer != winner:
        result.append("lucky winner is invalid")
    losers = set(range(TARGET_COUNT)) - ({winner} if isinstance(winner, int) else set())
    if len(order) != 6 or len(set(order)) != 6 or set(order) != losers or winner in order:
        result.append("lucky elimination order is invalid")
    if data.get("winner_color") != (targets[winner]["color_id"] if isinstance(winner, int) and winner in range(len(targets)) else None):
        result.append("lucky winner color is inconsistent")
    if data.get("selection_seconds") != 5.0 or data.get("eat_seconds") != LEGACY_EAT_DURATION:
        result.append("lucky timing metadata is invalid")
    expected_steps, expected_duration = _legacy_movement_steps(geometry, targets, order) if len(order) == 6 else ([], 0)
    if data.get("movement_steps") != expected_steps or data.get("timeline_duration") != expected_duration:
        result.append("lucky movement timeline is invalid")
    return result


# ---------------------------------------------------------------- neon maze (current)

def _grid_point(node: tuple[int, int]) -> list[int]:
    return [MAZE_COLUMNS[node[0]], MAZE_ROWS[node[1]]]


def _grid_neighbors(node: tuple[int, int]) -> list[tuple[int, int]]:
    column, row = node
    return [(column + dc, row + dr) for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1))
            if 0 <= column + dc < len(MAZE_COLUMNS) and 0 <= row + dr < len(MAZE_ROWS)]


def _tree_distance(edges: set[frozenset], start: tuple[int, int]) -> dict[tuple[int, int], int]:
    graph: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for edge in edges:
        a, b = tuple(edge)
        graph.setdefault(a, []).append(b); graph.setdefault(b, []).append(a)
    distance = {start: 0}; queue = [start]
    for node in queue:
        for neighbor in graph.get(node, []):
            if neighbor not in distance:
                distance[neighbor] = distance[node] + 1; queue.append(neighbor)
    return distance


def build_maze(map_seed: int) -> dict[str, Any]:
    """Seeded neon maze: a Wilson spanning tree over a 5x6 grid plus two long shortcut loops.

    Dead ends become the target pockets, so the character never walks over a target it has not chosen yet.
    """
    rng = random.Random(f"{MAP_VERSION}:{map_seed}")
    root = (len(MAZE_COLUMNS) // 2, len(MAZE_ROWS) - 1)
    nodes = [(column, row) for column in range(len(MAZE_COLUMNS)) for row in range(len(MAZE_ROWS))]
    for _ in range(400):
        tree = {root}; edges: set[frozenset] = set()
        for start in rng.sample(nodes, len(nodes)):
            walk: dict[tuple[int, int], tuple[int, int]] = {}; current = start
            while current not in tree:
                walk[current] = rng.choice(_grid_neighbors(current)); current = walk[current]
            current = start
            while current not in tree:
                tree.add(current); edges.add(frozenset((current, walk[current]))); current = walk[current]
        degree = {node: 0 for node in nodes}
        for edge in edges:
            for node in edge:
                degree[node] += 1
        degree[root] += 1  # the entrance corridor
        pockets = [node for node in nodes if degree[node] == 1]
        top = sum(node[1] <= 1 for node in pockets); bottom = sum(node[1] >= 3 for node in pockets)
        left = sum(node[0] <= 1 for node in pockets); right = sum(node[0] >= 3 for node in pockets)
        if len(pockets) < MAZE_MIN_POCKETS or min(top, bottom, left, right) < 2:
            continue
        # Shortcut loops between far-apart branches, never touching a pocket, so routes are less predictable.
        shortcuts = []
        for a in nodes:
            distance = _tree_distance(edges, a)
            shortcuts += [(distance[b], rng.random(), a, b) for b in _grid_neighbors(a)
                          if a < b and frozenset((a, b)) not in edges and degree[a] > 1 and degree[b] > 1
                          and distance[b] >= 6]
        if len(shortcuts) < MAZE_LOOPS:
            continue
        shortcuts.sort(reverse=True)
        pool = shortcuts[:MAZE_LOOPS * 3]; rng.shuffle(pool)
        for _, _, a, b in pool[:MAZE_LOOPS]:
            edges.add(frozenset((a, b)))
        corridors = [[list(MAZE_ENTRANCE), _grid_point(root)]]
        corridors += sorted([_grid_point(a), _grid_point(b)] for a, b in (sorted(edge) for edge in edges))
        return {"entrance": list(MAZE_ENTRANCE), "corridors": corridors,
                "target_nodes": sorted(_grid_point(node) for node in pockets)}
    raise RuntimeError("Could not build a Lucky Pick maze")


def maze_errors(geometry: dict[str, Any]) -> list[str]:
    result: list[str] = []
    segments = [(tuple(a), tuple(b)) for a, b in geometry["corridors"]]
    if any(not _axis_aligned(a, b) for a, b in segments):
        result.append("maze contains diagonal or zero-length corridors")
    x1, y1, x2, y2 = BOARD_BOUNDS
    if any(not (x1 + POCKET_RADIUS <= point[0] <= x2 - POCKET_RADIUS and y1 + POCKET_RADIUS <= point[1] <= y2 - POCKET_RADIUS)
           for segment in segments for point in segment):
        result.append("maze leaves the board")
    graph: dict[Point, set[Point]] = {}
    for a, b in segments:
        graph.setdefault(a, set()).add(b); graph.setdefault(b, set()).add(a)
    seen = {tuple(geometry["entrance"])}; stack = [tuple(geometry["entrance"])]
    while stack:
        for neighbor in graph.get(stack.pop(), set()) - seen:
            seen.add(neighbor); stack.append(neighbor)
    if seen != set(graph):
        result.append("maze must be connected")
    pockets = [tuple(point) for point in geometry["target_nodes"]]
    if len(pockets) < MAZE_MIN_POCKETS or any(len(graph.get(point, ())) != 1 for point in pockets):
        result.append("every target pocket must be a dead end")
    return result


def travel_distance(elapsed: float, duration: float, length: float) -> float:
    """Distance along a path: a short speed-up, a constant cruise, and a short slow-down."""
    if duration <= 0:
        return length
    ramp = min(TRAVEL_RAMP, duration / 2)
    cruise = length / max(1e-9, duration - ramp)
    elapsed = max(0.0, min(duration, elapsed))
    if elapsed < ramp:
        return cruise * elapsed * elapsed / (2 * ramp)
    if elapsed > duration - ramp:
        remaining = duration - elapsed
        return length - cruise * remaining * remaining / (2 * ramp)
    return cruise * (elapsed - ramp / 2)


def _maze_order(rng: random.Random, geometry: dict[str, Any], targets: list[dict[str, Any]], losers: list[int]) -> list[int]:
    scored: dict[tuple[int, ...], float] = {}
    for _ in range(120):
        order = list(losers); rng.shuffle(order)
        lengths = [path_length(shortest_route(
            geometry["corridors"], geometry["entrance"] if index == 0 else targets[order[index - 1]]["position"],
            targets[target]["position"])) for index, target in enumerate(order)]
        scored[tuple(order)] = sum(abs(length - 950) for length in lengths) + max(lengths) * .25 + max(0, 380 - min(lengths)) * 3
    ranked = sorted(scored, key=scored.get)
    return list(rng.choice(ranked[:min(12, len(ranked))]))


def maze_movement_steps(geometry: dict[str, Any], targets: list[dict[str, Any]], order: list[int]
                        ) -> tuple[list[dict[str, Any]], float]:
    steps: list[dict[str, Any]] = []
    total = LUCKY_APPEARANCE_DURATION + LUCKY_SELECTION_DURATION
    previous: int | None = None
    for target in order:
        route = shortest_route(geometry["corridors"],
                               geometry["entrance"] if previous is None else targets[previous]["position"],
                               targets[target]["position"])
        # The character stops STOP_GAP short of the target, so it travels that much less.
        travel = round((path_length(route) - STOP_GAP) / TRAVEL_SPEED + TRAVEL_RAMP, 4)
        step = {"target_index": target, "travel_path": route, "travel_duration": travel, "hesitation_duration": 0.0,
                "eat_duration": EAT_DURATION, "start_time": round(total, 4)}
        total += travel + EAT_DURATION
        step["end_time"] = round(total, 4)
        steps.append(step); previous = target
    return steps, round(total + LUCKY_WINNER_HOLD, 4)


def generate(seed: int, difficulty: str | None = None, theme: str = "lucky_pick",
             round_count: int | None = None) -> VideoSpec:
    """Current Lucky Pick: the snake chase in an open arena (see lucky_snake)."""
    from . import lucky_snake
    if round_count not in (None, 1):
        raise ValueError("Lucky Pick contains one game")
    rng = random.Random(f"lucky_pick_snake_v1:{seed}")
    shape_id = rng.choice(SHAPES)
    color_ids = list(COLORS); rng.shuffle(color_ids)
    data = lucky_snake.game_data(seed, shape_id, COLORS, color_ids)
    game = RoundSpec(0, "lucky_pick", data, data["winner_index"])
    stable_id = sha256(f"lucky_pick_snake_v1:{seed}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "lucky_pick", seed, None, "lucky_pick", (game,),
                     PUZZLE_FIT_INTRO_DURATION, data["timeline_duration"], PUZZLE_FIT_OUTRO_DURATION)


def is_snake(data: dict[str, Any]) -> bool:
    from .lucky_snake import VERSION
    return data.get("map_version") == VERSION


def generate_maze(seed: int, difficulty: str | None = None, theme: str = "lucky_pick",
                  round_count: int | None = None) -> VideoSpec:
    """The earlier neon-maze Lucky Pick; kept so saved maze videos stay valid and can be re-rendered."""
    if round_count not in (None, 1):
        raise ValueError("Lucky Pick contains one game")
    rng = random.Random(f"lucky_pick_neon_maze_v1:{seed}")
    map_seed = rng.randrange(2**31)
    geometry = build_maze(map_seed)
    shape_id = rng.choice(SHAPES)
    color_ids = list(COLORS); rng.shuffle(color_ids)
    # Spread the seven targets over the pockets: each pick is one of the pockets farthest from those chosen so far.
    pockets = list(geometry["target_nodes"]); rng.shuffle(pockets)
    chosen = [pockets.pop()]
    while len(chosen) < TARGET_COUNT:
        pockets.sort(key=lambda point: (min(math.dist(point, other) for other in chosen), rng.random()))
        chosen.append(pockets.pop(rng.randrange(max(0, len(pockets) - 3), len(pockets))))
    targets = [{"index": index, "shape_id": shape_id, "color_id": color_id, "color_value": COLORS[color_id],
                "position": position} for index, (color_id, position) in enumerate(zip(color_ids, chosen))]
    winner_index = rng.randrange(TARGET_COUNT)
    losers = [index for index in range(TARGET_COUNT) if index != winner_index]
    order = _maze_order(rng, geometry, targets, losers)
    steps, timeline_duration = maze_movement_steps(geometry, targets, order)
    data = {"map_version": MAP_VERSION, "map_seed": map_seed,
            "entrance": geometry["entrance"], "corridors": geometry["corridors"],
            "valid_target_positions": geometry["target_nodes"],
            "targets": targets, "target_count": TARGET_COUNT, "target_size": TARGET_SIZE, "shape_id": shape_id,
            "winner_index": winner_index, "winner_color": targets[winner_index]["color_id"],
            "elimination_order": order, "movement_steps": steps, "selection_seconds": LUCKY_SELECTION_DURATION,
            "eat_seconds": EAT_DURATION, "timeline_duration": timeline_duration}
    game = RoundSpec(0, "lucky_pick", data, winner_index)
    stable_id = sha256(f"lucky_pick_neon_maze_v1:{seed}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "lucky_pick", seed, None, "lucky_pick", (game,),
                     PUZZLE_FIT_INTRO_DURATION, timeline_duration, PUZZLE_FIT_OUTRO_DURATION)


def is_maze(data: dict[str, Any]) -> bool:
    return data.get("map_version") == MAP_VERSION


def errors(data: dict[str, Any], answer: Any) -> list[str]:
    if is_snake(data):
        from . import lucky_snake
        return lucky_snake.errors(data, answer, COLORS, SHAPES)
    if not is_maze(data):
        return _legacy_errors(data, answer)
    result: list[str] = []
    map_seed = data.get("map_seed")
    if not isinstance(map_seed, int):
        return ["lucky maze seed is invalid"]
    geometry = build_maze(map_seed)
    result.extend(maze_errors(geometry))
    if (data.get("entrance") != geometry["entrance"] or data.get("corridors") != geometry["corridors"]
            or data.get("valid_target_positions") != geometry["target_nodes"]):
        result.append("lucky maze geometry does not match its seed")
    targets = data.get("targets", []); shape_id = data.get("shape_id")
    colors = [target.get("color_id") for target in targets]
    if len(targets) != TARGET_COUNT or data.get("target_count") != TARGET_COUNT:
        result.append("lucky pick must contain exactly seven targets")
    if shape_id not in SHAPES or any(target.get("shape_id") != shape_id for target in targets):
        result.append("lucky targets must use one supported shape")
    if len(set(colors)) != TARGET_COUNT or set(colors) != set(COLORS):
        result.append("lucky pick must use seven distinct curated colors")
    positions = [target.get("position") for target in targets]
    if (len({tuple(position) for position in positions if isinstance(position, list)}) != len(positions)
            or any(position not in geometry["target_nodes"] for position in positions)):
        result.append("lucky targets must occupy unique dead-end pockets")
    if any(target.get("index") != index or target.get("color_value") != COLORS.get(target.get("color_id"))
           for index, target in enumerate(targets)):
        result.append("lucky target mapping is invalid")
    winner, order = data.get("winner_index"), data.get("elimination_order", [])
    if not isinstance(winner, int) or winner not in range(TARGET_COUNT) or answer != winner:
        result.append("lucky winner is invalid")
    losers = set(range(TARGET_COUNT)) - ({winner} if isinstance(winner, int) else set())
    if len(order) != 6 or len(set(order)) != 6 or set(order) != losers:
        result.append("lucky elimination order is invalid")
    if data.get("winner_color") != (targets[winner]["color_id"] if isinstance(winner, int) and winner in range(len(targets)) else None):
        result.append("lucky winner color is inconsistent")
    if data.get("selection_seconds") != LUCKY_SELECTION_DURATION or data.get("eat_seconds") != EAT_DURATION:
        result.append("lucky timing metadata is invalid")
    if not result:
        expected_steps, expected_duration = maze_movement_steps(geometry, targets, order)
        if data.get("movement_steps") != expected_steps or data.get("timeline_duration") != expected_duration:
            result.append("lucky movement timeline is invalid")
    return result
