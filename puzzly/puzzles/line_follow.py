from __future__ import annotations

from hashlib import sha256
import math
import random
from ..config import DEFAULT_ROUNDS, INTRO_DURATION, OUTRO_DURATION, round_duration
from ..models import RoundSpec, VideoSpec

TOP, BOTTOM = 430.0, 1320.0
DIFFICULTY_RULES = {
    "easy": {"path_count": 3, "crossings": 2, "target_crossings": 1, "span": 1, "turns": 0, "min_path_interactions": 1},
    "medium": {"path_count": 4, "crossings": 6, "target_crossings": 3, "span": 2, "turns": 1, "min_path_interactions": 1},
    "hard": {"path_count": 5, "crossings": 12, "target_crossings": 8, "span": 3, "turns": 3, "min_path_interactions": 3},
}

Point = tuple[float, float]
Curve = tuple[Point, Point, Point, Point]


def lane_positions(path_count: int) -> tuple[float, ...]:
    return tuple(200.0 + index * 680.0 / (path_count - 1) for index in range(path_count))


def cubic_point(curve: Curve, t: float) -> Point:
    p0, p1, p2, p3 = curve
    u = 1.0 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
    )


def _distance_to_line(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == dy == 0:
        return math.dist(point, start)
    return abs(dy * point[0] - dx * point[1] + end[0] * start[1] - end[1] * start[0]) / math.hypot(dx, dy)


def sample_cubic(curve: Curve, tolerance: float = 0.16) -> list[Point]:
    points: list[Point] = [curve[0]]

    def visit(current: Curve, depth: int = 0) -> None:
        p0, p1, p2, p3 = current
        flat = max(_distance_to_line(p1, p0, p3), _distance_to_line(p2, p0, p3)) <= tolerance
        if depth >= 12 or (flat and math.dist(p0, p3) <= 5.0):
            points.append(p3)
            return
        p01 = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        p12 = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
        p23 = ((p2[0] + p3[0]) / 2, (p2[1] + p3[1]) / 2)
        p012 = ((p01[0] + p12[0]) / 2, (p01[1] + p12[1]) / 2)
        p123 = ((p12[0] + p23[0]) / 2, (p12[1] + p23[1]) / 2)
        middle = ((p012[0] + p123[0]) / 2, (p012[1] + p123[1]) / 2)
        visit((p0, p01, p012, middle), depth + 1)
        visit((middle, p123, p23, p3), depth + 1)

    visit(curve)
    return points


def curve_geometry(swaps: list[int], path_count: int) -> tuple[list[list[Curve]], list[dict], list[int]]:
    """Build a C1-continuous braid with vertical tangents at every stage boundary."""
    lanes = lane_positions(path_count)
    positions = list(range(path_count))  # path id -> current lane
    curves: list[list[Curve]] = [[] for _ in range(path_count)]
    crossings: list[dict] = []
    height = (BOTTOM - TOP) / len(swaps)
    for stage, boundary in enumerate(swaps):
        before = positions.copy()
        left_path, right_path = positions.index(boundary), positions.index(boundary + 1)
        positions[left_path], positions[right_path] = positions[right_path], positions[left_path]
        y0, y3 = TOP + stage * height, TOP + (stage + 1) * height
        for line in range(path_count):
            x0, x3 = lanes[before[line]], lanes[positions[line]]
            curves[line].append(((x0, y0), (x0, y0 + height / 3),
                                 (x3, y0 + 2 * height / 3), (x3, y3)))
        center = cubic_point(curves[left_path][-1], 0.5)
        crossings.append({"stage": stage, "over": left_path, "under": right_path,
                          "center": [round(center[0], 6), round(center[1], 6)]})
    return curves, crossings, positions


def geometry(swaps: list[int], path_count: int = 3) -> tuple[list[list[Point]], list[dict], list[int]]:
    curves, crossings, destinations = curve_geometry(swaps, path_count)
    paths: list[list[Point]] = []
    for line_curves in curves:
        path = [line_curves[0][0]]
        for curve in line_curves:
            path.extend(sample_cubic(curve)[1:])
        paths.append(path)
    return paths, crossings, destinations


def crossing_curve(swaps: list[int], path_count: int, crossing: dict) -> list[Point]:
    curves, _, _ = curve_geometry(swaps, path_count)
    curve = curves[crossing["over"]][crossing["stage"]]
    # The visible top stroke deliberately extends far beyond the shorter
    # clearing halo so the bridge reconnects to the base path without gaps.
    return [cubic_point(curve, 0.14 + index * 0.72 / 40) for index in range(41)]


def crossing_halo_curve(swaps: list[int], path_count: int, crossing: dict) -> list[Point]:
    curves, _, _ = curve_geometry(swaps, path_count)
    curve = curves[crossing["over"]][crossing["stage"]]
    return [cubic_point(curve, 0.36 + index * 0.28 / 20) for index in range(21)]


def _max_idle_run(participation: list[list[int]], stage_count: int) -> int:
    maximum = 0
    for stages in participation:
        active = set(stages)
        run = 0
        for stage in range(stage_count):
            run = 0 if stage in active else run + 1
            maximum = max(maximum, run)
    return maximum


def _idle_run(stages: list[int], stage_count: int) -> int:
    active = set(stages)
    run = maximum = 0
    for stage in range(stage_count):
        run = 0 if stage in active else run + 1
        maximum = max(maximum, run)
    return maximum


def _metrics(swaps: list[int], path_count: int, source: int, include_trace: bool = True) -> dict[str, object]:
    curves, crossings, _ = curve_geometry(swaps, path_count)
    lanes = lane_positions(path_count)
    positions_by_path = [[curve[0][0] for curve in line_curves] + [line_curves[-1][-1][0]] for line_curves in curves]
    moves = [1 if end > start else -1 for start, end in zip(positions_by_path[source], positions_by_path[source][1:]) if end != start]
    turns = sum(a != b for a, b in zip(moves, moves[1:]))
    participation = [[crossing["stage"] for crossing in crossings if line in (crossing["over"], crossing["under"])]
                     for line in range(path_count)]
    target_stages = participation[source]
    target_opponents = {crossing["under"] if crossing["over"] == source else crossing["over"]
                        for crossing in crossings if source in (crossing["over"], crossing["under"])}
    trace_length = 0.0
    if include_trace:
        path = geometry(swaps, path_count)[0][source]
        trace_length = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
    lateral = [sum(abs(b - a) for a, b in zip(points, points[1:])) for points in positions_by_path]
    lane_gap = lanes[1] - lanes[0]
    source_points = positions_by_path[source]
    lower_start = len(crossings) // 2
    below_top_start = math.ceil(len(crossings) * 0.35)
    final_third_start = math.floor(len(crossings) * 2 / 3)
    path_lower_interactions = [sum(stage >= lower_start for stage in stages) for stages in participation]
    third_counts = [sum(min(2, stage * 3 // len(crossings)) == section for stage in target_stages)
                    for section in range(3)]
    return {
        "target_crossings": len(target_stages),
        "target_span": round((max(source_points) - min(source_points)) / lane_gap),
        "direction_changes": turns,
        "trace_length": round(trace_length, 3),
        "first_decision": min(target_stages),
        "last_decision": max(target_stages),
        "path_interactions": [len(stages) for stages in participation],
        "min_path_interactions": min(len(stages) for stages in participation),
        "target_unique_interactions": len(target_opponents),
        "target_lateral_travel": round(lateral[source], 3),
        "average_lateral_travel": round(sum(lateral) / path_count, 3),
        "max_idle_run": _max_idle_run(participation, len(crossings)),
        "target_max_idle_run": _idle_run(target_stages, len(crossings)),
        "target_below_top_35_interactions": sum(stage >= below_top_start for stage in target_stages),
        "target_lower_half_interactions": sum(stage >= lower_start for stage in target_stages),
        "target_final_third_interactions": sum(stage >= final_third_start for stage in target_stages),
        "target_interactions_by_third": third_counts,
        "path_lower_half_interactions": path_lower_interactions,
        "min_lower_half_path_interactions": min(path_lower_interactions),
        "lower_half_active_paths": sum(value > 0 for value in path_lower_interactions),
        "plausible_exits": path_count,
    }


def _routing(rng: random.Random, difficulty: str) -> tuple[list[int], int, dict[str, object]]:
    rules = DIFFICULTY_RULES[difficulty]
    count, stages = rules["path_count"], rules["crossings"]
    target_probability = {"easy": 0.45, "medium": 0.58, "hard": 0.72}[difficulty]
    for _ in range(12_000):
        source = rng.randrange(count)
        positions = list(range(count))
        swaps: list[int] = []
        if difficulty == "hard":
            target_stage_set: set[int] = set()
            for start in (0, 4, 8):
                target_stage_set.update(rng.sample(range(start, start + 4), 2))
            remaining = [stage for stage in range(stages) if stage not in target_stage_set]
            target_stage_set.update(rng.sample(remaining, 2))
        else:
            target_stage_set = set()
        for stage in range(stages):
            source_lane = positions[source]
            involving = [value for value in (source_lane - 1, source_lane) if 0 <= value < count - 1]
            all_boundaries = list(range(count - 1))
            if difficulty == "hard":
                non_involving = [value for value in all_boundaries if value not in involving]
                pool = involving if stage in target_stage_set else non_involving
            else:
                pool = involving if involving and rng.random() < target_probability else all_boundaries
            if swaps and len(pool) > 1:
                non_repeat = [value for value in pool if value != swaps[-1]]
                if non_repeat:
                    pool = non_repeat
            boundary = rng.choice(pool)
            left_path, right_path = positions.index(boundary), positions.index(boundary + 1)
            positions[left_path], positions[right_path] = positions[right_path], positions[left_path]
            swaps.append(boundary)
        metrics = _metrics(swaps, count, source, include_trace=False)
        if (metrics["target_crossings"] >= rules["target_crossings"]
                and metrics["target_span"] >= rules["span"]
                and metrics["direction_changes"] >= rules["turns"]
                and metrics["min_path_interactions"] >= rules["min_path_interactions"]
                and (difficulty != "hard" or (
                    metrics["first_decision"] <= 1
                    and metrics["last_decision"] >= stages - 2
                    and metrics["target_unique_interactions"] >= 3
                    and metrics["max_idle_run"] <= 4
                    and metrics["target_max_idle_run"] <= 2
                    and metrics["target_below_top_35_interactions"] >= 5
                    and metrics["target_lower_half_interactions"] >= 4
                    and metrics["target_final_third_interactions"] >= 2
                    and min(metrics["target_interactions_by_third"]) >= 2
                    and metrics["min_lower_half_path_interactions"] >= 1
                    and metrics["lower_half_active_paths"] == count))):
            return swaps, source, _metrics(swaps, count, source)
    raise RuntimeError("Could not create a balanced Line Follow route")


# ---------------------------------------------------------------- current: free-form tangle (see line_tangle)

def generate(seed: int, difficulty: str | None = None, theme: str = "lines", round_count: int | None = None) -> VideoSpec:
    """Current Line Follow (Weave V8, see line_weave): produced only in Hard; every video ramps up level by level."""
    from . import line_weave
    return line_weave.generate(seed, round_count or DEFAULT_ROUNDS["line_follow"])


def generate_legacy(seed: int, difficulty: str = "easy", theme: str = "lines", round_count: int | None = None) -> VideoSpec:
    """The earlier light-theme Line Follow (routing v8); kept so old records stay valid."""
    difficulty = difficulty if difficulty in DIFFICULTY_RULES else "easy"
    count = round_count or DEFAULT_ROUNDS["line_follow"]
    rng = random.Random(f"line_v8:{seed}:{difficulty}:{count}")
    rounds: list[RoundSpec] = []
    used: set[tuple[tuple[int, ...], int]] = set()
    for index in range(count):
        for _ in range(500):
            swaps, source, metrics = _routing(rng, difficulty)
            key = (tuple(swaps), source)
            if key in used:
                continue
            used.add(key)
            paths, crossings, destinations = geometry(swaps, DIFFICULTY_RULES[difficulty]["path_count"])
            answer = destinations[source]
            rounds.append(RoundSpec(index, "line_follow", {
                "path_count": len(paths), "swaps": swaps, "source": source, "destinations": destinations,
                "crossings": crossings, "correct_index": answer, "metrics": metrics, "routing_version": "v8",
            }, answer))
            break
        else:
            raise RuntimeError("Duplicate Line Follow retry limit")
    stable_id = sha256(f"line_v8:{seed}:{difficulty}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "line_follow", seed, difficulty, "lines", tuple(rounds),
                     INTRO_DURATION, round_duration("line_follow", difficulty), OUTRO_DURATION)


def errors(data: dict, answer: int) -> list[str]:
    from . import line_weave
    if line_weave.is_weave(data):
        return line_weave.validate(data, answer)
    if data.get("version") == "tangle_v4":  # earlier samples; they can no longer be rendered
        from . import line_tangle
        return line_tangle.validate(data, answer)
    path_count, swaps, source = data.get("path_count"), data.get("swaps", []), data.get("source")
    difficulty = {3: "easy", 4: "medium", 5: "hard"}.get(path_count)
    if difficulty is None or len(swaps) != DIFFICULTY_RULES[difficulty]["crossings"]:
        return ["path count or crossing count is invalid"]
    if any(type(value) is not int or value not in range(path_count - 1) for value in swaps):
        return ["invalid adjacent crossing"]
    if type(source) is not int or source not in range(path_count):
        return ["exactly one designated source is required"]
    paths, crossings, destinations = geometry(swaps, path_count)
    if data.get("crossings") != crossings or len({crossing["stage"] for crossing in crossings}) != len(crossings):
        return ["every crossing requires one explicit overpass"]
    if data.get("destinations") != destinations or sorted(destinations) != list(range(path_count)):
        return ["each independent path must have one unique destination"]
    if answer != destinations[source] or data.get("correct_index") != answer:
        return ["target line destination is incorrect"]
    if any(not (180 <= x <= 900 and 400 <= y <= 1350) for path in paths for x, y in path):
        return ["line geometry is clipped"]
    if any(not all(a[1] < b[1] for a, b in zip(path, path[1:])) for path in paths):
        return ["paths must remain monotonic without self-intersections"]
    lanes = lane_positions(path_count)
    if min(b - a for a, b in zip(lanes, lanes[1:])) < 150:
        return ["minimum lane spacing is too small"]
    metrics = _metrics(swaps, path_count, source)
    rules = DIFFICULTY_RULES[difficulty]
    if (data.get("metrics") != metrics or metrics["target_crossings"] < rules["target_crossings"]
            or metrics["target_span"] < rules["span"] or metrics["direction_changes"] < rules["turns"]
            or metrics["min_path_interactions"] < rules["min_path_interactions"]):
        return ["route complexity is below difficulty requirements"]
    if difficulty == "hard" and (metrics["first_decision"] > 1 or metrics["last_decision"] < 10
                                  or metrics["target_unique_interactions"] < 3 or metrics["max_idle_run"] > 4
                                  or metrics["target_max_idle_run"] > 2
                                  or metrics["target_below_top_35_interactions"] < 5
                                  or metrics["target_lower_half_interactions"] < 4
                                  or metrics["target_final_third_interactions"] < 2
                                  or min(metrics["target_interactions_by_third"]) < 2
                                  or metrics["min_lower_half_path_interactions"] < 1
                                  or metrics["lower_half_active_paths"] != path_count):
        return ["hard routing is not balanced across all paths"]
    if data.get("routing_version") != "v8":
        return ["line follow routing version is invalid"]
    return []
