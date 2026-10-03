"""Find the Exit, circular mazes (Hard): the start is in the middle and the exits are around the rim.

A polar maze is a graph of cells: a centre disc (node 0, the start) and rings of sectors around it. A ring has the same
number of sectors as the one inside it or twice as many (so corridors keep a similar shape from the middle to the rim).
It is built exactly like the rectangular Hard mazes: a forest of one tree per exit, so exactly one exit can be reached from
the start. First the answer route is walked from the centre to its exit through a few waypoints that send it out, back in
and out again, then every false exit digs a spine toward the middle and grows into a region of its own, and a multi-root
Wilson fill completes the maze, so region borders look like ordinary maze walls and tracing back from a false exit is as
long as solving from the start.

Difficulty is the number of rings (more rings: narrower corridors and a longer route) together with the route rules; the
first three levels have four exits and the later ones five. Levels with the same ring count differ in their route.
"""
from __future__ import annotations

from collections import deque
from functools import lru_cache
import math
import random

from ..models import RoundSpec

POLAR_LAYOUT = "polar_v1"
POLAR_VERSION = 1
OUTER = 430.0  # logical radius of the maze's outer wall
CENTRE = 56.0  # logical radius of the middle disc where the start stands
BASE_SECTORS = 8  # sectors of the first ring
ASPECT = 1.55  # a ring doubles its sectors when its cells would be longer than this many ring heights
DECOY_QUOTA = .62  # share of the off-route cells the false regions are grown to, together
MIN_DECOY_SHARE = .6  # every false region keeps at least this much of its fair share of that quota
DECOY_REACH = .4  # every false region digs at least this far toward the middle (fraction of the rings)
MAX_ARC_WALL = 150.0  # longest unbroken wall arc, in degrees: long seams give away sealed regions
# Levels (tier = level number - 1). `waypoints` are the ring fractions the answer route visits on its way out (it goes out,
# back in, and out again, so there is no straight spiral); `radial_runs` is the least number of alternating outward and inward
# runs the route must show. The first three levels have four exits, the next two five (the user's rule).
POLAR_LEVELS = (
    {"rings": 5, "waypoints": (.8, .4), "radial_runs": 3, "min_route": 22, "max_route": 80, "route_branches": 4,
     "false_share": .06, "exits": 4, "thinking": 6.0, "candidates": 5},
    {"rings": 6, "waypoints": (.8, .35), "radial_runs": 3, "min_route": 30, "max_route": 100, "route_branches": 6,
     "false_share": .06, "exits": 4, "thinking": 7.0, "candidates": 5},
    {"rings": 7, "waypoints": (.75, .3, .8), "radial_runs": 5, "min_route": 42, "max_route": 130, "route_branches": 8,
     "false_share": .06, "exits": 4, "thinking": 8.0, "candidates": 4},
    {"rings": 8, "waypoints": (.75, .3, .85, .45), "radial_runs": 5, "min_route": 56, "max_route": 170, "route_branches": 10,
     "false_share": .06, "exits": 5, "thinking": 9.0, "candidates": 3},
    {"rings": 9, "waypoints": (.75, .3, .85, .35), "radial_runs": 5, "min_route": 70, "max_route": 210, "route_branches": 12,
     "false_share": .06, "exits": 5, "thinking": 10.0, "candidates": 3},
)


def ring_height(rings: int) -> float:
    return (OUTER - CENTRE) / rings


def sector_counts(rings: int) -> list[int]:
    """Sectors of ring 1..rings: eight at first, doubling whenever the cells would get too long."""
    height = ring_height(rings)
    counts = [BASE_SECTORS]
    for ring in range(2, rings + 1):
        middle = CENTRE + (ring - .5) * height
        counts.append(counts[-1] * 2 if 2 * math.pi * middle / counts[-1] > ASPECT * height else counts[-1])
    return counts


