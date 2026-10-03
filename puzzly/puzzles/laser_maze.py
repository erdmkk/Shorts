"""Laser Maze: a laser enters a board of mirrors and the viewer says which numbered receiver the beam ends in.

A level is a square board (5x5 up to 9x9) with two-sided 45 degree mirrors (`/` and `\\`) in some cells, one laser entering from
a port on the edge, and numbered receivers on several other ports (4 to 6, numbered clockwise from the top left). The beam's
path is fully determined by the mirrors, so the answer is unique by construction: the beam leaves the board at exactly one
port and that port holds a receiver. Difficulty is the size of the board and the number of bounces (and, on the bigger boards,
how often the beam crosses its own path). The levels of a video use tiers spread over the five tiers by the number of levels
(3 levels: tiers 0, 2, 4; 4 levels: 0, 1, 3, 4; 5 levels: all), so the last level is always the hardest and the first the easiest.
"""
from __future__ import annotations

from hashlib import sha256
import random

from ..config import (DEFAULT_ROUNDS, LASER_TIER_SETS, LASER_TIERS, PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION,
                      laser_average_round, laser_trace_seconds)
from ..models import RoundSpec, VideoSpec

VERSION = "laser_v1"
DIRECTIONS = {"down": (1, 0), "up": (-1, 0), "right": (0, 1), "left": (0, -1)}
ATTEMPTS = 20000
MIN_PORT_GAP = 2  # receivers are at least this many ports apart, so the sockets never crowd each other


def port_count(n: int) -> int:
    return 4 * n


