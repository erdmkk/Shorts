"""Puzzle Fit V12: one big picture with three missing pieces (A, B, C) and six tilted, numbered options.

The picture is a 4x3 jigsaw of a calm illustrated scene (`visuals.scenes`). Three pieces are missing: never a corner,
never two touching each other, at least one fully enclosed. Six options lie below it, each tilted (12-30 degrees) and,
on Hard, also turned by quarter turns, so viewers must turn them in their head. Three options are the missing pieces;
the other three are traps that show a hole's own picture but have one tab or socket wrong, so they fit nowhere.

Edges are (top, right, bottom, left): 1 tab, -1 socket, 0 flat. A piece fits a hole when some quarter turn of its
edges equals the hole's edges. The three holes have different shapes (even up to rotation), so every missing piece
fits exactly one hole, and every trap fits none. The answer is written like `A4 B1 C6`.
"""
from __future__ import annotations

from hashlib import sha256
from itertools import product
import random

from ..config import (FIT_THINKING, PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION, fit_round)
from ..models import RoundSpec, VideoSpec
from .puzzle_fit import board_edges

VERSION = "fit_v12"
ROWS, COLUMNS = 3, 4
LETTERS = "ABC"
OPTIONS = 6
TILT = (12.0, 30.0)
SCENES = ("mountains", "city", "sea", "dunes")


def rotate(edges, turns: int) -> tuple[int, ...]:
    """Edges after `turns` clockwise quarter turns: the left edge becomes the top, and so on."""
    edges = tuple(edges)
    for _ in range(turns % 4):
        edges = (edges[3], edges[0], edges[1], edges[2])
    return edges


def rotations(edges) -> frozenset:
    return frozenset(rotate(edges, turns) for turns in range(4))


def fits(piece, hole) -> bool:
    return tuple(hole) in rotations(piece)


def _neighbours(slot: int) -> set[int]:
    row, column = divmod(slot, COLUMNS)
    result = set()
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        if 0 <= row + dr < ROWS and 0 <= column + dc < COLUMNS:
            result.add((row + dr) * COLUMNS + column + dc)
    return result


CORNERS = {0, COLUMNS - 1, (ROWS - 1) * COLUMNS, ROWS * COLUMNS - 1}
INNER = {5, 6}


def _holes(rng: random.Random) -> list[int]:
    open_slots = [slot for slot in range(ROWS * COLUMNS) if slot not in CORNERS]
    while True:
        holes = sorted(rng.sample(open_slots, 3))
        if any(b in _neighbours(a) for a in holes for b in holes) or not set(holes) & INNER:
            continue
        return holes


def _trap(correct: tuple[int, ...], banned: set, rng: random.Random) -> tuple[int, ...] | None:
    """A near look-alike of a hole: one edge (or two) changed, the same number of flat sides, fitting no hole."""
    options = [edges for edges in product((-1, 0, 1), repeat=4)
               if edges.count(0) == correct.count(0) and 1 <= sum(a != b for a, b in zip(edges, correct)) <= 2]
    rng.shuffle(options)
    options.sort(key=lambda edges: sum(a != b for a, b in zip(edges, correct)))
    for edges in options:
        if rotations(edges) not in banned:
            return edges
    return None


def _turns(difficulty: str, rng: random.Random) -> int:
    return {"easy": 0, "medium": rng.choice((0, 1, 3))}.get(difficulty, rng.randrange(4))


def make_round(difficulty: str, rng: random.Random) -> RoundSpec | None:
    pieces = board_edges(ROWS, COLUMNS, rng)
    holes = _holes(rng)
    classes = [rotations(pieces[slot]) for slot in holes]
    if len(set(classes)) != 3:
        return None  # two holes would accept the same piece
    banned = set(classes)
    options = []
    for letter, slot in zip(LETTERS, holes):
        options.append({"hole": letter, "art_slot": slot, "base": list(pieces[slot])})
    for slot in holes:
        trap = _trap(tuple(pieces[slot]), banned, rng)
        if trap is None:
            return None
        banned.add(rotations(trap))
        options.append({"hole": None, "art_slot": slot, "base": list(trap)})
    rng.shuffle(options)
    for option in options:
        option["turns"] = _turns(difficulty, rng)
        option["tilt"] = round(rng.choice((-1, 1)) * rng.uniform(*TILT), 1)
        option["edges"] = list(rotate(option["base"], option["turns"]))
    answer = " ".join(f"{letter}{next(index + 1 for index, option in enumerate(options) if option['hole'] == letter)}"
                      for letter in LETTERS)
    data = {"version": VERSION, "rows": ROWS, "columns": COLUMNS, "piece_edges": pieces, "holes": holes,
            "options": options, "scene": rng.choice(SCENES), "scene_seed": rng.randrange(1 << 30),
            "thinking_seconds": FIT_THINKING[difficulty]}
    return RoundSpec(0, "puzzle_fit", data, answer)