@lru_cache(maxsize=16)
def build_graph(sectors: tuple[int, ...]) -> dict:
    """Nodes: 0 is the centre, then ring 1's sectors, ring 2's, and so on. `adj` lists every neighbour of every node."""
    offsets, total = [], 1
    for count in sectors:
        offsets.append(total)
        total += count
    ring_of, sector_of = [0], [0]
    for ring, count in enumerate(sectors, start=1):
        ring_of += [ring] * count
        sector_of += list(range(count))
    adj: list[list[int]] = [[] for _ in range(total)]
    adj[0] = list(range(offsets[0], offsets[0] + sectors[0]))
    for ring, count in enumerate(sectors, start=1):
        for sector in range(count):
            node = offsets[ring - 1] + sector
            around = [offsets[ring - 1] + (sector - 1) % count, offsets[ring - 1] + (sector + 1) % count]
            inward = 0 if ring == 1 else offsets[ring - 2] + sector * sectors[ring - 2] // count
            outward: list[int] = []
            if ring < len(sectors):
                ratio = sectors[ring] // count
                outward = [offsets[ring] + sector * ratio + step for step in range(ratio)]
            adj[node] = sorted(set(around + [inward] + outward))
    return {"offsets": offsets, "total": total, "ring": ring_of, "sector": sector_of, "adj": adj}


def inward_of(graph: dict, node: int) -> int:
    ring = graph["ring"][node]
    return 0 if ring == 1 else next(other for other in graph["adj"][node] if graph["ring"][other] == ring - 1)


def angle_of(sectors: tuple[int, ...] | list[int], graph: dict, node: int) -> float:
    """The middle angle of a node's sector in radians, 0 at the top and growing clockwise."""
    ring = graph["ring"][node]
    return 0.0 if ring == 0 else (graph["sector"][node] + .5) * 2 * math.pi / sectors[ring - 1]


def _loop_erased_walk(start: int, goal, blocked: set[int], adj: list[list[int]], rng: random.Random, max_steps: int,
                      allowed=None) -> list[int] | None:
    route, positions = [start], {start: 0}
    for _ in range(max_steps):
        options = [node for node in adj[route[-1]] if node not in blocked and (allowed is None or allowed(route[-1], node))]
        if not options:
            return None
        node = rng.choice(options)
        if node in positions:
            route = route[:positions[node] + 1]
            positions = {value: index for index, value in enumerate(route)}
        else:
            route.append(node)
            positions[node] = len(route) - 1
        if goal(node):
            return route
    return None


def _free_reach(origin: int, blocked: set[int], adj: list[list[int]]) -> set[int]:
    seen, queue = {origin}, deque([origin])
    while queue:
        node = queue.popleft()
        for other in adj[node]:
            if other not in seen and other not in blocked:
                seen.add(other)
                queue.append(other)
    return seen


def radial_runs(route: list[int], ring_of: list[int]) -> int:
    """Alternating outward and inward runs of the route (one-ring wiggles ignored)."""
    runs: list[list[int]] = []
    for first, second in zip(route, route[1:]):
        delta = ring_of[second] - ring_of[first]
        if delta == 0:
            continue
        if runs and runs[-1][0] == delta:
            runs[-1][1] += 1
        else:
            runs.append([delta, 1])
    merged: list[list[int]] = []
    for direction, length in runs:
        if length < 2:
            continue
        if merged and merged[-1][0] == direction:
            merged[-1][1] += length
        else:
            merged.append([direction, length])
    return len(merged)


def branch_points(edges: list[list[int]], route: list[int]) -> int:
    degree: dict[int, int] = {}
    for first, second in edges:
        degree[first] = degree.get(first, 0) + 1
        degree[second] = degree.get(second, 0) + 1
    return sum(degree.get(node, 0) >= 3 for node in route[1:-1])


def longest_arc_wall(edges: list[list[int]], sectors: tuple[int, ...], graph: dict) -> float:
    """The longest unbroken wall along a ring boundary, in degrees (radial walls are short by construction)."""
    edge_set = {tuple(edge) for edge in edges}
    longest = 0.0
    for ring in range(1, len(sectors)):  # the boundary between ring and ring + 1
        count, outer = sectors[ring - 1], sectors[ring]
        ratio = outer // count
        first_out = graph["offsets"][ring]
        # Walk the outer ring's sectors: blocked when the cell is not joined to its inner neighbour.
        blocked = []
        for sector in range(outer):
            node = first_out + sector
            inner = graph["offsets"][ring - 1] + sector // ratio
            blocked.append((inner, node) not in edge_set)
        if all(blocked):
            longest = max(longest, 360.0)
            continue
        start = next(index for index, flag in enumerate(blocked) if not flag)
        run = 0
        for step in range(1, outer + 1):
            if blocked[(start + step) % outer]:
                run += 1
                longest = max(longest, run * 360.0 / outer)
            else:
                run = 0
    return longest


