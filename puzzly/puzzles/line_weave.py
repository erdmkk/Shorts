"""Line Follow, Weave V7: which target does the figure's line reach?

Target portals sit across the top, each with its own line. Only one line reaches the bottom: the figure's line, which
leaves the figure's head (the figure is the only start point, so the viewer never has to guess where to begin). Every
other line wanders the board and simply stops at a loose end, well away from the figure. Lines are smooth uniform cubic
B-splines (stored as their control points), all drawn in the same colour.

Lines are long and fill the board: while it grows, a line keeps heading for the emptiest part of the board it can
reach, until it has used its length budget. The figure's line is grown first, from the figure: it may use the whole
board, and when its length is used up it climbs to a gate under its target and straight up the target's chimney (the
band under the targets is only ever used for leaving targets, so that way is always open). It is stored in that
direction, figure to target. Every other line grows from its target and ends as soon as its tip is clear of
everything else.

Lines are grown one at a time, control point by control point. Each new control point finalises one more piece of
the curve, and that piece is checked against the board at once; if no heading works the line backs up and tries
another way. The rules, re-checked by `validate` from the stored control points:
- two lines closer than NEAR must be crossing there, and every crossing is at least CROSS_ANGLE steep;
- crossings keep CROSS_GAP apart (never three lines at one point), and the same two lines never cross twice within a
  few crossing lengths (no lens or S-shaped knots);
- no bend is tighter than MIN_RADIUS; every line leaves its start and enters its target straight;
- no line comes within END_CLEAR of another line's end or a target's chimney, and no other line comes near the figure.
Difficulty grows level by level (TIERS): longer lines, more crossings on the figure's line, a fuller board. The target
nearest above the figure is never the answer, so guessing "straight up" never works.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from hashlib import sha256
import math
import random

from ..config import LINE_THINKING, LINE_THINKING_V7, PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION, line_round
from ..models import RoundSpec, VideoSpec

VERSION = "weave_v8"  # 4, 5, 5, 6, 6 lines; weave_v7 (5, 5, 5, 4, 4) records still validate and render
VERSIONS = ("weave_v7", VERSION)


def is_weave(data: dict) -> bool:
    return data.get("version") in VERSIONS
BOX = (86.0, 452.0, 994.0, 1558.0)  # control points (so the whole curve) stay inside this box
TOP_Y, BOTTOM_Y = 410.0, 1600.0  # line starts under the target portals; the figure's head on the bottom row
TARGET_Y = 368.0  # centre of the target portals
FIGURE_X = (220.0, 860.0)  # the figure stands somewhere along the bottom row
FIGURE_CLEAR = 150.0  # other lines keep this far from the figure's head
LOWEST = 1640.0  # lines may fill the board down to here (the bottom corners too), away from the figure
END_MAX_Y = 1400.0  # loose ends stay well above the bottom row, so the figure's line is the only start down there
LEAD = (30.0, 62.0)  # straight lead-in (and lead-out into the figure): control points this far from each end
SAMPLE = 5.0  # arc spacing of the curve samples
NEAR = 18.0  # lines are 7.5 px wide, so two lines that do not cross always show a gap of more than 10 px
CROSS_ANGLE = math.radians(36)  # the casing makes a 36 degree crossing read clearly
WINDOW = NEAR / math.sin(CROSS_ANGLE) + 2 * SAMPLE  # arc length around a crossing where two lines may be close
CROSS_GAP = 32.0
REPEAT_WINDOWS = 2.5  # the same two lines never cross again within this many crossing windows
END_CLEAR = 40.0
MIN_RADIUS = 30.0
SELF_SKIP = 70.0  # arc length of its own neighbourhood a line ignores
STEP = 90.0  # control-point spacing
TURN = math.radians(45)  # most a line turns per control step (curves never tighter than ~115 px)
OFFSETS = tuple(math.radians(value) for value in (0, 15, -15, 30, -30, 45, -45))
REACH = 1.9 * STEP  # a goal counts as reached this close: wider than a turn, so a line never orbits one
GOAL_PATIENCE = 8  # control steps a line keeps heading for a blocked goal before it picks another
GOAL_SPAN = (230.0, 950.0)  # how far away a line looks for its next goal
GOAL_MARGIN = 90.0  # goals stay this far inside the sides and bottom (so lines reach the corners too) ...
GOAL_TOP_MARGIN = 130.0  # ... and this far under the top band
GOAL_SAMPLES = 36  # candidate goals it compares (it takes the one with the most room around it)
ROOM_RINGS = 16  # room is measured up to this many grid cells away, so big empty areas always win
# The band under the targets is only for leaving: a line moves down through it and never comes back, so loops never
# pile up right under a target and leave its line no way out.
ENTRY_Y = 540.0
ENTRY_DROP = 30.0  # least drop per control step while a line is still in the top band
ARRIVAL = math.radians(30)  # the figure's line reaches the figure heading at most this far from straight down
# The figure's line grows from the figure, wanders the whole board, and when its length is used up climbs to a gate
# just under the top band and straight up its target's chimney. The top band is only ever used for leaving targets,
# so its way home is always open.
GATE_DROP = 190.0  # the gate: a patch this far under the top band, straight below the target ...
GATE_SIZE = (70.0, 110.0)  # ... this wide and tall (half sizes), so the line never orbits a single point
ANSWER_KEEP_SKIP = 200.0  # the figure's own line leaves the figure's keep-out zone over its first stretch
MIN_DECOY_SHARE = .7  # a decoy that runs out of room may stop once it has this share of its length
EARLY_HOME = .9  # the figure's line that runs out of room heads home once it has this share of its length
MAX_CONTROLS = 170
LINE_BUDGET = 3000  # candidate control points a line may try (with backtracking) before it starts over
ANSWER_BUDGET = 6000  # the figure's line is long and must find its way home: it gets more tries
ANSWER_TRIES = 4  # growth attempts of the figure's line per target it tries
LINE_RESTARTS = 5  # fresh starts per line before the round backs up to the previous line
LINE_BACKTRACKS = 6  # times a round takes a finished line off again to make room
REGROWS = 4  # extra tries of the last line when the figure's line is not tangled enough or the board not full
ROUND_TRIES = 200
COVER_CELL = 40.0  # board coverage is measured on this grid ...
COVER_REACH = 44.0  # ... as the share of cells with a line this close
# Level tiers (Weave V8): lines on the board (4, 5, 5, 6, 6: one more target and line as the levels climb), the figure's
# line length and the other lines' length range (px), how often the figure's line and the others may cross themselves
# (long lines need loops to fill the board; each one is just another crossing to follow), the least crossings on the
# figure's line, and the least share of the board the lines must cover. The board fills up level by level (measured,
# about: total line 12.1k -> 17.4k -> 17.6k -> 18.1k -> 19.0k px, coverage .69 -> .82 -> .83 -> .82 -> .85). With six
# lines the board is about as full as the readability rules allow (18 px between lines that do not cross, 36 degree
# crossings; denser settings fail to weave), so six lines share it and their other lines are shorter than at level 3,
# while the figure's line keeps growing and crosses more lines.
TIERS = (
    {"lines": 4, "length": 2800, "decoy": (2400, 3000), "self_cross": 5, "decoy_self": 2, "min_cross": 11, "min_cover": .66},
    {"lines": 5, "length": 4300, "decoy": (3000, 3700), "self_cross": 6, "decoy_self": 3, "min_cross": 18, "min_cover": .73},
    {"lines": 5, "length": 5200, "decoy": (3300, 4000), "self_cross": 8, "decoy_self": 3, "min_cross": 22, "min_cover": .76},
    {"lines": 6, "length": 5400, "decoy": (2400, 3000), "self_cross": 8, "decoy_self": 4, "min_cross": 24, "min_cover": .77},
    {"lines": 6, "length": 6000, "decoy": (2600, 3200), "self_cross": 10, "decoy_self": 4, "min_cross": 28, "min_cover": .78},
)


TIERS_V7 = (  # weave_v7: 5, 5, 5, 4, 4 lines (kept so older records still validate)
    {"lines": 5, "length": 3400, "decoy": (2600, 3200), "self_cross": 5, "decoy_self": 2, "min_cross": 14, "min_cover": .70},
    {"lines": 5, "length": 4300, "decoy": (3000, 3700), "self_cross": 6, "decoy_self": 3, "min_cross": 18, "min_cover": .73},
    {"lines": 5, "length": 5200, "decoy": (3300, 4000), "self_cross": 8, "decoy_self": 3, "min_cross": 22, "min_cover": .76},
    {"lines": 4, "length": 6000, "decoy": (3500, 4200), "self_cross": 9, "decoy_self": 4, "min_cross": 24, "min_cover": .76},
    {"lines": 4, "length": 7000, "decoy": (3700, 4500), "self_cross": 12, "decoy_self": 5, "min_cross": 27, "min_cover": .78},
)


def tier_table(data: dict) -> tuple:
    return TIERS_V7 if data.get("version") == "weave_v7" else TIERS


def thinking_table(data: dict) -> tuple:
    return LINE_THINKING_V7 if data.get("version") == "weave_v7" else LINE_THINKING


CHIMNEY = (0.0, 45.0, 90.0, 135.0, 180.0)  # every target keeps a clear chimney under it: other lines stay END_CLEAR from these


def reserved_for(count: int, target: int, figure, loose_ends, own_end=None, is_answer: bool = False):
    """Points a line keeps END_CLEAR from: the chimneys under the other targets, the figure (unless it is the figure's
    line), and every other line's loose end."""
    points = [(x, TOP_Y + dy) for index, x in enumerate(slots(count)) if index != target for dy in CHIMNEY]
    if not is_answer:
        points.append(tuple(figure))
    return points + [tuple(end) for end in loose_ends if own_end is None or tuple(end) != tuple(own_end)]