def generate(seed: int, difficulty: str = "hard") -> VideoSpec:
    difficulty = difficulty if difficulty in FIT_THINKING else "hard"
    rng = random.Random(f"{VERSION}:{seed}:{difficulty}")
    for _ in range(500):
        item = make_round(difficulty, rng)
        if item is not None:
            break
    else:
        raise RuntimeError("could not build a puzzle fit picture")
    stable_id = sha256(f"{VERSION}:{seed}:{difficulty}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "puzzle_fit", seed, difficulty, "interlocking", (item,),
                     PUZZLE_FIT_INTRO_DURATION, fit_round(difficulty), PUZZLE_FIT_OUTRO_DURATION)


def errors(data: dict, answer, difficulty: str | None) -> list[str]:
    problems: list[str] = []
    try:
        pieces, holes, options = data["piece_edges"], list(data["holes"]), data["options"]
        rows, columns = data["rows"], data["columns"]
    except (KeyError, TypeError):
        return ["puzzle fit round data is malformed"]
    if (rows, columns) != (ROWS, COLUMNS) or len(pieces) != ROWS * COLUMNS:
        return ["puzzle fit board must be 4x3"]
    for position, edges in enumerate(pieces):
        row, column = divmod(position, COLUMNS)
        if (row == 0 and edges[0] != 0) or (column == COLUMNS - 1 and edges[1] != 0) or (
                row == ROWS - 1 and edges[2] != 0) or (column == 0 and edges[3] != 0):
            problems.append("outer board edge must be flat")
        if column + 1 < COLUMNS and (edges[1] == 0 or edges[1] != -pieces[position + 1][3]):
            problems.append("horizontal seam mismatch")
        if row + 1 < ROWS and (edges[2] == 0 or edges[2] != -pieces[position + COLUMNS][0]):
            problems.append("vertical seam mismatch")
    if len(holes) != 3 or set(holes) & CORNERS or any(b in _neighbours(a) for a in holes for b in holes) or not set(holes) & INNER:
        problems.append("puzzle fit needs three separate, non-corner holes, one of them enclosed")
        return problems
    if len({rotations(pieces[slot]) for slot in holes}) != 3:
        problems.append("two holes accept the same piece")
    if len(options) != OPTIONS:
        problems.append("puzzle fit needs six options")
    mapping = {}
    for number, option in enumerate(options, start=1):
        if tuple(option["edges"]) != rotate(option["base"], option["turns"]):
            problems.append("option edges do not match its base and turns")
        if not TILT[0] <= abs(float(option["tilt"])) <= TILT[1]:
            problems.append("every option lies tilted")
        if difficulty == "easy" and option["turns"]:
            problems.append("easy options are only tilted, never turned")
        fitting = [LETTERS[index] for index, slot in enumerate(holes) if fits(option["edges"], pieces[slot])]
        if option["hole"] is None and fitting:
            problems.append("a trap fits a hole")
        if option["hole"] is not None:
            if fitting != [option["hole"]] or option["art_slot"] != holes[LETTERS.index(option["hole"])]:
                problems.append("a missing piece does not fit exactly its own hole")
            mapping[option["hole"]] = number
    if sorted(mapping) != list(LETTERS):
        problems.append("every hole needs exactly one missing piece among the options")
    elif answer != " ".join(f"{letter}{mapping[letter]}" for letter in LETTERS):
        problems.append("puzzle fit answer does not match the options")
    if data.get("scene") not in SCENES:
        problems.append("unknown puzzle fit scene")
    if difficulty in FIT_THINKING and float(data.get("thinking_seconds", -1)) != FIT_THINKING[difficulty]:
        problems.append("puzzle fit thinking time does not match its difficulty")
    return problems
