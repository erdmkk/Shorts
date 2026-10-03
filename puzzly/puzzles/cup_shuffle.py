"""Cup Shuffle: follow the ball under the cup. Three levels with 3, 4 and 5 cups that shuffle faster every time.

A level shows the ball under one cup, hides it, shuffles the cups with a fixed list of swaps and asks where the ball is.
Everything is a deterministic function of the seed: the ball's start position, the swaps and the answer are stored in
the round data, and validation replays the swaps to prove the answer. The answer (the ball's final cup, 1..N from the
left) is drawn uniformly per level before any swap is built, so no position is favoured.

A swap exchanges the cups standing at two positions. `front` says which of the two travels in front (towards the
viewer) on its arc while the other passes behind, so the motion never reveals which cup holds the ball.
"""
from __future__ import annotations

from hashlib import sha256
import random

from ..config import (CUP_LEVELS, CUP_SWAP_SECONDS_RANGE, READY_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION,
                      cup_average_round)
from ..models import RoundSpec, VideoSpec

VERSION = "cups_v1"
LEVELS = 3
CUP_COLORS = ("coral", "violet", "teal", "blue")
MIN_BALL_SHARE = .5  # the ball's cup takes part in at least this share of the swaps (never fewer than 3)


def replay(cups: int, start: int, swaps: list) -> tuple[list[int], int]:
    """Cup standing at every position after all swaps (a list of cup ids), and the ball's final position.

    Cups are numbered by their starting position; the ball starts under cup `start`."""
    order = list(range(cups))
    for first, second, _front in swaps:
        order[first], order[second] = order[second], order[first]
    return order, order.index(start)


def states(cups: int, swaps: list) -> list[list[int]]:
    """The cup at every position before swap 0, after swap 0, ... after the last swap."""
    order = list(range(cups))
    result = [list(order)]
    for first, second, _front in swaps:
        order[first], order[second] = order[second], order[first]
        result.append(list(order))
    return result


def ball_swaps(cups: int, start: int, swaps: list) -> int:
    """How many swaps move the ball's cup."""
    order, count = list(range(cups)), 0
    for first, second, _front in swaps:
        if start in (order[first], order[second]):
            count += 1
        order[first], order[second] = order[second], order[first]
    return count


def _build(cups: int, count: int, start: int, final: int, rng: random.Random) -> list | None:
    """Random swaps (no pair twice in a row) that leave the ball at `final`, or None."""
    swaps, previous = [], None
    for _ in range(count):
        while True:
            first, second = sorted(rng.sample(range(cups), 2))
            if (first, second) != previous:
                break
        previous = (first, second)
        swaps.append([first, second, rng.choice((first, second))])  # `front` travels in front of the other cup
    _, position = replay(cups, start, swaps)
    if position != final or ball_swaps(cups, start, swaps) < max(3, round(count * MIN_BALL_SHARE)):
        return None
    return swaps


def make_round(index: int, rng: random.Random, answer_rng: random.Random, level: dict) -> RoundSpec:
    cups, count, seconds = level["cups"], level["swaps"], level["swap_seconds"]
    final = answer_rng.randrange(cups)  # the answer is drawn first, so no position is favoured
    start = rng.choice([position for position in range(cups) if position != final])
    for _ in range(20000):
        swaps = _build(cups, count, start, final, rng)
        if swaps is not None:
            break
    else:
        raise RuntimeError("could not build a cup shuffle")
    data = {"version": VERSION, "level": index + 1, "cups": cups, "start": start, "swaps": swaps,
            "swap_seconds": seconds, "thinking_seconds": level["thinking"], "color": rng.choice(CUP_COLORS)}
    return RoundSpec(index, "cup_shuffle", data, final + 1)


def generate(seed: int, difficulty: str = "hard") -> VideoSpec:
    """Always Hard (the user's rule); any requested difficulty gives the same video."""
    rng = random.Random(f"{VERSION}:{seed}")
    answer_rng = random.Random(f"{VERSION}:answers:{seed}")
    colors = rng.sample(CUP_COLORS, LEVELS)
    rounds = []
    for index, level in enumerate(CUP_LEVELS):
        item = make_round(index, rng, answer_rng, level)
        item.data["color"] = colors[index]  # a different cup colour on every level
        rounds.append(item)
    stable_id = sha256(f"{VERSION}:{seed}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "cup_shuffle", seed, "hard", "cups", tuple(rounds), READY_INTRO_DURATION,
                     cup_average_round([item.data for item in rounds]), PUZZLE_FIT_OUTRO_DURATION)


def errors(data: dict, answer, difficulty: str | None) -> list[str]:
    problems: list[str] = []
    try:
        cups, start, swaps = int(data["cups"]), int(data["start"]), data["swaps"]
        seconds, thinking = float(data["swap_seconds"]), float(data["thinking_seconds"])
        level = int(data["level"])
    except (KeyError, TypeError, ValueError):
        return ["cup shuffle round data is malformed"]
    if data.get("version") != VERSION or cups != CUP_LEVELS[min(max(level, 1), LEVELS) - 1]["cups"]:
        problems.append("cup shuffle level does not match its number of cups")
    if difficulty is not None and difficulty != "hard":
        problems.append("cup shuffle is produced in Hard only")
    if not 0 <= start < cups:
        return problems + ["cup shuffle ball starts outside the cups"]
    low, high = CUP_SWAP_SECONDS_RANGE
    if not low <= seconds <= high or not 2.0 <= thinking <= 15.0:
        problems.append("cup shuffle speed or thinking time is out of range")
    if data.get("color") not in CUP_COLORS or not swaps:
        problems.append("cup shuffle needs a cup colour and swaps")
    previous = None
    for swap in swaps:
        if len(swap) != 3 or not (0 <= swap[0] < swap[1] < cups) or swap[2] not in swap[:2]:
            return problems + ["cup shuffle has an invalid swap"]
        if (swap[0], swap[1]) == previous:
            problems.append("cup shuffle repeats the same swap twice in a row")
        previous = (swap[0], swap[1])
    _, final = replay(cups, start, swaps)
    if answer != final + 1:
        problems.append("cup shuffle answer does not match the swaps")
    if final == start:
        problems.append("the ball must end under a different cup than it started")
    if ball_swaps(cups, start, swaps) < max(3, round(len(swaps) * MIN_BALL_SHARE)):
        problems.append("the ball's cup must take part in enough swaps")
    return problems
