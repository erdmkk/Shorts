from __future__ import annotations

from collections import deque
from hashlib import sha256
import random

from ..config import DEFAULT_ROUNDS, INTRO_DURATION, OUTRO_DURATION, round_duration
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


def generate(seed: int, difficulty: str = "easy", theme: str = "paths", round_count: int | None = None) -> VideoSpec:
    count = round_count or DEFAULT_ROUNDS["find_the_exit"]
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