def port_cell(n: int, port: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """Ports run clockwise from the top left: top (left to right), right (top to bottom), bottom (right to left), left (bottom to
    top). Returns the edge cell a port opens onto and the direction a beam entering there travels."""
    side, index = divmod(port, n)
    if side == 0:
        return (0, index), (1, 0)
    if side == 1:
        return (index, n - 1), (0, -1)
    if side == 2:
        return (n - 1, n - 1 - index), (-1, 0)
    return (n - 1 - index, 0), (0, 1)


def exit_port(n: int, row: int, column: int, direction: tuple[int, int]) -> int:
    """The port a beam leaves through when it steps off the board from (row, column) in `direction`."""
    if direction == (-1, 0):
        return column
    if direction == (0, 1):
        return n + row
    if direction == (1, 0):
        return 2 * n + (n - 1 - column)
    return 3 * n + (n - 1 - row)


def reflect(direction: tuple[int, int], mirror: str) -> tuple[int, int]:
    dr, dc = direction
    return (-dc, -dr) if mirror == "/" else (dc, dr)


def trace(n: int, mirrors: dict[tuple[int, int], str], entry: int) -> dict:
    """Follow the beam from `entry`: the cells it visits in order, the path positions where a mirror turns it, and the exit port."""
    (row, column), direction = port_cell(n, entry)
    path, hits = [], []
    for _ in range(4 * n * n + 4):
        if not (0 <= row < n and 0 <= column < n):
            return {"path": path, "hits": hits, "exit": exit_port(n, row - direction[0], column - direction[1], direction)}
        path.append((row, column))
        mirror = mirrors.get((row, column))
        if mirror:
            direction = reflect(direction, mirror)
            hits.append(len(path) - 1)
        row, column = row + direction[0], column + direction[1]
    raise ValueError("a beam in a board of mirrors always leaves it")


def revisits(path: list[tuple[int, int]]) -> int:
    """How many times the beam passes through a cell it has already crossed."""
    return len(path) - len(set(path))


def tiers_for(count: int) -> tuple[int, ...]:
    return LASER_TIER_SETS.get(count, LASER_TIER_SETS[DEFAULT_ROUNDS["laser_maze"]])


def make_round(index: int, tier: int, rng: random.Random, answer: int, previous_exit: int | None = None) -> RoundSpec | None:
    """One attempt at a level whose correct receiver is number `answer` (1-based); None when it does not work out."""
    level = LASER_TIERS[tier]
    n, receivers = level["n"], level["receivers"]
    mirrors = {(row, column): rng.choice("/\\") for row in range(n) for column in range(n) if rng.random() < level["density"]}
    entry = rng.randrange(port_count(n))
    result = trace(n, mirrors, entry)
    low, high = level["bounces"]
    if not low <= len(result["hits"]) <= high or len(set(result["path"])) < level["min_cells"] or revisits(result["path"]) < level["revisits"]:
        return None
    end = result["exit"]
    if end == entry:
        return None
    # Receivers: the true exit with exactly `answer - 1` of them clockwise before it, the rest after it, none next to another.
    ports = [port for port in range(port_count(n)) if port not in (entry, end)]
    before = [port for port in ports if port < end]
    after = [port for port in ports if port > end]
    if len(before) < answer - 1 or len(after) < receivers - answer:
        return None
    picked = _spaced(before, answer - 1, rng, end, entry, n) + [end] + _spaced(after, receivers - answer, rng, end, entry, n)
    if len(picked) != receivers or any(_gap(a, b, n) < MIN_PORT_GAP for a in picked for b in picked if a < b):
        return None
    if _gap(entry, end, n) < 1 or any(_gap(entry, port, n) < 1 for port in picked):
        return None
    trace_seconds = laser_trace_seconds(len(result["path"]))
    data = {"version": VERSION, "n": n, "mirrors": [[row, column, kind] for (row, column), kind in sorted(mirrors.items())],
            "entry": entry, "receivers": sorted(picked), "path": [list(cell) for cell in result["path"]], "hits": result["hits"],
            "exit": end, "bounces": len(result["hits"]), "level": index + 1, "tier": tier, "thinking_seconds": level["thinking"],
            "trace_seconds": trace_seconds,
            "rules": {"bounces": list(level["bounces"]), "min_cells": level["min_cells"], "revisits": level["revisits"]}}
    return RoundSpec(index, "laser_maze", data, sorted(picked).index(end) + 1)


def _gap(first: int, second: int, n: int) -> int:
    """How many ports apart two ports are around the edge of the board."""
    around = port_count(n)
    return min((first - second) % around, (second - first) % around)


def _spaced(pool: list[int], count: int, rng: random.Random, end: int, entry: int, n: int) -> list[int]:
    chosen: list[int] = []
    for port in rng.sample(pool, len(pool)):
        if len(chosen) == count:
            break
        if all(_gap(port, other, n) >= MIN_PORT_GAP for other in chosen) and _gap(port, end, n) >= MIN_PORT_GAP and _gap(port, entry, n) >= 1:
            chosen.append(port)
    return chosen


def generate(seed: int, difficulty: str = "hard", theme: str = "lasers", round_count: int | None = None) -> VideoSpec:
    """Always Hard (the levels escalate inside one video); the number of levels sets which tiers are used."""
    count = round_count or DEFAULT_ROUNDS["laser_maze"]
    if count not in LASER_TIER_SETS:
        raise ValueError("Laser Maze has 3 to 5 levels")
    rng = random.Random(f"laser_maze_v1:{seed}:{count}")
    answer_rng = random.Random(f"laser_answers_v1:{seed}:{count}")  # the correct number of every level, drawn before any board
    rounds: list[RoundSpec] = []
    previous = None
    for index, tier in enumerate(tiers_for(count)):
        answer = answer_rng.randrange(1, LASER_TIERS[tier]["receivers"] + 1)
        for _ in range(ATTEMPTS):
            item = make_round(index, tier, rng, answer, previous)
            if item is not None and item.fingerprint() not in {other.fingerprint() for other in rounds}:
                break
        else:
            raise RuntimeError("Could not generate a laser board")
        rounds.append(item)
        previous = item.data["exit"]
    stable_id = sha256(f"laser_maze_v1:{seed}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "laser_maze", seed, "hard", "lasers", tuple(rounds), PUZZLE_FIT_INTRO_DURATION,
                     laser_average_round([item.data for item in rounds]), PUZZLE_FIT_OUTRO_DURATION)


def errors(data: dict, answer: int, difficulty: str | None = None) -> list[str]:
    if data.get("version") != VERSION:
        return ["unknown laser board version"]
    n = data.get("n")
    if not isinstance(n, int) or not 5 <= n <= 9:
        return ["a laser board is 5x5 to 9x9"]
    mirrors: dict[tuple[int, int], str] = {}
    for entry in data.get("mirrors", []):
        if len(entry) != 3 or entry[2] not in ("/", "\\") or not (0 <= entry[0] < n and 0 <= entry[1] < n) or (entry[0], entry[1]) in mirrors:
            return ["mirrors must sit in distinct cells of the board"]
        mirrors[(entry[0], entry[1])] = entry[2]
    entry, receivers = data.get("entry"), data.get("receivers", [])
    if not isinstance(entry, int) or not 0 <= entry < port_count(n):
        return ["the laser enters through a port of the board"]
    if (len(set(receivers)) != len(receivers) or receivers != sorted(receivers) or not 3 <= len(receivers) <= 8
            or any(not isinstance(port, int) or not 0 <= port < port_count(n) for port in receivers) or entry in receivers):
        return ["receivers are distinct ports, in clockwise order, apart from the laser's"]
    if any(_gap(a, b, n) < MIN_PORT_GAP for a in receivers for b in receivers if a < b):
        return ["receivers must not crowd each other"]
    result = trace(n, mirrors, entry)
    if data.get("path") != [list(cell) for cell in result["path"]] or data.get("hits") != result["hits"] or data.get("exit") != result["exit"]:
        return ["the stored beam does not match the mirrors"]
    if data.get("bounces") != len(result["hits"]):
        return ["the stored bounce count does not match the beam"]
    if result["exit"] not in receivers or answer != receivers.index(result["exit"]) + 1:
        return ["the answer must be the receiver the beam ends in"]
    rules = data.get("rules", {})
    low, high = rules.get("bounces", [1, 99])
    if not low <= len(result["hits"]) <= high or len(set(result["path"])) < rules.get("min_cells", 1) or revisits(result["path"]) < rules.get("revisits", 0):
        return ["the beam does not meet its level's bounces, length and crossings"]
    if not 3.0 <= float(data.get("thinking_seconds", 0)) <= 15.0 or not 1.0 <= float(data.get("trace_seconds", 0)) <= 6.0:
        return ["laser level timing is out of range"]
    if data.get("tier") not in range(len(LASER_TIERS)):
        return ["unknown laser tier"]
    return []
