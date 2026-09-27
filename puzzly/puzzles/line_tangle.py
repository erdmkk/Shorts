"""Line Follow, Tangle V4: grown lines. Which target does the figure's line reach?

Difficulty comes from line length: every line is grown step by step to a length budget that multiplies level by level
(the figure's line is about 4x longer on level 5 than on level 1, and the decoys grow in proportion), so later levels
fill the board with long, looping lines.

Growing: a line starts at its target and advances in STEP px steps. Its heading drifts smoothly (a correlated random
walk with a bounded turn per step, so it meanders and loops but never kinks) and it bends away from the walls. When it
comes near another line (or an older part of itself) it either crosses it cleanly or turns away:
- a crossing is allowed only at a steep angle and only if the way through is clear of every other line; the line then
  holds its heading until it is well past;
- otherwise it steers away; lines therefore never run alongside or touch without crossing.
The figure's line wanders until it has used its budget, then homes in on the bottom edge; the figure stands where it
lands. Decoys end in dead ends (drawn as small rings), noise lines start at a side edge and end in a dead end.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import math
import random
from typing import Any

from ..config import DEFAULT_ROUNDS, LINE_THINKING, PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION, line_round
from ..models import RoundSpec, VideoSpec

VERSION = "tangle_v4"
BOX = (70.0, 410.0, 1010.0, 1560.0)  # lines stay inside this area (logical 1080x1920)
TARGET_Y = 360.0  # target portals above the box
FIGURE_Y = 1600.0  # the figure's head, below the box
STEP = 8.0
MAX_TURN = STEP / 38.0  # radians per step: curves never bend tighter than a 38 px radius
KISS = 18.0  # closer than this to another line means crossing it (lines are 8 px wide: always a 10 px gap)
CROSS_ANGLE = math.radians(42)  # crossings are at least this steep
CROSS_CLEAR = 30.0  # the way through a crossing is clear of every other line for this far on each side
SELF_SKIP = 70.0  # arc length of its own most recent path a line ignores
WALL = 110.0  # lines turn away from the walls within this distance (a U-turn needs about 2 x 38 px)
FIGURE_KEEP_OUT = 110.0  # other lines keep this far from the figure
END_CLEAR = 26.0  # dead ends keep this far from other lines
LOOKAHEAD = 44.0  # how far ahead a line looks for lines it would meet at a shallow angle
# Level tiers: targets, noise lines, and the figure's line length (px); decoys grow to DECOY_SHARE of it.
TIERS = (
    {"targets": 3, "noise": 0, "length": 1200, "min_cross": 3},
    {"targets": 3, "noise": 0, "length": 2400, "min_cross": 10},
    {"targets": 4, "noise": 1, "length": 3600, "min_cross": 18},
    {"targets": 4, "noise": 0, "length": 4800, "min_cross": 24},
    {"targets": 5, "noise": 0, "length": 5400, "decoy_share": (.62, .78), "min_cross": 30},
)
DECOY_SHARE = (.8, 1.0)
NOISE_SHARE = .6
MIN_DECOY_SHARE = .6  # a decoy that gets stuck early is kept only if it reached this share of its budget


def tiers_for(count: int) -> list[int]:
    """Level 1 is always the shortest tangle and the last level the longest one."""
    return [0, 2, 4] if count <= 3 else [min(index, 4) for index in range(count)]


def target_positions(count: int) -> list[tuple[float, float]]:
    x1, x2 = BOX[0] + 80, BOX[2] - 80
    return [(x1 + index * (x2 - x1) / (count - 1), TARGET_Y) for index in range(count)]


def _angle_between(a: float, b: float) -> float:
    """Angle between two line directions (0..pi/2): a crossing's steepness."""
    d = abs(a - b) % math.pi
    return min(d, math.pi - d)