def target_lead(x: float) -> list[list[float]]:
    """The first control points of a line leaving target x: straight down."""
    return [[round(x, 1), y] for y in (TOP_Y, TOP_Y + LEAD[0], TOP_Y + LEAD[1])]


def figure_lead(x: float) -> list[list[float]]:
    """The first control points of the figure's line: straight up out of the figure's head."""
    return [[round(x, 1), y] for y in (BOTTOM_Y, BOTTOM_Y - LEAD[0], BOTTOM_Y - LEAD[1])]


def tiers_for(count: int) -> list[int]:
    """Level 1 is always tier 0 and the last level the hardest tier of the video."""
    return [0, 2, 4] if count <= 3 else [min(index, 4) for index in range(count)]


def slots(count: int) -> list[float]:
    """x positions of the target portals."""
    left, right = 150.0, 930.0
    return [left + index * (right - left) / (count - 1) for index in range(count)]


def straight_up(figure_x: float, count: int) -> int:
    """The target a guesser would pick: the one nearest above the figure."""
    return min(range(count), key=lambda index: abs(slots(count)[index] - figure_x))


# ---------------------------------------------------------------- curves

_BASIS = [((1 - t) ** 3 / 6, (3 * t ** 3 - 6 * t ** 2 + 4) / 6, (-3 * t ** 3 + 3 * t ** 2 + 3 * t + 1) / 6, t ** 3 / 6)
          for t in (step / 24 for step in range(25))]  # cubic B-spline weights at 25 points of a piece


