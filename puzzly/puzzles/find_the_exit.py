from __future__ import annotations

from collections import deque
from hashlib import sha256
import random

from ..config import (DEFAULT_ROUNDS, INTRO_DURATION, OUTRO_DURATION, PUZZLE_FIT_INTRO_DURATION,
                      PUZZLE_FIT_OUTRO_DURATION, round_duration)
from ..models import RoundSpec, VideoSpec


DIFFICULTY_RULES = {
    "easy": {"size": 5, "min_route": 7, "max_route": 13, "turns": 3, "down_steps": 0,
             "horizontal_steps": 2, "route_branches": 1, "false_depth": 1},
    "medium": {"size": 6, "min_route": 11, "max_route": 19, "turns": 5, "down_steps": 1,
               "horizontal_steps": 4, "route_branches": 3, "false_depth": 2},
    "hard": {"size": 7, "min_route": 16, "max_route": 27, "turns": 8, "down_steps": 2,
             "horizontal_steps": 6, "route_branches": 5, "false_depth": 2},
}


def neighbors(node: int, size: int) -> list[int]:
    row, column = divmod(node, size)
    return [r * size + c for r, c in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1))
            if 0 <= r < size and 0 <= c < size]


def routes(start: int, edges: list[list[int]]) -> dict[int, list[int]]:
    graph: dict[int, list[int]] = {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
        graph.setdefault(b, []).append(a)
    result, queue = {start: [start]}, deque([start])
    while queue:
        node = queue.popleft()
        for other in graph.get(node, []):
            if other not in result:
                result[other] = result[node] + [other]
                queue.append(other)
    return result


def route_metrics(route: list[int], size: int) -> dict[str, int]:
    steps = []
    for first, second in zip(route, route[1:]):
        first_row, first_column = divmod(first, size)
        second_row, second_column = divmod(second, size)
        steps.append((second_row - first_row, second_column - first_column))
    return {
        "nodes": len(route),
        "turns": sum(first != second for first, second in zip(steps, steps[1:])),
        "down_steps": sum(row_delta > 0 for row_delta, _ in steps),
        "horizontal_steps": sum(column_delta != 0 for _, column_delta in steps),
    }


def _balanced_route(route: list[int], size: int, target: int, difficulty: str) -> bool:
    rules = DIFFICULTY_RULES[difficulty]
    metrics = route_metrics(route, size)
    return (
        len(route) >= 2
        and route[-2] == target + size
        and rules["min_route"] <= metrics["nodes"] <= rules["max_route"]
        and metrics["turns"] >= rules["turns"]
        and metrics["down_steps"] >= rules["down_steps"]
        and metrics["horizontal_steps"] >= rules["horizontal_steps"]
    )


def _make_route(start: int, target: int, exits: list[int], size: int, difficulty: str,
                rng: random.Random) -> list[int] | None:
    rules = DIFFICULTY_RULES[difficulty]
    false_exits = [node for node in exits if node != target]
    blocked = set(false_exits)
    for root in false_exits:
        blocked.update(root + size * depth for depth in range(1, rules["false_depth"] + 1))

    # A loop-erased local walk creates readable detours without cycles. Medium
    # and Hard filters explicitly require downward revisits and extra turns.
    for _ in range(700):
        route, positions = [start], {start: 0}
        for _ in range(size * size * 16):
            options = [node for node in neighbors(route[-1], size) if node not in blocked]
            if not options:
                break
            node = rng.choice(options)
            if node in positions:
                route = route[:positions[node] + 1]
                positions = {value: index for index, value in enumerate(route)}
            else:
                route.append(node)
                positions[node] = len(route) - 1
            if node == target:
                if _balanced_route(route, size, target, difficulty):
                    return route
                break
    return None


def _grow_forest(route: list[int], exits: list[int], answer: int, size: int, difficulty: str,
                 rng: random.Random) -> tuple[list[list[int]], dict[int, int]]:
    rules = DIFFICULTY_RULES[difficulty]
    labels = {node: answer for node in route}
    edges = [sorted((first, second)) for first, second in zip(route, route[1:])]
    for index, root in enumerate(exits):
        if index == answer:
            continue
        labels[root] = index
        previous = root
        for depth in range(1, rules["false_depth"] + 1):
            node = root + size * depth
            labels[node] = index
            edges.append(sorted((previous, node)))
            previous = node

    frontier = [(node, other) for node in labels for other in neighbors(node, size) if other not in labels]
    while frontier:
        first, second = frontier.pop(rng.randrange(len(frontier)))
        if second in labels:
            continue
        labels[second] = labels[first]
        edges.append(sorted((first, second)))
        frontier.extend((second, other) for other in neighbors(second, size) if other not in labels)
    return sorted(edges), labels


def make_round(index: int, difficulty: str, rng: random.Random) -> RoundSpec:
    rules = DIFFICULTY_RULES[difficulty]
    size = rules["size"]
    exits, start = [0, size // 2, size - 1], (size - 1) * size + size // 2
    for _ in range(500):
        answer = rng.randrange(len(exits))
        route = _make_route(start, exits[answer], exits, size, difficulty, rng)
        if route is None:
            continue
        edges, labels = _grow_forest(route, exits, answer, size, difficulty, rng)
        degree: dict[int, int] = {}
        for first, second in edges:
            degree[first] = degree.get(first, 0) + 1
            degree[second] = degree.get(second, 0) + 1
        route_branches = sum(degree.get(node, 0) >= 3 for node in route[1:-1])
        if route_branches < rules["route_branches"]:
            continue
        component_sizes = [sum(label == component for label in labels.values()) for component in range(3)]
        return RoundSpec(index, "find_the_exit", {
            "size": size, "start": start, "exits": exits, "edges": edges,
            "route": route, "correct_index": answer,
            "route_metrics": route_metrics(route, size),
            "route_branch_points": route_branches,
            "exit_component_sizes": component_sizes,
        }, answer)
    raise RuntimeError("Could not generate a balanced deceptive maze")


# ---------------------------------------------------------------- Hard: large deceptive mazes

HARD_LAYOUT = "deceptive_v2"
# Levels escalate inside every Hard video: larger grids, more up/down sweeps, longer routes.
# `sweeps` is how many times the answer route dives back down; `vertical_runs` = 2 * sweeps + 1.
HARD_LEVELS = (
    {"columns": 8, "rows": 10, "sweeps": 1, "min_route": 32, "max_route": 70, "turn_ratio": .40,
     "route_branches": 6, "false_share": .06, "max_straight": 5},
    {"columns": 9, "rows": 11, "sweeps": 2, "min_route": 42, "max_route": 84, "turn_ratio": .40,
     "route_branches": 8, "false_share": .06, "max_straight": 5},
    {"columns": 10, "rows": 12, "sweeps": 2, "min_route": 50, "max_route": 100, "turn_ratio": .40,
     "route_branches": 10, "false_share": .06, "max_straight": 5},
)
HARD_CANDIDATES = 10  # valid mazes generated per round; the most deceptive one is kept
DECOY_DEPTH = 0.3  # each false region must dive at least this deep (fraction of rows) ...


def decoy_point(region: set[int], route_cells: set[int], rows: int, columns: int) -> int | None:
    """... and dead-end there right beside the answer route, one wall away: the deepest such cell."""
    touching = [node for node in region if node // columns >= rows * DECOY_DEPTH
                and any(other in route_cells for other in grid_neighbors(node, rows, columns))]
    return max(touching, key=lambda node: (node // columns, -node)) if touching else None


def grid_neighbors(node: int, rows: int, columns: int) -> list[int]:
    row, column = divmod(node, columns)
    return [r * columns + c for r, c in ((row - 1, column), (row + 1, column), (row, column - 1), (row, column + 1))
            if 0 <= r < rows and 0 <= c < columns]


def vertical_runs(route: list[int], columns: int) -> int:
    """Number of alternating up/down sweeps, ignoring horizontal moves and one-row wiggles."""
    runs: list[list[int]] = []
    for first, second in zip(route, route[1:]):
        delta = second // columns - first // columns
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


def grid_metrics(route: list[int], columns: int) -> dict[str, int]:
    steps = []
    for first, second in zip(route, route[1:]):
        (r1, c1), (r2, c2) = divmod(first, columns), divmod(second, columns)
        steps.append((r2 - r1, c2 - c1))
    return {"nodes": len(route), "turns": sum(a != b for a, b in zip(steps, steps[1:])),
            "down_steps": sum(dr > 0 for dr, _ in steps), "horizontal_steps": sum(dc != 0 for _, dc in steps),
            "vertical_runs": vertical_runs(route, columns)}


def level_tier(index: int, count: int) -> int:
    if count <= 1:
        return 2
    fraction = index / (count - 1)
    return 0 if fraction < 0.34 else (1 if fraction < 0.75 else 2)


def _level_for(rows: int, columns: int) -> dict | None:
    return next((level for level in HARD_LEVELS if (level["rows"], level["columns"]) == (rows, columns)), None)


def _route_ok(route: list[int], target: int, level: dict) -> bool:
    metrics = grid_metrics(route, level["columns"])
    return (len(route) >= 2 and route[-2] == target + level["columns"]
            and level["min_route"] <= metrics["nodes"] <= level["max_route"]
            and metrics["turns"] >= level["turn_ratio"] * (metrics["nodes"] - 1)
            and metrics["vertical_runs"] >= 2 * level["sweeps"] + 1)


def _loop_erased_walk(start: int, goal, blocked: set[int], rows: int, columns: int, rng: random.Random,
                      max_steps: int, allowed=None) -> list[int] | None:
    route, positions = [start], {start: 0}
    for _ in range(max_steps):
        options = [node for node in grid_neighbors(route[-1], rows, columns)
                   if node not in blocked and (allowed is None or allowed(route[-1], node))]
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


def _free_reach(origin: int, blocked: set[int], rows: int, columns: int) -> set[int]:
    seen, queue = {origin}, deque([origin])
    while queue:
        node = queue.popleft()
        for other in grid_neighbors(node, rows, columns):
            if other not in seen and other not in blocked:
                seen.add(other)
                queue.append(other)
    return seen


def _lanes(columns: int, count: int) -> list[set[int]]:
    bounds = [round(index * columns / count) for index in range(count + 1)]
    return [set(range(bounds[index], bounds[index + 1])) for index in range(count)]


def _serpentine_route(start: int, target: int, blocked: set[int], rows: int, columns: int,
                      rng: random.Random, sweeps: int) -> list[int] | None:
    """Answer route that snakes up and down through vertical lanes, then climbs into the exit from below.

    Edge exits: the snake starts on the far side and works lane by lane toward the exit.
    Middle exit with two sweeps: climb and dive on one side, cross underneath the middle, climb and dive on
    the other side, then climb the middle lane: up, down, up, down, up.
    """
    entry = target + columns
    blocked = blocked | {target}
    everything = set(range(rows * columns))
    top_band = set(range(round(rows * .2), round(rows * .42)))
    low_band = set(range(round(rows * .62), rows - 2))
    route = [start]

    def cells(column_set: set[int], row_set: set[int]) -> set[int]:
        return {row * columns + column for row in row_set for column in column_set}

    def walk_to(goal_cells: set[int], box: set[int]) -> bool:
        used = set(route[:-1]) | blocked
        outside = everything - box
        reach = _free_reach(route[-1], used | outside, rows, columns)
        goals = sorted(goal_cells & reach)
        if not goals:
            return False
        goal = rng.choice(goals)
        segment = _loop_erased_walk(route[-1], lambda node: node == goal, used | outside, rows, columns, rng,
                                    rows * columns * 60)
        if not segment:
            return False
        route.extend(segment[1:])
        return True

    all_rows = set(range(rows))
    start_column = start % columns
    target_column = target % columns
    lane_count = 2 * sweeps + 1
    lanes = _lanes(columns, lane_count)
    target_lane = next(index for index, lane in enumerate(lanes) if target_column in lane)
    if 0 < target_lane < lane_count - 1 and sweeps == 2:
        # Middle exit: side A (two lanes), cross underneath, side B (two lanes), then the middle lane.
        side_a, side_b = ([0, 1], [4, 3]) if rng.random() < .5 else ([4, 3], [0, 1])
        cross_rows = {rows - 3, rows - 2}
        upper_low = set(range(round(rows * .55), rows - 3))
        outer_a, inner_a = lanes[side_a[0]], lanes[side_a[1]]
        outer_b, inner_b = lanes[side_b[0]], lanes[side_b[1]]
        lead = set(range(min(start_column, min(outer_a)), max(start_column, max(outer_a)) + 1))
        steps = [
            (cells(outer_a, {rows - 1}), cells(lead, {rows - 1})),
            (cells(outer_a, top_band), cells(outer_a, all_rows)),
            (cells(inner_a, cross_rows), cells(outer_a | inner_a, all_rows)),
            (cells(outer_b, cross_rows), cells(set(range(columns)) - outer_a, cross_rows)),
            (cells(outer_b, top_band), cells(outer_b, all_rows)),
            (cells(inner_b, upper_low), cells(outer_b | inner_b, set(range(rows - 3)))),
            ({entry}, cells(inner_b | lanes[target_lane], set(range(rows - 3)))),
        ]
        for goal_cells, box in steps:
            if not walk_to(goal_cells, box):
                return None
        return route + [target]
    if 0 < target_lane < lane_count - 1:
        # Middle exit with one sweep: use four lanes so a three-run window can end under the exit.
        lanes = _lanes(columns, lane_count + 1)
        target_lane = next(index for index, lane in enumerate(lanes) if target_column in lane)
        if target_lane - 2 >= 0 and (target_lane + 2 > len(lanes) - 1 or rng.random() < .5):
            order = list(range(target_lane - 2, target_lane + 1))
        elif target_lane + 2 <= len(lanes) - 1:
            order = list(range(target_lane + 2, target_lane - 1, -1))
        else:
            return None
    else:
        order = list(range(lane_count)) if target_lane == lane_count - 1 else list(reversed(range(lane_count)))
    first = lanes[order[0]]
    lead = set(range(min(start_column, min(first)), max(start_column, max(first)) + 1))
    if not walk_to(cells(first, {rows - 1, rows - 2}), cells(lead, {rows - 1, rows - 2})):
        return None
    for step, lane_index in enumerate(order):
        lane = lanes[lane_index]
        previous = lanes[order[step - 1]] if step else lane
        box = cells(lane | previous, all_rows)
        if step == len(order) - 1:
            goal_cells = {entry} if target_column in lane else cells(lane, top_band)
        else:
            goal_cells = cells(lane, top_band if step % 2 == 0 else low_band) - {entry}
        if not walk_to(goal_cells, box):
            return None
    if route[-1] != entry:
        if not walk_to({entry}, cells(lanes[order[-1]] | {target_column}, set(range(max(top_band) + 1)))):
            return None
    return route + [target]


def longest_straight_wall(edges: list[list[int]], rows: int, columns: int) -> int:
    """Longest unbroken interior wall, in cells; long seams are what give away sealed regions."""
    edge_set = {tuple(edge) for edge in edges}
    longest = 0
    for row in range(rows - 1):  # horizontal walls between row and row + 1
        run = 0
        for column in range(columns):
            node = row * columns + column
            run = run + 1 if (node, node + columns) not in edge_set else 0
            longest = max(longest, run)
    for column in range(columns - 1):  # vertical walls between column and column + 1
        run = 0
        for row in range(rows):
            node = row * columns + column
            run = run + 1 if (node, node + 1) not in edge_set else 0
            longest = max(longest, run)
    return longest


def _degree_branches(edges: list[list[int]], route: list[int]) -> int:
    degree: dict[int, int] = {}
    for first, second in edges:
        degree[first] = degree.get(first, 0) + 1
        degree[second] = degree.get(second, 0) + 1
    return sum(degree.get(node, 0) >= 3 for node in route[1:-1])


def _hard_round(index: int, level: dict, rng: random.Random, answer: int) -> RoundSpec | None:
    rows, columns = level["rows"], level["columns"]
    cells = rows * columns
    start = (rows - 1) * columns + rng.choice((columns // 2 - 1, columns // 2))
    route_lanes = _lanes(columns, 2 * level["sweeps"] + 1)
    target = rng.choice(sorted(route_lanes[(0, len(route_lanes) // 2, -1)[answer]]))
    # 1. The answer route: a long serpentine that snakes lane by lane, diving up and down.
    route = _serpentine_route(start, target, set(), rows, columns, rng, level["sweeps"])
    if route is None or not _route_ok(route, target, level):
        return None
    route_cells = set(route)
    labels = {node: answer for node in route}
    edges = [sorted(pair) for pair in zip(route, route[1:])]
    # 2. False exits are placed only where a decoy can dive deep and dead-end right beside the route.
    def decoy_goals(column: int) -> list[int]:
        if column in labels or column + columns in labels:
            return []
        reach = _free_reach(column + columns, set(labels) | {start, column}, rows, columns)
        return sorted(node for node in reach if node // columns >= rows * DECOY_DEPTH
                      and any(n in route_cells for n in grid_neighbors(node, rows, columns)))

    viable = [column for column in range(columns) if decoy_goals(column)]
    combos = []
    for first in viable:
        for second in viable:
            trio = sorted((first, second, target))
            if first < second and trio.index(target) == answer and trio[1] - trio[0] >= 2 and trio[2] - trio[1] >= 2:
                combos.append((first, second))
    if not combos:
        return None
    exits = sorted((*rng.choice(combos), target))
    for label in rng.sample([index for index in range(3) if index != answer], 2):
        column = exits[label]
        goals = decoy_goals(column)  # recomputed: the first decoy may have claimed cells
        if not goals:
            return None
        goal = rng.choice(goals)
        spine = _loop_erased_walk(column + columns, lambda node: node == goal, set(labels) | {start, column},
                                  rows, columns, rng, cells * 80)
        if not spine:
            return None
        spine = [column] + spine
        for node in spine:
            labels[node] = label
        edges.extend(sorted(pair) for pair in zip(spine, spine[1:]))
    false_exits = [node for index, node in enumerate(exits) if index != answer]

    def allowed(first: int, second: int) -> bool:  # top exits only ever open straight down
        return not ((second in exits and first != second + columns) or (first in exits and second != first + columns))

    # 3. Multi-root Wilson forest: region borders follow random walks, so they look like ordinary maze walls.
    order = [node for node in range(cells) if node not in labels]
    rng.shuffle(order)
    for node in order:
        if node in labels:
            continue
        walk = _loop_erased_walk(node, lambda other: other in labels, set(), rows, columns, rng, cells * 400, allowed)
        if walk is None:
            return None
        label = labels[walk[-1]]
        for cell in walk[:-1]:
            labels[cell] = label
        edges.extend(sorted(pair) for pair in zip(walk, walk[1:]))
    edges.sort()
    if len(edges) != cells - 3 or routes(start, edges).get(target) != route:
        return None
    component_sizes = [len(routes(node, edges)) for node in exits]
    if min(size for label, size in enumerate(component_sizes) if label != answer) < level["false_share"] * cells:
        return None
    if longest_straight_wall(edges, rows, columns) > level["max_straight"]:
        return None
    decoy_ends = []
    for exit_node in false_exits:
        point = decoy_point(set(routes(exit_node, edges)), route_cells, rows, columns)
        if point is None:
            return None
        decoy_ends.append(point)
    branches = _degree_branches(edges, route)
    if branches < level["route_branches"]:
        return None
    return RoundSpec(index, "find_the_exit", {
        "layout": HARD_LAYOUT, "rows": rows, "columns": columns, "start": start, "exits": exits,
        "edges": edges, "route": route, "correct_index": answer, "level": index + 1,
        "route_metrics": grid_metrics(route, columns), "route_branch_points": branches,
        "exit_component_sizes": component_sizes, "decoy_ends": decoy_ends,
    }, answer)


def _generate_hard(seed: int, count: int) -> VideoSpec:
    rng = random.Random(f"exit_hard_v3:{seed}:{count}")
    rounds, used = [], set()
    # Answers come from shuffled [0, 1, 2] blocks: every exit is correct at least once per video and
    # the choice is fixed before retries, so acceptance rates cannot bias it.
    answer_rng = random.Random(f"exit_hard_answers:{seed}:{count}")
    answers: list[int] = []
    while len(answers) < count:
        block = [0, 1, 2]
        answer_rng.shuffle(block)
        answers.extend(block)
    for index in range(count):
        level = HARD_LEVELS[level_tier(index, count)]
        answer = answers[index]
        # Keep several valid mazes and publish the most deceptive: the largest smallest decoy region.
        candidates = []
        for _ in range(8000):
            item = _hard_round(index, level, rng, answer)
            if item is not None and item.fingerprint() not in used:
                candidates.append(item)
                if len(candidates) == HARD_CANDIDATES:
                    break
        if not candidates:
            raise RuntimeError("Could not generate a deceptive hard maze")
        best = max(candidates, key=lambda item: (min(size for label, size in enumerate(item.data["exit_component_sizes"])
                                                     if label != item.answer), len(item.data["route"])))
        used.add(best.fingerprint())
        rounds.append(best)
    stable_id = sha256(f"exit_hard_v3:{seed}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "find_the_exit", seed, "hard", "paths", tuple(rounds),
                     PUZZLE_FIT_INTRO_DURATION, round_duration("find_the_exit", "hard"), PUZZLE_FIT_OUTRO_DURATION)


def _hard_errors(data: dict, answer: int) -> list[str]:
    rows, columns = data.get("rows", 0), data.get("columns", 0)
    level = _level_for(rows, columns)
    if level is None:
        return ["invalid hard maze size"]
    cells = rows * columns
    start, exits, edges = data.get("start"), data.get("exits", []), data.get("edges", [])
    if not isinstance(start, int) or start // columns != rows - 1:
        return ["hard maze start must sit on the bottom row"]
    if len(exits) != 3 or len(set(exits)) != 3 or any(node not in range(columns) for node in exits) or exits != sorted(exits):
        return ["hard maze needs three distinct top exits"]
    if any(len(edge) != 2 or edge[0] not in range(cells) or edge[1] not in grid_neighbors(edge[0], rows, columns) for edge in edges):
        return ["maze passages must join adjacent cells"]
    if len(edges) != cells - 3 or len({tuple(sorted(edge)) for edge in edges}) != len(edges):
        return ["maze must contain three disjoint trees"]
    parent = list(range(cells))

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
    route = data.get("route")
    if route != paths[exits[answer]] or not _route_ok(route, exits[answer], level) or data.get("route_metrics") != grid_metrics(route, columns):
        return ["maze reveal route is incorrect or not serpentine enough"]
    edge_set = {tuple(sorted(edge)) for edge in edges}
    if any((node, node + columns) not in edge_set for node in exits):
        return ["every visible exit needs a plausible inward passage"]
    component_sizes = [len(routes(node, edges)) for node in exits]
    false_sizes = [size for index, size in enumerate(component_sizes) if index != answer]
    if data.get("exit_component_sizes") != component_sizes or min(false_sizes) < level["false_share"] * cells:
        return ["false exits must own convincingly large regions"]
    if longest_straight_wall(edges, rows, columns) > level["max_straight"]:
        return ["a long unbroken wall would give away a sealed region"]
    route_cells = set(route)
    expected = [decoy_point(set(routes(node, edges)), route_cells, rows, columns)
                for index, node in enumerate(exits) if index != answer]
    if None in expected or data.get("decoy_ends") != expected:
        return ["each false region must dive deep and dead-end beside the answer route"]
    branches = _degree_branches(edges, route)
    if branches < level["route_branches"] or data.get("route_branch_points") != branches:
        return ["maze does not have enough route branch competition"]
    return []


def generate(seed: int, difficulty: str = "easy", theme: str = "paths", round_count: int | None = None) -> VideoSpec:
    count = round_count or DEFAULT_ROUNDS["find_the_exit"]
    if difficulty == "hard":
        return _generate_hard(seed, count)
    rng = random.Random(f"exit_polish_v1:{seed}:{difficulty}:{count}")
    rounds, used = [], set()
    for index in range(count):
        for _ in range(100):
            item = make_round(index, difficulty, rng)
            if item.fingerprint() not in used:
                used.add(item.fingerprint())
                rounds.append(item)
                break
        else:
            raise RuntimeError("Duplicate maze retry limit")
    stable_id = sha256(f"exit_polish_v1:{seed}:{difficulty}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "find_the_exit", seed, difficulty, "paths", tuple(rounds),
                     INTRO_DURATION, round_duration("find_the_exit", difficulty), OUTRO_DURATION)


def errors(data: dict, answer: int) -> list[str]:
    if data.get("layout") == HARD_LAYOUT:
        return _hard_errors(data, answer)
    size, edges = data.get("size", 0), data.get("edges", [])
    if size not in (5, 6, 7):
        return ["invalid maze size"]
    start, exits = data.get("start"), data.get("exits", [])
    if start != (size - 1) * size + size // 2 or exits != [0, size // 2, size - 1]:
        return ["maze must have one start and three distinct boundary exits"]
    if any(len(edge) != 2 or edge[0] not in range(size * size) or edge[1] not in neighbors(edge[0], size) for edge in edges):
        return ["maze passages must join adjacent cells"]
    if len(edges) != size * size - 3 or len({tuple(sorted(edge)) for edge in edges}) != len(edges):
        return ["maze must contain three disjoint trees"]
    parent = list(range(size * size))
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
    if data.get("route") != paths[exits[answer]]:
        return ["maze reveal route is incorrect"]
    difficulty = {5: "easy", 6: "medium", 7: "hard"}[size]
    rules = DIFFICULTY_RULES[difficulty]
    route = data["route"]
    metrics = route_metrics(route, size)
    if not _balanced_route(route, size, exits[answer], difficulty) or data.get("route_metrics") != metrics:
        return ["maze route does not meet its difficulty profile"]
    edge_set = {tuple(sorted(edge)) for edge in edges}
    if any((root, root + size) not in edge_set for root in exits):
        return ["every visible exit needs a plausible inward passage"]
    degree: dict[int, int] = {}
    for first, second in edges:
        degree[first] = degree.get(first, 0) + 1
        degree[second] = degree.get(second, 0) + 1
    route_branches = sum(degree.get(node, 0) >= 3 for node in route[1:-1])
    if route_branches < rules["route_branches"] or data.get("route_branch_points") != route_branches:
        return ["maze does not have enough route branch competition"]
    component_sizes = [len(routes(root, edges)) for root in exits]
    if data.get("exit_component_sizes") != component_sizes:
        return ["maze exit component metadata is invalid"]
    return []