class Field:
    """Spatial grid of every drawn point: (line, arc position, tangent angle)."""

    CELL = 24.0

    def __init__(self) -> None:
        self.cells = defaultdict(list)

    def add(self, line: int, point, arc: float, tangent: float):
        key = (int(point[0] // self.CELL), int(point[1] // self.CELL))
        item = (line, arc, tangent, point)
        self.cells[key].append(item)
        return key, item

    def discard(self, entry) -> None:
        key, item = entry
        self.cells[key].remove(item)

    def near(self, point, radius: float, line: int, arc: float):
        """Points of other lines (and of this line away from its recent path) within radius."""
        cell, cells = self.CELL, self.cells
        x, y = point
        for cx in range(int((x - radius) // cell), int((x + radius) // cell) + 1):
            for cy in range(int((y - radius) // cell), int((y + radius) // cell) + 1):
                for item in cells.get((cx, cy), ()):
                    if item[0] == line and arc - item[1] < SELF_SKIP:
                        continue
                    if math.dist(point, item[3]) < radius:
                        yield item


def _grow(field: Field, line_id: int, start, heading: float, budget: float, rng: random.Random,
          home: bool = False, forbid=None) -> tuple[list[tuple[float, float]], float] | None:
    """Grow one line from start. Returns (points, length) or None when the figure's line cannot finish."""
    points = [tuple(start)]
    x, y = start
    arc, drift = 0.0, 0.0
    crossing_left = 0  # steps still to go straight through a crossing
    pending: list[tuple] = []  # points drawn but not yet in the field (own recent path)
    lead_in = 8  # leave the start straight for a moment
    states = [(heading, drift, crossing_left, lead_in, arc)]  # walk state after each point, for backing up
    added: list[tuple] = []  # (arc, field entry) of this line's points already in the field
    backtracks = 60
    while True:
        homing = home and arc >= budget
        if not home and arc >= budget:
            break
        if crossing_left > 0:
            candidates = [heading]
        else:
            if lead_in > 0:
                drift = 0.0
            else:
                drift = max(-MAX_TURN, min(MAX_TURN, drift * .86 + rng.gauss(0, MAX_TURN * .38)))
            base = heading + drift
            # Walls (and, while homing, the pull toward the bottom edge).
            # The pull grows smoothly with depth into the wall zone (a hard threshold makes lines zigzag along it).
            push = 0.0
            for depth, away in ((BOX[0] + WALL - x, 0.0), (x - BOX[2] + WALL, math.pi),
                                (BOX[1] + WALL - y, math.pi / 2), (y - BOX[3] + WALL, -math.pi / 2)):
                if depth > 0 and not (homing and away < 0):
                    weight = min(1.0, depth / (WALL * .6)) ** 1.5
                    push += weight * ((away - base + math.pi) % (2 * math.pi) - math.pi)
            if homing:
                push += ((math.pi / 2 - base + math.pi) % (2 * math.pi) - math.pi) * .6
            # Look ahead: lines we would meet at a shallow angle push us away early (steep ones we simply cross).
            ahead = (x + math.cos(base) * LOOKAHEAD, y + math.sin(base) * LOOKAHEAD)
            for hit in field.near(ahead, LOOKAHEAD, line_id, arc + LOOKAHEAD):
                if _angle_between(base, hit[2]) < CROSS_ANGLE:
                    side = math.cos(base) * (hit[3][1] - y) - math.sin(base) * (hit[3][0] - x)  # >0: it is on our right
                    closeness = 1 - math.dist(ahead, hit[3]) / LOOKAHEAD
                    push -= math.copysign(.35 * closeness, side)
            base = heading + max(-2 * MAX_TURN, min(2 * MAX_TURN, drift + push * .9))
            candidates = [base] + [base + side * k * MAX_TURN * .5 for k in (1, 2, 3, 4) for side in (1, -1)]
        moved = False
        for candidate in candidates:
            if abs((candidate - heading + math.pi) % (2 * math.pi) - math.pi) > MAX_TURN * 2.01 and crossing_left == 0:
                continue
            nx, ny = x + math.cos(candidate) * STEP, y + math.sin(candidate) * STEP
            if not (BOX[0] <= nx <= BOX[2] and BOX[1] - 40 <= ny <= BOX[3] + (40 if homing else 0)):
                continue
            if forbid and forbid((nx, ny)):
                continue
            hits = list(field.near((nx, ny), KISS, line_id, arc + STEP))
            if crossing_left == 0 and hits:
                others = {hit[0] for hit in hits}
                if len(others) != 1 or any(_angle_between(candidate, hit[2]) < CROSS_ANGLE for hit in hits):
                    continue  # too shallow, or two lines at once: turn away instead
                # The way through must be clear of everything but this one line.
                # It must also be a single clean pass over that line: no clipping the tip of one of its loops.
                through = int((2 * KISS + 2 * CROSS_CLEAR) / STEP)
                clear = True
                crossed_arcs = [hit[1] for hit in hits]
                for k in range(1, through + 1):
                    px, py = x + math.cos(candidate) * STEP * k, y + math.sin(candidate) * STEP * k
                    if not (BOX[0] <= px <= BOX[2] and BOX[1] - 40 <= py <= BOX[3] + 40):
                        clear = False
                        break
                    in_zone = k * STEP <= 2 * KISS + STEP
                    for hit in field.near((px, py), KISS, line_id, arc + STEP * k):
                        if hit[0] not in others or (in_zone and _angle_between(candidate, hit[2]) < CROSS_ANGLE - .14):
                            clear = False
                            break
                        if in_zone:
                            crossed_arcs.append(hit[1])
                    if not clear or max(crossed_arcs) - min(crossed_arcs) > 5 * KISS:
                        clear = False
                        break
                if not clear:
                    continue
                crossing_left = int((2 * KISS + CROSS_CLEAR) / STEP) + 1
            if crossing_left == 0:  # keep turning the way we just turned: dodging never wiggles back and forth
                turn = (candidate - heading + math.pi) % (2 * math.pi) - math.pi
                drift = max(-MAX_TURN, min(MAX_TURN, turn))
            heading = candidate
            x, y = nx, ny
            moved = True
            break
        if not moved:
            # Boxed in. A decoy that is long enough simply ends here in a dead end; otherwise back up a little
            # and grow that stretch again (the drift is random, so it takes another way).
            if (not home and crossing_left == 0 and arc >= budget * MIN_DECOY_SHARE
                    and _dead_end_ok(field, points, line_id, arc)):
                break
            if backtracks == 0 or len(points) < 12:
                return None if home else (points, arc)
            backtracks -= 1
            keep = max(9, len(points) - rng.randint(10, 40))
            del points[keep:]
            del states[keep:]
            x, y = points[-1]
            heading, drift, crossing_left, lead_in, arc = states[-1]
            while added and added[-1][0] > arc - SELF_SKIP:
                field.discard(added.pop()[1])
            pending = [(line_id, points[i], states[i][4], states[i][0]) for i in range(len(points))
                       if arc - SELF_SKIP < states[i][4] <= arc and states[i][4] > 0]
            continue
        crossing_left = max(0, crossing_left - 1)
        lead_in = max(0, lead_in - 1)
        arc += STEP
        points.append((x, y))
        states.append((heading, drift, crossing_left, lead_in, arc))
        pending.append((line_id, (x, y), arc, heading))
        while pending and arc - pending[0][2] >= SELF_SKIP:  # own path joins the field once it is behind us
            item = pending.pop(0)
            added.append((item[2], field.add(item[0], item[1], item[2], item[3])))
        if homing and y >= BOX[3] and crossing_left == 0:
            if abs((heading - math.pi / 2 + math.pi) % (2 * math.pi) - math.pi) < .7:
                break
        if homing and arc > budget * 1.6:
            for _, entry in added:
                field.discard(entry)
            return None  # could not find the way down
    for item in pending:
        field.add(item[0], item[1], item[2], item[3])
    return points, arc


def _dead_end_ok(field: Field, points, line_id: int, arc: float) -> bool:
    """A dead end must stand clear of other lines (its own path just behind it does not count)."""
    return not any(True for _ in field.near(points[-1], END_CLEAR, line_id, arc))


def _try_round(tier: dict, answer: int, rng: random.Random, scale: float = 1.0) -> dict | None:
    """scale shrinks the decoy and noise budgets a little when a crowded board keeps failing."""
    targets = target_positions(tier["targets"])
    field = Field()
    lines: list[dict] = []
    # 1. The figure's line: grown first, to its full length, then down to the bottom edge.
    start = (targets[answer][0], BOX[1] - 30)
    grown = _grow(field, 0, start, math.pi / 2, tier["length"], rng, home=True)
    if grown is None:
        return None
    points, length = grown
    figure_x = points[-1][0]
    if not (BOX[0] + 60 <= figure_x <= BOX[2] - 60):
        return None
    drop = max(1, math.ceil((FIGURE_Y - 4 - points[-1][1]) / STEP))  # straight down into the figure's head
    points = points + [(figure_x, points[-1][1] + (FIGURE_Y - 4 - points[-1][1]) * k / drop) for k in range(1, drop + 1)]
    lines.append({"kind": "answer", "target": answer, "points": points, "length": round(length, 1)})
    figure = [round(figure_x, 1), FIGURE_Y]

    def forbid(point) -> bool:
        return math.dist(point, (figure_x, FIGURE_Y)) < FIGURE_KEEP_OUT or (abs(point[0] - figure_x) < 40 and point[1] > BOX[3] - 60)

    # 2. Decoys from the other targets, 3. noise lines from the side edges; each ends in a dead end.
    plans = [(index, (target[0], BOX[1] - 30), math.pi / 2, tier["length"] * scale * rng.uniform(*tier.get("decoy_share", DECOY_SHARE)), "decoy")
             for index, target in enumerate(targets) if index != answer]
    for _ in range(tier["noise"]):
        left = rng.random() < .5
        plans.append((-1, (BOX[0] + 2 if left else BOX[2] - 2, rng.uniform(BOX[1] + 250, BOX[3] - 250)),
                      0.0 if left else math.pi, tier["length"] * scale * NOISE_SHARE, "noise"))
    for number, (target, begin, heading, budget, kind) in enumerate(plans, start=1):
        for _ in range(4):
            grown = _grow(field, number, begin, heading, budget, rng, forbid=forbid)
            if grown and grown[1] >= budget * MIN_DECOY_SHARE and _dead_end_ok(field, grown[0], number, grown[1]):
                break
            _remove_line(field, number)
        else:
            return None
        lines.append({"kind": kind, "target": target, "points": grown[0], "length": round(grown[1], 1)})
    for line in lines:
        line["points"] = [[round(x, 1), round(y, 1)] for x, y in _smooth(line["points"])]
        line["start"], line["end"] = line["points"][0], line["points"][-1]
    crossings = crossings_of({"lines": lines})
    answer_crossings = sum(0 in crossing["lines"] for crossing in crossings)
    if answer_crossings < tier["min_cross"]:  # the figure's line must really be tangled up with the others
        return None
    return {"lines": lines, "figure": figure, "targets": [list(target) for target in targets],
            "crossing_count": len(crossings), "answer_crossings": answer_crossings}


def _smooth(points, passes: int = 3) -> list[tuple[float, float]]:
    """Irons out step-to-step jitter (a pixel or two) left by dodging; the ends stay where they are."""
    points = list(points)
    for _ in range(passes):
        points = [points[0]] + [((a[0] + 2 * b[0] + c[0]) / 4, (a[1] + 2 * b[1] + c[1]) / 4)
                                for a, b, c in zip(points, points[1:], points[2:])] + [points[-1]]
    return points


def _remove_line(field: Field, line_id: int) -> None:
    for key in list(field.cells):
        field.cells[key] = [item for item in field.cells[key] if item[0] != line_id]


def make_round(index: int, tier_index: int, rng: random.Random) -> RoundSpec:
    tier = TIERS[tier_index]
    answer = rng.randrange(tier["targets"])  # chosen first, so every target is equally likely
    for attempt in range(320):
        result = _try_round(tier, answer, rng, .94 ** (attempt // 30))
        if result is None:
            continue
        data = {"version": VERSION, "level": index + 1, "tier": tier_index, **result, "correct_index": answer,
                "thinking_seconds": LINE_THINKING[tier_index]}
        if not validate(data, answer):
            return RoundSpec(index, "line_follow", data, answer)
    raise RuntimeError("Could not grow a readable Line Follow tangle")


def average_round(rounds) -> float:
    return round(sum(line_round(float(item.data["thinking_seconds"])) for item in rounds) / max(1, len(rounds)), 4)


def generate(seed: int, count: int) -> VideoSpec:
    rng = random.Random(f"{VERSION}:{seed}:{count}")
    rounds = [make_round(index, tier, rng) for index, tier in enumerate(tiers_for(count))]
    stable_id = sha256(f"{VERSION}:{seed}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "line_follow", seed, None, "lines", tuple(rounds),
                     PUZZLE_FIT_INTRO_DURATION, average_round(rounds), PUZZLE_FIT_OUTRO_DURATION)


# ---------------------------------------------------------------- geometry for drawing and validation

def line_points(line: dict) -> list[tuple[float, float]]:
    return [tuple(point) for point in line["points"]]


def _segment_hit(p1, p2, q1, q2):
    rx, ry = p2[0] - p1[0], p2[1] - p1[1]
    sx, sy = q2[0] - q1[0], q2[1] - q1[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) < 1e-9:
        return None
    qpx, qpy = q1[0] - p1[0], q1[1] - p1[1]
    t = (qpx * sy - qpy * sx) / denominator
    u = (qpx * ry - qpy * rx) / denominator
    if 0 <= t < 1 and 0 <= u < 1:
        return (p1[0] + rx * t, p1[1] + ry * t)
    return None


def crossings_of(data: dict) -> list[dict]:
    """Every crossing (point, the two line indices, and its steepness) of a round's lines."""
    cell = 24.0
    grid = defaultdict(list)
    found = []
    for line_index, line in enumerate(data["lines"]):
        points = line_points(line)
        for index, (a, b) in enumerate(zip(points, points[1:])):
            keys = {(int(p[0] // cell), int(p[1] // cell)) for p in (a, b)}
            seen = set()
            for key in keys:
                for other, j, q1, q2 in grid.get(key, ()):
                    if (other, j) in seen or (other == line_index and index - j < 3):
                        continue
                    seen.add((other, j))
                    hit = _segment_hit(a, b, q1, q2)
                    if hit:
                        angle = _angle_between(math.atan2(b[1] - a[1], b[0] - a[0]), math.atan2(q2[1] - q1[1], q2[0] - q1[0]))
                        found.append({"point": hit, "lines": (line_index, other), "angle": angle})
            for key in keys:
                grid[key].append((line_index, index, a, b))
    return found


def validate(data: dict, answer: int) -> list[str]:
    tier_index = data.get("tier")
    if tier_index not in range(len(TIERS)):
        return ["line follow level is invalid"]
    tier = TIERS[tier_index]
    lines = data.get("lines", [])
    answers = [line for line in lines if line.get("kind") == "answer"]
    if len(answers) != 1 or answers[0].get("target") != answer or data.get("correct_index") != answer:
        return ["exactly one line must lead from the figure to the answer"]
    if sum(line.get("kind") == "decoy" for line in lines) != tier["targets"] - 1:
        return ["every other target needs a decoy line"]
    figure = data.get("figure")
    end = answers[0]["points"][-1]
    if not figure or abs(end[0] - figure[0]) > 1 or end[1] < FIGURE_Y - 10:
        return ["the figure's line must end at the figure"]
    if answers[0].get("length", 0) < tier["length"] * .99:
        return ["the figure's line is shorter than its level requires"]
    for line in lines:
        points = line_points(line)
        for a, b, c in zip(points, points[1:], points[2:]):
            turn = abs((math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0]) + math.pi) % (2 * math.pi) - math.pi)
            if turn > MAX_TURN * 2.3:  # 2 x MAX_TURN plus the 0.1 px rounding of stored points
                return ["a line bends too sharply"]
    crossings = crossings_of(data)
    if any(crossing["angle"] < CROSS_ANGLE - .12 for crossing in crossings):
        return ["a crossing is too shallow to read"]
    answer_index = lines.index(answers[0])
    if sum(answer_index in crossing["lines"] for crossing in crossings) < tier["min_cross"]:
        return ["the figure's line crosses too few other lines for its level"]
    if data.get("thinking_seconds") != LINE_THINKING[tier_index]:
        return ["line follow thinking time does not match its level"]
    return []