def _window(padded, m: int, first: bool) -> list[tuple[float, float]]:
    """Dense points of B-spline piece m (its four control points are padded[m:m + 4])."""
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = padded[m:m + 4]
    return [(a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3)
            for a, b, c, d in (_BASIS if first else _BASIS[1:])]


class Resampler:
    """Turns dense curve points into samples every SAMPLE px of arc length, piece by piece."""

    def __init__(self, first: tuple[float, float]) -> None:
        self.last, self.travelled = first, 0.0

    def state(self):
        return self.last, self.travelled

    def restore(self, state) -> None:
        self.last, self.travelled = state

    def feed(self, dense) -> list[tuple[float, float]]:
        out = []
        for q in dense:
            p = self.last
            length = math.dist(p, q)
            position = SAMPLE - self.travelled
            while position <= length:
                t = position / length
                out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
                position += SAMPLE
            self.travelled = (self.travelled + length) % SAMPLE if length else self.travelled
            self.last = q
        return out


def _padded(controls, closed: bool):
    points = [tuple(controls[0])] * 2 + [tuple(point) for point in controls]
    return points + [tuple(controls[-1])] * 2 if closed else points


def spline(controls) -> list[tuple[float, float]]:
    """The whole curve (tripled end points: it starts and ends exactly on them), sampled every SAMPLE px."""
    padded = _padded(controls, True)
    first = _window(padded, 0, True)
    sampler = Resampler(first[0])
    samples = [first[0]] + sampler.feed(first[1:])
    for m in range(1, len(padded) - 3):
        samples += sampler.feed(_window(padded, m, False))
    if math.dist(samples[-1], tuple(controls[-1])) > 1e-6:
        samples.append(tuple(controls[-1]))
    return samples


def line_points(line: dict) -> list[tuple[float, float]]:
    return spline(line["controls"])


def _turn(a, b, c) -> float:
    return abs((math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0]) + math.pi) % (2 * math.pi) - math.pi)


TURN_LIMIT = 2 * 2 * SAMPLE / MIN_RADIUS  # most turning over two 10 px chords


def _smooth_from(points, start: int) -> bool:
    return all(_turn(points[i - 4], points[i - 2], points[i]) <= TURN_LIMIT for i in range(max(4, start), len(points)))


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
        return t, u
    return None


def _crossing(p, i, t, q, j, u, lines) -> dict:
    a, b, c, d = p[i], p[i + 1], q[j], q[j + 1]
    angle = abs(math.atan2(b[1] - a[1], b[0] - a[0]) - math.atan2(d[1] - c[1], d[0] - c[0])) % math.pi
    return {"lines": lines, "arcs": ((i + t) * SAMPLE, (j + u) * SAMPLE),
            "point": (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), "angle": min(angle, math.pi - angle)}


