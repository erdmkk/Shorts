from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
import random
from typing import Any

from ..config import (LUCKY_APPEARANCE_DURATION, LUCKY_INTRO_DURATION, LUCKY_SELECTION_DURATION,
                      LUCKY_WINNER_HOLD, OUTRO_DURATION)
from ..models import RoundSpec, VideoSpec
from .memory_challenge import SHAPES

TARGET_COUNT = 7
TARGET_SIZE = 136
CORRIDOR_WIDTH = 170
BOARD_BOUNDS = (90, 245, 990, 1595)
TRAVEL_SPEED = 640.0
EAT_ANTICIPATION = 0.14
EAT_BITE = 0.32
POST_EAT = 0.12
EAT_DURATION = 0.58
COLORS = {"red": "#D9434E", "blue": "#2874C6", "yellow": "#DCA915", "green": "#319457",
          "purple": "#7654C5", "orange": "#E86F27", "pink": "#D94F8A"}

Point = tuple[int, int]
Path = tuple[Point, ...]


@dataclass(frozen=True)
class CorridorTemplate:
    id: str
    entrance: Point
    terminal_paths: tuple[Path, ...]


def _tree(identifier: str, top_y: int, branches: tuple[tuple[int,int],...]) -> CorridorTemplate:
    spine: Path = ((540,1450),) + tuple((540,y) for y,_ in branches) + ((540,top_y),)
    paths = tuple(spine[:index+2] + ((x,y),) for index,(y,x) in enumerate(branches))
    return CorridorTemplate(identifier, spine[0], paths + (spine,))


TEMPLATES = (
    _tree("staggered_sprout",340,((1250,240),(1090,850),(920,190),(755,875),(590,265),(435,820))),
    _tree("side_switch",350,((1270,820),(1110,210),(945,870),(775,250),(610,845),(450,190))),
    _tree("gentle_ladder",335,((1230,300),(1050,880),(885,220),(720,820),(550,180),(400,760))),
    _tree("playful_trunk",345,((1260,850),(1080,280),(910,890),(745,190),(575,790),(420,250))),
    _tree("garden_steps",340,((1240,210),(1070,810),(895,270),(730,880),(565,200),(410,835))),
    _tree("curious_branches",345,((1280,780),(1100,180),(930,840),(760,300),(600,890),(440,230))),
)


def _mirror_point(point: Point) -> Point:
    return 1080 - point[0], point[1]


def _axis_aligned(a: Point | list[int], b: Point | list[int]) -> bool:
    return (a[0] == b[0]) != (a[1] == b[1])


def _segment_key(a: Point, b: Point) -> tuple[Point, Point]:
    return (a, b) if a <= b else (b, a)