def exit_nodes(sectors: tuple[int, ...], graph: dict, count: int, rng: random.Random) -> list[int] | None:
    """`count` exits spread around the outer ring: evenly spaced, rotated at random, each nudged a little."""
    outer, first = sectors[-1], graph["offsets"][len(sectors) - 1]
    base, share = rng.uniform(0, 2 * math.pi / count), 2 * math.pi / count
    picked = []
    for index in range(count):
        angle = base + index * share + rng.uniform(-.12, .12) * share
        picked.append(first + int(angle / (2 * math.pi) * outer) % outer)
    picked.sort()
    gaps = [(b - a) for a, b in zip(picked, picked[1:] + [picked[0] + outer])]
    return picked if len(set(picked)) == count and min(gaps) >= 3 else None


def _allowed_rule(graph: dict, exits: set[int]):
    """An exit cell only ever opens inward: it is a leaf on the rim."""
    def allowed(first: int, second: int) -> bool:
        if second in exits:
            return first == inward_of(graph, second)
        if first in exits:
            return second == inward_of(graph, first)
        return True
    return allowed


def _grow_decoys(labels: dict[int, int], edges: list, quotas: dict[int, int], adj: list[list[int]], rng: random.Random, allowed) -> None:
    """Grow every false region toward its quota with loop-erased walks from free cells it can reach."""
    total = len(adj)
    stuck: set[int] = set()
    while True:
        sizes = {label: 0 for label in quotas}
        for value in labels.values():
            if value in sizes:
                sizes[value] += 1
        hungry = [label for label in quotas if sizes[label] < quotas[label] and label not in stuck]
        if not hungry:
            return
        label = min(hungry, key=lambda item: sizes[item] / quotas[item])
        others = {node for node, value in labels.items() if value != label}
        reach: set[int] = set()
        for seed in [node for node, value in labels.items() if value == label]:
            for other in adj[seed]:
                if other not in labels and other not in reach:
                    reach |= _free_reach(other, set(labels), adj)
        if not reach:
            stuck.add(label)
            continue
        walk = _loop_erased_walk(rng.choice(sorted(reach)), lambda node: labels.get(node) == label, others, adj, rng, total * 60, allowed)
        if walk is None:
            stuck.add(label)
            continue
        for node in walk[:-1]:
            labels[node] = label
        edges.extend(sorted(pair) for pair in zip(walk, walk[1:]))


def region_reach(region: set[int], graph: dict, rings: int) -> float:
    """How far toward the middle a region digs (0 = it stays on the rim ring, 1 = it reaches the first ring)."""
    return (rings - min(graph["ring"][node] for node in region)) / max(1, rings - 1)