CELL = 24.0
_REACH = int(NEAR // CELL) + 1
_AROUND = [(dx, dy) for dx in range(-_REACH, _REACH + 1) for dy in range(-_REACH, _REACH + 1)]


def _key(point) -> tuple[int, int]:
    return int(point[0] // CELL), int(point[1] // CELL)


class Board:
    """Finished lines with spatial grids of their samples and segments, and every crossing so far."""

    def __init__(self) -> None:
        self.lines: list[list[tuple[float, float]]] = []
        self.points = defaultdict(list)  # cell -> (line, sample index)
        self.segments = defaultdict(list)  # cell -> (line, segment index)
        self.crossings: list[dict] = []
        self.added: list[int] = []  # crossings each line brought

    def add(self, points, crossings) -> None:
        line_id = len(self.lines)
        self.lines.append(points)
        for index, point in enumerate(points):
            self.points[_key(point)].append((line_id, index))
        for index, (a, b) in enumerate(zip(points, points[1:])):
            for key in {_key(a), _key(b)}:
                self.segments[key].append((line_id, index))
        self.crossings.extend(crossings)
        self.added.append(len(crossings))

    def pop(self) -> None:
        """Take the last line off again (its grid entries and crossings are the newest ones)."""
        points = self.lines.pop()
        for index in range(len(points) - 1, -1, -1):
            if index < len(points) - 1:
                for key in {_key(points[index]), _key(points[index + 1])}:
                    self.segments[key].pop()
            self.points[_key(points[index])].pop()
        self.crossings = self.crossings[:len(self.crossings) - self.added.pop()]


class Tracer:
    """Checks one line against a board of finished lines, sample by sample (see the module notes). The grower feeds
    it piece by piece while it grows; validation feeds it a finished line in one go: the same rules either way."""

    def __init__(self, board: Board, reserved, self_limit: int = 0, keep_out=None, keep_skip: float = 0.0) -> None:
        self.board = board
        self.keep_skip = keep_skip  # arc length at the start of the line that may lie inside keep_out
        self.line_id = len(board.lines)
        self.reserved = reserved  # every other line end this line must keep clear of
        self.self_limit = self_limit  # how often the line may cross itself; more reads as a scribble
        self.keep_out = keep_out  # (point, radius) this line must stay out of: the figure, for all but its own line
        self.samples: list[tuple[float, float]] = []
        self.keys: list[tuple[int, int]] = []
        self.own_points = defaultdict(list)
        self.own_segments = defaultdict(list)
        self.crossings: list[dict] = []
        self.checked = 0

    def _snapshot(self):
        return len(self.samples), len(self.crossings), self.checked

    def _restore(self, snap) -> None:
        samples, crossings, checked = snap
        for index in range(len(self.samples) - 1, samples - 1, -1):
            self.own_points[self.keys[index]].pop()
            if index >= 1:
                for key in {_key(self.samples[index - 1]), self.keys[index]}:
                    self.own_segments[key].pop()
        self.samples = self.samples[:samples]
        self.keys = self.keys[:samples]
        self.checked = min(checked, samples)
        self.crossings = self.crossings[:crossings]

    def extend(self, new) -> bool:
        """Append new samples and check them. False means they break a rule (the caller undoes them)."""
        start = len(self.samples)
        for point in new:
            index = len(self.samples)
            self.samples.append(point)
            key = _key(point)
            self.keys.append(key)
            self.own_points[key].append(index)
            if index >= 1:
                a = self.samples[index - 1]
                for segment_key in {_key(a), key}:
                    self.own_segments[segment_key].append(index - 1)
                if not self._segment(index - 1, a, point):
                    return False
        if not _smooth_from(self.samples, start):
            return False
        for offset, (px, py) in enumerate(new):
            for ex, ey in self.reserved:
                if abs(px - ex) < END_CLEAR and abs(py - ey) < END_CLEAR and math.dist((px, py), (ex, ey)) < END_CLEAR:
                    return False
            if self.keep_out and (start + offset) * SAMPLE >= self.keep_skip \
                    and math.dist((px, py), self.keep_out[0]) < self.keep_out[1]:
                return False
        return self._near_check(len(self.samples) - math.ceil(WINDOW / SAMPLE))

    def close(self) -> bool:
        """The line is complete: check its last samples too."""
        return self._near_check(len(self.samples))

    def _segment(self, index: int, a, b) -> bool:
        """Crossings of one new segment with the board and with this line's own earlier segments."""
        keys = {_key(a), _key(b)}
        seen = set()
        for key in keys:
            for other, j in self.board.segments.get(key, ()):
                if (other, j) in seen:
                    continue
                seen.add((other, j))
                q = self.board.lines[other]
                hit = _segment_hit(a, b, q[j], q[j + 1])
                if hit and not self._accept(_crossing(self.samples, index, hit[0], q, j, hit[1], (self.line_id, other))):
                    return False
            for j in self.own_segments.get(key, ()):
                if (self.line_id, j) in seen or index - j < 3:
                    continue
                seen.add((self.line_id, j))
                hit = _segment_hit(a, b, self.samples[j], self.samples[j + 1])
                if hit and not self._accept(_crossing(self.samples, index, hit[0], self.samples, j, hit[1],
                                                      (self.line_id, self.line_id))):
                    return False
        return True

    def _accept(self, crossing: dict) -> bool:
        if crossing["angle"] < CROSS_ANGLE:
            return False
        point = crossing["point"]
        for group in (self.crossings, self.board.crossings):
            for other in group:
                if math.dist(point, other["point"]) < CROSS_GAP:
                    return False
        other_line = crossing["lines"][1]
        if other_line == self.line_id and sum(c["lines"][1] == self.line_id for c in self.crossings) >= self.self_limit:
            return False
        if other_line != self.line_id:
            s, t = crossing["arcs"]
            repeat = REPEAT_WINDOWS * WINDOW
            if any(c["lines"][1] == other_line and (abs(c["arcs"][0] - s) < repeat or abs(c["arcs"][1] - t) < repeat)
                   for c in self.crossings):
                return False
        self.crossings.append(crossing)
        return True

    def _covered(self, s: float, other: int, t: float) -> bool:
        for crossing in self.crossings:
            if crossing["lines"][1] != other:
                continue
            a, b = crossing["arcs"]
            if (abs(s - a) <= WINDOW and abs(t - b) <= WINDOW) or (other == self.line_id and abs(s - b) <= WINDOW and abs(t - a) <= WINDOW):
                return True
        return False

    def _near_check(self, upto: int) -> bool:
        """Samples far enough behind the growing tip: anything within NEAR must be at a crossing."""
        board_points, board_lines, own_points, samples = self.board.points, self.board.lines, self.own_points, self.samples
        skip = SELF_SKIP / SAMPLE
        for index in range(self.checked, max(self.checked, upto)):
            px, py = point = samples[index]
            cx, cy = self.keys[index]
            s = index * SAMPLE
            for dx, dy in _AROUND:
                cell = (cx + dx, cy + dy)
                for other, j in board_points.get(cell, ()):
                    qx, qy = board_lines[other][j]
                    if abs(px - qx) < NEAR and abs(py - qy) < NEAR and math.dist(point, (qx, qy)) < NEAR \
                            and not self._covered(s, other, j * SAMPLE):
                        return False
                for j in own_points.get(cell, ()):
                    if j < index and index - j > skip and math.dist(point, samples[j]) < NEAR \
                            and not self._covered(s, self.line_id, j * SAMPLE):
                        return False
        self.checked = max(self.checked, upto)
        return True

    def tip_clear(self) -> bool:
        """The line may end here: its tip keeps END_CLEAR from every other line and from its own earlier path."""
        tip = self.samples[-1]
        cx, cy = _key(tip)
        reach = int(END_CLEAR // CELL) + 1
        last = len(self.samples) - 1
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                cell = (cx + dx, cy + dy)
                for other, j in self.board.points.get(cell, ()):
                    if math.dist(tip, self.board.lines[other][j]) < END_CLEAR:
                        return False
                for j in self.own_points.get(cell, ()):
                    if (last - j) * SAMPLE > END_CLEAR * 1.6 and math.dist(tip, self.samples[j]) < END_CLEAR:
                        return False
        return all(math.dist(tip, end) >= END_CLEAR for end in self.reserved)


class Grower(Tracer):
    """Grows one line control point by control point, always heading for the emptiest room it can find, until it has
    used its length budget. The figure's line starts at the figure and, once its length is used up, climbs to the gate
    under its target and up the target's chimney; every other line starts at its target and ends at a loose end as soon
    as its tip is clear."""

    def __init__(self, board: Board, start, heading: float, length: float, reserved, rng: random.Random,
                 self_limit: int, target_x: float | None, keep_out, keep_skip: float = 0.0) -> None:
        super().__init__(board, reserved, self_limit, keep_out, keep_skip)
        self.rng, self.length, self.planned = rng, length, length
        self.homes = target_x is not None  # the figure's line: it ends at its target
        self.loops = self_limit
        if self.homes:
            self.end = (target_x, TOP_Y + LEAD[1])
            self.tail = [(target_x, TOP_Y + LEAD[0]), (target_x, TOP_Y)]
            self.gate = (target_x, ENTRY_Y + GATE_DROP)
        self.controls = list(start)
        padded = _padded(self.controls, False)
        first = _window(padded, 0, True)
        self.sampler = Resampler(first[0])
        self.heading = heading
        self.goal, self.goal_steps = None, 0
        self.gated = False  # the figure's line has reached the gate under its target
        self.budget = ANSWER_BUDGET if self.homes else LINE_BUDGET
        self.extend([first[0]] + self.sampler.feed(first[1:]) + self.sampler.feed(_window(padded, 1, False)))

    def _snapshot(self):
        return (super()._snapshot(), len(self.controls), self.sampler.state(), self.heading, self.goal, self.goal_steps,
                self.gated)

    def _restore(self, snap) -> None:
        tracer, controls, sampler, heading, goal, goal_steps, gated = snap
        super()._restore(tracer)
        self.controls = self.controls[:controls]
        self.sampler.restore(sampler)
        self.heading, self.goal, self.goal_steps, self.gated = heading, goal, goal_steps, gated

    @property
    def arc(self) -> float:
        return len(self.samples) * SAMPLE

    def _accept(self, crossing: dict) -> bool:
        # The figure's line keeps one of its self-crossings for the way home: its own loops may stand in the way.
        self.self_limit = self.loops - (1 if self.homes and not self._homing() else 0)
        return super()._accept(crossing)

    def _homing(self) -> bool:
        return self.homes and self.arc >= self.length

    def _room(self, point) -> float:
        """How far the nearest line is from a point (capped): the grid is searched in growing square rings."""
        cx, cy = _key(point)
        for ring in range(0, ROOM_RINGS):
            for dx in range(-ring, ring + 1):
                for dy in (-ring, ring) if abs(dx) != ring else range(-ring, ring + 1):
                    cell = (cx + dx, cy + dy)
                    if cell in self.board.points and self.board.points[cell] or self.own_points.get(cell):
                        return ring * CELL
        return ROOM_RINGS * CELL

    def _pick_goal(self):
        """The next place to head for: of a handful of random spots at a good distance, the one with the most room."""
        x, y = self.controls[-1]
        best, best_room = None, -1.0
        for _ in range(GOAL_SAMPLES):
            gx = self.rng.uniform(BOX[0] + GOAL_MARGIN, BOX[2] - GOAL_MARGIN)
            gy = self.rng.uniform(ENTRY_Y + GOAL_TOP_MARGIN, LOWEST - GOAL_MARGIN)
            distance = math.dist((x, y), (gx, gy))
            if not GOAL_SPAN[0] <= distance <= GOAL_SPAN[1]:
                continue
            if math.dist((gx, gy), self.keep_out[0]) < self.keep_out[1] + 80:
                continue
            room = self._room((gx, gy)) + self.rng.uniform(0, 30)
            if room > best_room:
                best, best_room = (gx, gy), room
        return best or (self.rng.uniform(BOX[0] + 60, BOX[2] - 60), self.rng.uniform(ENTRY_Y + 60, LOWEST - 200))

    def _update_goal(self) -> None:
        """Pick a new goal when there is none, it is reached, or the way to it stays blocked (before a snapshot, so
        backing up keeps the goal)."""
        if self._homing():
            return
        tip = self.controls[-1]
        if self.goal is None or math.dist(tip, self.goal) < REACH or self.goal_steps > GOAL_PATIENCE:
            self.goal, self.goal_steps = self._pick_goal(), 0

    def _candidates(self) -> list[tuple[float, float, float]]:
        x, y = self.controls[-1]
        homing = self._homing()
        goal = (self.end if self.gated else self.gate) if homing else self.goal
        want = math.atan2(goal[1] - y, goal[0] - x)
        delta = (want - self.heading + math.pi) % (2 * math.pi) - math.pi
        base = self.heading + max(-TURN * .75, min(TURN * .75, delta)) + self.rng.uniform(-.12, .12)
        result = []
        for offset in OFFSETS:
            heading = base + offset
            turn = (heading - self.heading + math.pi) % (2 * math.pi) - math.pi
            if abs(turn) > TURN:
                continue
            nx, ny = x + math.cos(heading) * STEP, y + math.sin(heading) * STEP
            if not (BOX[0] <= nx <= BOX[2] and BOX[1] <= ny <= LOWEST):
                continue
            if ny < ENTRY_Y:
                if not self.homes and ny < y + ENTRY_DROP:
                    continue  # a decoy still leaving the top band keeps heading down
                if self.homes and not (self.gated and abs(nx - self.end[0]) < 45):
                    continue  # the figure's line enters the top band only up its own target's chimney
            if self.arc > self.keep_skip and math.dist((nx, ny), self.keep_out[0]) < self.keep_out[1]:
                continue
            if (self.homes and not homing and abs(nx - self.gate[0]) < GATE_SIZE[0] + 30
                    and ny < self.gate[1] + GATE_SIZE[1]):
                continue  # the strip under its target stays free for the way home
            result.append((round(nx, 1), round(ny, 1), heading))
        if homing and self.gated and math.dist((x, y), self.end) < 2.2 * STEP:
            # Docking point straight under the target's lead-in: from there the line climbs straight up into it.
            dock = (self.end[0], self.end[1] + .8 * STEP)
            heading = math.atan2(dock[1] - y, dock[0] - x)
            if math.dist((x, y), dock) > .45 * STEP and abs((heading - self.heading + math.pi) % (2 * math.pi) - math.pi) <= TURN:
                result.insert(0, (round(dock[0], 1), round(dock[1], 1), heading))
        return result

    def _add_control(self, control, heading: float) -> bool:
        self.controls.append(control)
        self.heading = heading
        self.goal_steps += 1
        if (self._homing() and not self.gated and abs(control[0] - self.gate[0]) < GATE_SIZE[0]
                and abs(control[1] - self.gate[1]) < GATE_SIZE[1]):
            self.gated = True
        padded = _padded(self.controls, False)
        return self.extend(self.sampler.feed(_window(padded, len(padded) - 4, False)))

    def _close_windows(self) -> list[tuple[float, float]]:
        """Samples of the last pieces once the line's final control point is known (it is tripled: the curve ends
        exactly on it)."""
        padded = _padded(self.controls, True)
        done = len(_padded(self.controls, False)) - 3 - self._pending
        new = []
        for m in range(done, len(padded) - 3):
            new += self.sampler.feed(_window(padded, m, False))
        end = tuple(self.controls[-1])
        if math.dist(new[-1] if new else self.samples[-1], end) > 1e-6:
            new.append(end)
        return new

    def _finish_target(self) -> bool:
        if math.dist(self.controls[-1], self.end) < STEP * .4:
            return False
        self.controls += [self.end] + self.tail
        self._pending = 3
        return self.extend(self._close_windows()) and self.close()

    def _finish_loose(self) -> bool:
        if self.controls[-1][1] > END_MAX_Y:
            return False
        self._pending = 0
        return self.extend(self._close_windows()) and self.close() and self.tip_clear()

    def grow(self) -> list[list[float]] | None:
        self._update_goal()
        stack = [(self._snapshot(), self._candidates())]
        dead_ends = 0  # dead ends in a row: each one backs up twice as far, out of the pocket that traps the line
        while stack and self.budget > 0:
            snap, options = stack[-1]
            if not options:
                # Out of room: a decoy that is long enough simply ends here (the others back up and try again).
                self._restore(snap)
                if self.homes and not self._homing() and self.arc >= self.planned * EARLY_HOME:
                    self.length = self.arc  # the figure's line is nearly long enough: it heads home from here
                    stack[-1] = (self._snapshot(), self._candidates())
                    continue
                if not self.homes and self.arc >= self.length * MIN_DECOY_SHARE and len(self.controls) > 4:
                    before = self._snapshot()
                    if self._finish_loose():
                        return [[round(x, 1), round(y, 1)] for x, y in self.controls]
                    self._restore(before)
                for _ in range(min(2 ** dead_ends, max(1, len(stack) - 1))):
                    stack.pop()
                dead_ends = min(dead_ends + 1, 5)
                if stack:
                    self._restore(stack[-1][0])
                continue
            nx, ny, heading = options.pop(0)
            self.budget -= 1
            self._restore(snap)
            if not self._add_control((nx, ny), heading):
                continue
            if not self.homes and self.arc >= self.length:
                before = self._snapshot()
                if self._finish_loose():
                    return [[round(x, 1), round(y, 1)] for x, y in self.controls]
                self._restore(before)
                if self.arc > self.length * 1.3:
                    continue
            if self._homing():
                to_end = math.atan2(self.end[1] - ny, self.end[0] - nx)
                if (self.gated and math.dist((nx, ny), self.end) < STEP * 1.05
                        and abs(heading % (2 * math.pi) - 3 * math.pi / 2) < ARRIVAL
                        and abs(to_end + math.pi / 2) < ARRIVAL / 2):  # climb in from straight below: no hook
                    before = self._snapshot()
                    if self._finish_target():
                        return [[round(x, 1), round(y, 1)] for x, y in self.controls]
                    self._restore(before)
                    continue
                if self.arc > self.length + 1800:
                    continue  # cannot find its way up
            if len(self.controls) >= MAX_CONTROLS:
                continue
            self._update_goal()
            stack.append((self._snapshot(), self._candidates()))
            dead_ends = 0
        # Out of tries: a decoy that got far enough ends at the deepest point where it can end cleanly.
        if not self.homes:
            for snap, _ in reversed(stack):
                self._restore(snap)
                if self.arc < self.length * MIN_DECOY_SHARE:
                    break
                before = self._snapshot()
                if self._finish_loose():
                    return [[round(x, 1), round(y, 1)] for x, y in self.controls]
                self._restore(before)
        return None


# ---------------------------------------------------------------- rounds

def crossings_of(data: dict) -> list[dict]:
    """Every crossing of a round: point, the two line indices, arc positions, and steepness."""
    lines = [line_points(line) for line in data["lines"]]
    grid = defaultdict(list)
    found = []
    for line_id, points in enumerate(lines):
        for index, (a, b) in enumerate(zip(points, points[1:])):
            keys = {_key(a), _key(b)}
            seen = set()
            for key in keys:
                for other, j in grid.get(key, ()):
                    if (other, j) in seen or (other == line_id and index - j < 3):
                        continue
                    seen.add((other, j))
                    q = lines[other]
                    hit = _segment_hit(a, b, q[j], q[j + 1])
                    if hit:
                        found.append(_crossing(points, index, hit[0], q, j, hit[1], (line_id, other)))
            for key in keys:
                grid[key].append((line_id, index))
    return found


def coverage(lines_points, figure) -> float:
    """Share of the board the lines fill: grid cells (below the top band, away from the figure) with a line close by."""
    near = defaultdict(list)
    for points in lines_points:
        for point in points:
            near[(int(point[0] // COVER_CELL), int(point[1] // COVER_CELL))].append(point)
    cells = filled = 0
    y = ENTRY_Y + COVER_CELL / 2
    while y < LOWEST:
        x = BOX[0] + COVER_CELL / 2
        while x < BOX[2]:
            if math.dist((x, y), figure) > FIGURE_CLEAR + 40:
                cells += 1
                cx, cy = int(x // COVER_CELL), int(y // COVER_CELL)
                if any(math.dist((x, y), point) < COVER_REACH for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                       for point in near.get((cx + dx, cy + dy), ())):
                    filled += 1
            x += COVER_CELL
        y += COVER_CELL
    return round(filled / max(1, cells), 4)


def _try_round(tier: dict, figure_x: float, rng: random.Random) -> dict | None:
    count = tier["lines"]
    tops = slots(count)
    figure = (figure_x, BOTTOM_Y)
    board = Board()
    lines: list[dict] = []
    # The figure's line first. It tries the targets in random order (never the one nearest above the figure) and the
    # first one it finds its way home to is the answer, so every allowed target is equally likely.
    answer = None
    for target in rng.sample([index for index in range(count) if index != straight_up(figure_x, count)], count - 1):
        reserved = reserved_for(count, target, figure, [], is_answer=True)
        for _ in range(ANSWER_TRIES):
            grower = Grower(board, figure_lead(figure_x), -math.pi / 2, tier["length"], reserved, rng,
                            tier["self_cross"], tops[target], (figure, FIGURE_CLEAR), ANSWER_KEEP_SKIP)
            controls = grower.grow()
            if controls is not None:
                board.add(grower.samples, grower.crossings)
                lines.append({"kind": "answer", "target": target, "controls": controls})
                answer = target
                break
        if answer is not None:
            break
    if answer is None:
        return None
    order = [answer] + rng.sample([index for index in range(count) if index != answer], count - 1)

    def grow(target: int) -> bool:
        is_answer = target == answer
        length = tier["length"] if is_answer else rng.uniform(*tier["decoy"])
        reserved = reserved_for(count, target, figure, [line["controls"][-1] for line in lines[1:]], is_answer=is_answer)
        for _ in range(LINE_RESTARTS):
            if is_answer:  # from the figure, up to its target
                grower = Grower(board, figure_lead(figure_x), -math.pi / 2, length, reserved, rng, tier["self_cross"],
                                tops[target], (figure, FIGURE_CLEAR), ANSWER_KEEP_SKIP)
            else:  # from its target, down to a loose end
                grower = Grower(board, target_lead(tops[target]), math.pi / 2, length, reserved, rng, tier["decoy_self"],
                                None, (figure, FIGURE_CLEAR))
            controls = grower.grow()
            if controls is not None:
                board.add(grower.samples, grower.crossings)
                lines.append({"kind": "answer" if is_answer else "decoy", "target": target, "controls": controls})
                return True
        return False

    def undo() -> None:
        board.pop()
        lines.pop()

    # Place every line; when one cannot be placed, take the previous decoy off and grow it another way.
    backtracks = 0
    while len(lines) < count:  # (the figure's line is already in place)
        if grow(order[len(lines)]):
            continue
        if len(lines) <= 1 or backtracks >= LINE_BACKTRACKS:
            return None
        backtracks += 1
        undo()
    # Not tangled or full enough: grow the last decoy again a few times.
    for attempt in range(REGROWS + 1):
        answer_crossings = sum(0 in crossing["lines"] for crossing in board.crossings)
        untangled = any(not any(set(c["lines"]) == {0, index} for c in board.crossings) for index in range(1, count))
        filled = coverage(board.lines, figure)
        if answer_crossings >= tier["min_cross"] and not untangled and filled >= tier["min_cover"]:
            return {"lines": lines, "targets": [[x, TARGET_Y] for x in tops], "figure": [figure_x, BOTTOM_Y],
                    "crossing_count": len(board.crossings), "answer_crossings": answer_crossings, "coverage": filled,
                    "correct_index": answer}
        if attempt == REGROWS:
            break
        undo()
        if not grow(order[len(lines)]):
            return None
    return None


def make_round(index: int, tier_index: int, rng: random.Random) -> RoundSpec:
    tier = TIERS[tier_index]
    count = tier["lines"]
    figure_x = round(rng.uniform(*FIGURE_X), 1)
    for _ in range(ROUND_TRIES):
        result = _try_round(tier, figure_x, rng)
        if result is None:
            continue
        answer = result["correct_index"]
        data = {"version": VERSION, "level": index + 1, "tier": tier_index, **result,
                "thinking_seconds": LINE_THINKING[tier_index]}
        if not validate(data, answer):
            return RoundSpec(index, "line_follow", data, answer)
    raise RuntimeError("Could not weave a readable Line Follow board")


def average_round(rounds) -> float:
    return round(sum(line_round(float(item.data["thinking_seconds"])) for item in rounds) / max(1, len(rounds)), 4)


@lru_cache(maxsize=16)  # weaving takes a while; the same seed always gives the same video
def generate(seed: int, count: int) -> VideoSpec:
    rng = random.Random(f"{VERSION}:{seed}:{count}")
    rounds = [make_round(index, tier, rng) for index, tier in enumerate(tiers_for(count))]
    stable_id = sha256(f"{VERSION}:{seed}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "line_follow", seed, "hard", "lines", tuple(rounds),
                     PUZZLE_FIT_INTRO_DURATION, average_round(rounds), PUZZLE_FIT_OUTRO_DURATION)


# ---------------------------------------------------------------- validation

def _readable(lines, lines_points, loops: int, decoy_loops: int, figure) -> bool:
    """Replay the grower's rules on the finished lines, in the order they were grown (the figure's line first)."""
    board = Board()
    loose = [line["controls"][-1] for line in lines[1:]]
    for line_id, (line, points) in enumerate(zip(lines, lines_points)):
        others = reserved_for(len(lines), line["target"], figure, loose, None if line_id == 0 else line["controls"][-1],
                              is_answer=line_id == 0)
        tracer = Tracer(board, others, loops if line_id == 0 else decoy_loops, (figure, FIGURE_CLEAR),
                        ANSWER_KEEP_SKIP if line_id == 0 else 0.0)
        if not (tracer.extend(points) and tracer.close()):
            return False
        if line_id and not tracer.tip_clear():
            return False
        board.add(tracer.samples, tracer.crossings)
    return True


def validate(data: dict, answer: int) -> list[str]:
    tier_index = data.get("tier")
    tiers = tier_table(data)
    if tier_index not in range(len(tiers)):
        return ["line follow level is invalid"]
    tier = tiers[tier_index]
    lines = data.get("lines", [])
    count = tier["lines"]
    if len(lines) != count or len(data.get("targets", [])) != count:
        return ["line follow level has the wrong number of lines"]
    if sorted(line.get("target") for line in lines) != list(range(count)):
        return ["every target has exactly one line"]
    if [line.get("kind") for line in lines] != ["answer"] + ["decoy"] * (count - 1):
        return ["exactly one line, the first, must lead from the figure to its target"]
    figure = tuple(data.get("figure") or ())
    if len(figure) != 2 or figure[1] != BOTTOM_Y or not FIGURE_X[0] <= figure[0] <= FIGURE_X[1]:
        return ["the figure must stand on the bottom row"]
    if lines[0]["target"] != answer or data.get("correct_index") != answer:
        return ["the figure's line must lead to the answer"]
    if answer == straight_up(figure[0], count):
        return ["the target nearest above the figure must not be the answer"]
    tops = slots(count)
    points_list = []
    for index, line in enumerate(lines):
        controls = line.get("controls", [])
        target_x = tops[line["target"]]
        if index == 0:  # the figure's line runs from the figure up to its target
            if len(controls) < 7 or controls[:3] != figure_lead(figure[0]) or controls[-3:] != target_lead(target_x)[::-1]:
                return ["the figure's line must leave the figure straight up and climb straight into its target"]
            body = controls[3:-3]
        else:
            if len(controls) < 5 or controls[:3] != target_lead(target_x):
                return ["a line must leave its target straight"]
            if controls[-1][1] > END_MAX_Y:
                return ["a loose end sits too close to the bottom row, where only the figure's line may start"]
            body = controls[3:]
        if any(not (BOX[0] <= x <= BOX[2] and BOX[1] <= y <= LOWEST) for x, y in body):
            return ["a line leaves the board"]
        points = spline(controls)
        if not _smooth_from(points, 4):
            return ["a line bends too sharply"]
        points_list.append(points)
    if not _readable(lines, points_list, tier["self_cross"], tier["decoy_self"], figure):
        return ["lines touch, cross too shallow or too close together, or crowd a line end or the figure"]
    crossings = crossings_of(data)
    answer_crossings = sum(0 in crossing["lines"] for crossing in crossings)
    if answer_crossings < tier["min_cross"] or data.get("answer_crossings") != answer_crossings:
        return ["the figure's line does not cross enough lines for its level"]
    if data.get("crossing_count") != len(crossings):
        return ["crossing count is wrong"]
    if len(points_list[0]) * SAMPLE < tier["length"] * EARLY_HOME:
        return ["the figure's line is too short for its level"]
    if any(len(points) * SAMPLE < tier["decoy"][0] * MIN_DECOY_SHARE - STEP for points in points_list[1:]):
        return ["a line is too short for its level"]
    filled = coverage(points_list, figure)
    if filled < tier["min_cover"] or data.get("coverage") != filled:
        return ["the lines do not fill enough of the board for its level"]
    if data.get("thinking_seconds") != thinking_table(data)[tier_index]:
        return ["line follow thinking time does not match its level"]
    return []
