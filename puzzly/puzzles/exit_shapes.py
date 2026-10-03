"""Find the Exit, shaped mazes (Hard): a hexagon, a six-pointed star, and a diamond.

Like the circular maze, the start is in the middle and four or five exits are on the rim, and it is a forest of one tree per
exit, so exactly one exit can be reached. What changes is the cell: a shape is a set of polygons (honeycomb hexagons, the
triangles of the star, or rotated squares) whose shared edges give the neighbours. Everything else is the same recipe as
`exit_polar.py` and the rectangular Hard mazes: the answer route is walked first through a few waypoints that send it out,
back in, and out again; every false exit digs a spine toward the middle and grows into a region of its own; a multi-root
Wilson fill completes the maze. Difficulty is the size of the shape (more cells: narrower corridors, a longer route).

All shapes are inscribed in a circle of radius `OUTER` around the centre of the plate, so they share the circular maze's plate.
"""
from __future__ import annotations

from collections import deque
from functools import lru_cache
import math
import random

from ..models import RoundSpec
from .exit_polar import _grow_decoys as _grow_regions, branch_points, _loop_erased_walk

CELLS_LAYOUT = "cells_v1"
CELLS_VERSION = 1
SHAPES = ("hex", "star", "diamond")
SHAPE_NAMES = {"hex": "HEXAGON", "star": "STAR", "diamond": "DIAMOND"}
OUTER = 430.0  # the circle every shape is inscribed in
GATE = 42.0  # how far outside the rim an exit's portal sits
DECOY_QUOTA = .62
MIN_DECOY_SHARE = .6
DECOY_REACH = .4
# Per level (tier = level number - 1): the size of every shape, and the rules. Cells go from about 100 to about 300 so that
# corridors get narrower and the route longer, as in the circular and rectangular mazes.
SIZES = {"hex": (5, 6, 7, 8, 9), "star": (3, 4, 4, 5, 6), "diamond": (9, 11, 13, 15, 17)}
TIERS = (
    {"waypoints": (.75, .35), "runs": 3, "exits": 4, "thinking": 6.0, "candidates": 5, "bands": 6},
    {"waypoints": (.8, .35), "runs": 3, "exits": 4, "thinking": 7.0, "candidates": 5, "bands": 7},
    {"waypoints": (.75, .3, .8), "runs": 5, "exits": 4, "thinking": 8.0, "candidates": 4, "bands": 8},
    {"waypoints": (.75, .3, .85, .45), "runs": 5, "exits": 5, "thinking": 9.0, "candidates": 3, "bands": 9},
    {"waypoints": (.75, .3, .85, .35), "runs": 5, "exits": 5, "thinking": 10.0, "candidates": 3, "bands": 10},
)
MAX_STRAIGHT = {"hex": 99, "star": 6, "diamond": 6}  # longest straight inner wall, in cell edges


# ---------------------------------------------------------------- the cells of each shape

def _hex_cells(size: int) -> list[list[tuple[float, float]]]:
    unit = OUTER / (math.sqrt(3) * size + 1)  # circumradius of one hexagon
    cells = []
    for q in range(-size, size + 1):
        for r in range(max(-size, -q - size), min(size, -q + size) + 1):
            cx, cy = unit * math.sqrt(3) * (q + r / 2), unit * 1.5 * r
            cells.append([(cx + unit * math.cos(math.radians(30 + 60 * k)), cy + unit * math.sin(math.radians(30 + 60 * k))) for k in range(6)])
    return cells