def template_geometry(template: CorridorTemplate, mirrored: bool) -> dict[str, Any]:
    paths = [[list(_mirror_point(point) if mirrored else point) for point in path]
             for path in template.terminal_paths]
    segments: list[list[list[int]]] = []
    seen: set[tuple[Point, Point]] = set()
    for path in paths:
        for first, second in zip(path, path[1:]):
            a, b = tuple(first), tuple(second)
            key = _segment_key(a, b)
            if key not in seen:
                seen.add(key)
                segments.append([list(a), list(b)])
    entrance = list(_mirror_point(template.entrance) if mirrored else template.entrance)
    return {"entrance": entrance, "terminal_paths": paths, "corridors": segments,
            "terminals": [path[-1] for path in paths]}


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
    paths, terminals = geometry["terminal_paths"], geometry["terminals"]
    if len(paths) != TARGET_COUNT or len(terminals) != TARGET_COUNT:
        result.append("corridor template must contain seven terminal paths")
    x1, y1, x2, y2 = BOARD_BOUNDS
    entrance = geometry["entrance"]
    if not (x1 <= entrance[0] <= x2 and y1 <= entrance[1] <= y2):
        result.append("corridor entrance is outside the board")
    for path in paths:
        if path[0] != entrance or len(path) < 3 or len(set(map(tuple, path))) != len(path):
            result.append("every terminal path must be connected to the single entrance")
        if any(not _axis_aligned(a, b) for a, b in zip(path, path[1:])):
            result.append("corridor contains diagonal or zero-length travel")
        if any(not (x1 <= point[0] <= x2 and y1 <= point[1] <= y2) for point in path):
            result.append("corridor point is outside safe bounds")
    if len(set(map(tuple, terminals))) != TARGET_COUNT:
        result.append("corridor terminals must be unique")
    if any(math.dist(a, b) < TARGET_SIZE + 28 for index, a in enumerate(terminals) for b in terminals[index+1:]):
        result.append("corridor terminals overlap")
    radius = TARGET_SIZE / 2
    if any(not (x1+radius <= point[0] <= x2-radius and y1+radius <= point[1] <= y2-radius) for point in terminals):
        result.append("target region leaves safe bounds")
    segments = [(tuple(a), tuple(b)) for a, b in geometry["corridors"]]
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
    if visited != set(nodes) or len(segments) != len(nodes) - 1:
        result.append("corridor network must be one connected loop-free tree")
    terminal_set = set(map(tuple, terminals))
    if any(len(nodes.get(point, set())) != 1 for point in terminal_set):
        result.append("every target must be anchored to a terminal endpoint")
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


def route_between(paths: list[list[list[int]]], previous: int | None, target: int) -> list[list[int]]:
    destination = paths[target]
    if previous is None:
        return [list(point) for point in destination]
    origin = paths[previous]
    shared = 0
    for first, second in zip(origin, destination):
        if first != second:
            break
        shared += 1
    junction = max(0, shared - 1)
    return ([list(point) for point in reversed(origin[junction:])] +
            [list(point) for point in destination[junction+1:]])


def _balanced_order(rng: random.Random, paths: list[list[list[int]]], losers: list[int]) -> list[int]:
    candidates: dict[tuple[int, ...], float] = {}
    for _ in range(96):
        order = list(losers); rng.shuffle(order)
        lengths = [path_length(route_between(paths, order[index-1] if index else None, target))
                   for index, target in enumerate(order)]
        score = sum(abs(length - 1050) for length in lengths) + max(lengths) * .22
        if min(lengths) < 420:
            score += (420 - min(lengths)) * 3
        key = tuple(order)
        candidates[key] = min(score, candidates.get(key, score))
    ranked = sorted(candidates, key=candidates.get)
    pool = ranked[:min(12, len(ranked))]
    return list(rng.choice(pool))


def _movement_steps(geometry: dict[str, Any], order: list[int]) -> tuple[list[dict[str, Any]], float]:
    steps: list[dict[str, Any]] = []
    total = LUCKY_APPEARANCE_DURATION + LUCKY_SELECTION_DURATION
    paths = geometry["terminal_paths"]
    previous: int | None = None
    for target in order:
        route = route_between(paths, previous, target)
        travel_duration = path_length(route) / TRAVEL_SPEED
        step = {"target_index": target, "travel_path": route, "travel_duration": round(travel_duration, 4),
                "hesitation_duration": 0.0, "eat_duration": EAT_DURATION,
                "start_time": round(total, 4)}
        total += travel_duration + EAT_DURATION
        step["end_time"] = round(total, 4)
        steps.append(step); previous = target
    return steps, round(total + LUCKY_WINNER_HOLD, 4)