def make_round(index: int, tier: int, rng: random.Random, answer: int, min_route: int | None = None) -> RoundSpec | None:
    """One attempt at a level of tier `tier` whose correct exit (by angle) is `answer`; None when it does not work out."""
    level = POLAR_LEVELS[tier]
    rings = level["rings"]
    sectors = tuple(sector_counts(rings))
    graph = build_graph(sectors)
    adj, ring_of, total = graph["adj"], graph["ring"], graph["total"]
    count = level["exits"]
    exits = exit_nodes(sectors, graph, count, rng)
    if exits is None:
        return None
    exit_set = set(exits)
    allowed = _allowed_rule(graph, exit_set)
    target = exits[answer]
    false_exits = {node for index_, node in enumerate(exits) if index_ != answer}
    # 1. The answer route: out, back in, and out again through a few waypoints, then up to its exit.
    route, inner_target = [0], inward_of(graph, target)
    # The waypoints sweep around the circle in one direction and end at the exit's own angle, so the route winds in and out
    # around the maze without walling its own exit in.
    sweep, spin = rng.uniform(1.2 * math.pi, 1.9 * math.pi), rng.choice((-1, 1))
    exit_angle = angle_of(sectors, graph, target)
    stops = len(level["waypoints"]) + 1
    for position, fraction in enumerate(level["waypoints"] + (None,), start=1):
        if fraction is None:
            waypoint = inner_target
        else:
            angle = exit_angle - spin * sweep * (stops - position) / stops
            ring = max(1, round(fraction * rings))
            taken = set(route) | false_exits | {target, inner_target}
            reach = _free_reach(route[-1], set(route[:-1]) | false_exits | {target}, adj)  # cells the walk can still get to
            if inner_target not in reach:
                return None
            wanted = int((angle % (2 * math.pi)) / (2 * math.pi) * sectors[ring - 1]) % sectors[ring - 1]
            free = [graph["offsets"][ring - 1] + (wanted + step) % sectors[ring - 1]
                    for step in sorted(range(-sectors[ring - 1] // 2, sectors[ring - 1] // 2), key=abs)
                    if graph["offsets"][ring - 1] + (wanted + step) % sectors[ring - 1] not in taken
                    and graph["offsets"][ring - 1] + (wanted + step) % sectors[ring - 1] in reach]
            if not free:
                return None
            waypoint = free[0]
        for _attempt in range(6):  # a random walk can wall itself in: try the leg again from the same spot
            blocked = (set(route[:-1]) | false_exits | {target}) - {waypoint}
            leg = _loop_erased_walk(route[-1], lambda node, goal=waypoint: node == goal, blocked, adj, rng, total * 60, allowed)
            if leg is not None:
                break
        else:
            return None
        route += leg[1:]
    route.append(target)
    low = min_route if min_route is not None else level["min_route"]
    if not low <= len(route) <= level["max_route"] or radial_runs(route, ring_of) < level["radial_runs"]:
        return None
    labels = {node: answer for node in route}
    edges = [sorted(pair) for pair in zip(route, route[1:])]
    first_step = route[1]
    plain_rule = allowed

    def allowed(first: int, second: int) -> bool:  # the middle opens only onto the route's first cell: the arrow points there
        if 0 in (first, second):
            return {first, second} == {0, first_step}
        return plain_rule(first, second)

    # 2. Every false exit digs a winding spine inward until it is deep enough.
    deep = max(1, math.ceil(rings * (1 - DECOY_REACH)))
    decoy_labels = [label for label in range(count) if label != answer]
    for label in rng.sample(decoy_labels, len(decoy_labels)):
        origin = exits[label]
        spine_blocked = set(labels) | {0, origin}
        walk = _loop_erased_walk(inward_of(graph, origin), lambda node: ring_of[node] <= deep, spine_blocked, adj, rng, total * 80, allowed)
        if walk is None:
            return None
        spine = [origin] + walk
        for node in spine:
            labels[node] = label
        edges.extend(sorted(pair) for pair in zip(spine, spine[1:]))
    # 3. Grow the false regions first, so each is a real maze of its own.
    quota = max(1, round(DECOY_QUOTA * (total - len(route)) / len(decoy_labels)))
    _grow_decoys(labels, edges, {label: quota for label in decoy_labels}, adj, rng, allowed)
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
    edges.sort()
    from .find_the_exit import routes
    if len(edges) != total - count or routes(0, edges).get(target) != route or sum(0 in edge for edge in edges) != 1:
        return None
    sizes = [len(routes(node, edges)) for node in exits]
    if min(size for label, size in enumerate(sizes) if label != answer) < MIN_DECOY_SHARE * quota:
        return None
    if any(region_reach(set(routes(exits[label], edges)), graph, rings) < DECOY_REACH for label in decoy_labels):
        return None
    if longest_arc_wall(edges, sectors, graph) > MAX_ARC_WALL:
        return None
    branches = branch_points(edges, route)
    if branches < level["route_branches"]:
        return None
    return RoundSpec(index, "find_the_exit", {
        "layout": POLAR_LAYOUT, "maze_version": POLAR_VERSION, "rings": rings, "sectors": list(sectors), "start": 0,
        "exits": exits, "edges": edges, "route": route, "correct_index": answer, "level": index + 1, "tier": tier,
        "route_metrics": {"nodes": len(route), "radial_runs": radial_runs(route, ring_of)}, "route_branch_points": branches,
        "exit_component_sizes": sizes, "thinking_seconds": level["thinking"],
        "rules": {"min_route": low, "radial_runs": level["radial_runs"], "route_branches": level["route_branches"],
                  "false_share": level["false_share"]},
    }, answer)


def build_level(index: int, tier: int, rng: random.Random, answer: int, used: set[str], min_route: int | None = None) -> RoundSpec:
    """Several valid mazes for the level; the most deceptive one (the largest smallest false region) is kept."""
    level = POLAR_LEVELS[tier]
    candidates: list[RoundSpec] = []
    for attempt in range(40000):
        if attempt >= 6000 and candidates:
            break
        item = make_round(index, tier, rng, answer, min_route)
        if item is not None and item.fingerprint() not in used:
            candidates.append(item)
            if len(candidates) == level["candidates"]:
                break
    if not candidates:
        raise RuntimeError("Could not generate a circular maze")
    return max(candidates, key=lambda item: (min(size for label, size in enumerate(item.data["exit_component_sizes"])
                                                  if label != item.answer), len(item.data["route"])))


# ---------------------------------------------------------------- validation

def errors(data: dict, answer: int) -> list[str]:
    from .find_the_exit import routes
    if data.get("maze_version") != POLAR_VERSION:
        return ["unknown circular maze version"]
    rings, sectors = data.get("rings"), tuple(data.get("sectors", ()))
    if not isinstance(rings, int) or not 3 <= rings <= 12 or len(sectors) != rings or sectors[0] < 6 or any(
            count not in (previous, 2 * previous) for previous, count in zip(sectors, sectors[1:])):
        return ["a circular maze has rings of equal or doubling sectors"]
    graph = build_graph(sectors)
    total = graph["total"]
    start, exits, edges = data.get("start"), data.get("exits", []), data.get("edges", [])
    count = len(exits)
    if start != 0 or not 3 <= count <= 6 or exits != sorted(set(exits)) or any(graph["ring"][node] != rings for node in exits if 0 <= node < total):
        return ["a circular maze starts in the middle and has 3 to 6 exits on the rim"]
    if any(node not in range(total) for node in exits):
        return ["exits must be cells of the rim"]
    if any(len(edge) != 2 or edge[0] not in range(total) or edge[1] not in graph["adj"][edge[0]] for edge in edges):
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
    reachable = [index for index, node in enumerate(exits) if node in paths]
    if reachable != [answer] or data.get("correct_index") != answer:
        return ["maze must have exactly one reachable exit matching its answer"]
    route, rules = data.get("route"), data.get("rules", {})
    ring_of = graph["ring"]
    if (route != paths[exits[answer]] or len(route) < max(10, rules.get("min_route", 10))
            or radial_runs(route, ring_of) < rules.get("radial_runs", 3)
            or data.get("route_metrics") != {"nodes": len(route), "radial_runs": radial_runs(route, ring_of)}):
        return ["maze reveal route is incorrect or too direct"]
    edge_set = {tuple(sorted(edge)) for edge in edges}
    if sum(0 in edge for edge in edges) != 1:
        return ["the middle of a circular maze has exactly one opening"]
    if any(tuple(sorted((node, inward_of(graph, node)))) not in edge_set for node in exits):
        return ["every visible exit needs an inward passage"]
    if any(sum(node in pair for pair in edge_set) != 1 for node in exits):
        return ["an exit cell opens only inward"]
    sizes = [len(routes(node, edges)) for node in exits]
    false_sizes = [size for index, size in enumerate(sizes) if index != answer]
    if data.get("exit_component_sizes") != sizes or min(false_sizes) < rules.get("false_share", .06) * total:
        return ["false exits must own convincingly large regions"]
    quota = max(1, round(DECOY_QUOTA * (total - len(route)) / (count - 1)))
    if min(false_sizes) < MIN_DECOY_SHARE * quota:
        return ["a false region is small enough to rule out by tracing back from its exit"]
    if any(region_reach(set(routes(node, edges)), graph, rings) < DECOY_REACH for index, node in enumerate(exits) if index != answer):
        return ["a false region does not dig deep enough toward the middle"]
    if longest_arc_wall(edges, sectors, graph) > MAX_ARC_WALL:
        return ["a long unbroken wall would give away a sealed region"]
    branches = branch_points(edges, route)
    if branches < rules.get("route_branches", 3) or data.get("route_branch_points") != branches:
        return ["maze does not have enough route branch competition"]
    if not 3.0 <= float(data.get("thinking_seconds", 0)) <= 15.0:
        return ["maze thinking time is out of range"]
    return []