def _inside(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _star_cells(size: int) -> list[list[tuple[float, float]]]:
    unit = OUTER / (math.sqrt(3) * size)  # one triangle edge: the points are triangles of `size` edges
    def point(i: float, j: float) -> tuple[float, float]:
        return unit * (i + j / 2), unit * j * math.sqrt(3) / 2
    outline = []
    for k in range(6):
        angle = math.radians(60 * k)
        outline.append((size * unit * math.cos(angle), size * unit * math.sin(angle)))
        tip = math.radians(60 * k + 30)
        outline.append((size * unit * math.sqrt(3) * math.cos(tip), size * unit * math.sqrt(3) * math.sin(tip)))
    cells = []
    span = 2 * size + 1
    for i in range(-span, span + 1):
        for j in range(-span, span + 1):
            for triangle in ([point(i, j), point(i + 1, j), point(i, j + 1)], [point(i + 1, j), point(i + 1, j + 1), point(i, j + 1)]):
                centre = (sum(x for x, _ in triangle) / 3, sum(y for _, y in triangle) / 3)
                if _inside(centre, outline):
                    cells.append(triangle)
    return cells


def _diamond_cells(size: int) -> list[list[tuple[float, float]]]:
    cell = OUTER * math.sqrt(2) / size  # a square grid turned 45 degrees: the diagonal of the whole is 2 * OUTER
    cells = []
    for row in range(size):
        for column in range(size):
            corners = []
            for dx, dy in ((0, 0), (1, 0), (1, 1), (0, 1)):
                x, y = (column + dx - size / 2) * cell, (row + dy - size / 2) * cell
                corners.append(((x - y) / math.sqrt(2), (x + y) / math.sqrt(2)))
            cells.append(corners)
    return cells


BUILDERS = {"hex": _hex_cells, "star": _star_cells, "diamond": _diamond_cells}


class Layout:
    """The cells of a shape and what the generator and the drawing need to know about them."""

    def __init__(self, shape: str, size: int):
        raw = BUILDERS[shape](size)
        key = lambda point: (round(point[0], 2), round(point[1], 2))
        self.shape, self.size = shape, size
        self.polygons = [[key(point) for point in polygon] for polygon in raw]
        self.centers = [(sum(x for x, _ in polygon) / len(polygon), sum(y for _, y in polygon) / len(polygon)) for polygon in self.polygons]
        self.total = len(self.polygons)
        owners: dict[tuple, list[int]] = {}
        for node, polygon in enumerate(self.polygons):
            for first, second in zip(polygon, polygon[1:] + polygon[:1]):
                owners.setdefault(tuple(sorted((first, second))), []).append(node)
        self.adj: list[list[int]] = [[] for _ in range(self.total)]
        self.shared: dict[tuple[int, int], tuple[tuple, tuple]] = {}
        self.outer_edges: list[list[tuple[tuple, tuple]]] = [[] for _ in range(self.total)]
        for edge, nodes in owners.items():
            if len(nodes) == 2:
                a, b = nodes
                self.adj[a].append(b)
                self.adj[b].append(a)
                self.shared[(min(a, b), max(a, b))] = edge
            else:
                self.outer_edges[nodes[0]].append(edge)
        self.adj = [sorted(set(neighbours)) for neighbours in self.adj]
        far = max(math.hypot(x, y) for x, y in self.centers)
        self.depth = [math.hypot(x, y) / far for x, y in self.centers]
        self.angle = [math.atan2(x, -y) % (2 * math.pi) for x, y in self.centers]  # 0 at the top, clockwise
        self.start = min(range(self.total), key=lambda node: (round(self.depth[node], 4), node))
        self.rim = [node for node in range(self.total) if self.outer_edges[node]]
        lengths = [math.dist(a, b) for edges in self.outer_edges for a, b in edges]
        self.unit = sum(lengths) / len(lengths)

    def inward(self, node: int) -> int:
        """The neighbour an exit cell opens onto: the one closest to the middle."""
        return min(self.adj[node], key=lambda other: (round(self.depth[other], 4), other))

    def gate(self, node: int) -> tuple[tuple[float, float], tuple[float, float], tuple[tuple, tuple]]:
        """An exit cell's opening: the middle of its outermost outer edge, the outward direction, and the edge itself."""
        def reach(edge):
            return math.hypot((edge[0][0] + edge[1][0]) / 2, (edge[0][1] + edge[1][1]) / 2)
        edge = max(self.outer_edges[node], key=reach)
        middle = ((edge[0][0] + edge[1][0]) / 2, (edge[0][1] + edge[1][1]) / 2)
        norm = math.hypot(*middle) or 1.0
        return middle, (middle[0] / norm, middle[1] / norm), edge


@lru_cache(maxsize=24)
def layout_of(shape: str, size: int) -> Layout:
    return Layout(shape, size)


def cell_count(shape: str, size: int) -> int:
    return layout_of(shape, size).total


# ---------------------------------------------------------------- generation

def band_of(layout: Layout, node: int, bands: int) -> int:
    return min(bands - 1, int(layout.depth[node] * bands))


def radial_runs(route: list[int], layout: Layout, bands: int) -> int:
    """Alternating outward and inward runs of the route, by distance band (one-band wiggles ignored)."""
    runs: list[list[int]] = []
    for first, second in zip(route, route[1:]):
        delta = band_of(layout, second, bands) - band_of(layout, first, bands)
        if delta == 0:
            continue
        sign = 1 if delta > 0 else -1
        if runs and runs[-1][0] == sign:
            runs[-1][1] += abs(delta)
        else:
            runs.append([sign, abs(delta)])
    merged: list[list[int]] = []
    for direction, length in runs:
        if length < 2:
            continue
        if merged and merged[-1][0] == direction:
            merged[-1][1] += length
        else:
            merged.append([direction, length])
    return len(merged)


def _line_key(first: tuple, second: tuple):
    dx, dy = second[0] - first[0], second[1] - first[1]
    length = math.hypot(dx, dy)
    dx, dy = dx / length, dy / length
    if dx < -1e-9 or (abs(dx) <= 1e-9 and dy < 0):
        dx, dy = -dx, -dy
    return (round(math.degrees(math.atan2(dy, dx))), round(-dy * first[0] + dx * first[1], 0)), (dx, dy)


def longest_straight_wall(layout: Layout, edges: list[list[int]]) -> int:
    """The longest unbroken straight wall between cells, in cell edges: long seams give away sealed regions."""
    joined = {tuple(edge) for edge in edges}
    groups: dict[tuple, list[tuple[float, float]]] = {}
    for pair, (first, second) in layout.shared.items():
        if pair in joined:
            continue
        key, (dx, dy) = _line_key(first, second)
        ends = sorted((first[0] * dx + first[1] * dy, second[0] * dx + second[1] * dy))
        groups.setdefault(key, []).append((ends[0], ends[1]))
    longest = 0
    for segments in groups.values():
        segments.sort()
        chain, reach = 0, -1e9
        for low, high in segments:
            chain = chain + 1 if low <= reach + 1.0 else 1
            reach = max(reach, high) if chain > 1 else high
            longest = max(longest, chain)
    return longest


def exit_nodes(layout: Layout, count: int, rng: random.Random) -> list[int] | None:
    """`count` exits spread around the rim: evenly spaced angles, rotated at random, each nudged a little."""
    share = 2 * math.pi / count
    base = rng.uniform(0, share)
    picked: list[int] = []
    for index in range(count):
        wanted = base + index * share + rng.uniform(-.12, .12) * share
        candidates = sorted(layout.rim, key=lambda node: abs((layout.angle[node] - wanted + math.pi) % (2 * math.pi) - math.pi))
        for node in candidates:
            if node in picked or layout.start in layout.adj[node] and False:
                continue
            picked.append(node)
            break
    angles = sorted(layout.angle[node] for node in picked)
    gaps = [(b - a) for a, b in zip(angles, angles[1:] + [angles[0] + 2 * math.pi])]
    if len(set(picked)) != count or min(gaps) < .55 * share:
        return None
    return sorted(picked, key=lambda node: layout.angle[node])


def _allowed_rule(layout: Layout, exits: set[int]):
    """An exit cell only ever opens inward: it is a leaf on the rim."""
    def allowed(first: int, second: int) -> bool:
        if second in exits:
            return first == layout.inward(second)
        if first in exits:
            return second == layout.inward(first)
        return True
    return allowed


def _free_reach(origin: int, blocked: set[int], adj) -> set[int]:
    seen, queue = {origin}, deque([origin])
    while queue:
        node = queue.popleft()
        for other in adj[node]:
            if other not in seen and other not in blocked:
                seen.add(other)
                queue.append(other)
    return seen


def region_reach(region: set[int], layout: Layout) -> float:
    """How far toward the middle a region digs (0 = it stays on the rim, 1 = it reaches the centre)."""
    return 1 - min(layout.depth[node] for node in region)


def rules_for(shape: str, tier: int) -> dict:
    size = SIZES[shape][tier]
    total = cell_count(shape, size)
    level = TIERS[tier]
    return {"min_route": round(.2 * total), "max_route": round(.7 * total), "route_branches": max(3, round(.035 * total)),
            "false_share": .06, "runs": level["runs"], "bands": level["bands"], "max_straight": MAX_STRAIGHT[shape]}


def make_round(index: int, shape: str, tier: int, rng: random.Random, answer: int, min_route: int | None = None) -> RoundSpec | None:
    """One attempt at a level; None when it does not work out."""
    level = TIERS[tier]
    size = SIZES[shape][tier]
    layout = layout_of(shape, size)
    rules = rules_for(shape, tier)
    adj, total = layout.adj, layout.total
    count = level["exits"]
    exits = exit_nodes(layout, count, rng)
    if exits is None:
        return None
    exit_set = set(exits)
    allowed = _allowed_rule(layout, exit_set)
    target = exits[answer]
    false_exits = {node for position, node in enumerate(exits) if position != answer}
    inner_target = layout.inward(target)
    # 1. The answer route: out, back in, and out again through a few waypoints, then up to its exit.
    route = [layout.start]
    sweep, spin = rng.uniform(1.2 * math.pi, 1.9 * math.pi), rng.choice((-1, 1))
    stops = len(level["waypoints"]) + 1
    for position, fraction in enumerate(level["waypoints"] + (None,), start=1):
        if fraction is None:
            waypoint = inner_target
        else:
            angle = layout.angle[target] - spin * sweep * (stops - position) / stops
            reach = _free_reach(route[-1], set(route[:-1]) | false_exits | {target}, adj)
            if inner_target not in reach:
                return None
            taken = set(route) | false_exits | {target, inner_target}
            free = [node for node in reach if node not in taken and node != layout.start]
            if not free:
                return None
            waypoint = min(free, key=lambda node: (abs(layout.depth[node] - fraction) * 3
                                                    + abs((layout.angle[node] - angle + math.pi) % (2 * math.pi) - math.pi) / math.pi, node))
        for _attempt in range(6):
            blocked = (set(route[:-1]) | false_exits | {target}) - {waypoint}
            leg = _loop_erased_walk(route[-1], lambda node, goal=waypoint: node == goal, blocked, adj, rng, total * 60, allowed)
            if leg is not None:
                break
        else:
            return None
        route += leg[1:]
    route.append(target)
    low = min_route if min_route is not None else rules["min_route"]
    if not low <= len(route) <= rules["max_route"] or radial_runs(route, layout, rules["bands"]) < rules["runs"]:
        return None
    labels = {node: answer for node in route}
    edges = [sorted(pair) for pair in zip(route, route[1:])]
    first_step = route[1]
    plain_rule = allowed

    def allowed(first: int, second: int) -> bool:  # the start opens only onto the route's first cell: the arrow points there
        if layout.start in (first, second):
            return {first, second} == {layout.start, first_step}
        return plain_rule(first, second)

    # 2. Every false exit digs a winding spine toward the middle until it is deep enough.
    deep = 1 - DECOY_REACH
    decoy_labels = [label for label in range(count) if label != answer]
    for label in rng.sample(decoy_labels, len(decoy_labels)):
        origin = exits[label]
        walk = _loop_erased_walk(layout.inward(origin), lambda node: layout.depth[node] <= deep, set(labels) | {layout.start, origin},
                                 adj, rng, total * 80, allowed)
        if walk is None:
            return None
        spine = [origin] + walk
        for node in spine:
            labels[node] = label
        edges.extend(sorted(pair) for pair in zip(spine, spine[1:]))
    # 3. Grow the false regions first, so each is a real maze of its own.
    quota = max(1, round(DECOY_QUOTA * (total - len(route)) / len(decoy_labels)))
    _grow_regions(labels, edges, {label: quota for label in decoy_labels}, adj, rng, allowed)
    # 4. A multi-root Wilson forest fills the rest.
    order = [node for node in range(total) if node not in labels]
    rng.shuffle(order)
    for node in order:
        if node in labels:
            continue
        walk = _loop_erased_walk(node, lambda other: other in labels, set(), adj, rng, total * 400, allowed)
        if walk is None:
            return None
        label = labels[walk[-1]]
        for cell in walk[:-1]:
            labels[cell] = label
        edges.extend(sorted(pair) for pair in zip(walk, walk[1:]))
    edges = sorted([min(pair), max(pair)] for pair in edges)
    from .find_the_exit import routes
    if len(edges) != total - count or routes(layout.start, edges).get(target) != route or sum(layout.start in edge for edge in edges) != 1:
        return None
    sizes = [len(routes(node, edges)) for node in exits]
    if min(value for label, value in enumerate(sizes) if label != answer) < max(MIN_DECOY_SHARE * quota, rules["false_share"] * total):
        return None
    if any(region_reach(set(routes(exits[label], edges)), layout) < DECOY_REACH for label in decoy_labels):
        return None
    if longest_straight_wall(layout, edges) > rules["max_straight"]:
        return None
    branches = branch_points(edges, route)
    if branches < rules["route_branches"]:
        return None
    return RoundSpec(index, "find_the_exit", {
        "layout": CELLS_LAYOUT, "maze_version": CELLS_VERSION, "shape": shape, "size": size, "start": layout.start,
        "exits": exits, "edges": edges, "route": route, "correct_index": answer, "level": index + 1, "tier": tier,
        "route_metrics": {"nodes": len(route), "radial_runs": radial_runs(route, layout, rules["bands"])},
        "route_branch_points": branches, "exit_component_sizes": sizes, "thinking_seconds": level["thinking"],
        "rules": {"min_route": low, "runs": rules["runs"], "bands": rules["bands"], "route_branches": rules["route_branches"],
                  "false_share": rules["false_share"], "max_straight": rules["max_straight"]},
    }, answer)


def build_level(index: int, shape: str, tier: int, rng: random.Random, answer: int, used: set[str],
                min_route: int | None = None) -> RoundSpec:
    """Several valid mazes for the level; the most deceptive one (the largest smallest false region) is kept."""
    level = TIERS[tier]
    candidates: list[RoundSpec] = []
    for attempt in range(40000):
        if attempt >= 6000 and candidates:
            break
        item = make_round(index, shape, tier, rng, answer, min_route)
        if item is not None and item.fingerprint() not in used:
            candidates.append(item)
            if len(candidates) == level["candidates"]:
                break
    if not candidates:
        raise RuntimeError(f"Could not generate a {shape} maze")
    return max(candidates, key=lambda item: (min(size for label, size in enumerate(item.data["exit_component_sizes"])
                                                  if label != item.answer), len(item.data["route"])))


# ---------------------------------------------------------------- validation

def errors(data: dict, answer: int) -> list[str]:
    from .find_the_exit import routes
    if data.get("maze_version") != CELLS_VERSION or data.get("shape") not in SHAPES:
        return ["unknown shaped maze version or shape"]
    size = data.get("size")
    if not isinstance(size, int) or size not in SIZES[data["shape"]]:
        return ["unsupported shaped maze size"]
    layout = layout_of(data["shape"], size)
    total = layout.total
    start, exits, edges = data.get("start"), data.get("exits", []), data.get("edges", [])
    count = len(exits)
    if start != layout.start or not 3 <= count <= 6 or len(set(exits)) != count or any(node not in layout.rim for node in exits if 0 <= node < total) \
            or any(node not in range(total) for node in exits):
        return ["a shaped maze starts in the middle and has 3 to 6 exits on the rim"]
    if exits != sorted(exits, key=lambda node: layout.angle[node]):
        return ["exits are listed around the rim, clockwise"]
    if any(len(edge) != 2 or edge[0] not in range(total) or edge[1] not in layout.adj[edge[0]] for edge in edges):
        return ["maze passages must join adjacent cells"]
    if len(edges) != total - count or len({tuple(sorted(edge)) for edge in edges}) != len(edges):
        return ["maze must contain one disjoint tree per exit"]
    parent = list(range(total))

    def root(node: int) -> int:
        while parent[node] != node:
            node = parent[node]
        return node

    for a, b in edges:
        if root(a) == root(b):
            return ["maze contains a cycle and ambiguous routes"]
        parent[root(a)] = root(b)
    paths = routes(start, edges)
    reachable = [position for position, node in enumerate(exits) if node in paths]
    if reachable != [answer] or data.get("correct_index") != answer:
        return ["maze must have exactly one reachable exit matching its answer"]
    route, rules = data.get("route"), data.get("rules", {})
    bands = rules.get("bands", 6)
    if (route != paths[exits[answer]] or len(route) < max(10, rules.get("min_route", 10))
            or radial_runs(route, layout, bands) < rules.get("runs", 3)
            or data.get("route_metrics") != {"nodes": len(route), "radial_runs": radial_runs(route, layout, bands)}):
        return ["maze reveal route is incorrect or too direct"]
    edge_set = {tuple(sorted(edge)) for edge in edges}
    if sum(start in edge for edge in edges) != 1:
        return ["the middle of a shaped maze has exactly one opening"]
    if any(tuple(sorted((node, layout.inward(node)))) not in edge_set for node in exits):
        return ["every visible exit needs an inward passage"]
    if any(sum(node in pair for pair in edge_set) != 1 for node in exits):
        return ["an exit cell opens only inward"]
    sizes = [len(routes(node, edges)) for node in exits]
    false_sizes = [value for position, value in enumerate(sizes) if position != answer]
    if data.get("exit_component_sizes") != sizes or min(false_sizes) < rules.get("false_share", .06) * total:
        return ["false exits must own convincingly large regions"]
    quota = max(1, round(DECOY_QUOTA * (total - len(route)) / (count - 1)))
    if min(false_sizes) < MIN_DECOY_SHARE * quota:
        return ["a false region is small enough to rule out by tracing back from its exit"]
    if any(region_reach(set(routes(node, edges)), layout) < DECOY_REACH for position, node in enumerate(exits) if position != answer):
        return ["a false region does not dig deep enough toward the middle"]
    if longest_straight_wall(layout, edges) > rules.get("max_straight", MAX_STRAIGHT[data["shape"]]):
        return ["a long unbroken wall would give away a sealed region"]
    branches = branch_points(edges, route)
    if branches < rules.get("route_branches", 3) or data.get("route_branch_points") != branches:
        return ["maze does not have enough route branch competition"]
    if not 3.0 <= float(data.get("thinking_seconds", 0)) <= 15.0:
        return ["maze thinking time is out of range"]
    return []