def generate(seed: int, difficulty: str | None = None, theme: str = "lucky_pick",
             round_count: int | None = None) -> VideoSpec:
    if round_count not in (None, 1):
        raise ValueError("Lucky Pick contains one game")
    rng = random.Random(f"lucky_pick_entry_tree_v1:{seed}")
    template = rng.choice(TEMPLATES); mirrored = bool(rng.randrange(2)); shape_id = rng.choice(SHAPES)
    geometry = template_geometry(template, mirrored)
    color_ids = list(COLORS); rng.shuffle(color_ids)
    targets = [{"index": index, "shape_id": shape_id, "color_id": color_id,
                "color_value": COLORS[color_id], "position": position}
               for index, (color_id, position) in enumerate(zip(color_ids, geometry["terminals"]))]
    winner_index = rng.randrange(TARGET_COUNT)
    losers = [index for index in range(TARGET_COUNT) if index != winner_index]
    order = _balanced_order(rng, geometry["terminal_paths"], losers)
    steps, timeline_duration = _movement_steps(geometry, order)
    data = {"corridor_template_id": template.id, "mirrored": mirrored,
            "entrance": geometry["entrance"], "terminal_paths": geometry["terminal_paths"],
            "corridors": geometry["corridors"], "targets": targets, "target_count": TARGET_COUNT,
            "target_size": TARGET_SIZE, "shape_id": shape_id, "winner_index": winner_index,
            "winner_color": targets[winner_index]["color_id"], "elimination_order": order,
            "movement_steps": steps, "selection_seconds": LUCKY_SELECTION_DURATION,
            "eat_seconds": EAT_DURATION, "timeline_duration": timeline_duration}
    game = RoundSpec(0, "lucky_pick", data, winner_index)
    stable_id = sha256(f"lucky_pick_visual_balance_v1:{seed}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "lucky_pick", seed, None, "lucky_pick", (game,),
                     LUCKY_INTRO_DURATION, timeline_duration, OUTRO_DURATION)


def errors(data: dict[str, Any], answer: Any) -> list[str]:
    result: list[str] = []
    template = next((item for item in TEMPLATES if item.id == data.get("corridor_template_id")), None)
    if template is None:
        return ["lucky corridor template is unknown"]
    mirrored = data.get("mirrored")
    if not isinstance(mirrored, bool):
        result.append("lucky mirror state is invalid"); mirrored = False
    geometry = template_geometry(template, mirrored); result.extend(template_errors(template, mirrored))
    if (data.get("entrance") != geometry["entrance"] or data.get("terminal_paths") != geometry["terminal_paths"]
            or data.get("corridors") != geometry["corridors"]):
        result.append("lucky corridor geometry does not match its template")
    targets = data.get("targets", []); shape_id = data.get("shape_id")
    colors = [target.get("color_id") for target in targets]
    if len(targets) != TARGET_COUNT or data.get("target_count") != TARGET_COUNT:
        result.append("lucky pick must contain exactly seven targets")
    if shape_id not in SHAPES or any(target.get("shape_id") != shape_id for target in targets):
        result.append("lucky targets must use one supported shape")
    if len(set(colors)) != TARGET_COUNT or set(colors) != set(COLORS):
        result.append("lucky pick must use seven distinct curated colors")
    if any(target.get("index") != index or target.get("position") != geometry["terminals"][index]
           or target.get("color_value") != COLORS.get(target.get("color_id")) for index, target in enumerate(targets)):
        result.append("lucky target mapping is invalid")
    winner, order = data.get("winner_index"), data.get("elimination_order", [])
    if not isinstance(winner, int) or winner not in range(TARGET_COUNT) or answer != winner:
        result.append("lucky winner is invalid")
    losers = set(range(TARGET_COUNT)) - ({winner} if isinstance(winner, int) else set())
    if len(order) != 6 or len(set(order)) != 6 or set(order) != losers or winner in order:
        result.append("lucky elimination order is invalid")
    if data.get("winner_color") != (targets[winner]["color_id"] if isinstance(winner, int) and winner in range(len(targets)) else None):
        result.append("lucky winner color is inconsistent")
    if data.get("selection_seconds") != 5.0 or data.get("eat_seconds") != EAT_DURATION:
        result.append("lucky timing metadata is invalid")
    expected_steps, expected_duration = _movement_steps(geometry, order) if len(order) == 6 else ([], 0)
    if data.get("movement_steps") != expected_steps or data.get("timeline_duration") != expected_duration:
        result.append("lucky movement timeline is invalid")
    return result
