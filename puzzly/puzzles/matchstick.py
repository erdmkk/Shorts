"""Matchstick equations: "move one match to make the equation true". Generated locally and checked exhaustively.

Every symbol is built from matchsticks on fixed slots: digits use the seven segments of a digital clock (a top,
b upper right, c lower right, d bottom, e lower left, f upper left, g middle), `+` and `-` use a horizontal (h) and a
vertical (v) slot, and `=` is fixed. The glyphs never vary (1 is the right-hand pair, 7 has three sticks, 6 and 9
always have their tails), so every stick pattern reads as exactly one symbol.

A move takes one stick from any slot and puts it on any empty slot (the same symbol or another one). Generation
draws a false equation, tries every possible move, and keeps the equation only when exactly one resulting equation is
true. Validation repeats the full search before rendering.
"""
from __future__ import annotations

from hashlib import sha256
from itertools import product
import random

from ..config import MATCH_THINKING, matchstick_average_round
from ..models import RoundSpec, VideoSpec

VERSION = "matchstick_v1"
DIGITS = {0: "abcdef", 1: "bc", 2: "abdeg", 3: "abcdg", 4: "bcfg", 5: "acdfg", 6: "acdefg", 7: "abc", 8: "abcdefg",
          9: "abcdfg"}
DIGIT_OF = {frozenset(value): key for key, value in DIGITS.items()}
OPERATORS = {"+": "hv", "-": "h"}
OPERATOR_OF = {frozenset(value): key for key, value in OPERATORS.items()}
SEGMENTS = "abcdefg"
LEVELS = 3
# Tier templates: digits in (left operand, right operand, result). Tier 0: single digits. Tier 1: one or two numbers
# with two digits, and the stick moves between two different symbols. Tier 2: two-digit numbers on both sides, and the
# stick crosses the equals sign or changes the operator.
TEMPLATES = {0: ((1, 1, 1),), 1: ((2, 1, 2), (1, 2, 2), (2, 1, 1)), 2: ((2, 2, 2), (2, 1, 2), (2, 2, 1))}


def symbols(text: str) -> list[tuple[str, frozenset]]:
    """The equation as (kind, sticks) per symbol: kind is 'digit', 'op' or 'eq'."""
    result = []
    for char in text:
        if char.isdigit():
            result.append(("digit", frozenset(DIGITS[int(char)])))
        elif char in OPERATORS:
            result.append(("op", frozenset(OPERATORS[char])))
        elif char == "=":
            result.append(("eq", frozenset()))
        else:
            raise ValueError(f"unsupported symbol: {char}")
    return result


def decode(parts: list[tuple[str, frozenset]]) -> str | None:
    text = ""
    for kind, sticks in parts:
        if kind == "eq":
            text += "="
        elif kind == "op":
            if sticks not in OPERATOR_OF:
                return None
            text += OPERATOR_OF[sticks]
        else:
            if sticks not in DIGIT_OF:
                return None
            text += str(DIGIT_OF[sticks])
    return text


def split(text: str) -> tuple[str, str, str, str]:
    left, result = text.split("=")
    op = "+" if "+" in left else "-"
    a, b = left.split(op)
    return a, op, b, result


def is_true(text: str) -> bool:
    """A well-formed true equation: numbers without leading zeros, `a op b = c` with a non-negative result."""
    if text.count("=") != 1 or sum(text.count(op) for op in OPERATORS) != 1:
        return False
    try:
        a, op, b, c = split(text)
    except ValueError:
        return False
    if not all(part.isdigit() and (len(part) == 1 or part[0] != "0") for part in (a, b, c)):
        return False
    value = int(a) + int(b) if op == "+" else int(a) - int(b)
    return value == int(c)


def slots(parts: list[tuple[str, frozenset]]) -> list[tuple[int, str]]:
    result = []
    for index, (kind, _) in enumerate(parts):
        if kind == "digit":
            result += [(index, segment) for segment in SEGMENTS]
        elif kind == "op":
            result += [(index, segment) for segment in "hv"]
    return result


def moves(text: str) -> dict[str, list[tuple[tuple[int, str], tuple[int, str]]]]:
    """Every true equation one move away, with the moves (from slot, to slot) that make it, in a fixed order."""
    parts = symbols(text)
    places = slots(parts)
    found: dict[str, list] = {}
    for source, target in product(places, places):
        (i, s), (j, t) = source, target
        if source == target or s not in parts[i][1] or t in parts[j][1]:
            continue
        changed = list(parts)
        changed[i] = (changed[i][0], changed[i][1] - {s})
        changed[j] = (changed[j][0], changed[j][1] | {t})
        result = decode(changed)
        if result is not None and is_true(result):
            found.setdefault(result, []).append((source, target))
    return found


def _operator_index(text: str) -> int:
    return next(index for index, char in enumerate(text) if char in OPERATORS)


def tier_errors(text: str, move: tuple[tuple[int, str], tuple[int, str]], tier: int) -> list[str]:
    (i, _), (j, _) = move
    a, _, b, c = split(text)
    shape = (len(a), len(b), len(c))
    problems = []
    if shape not in TEMPLATES[tier]:
        problems.append("matchstick equation does not use its tier's number sizes")
    if a[0] == "0" or b[0] == "0" and len(b) > 1:
        problems.append("matchstick equation starts a number with 0")
    if tier >= 1 and i == j:
        problems.append("matchstick move must change two different symbols")
    if tier >= 2:
        equals = text.index("=")
        crosses = (i < equals) != (j < equals)
        operator = _operator_index(text) in (i, j)
        if not (crosses or operator):
            problems.append("hardest matchstick move must cross the equals sign or change the operator")
    return problems


def _candidate(tier: int, rng: random.Random) -> str:
    sizes = rng.choice(TEMPLATES[tier])
    numbers = [str(rng.randrange(1 if size == 1 else 10, 10 ** size)) for size in sizes]
    if sizes[0] == 1 and numbers[0] == "0":
        numbers[0] = str(rng.randrange(1, 10))
    return f"{numbers[0]}{rng.choice('+-')}{numbers[1]}={numbers[2]}"


def make_round(index: int, tier: int, rng: random.Random, thinking: float, used: set[str]) -> RoundSpec:
    for _ in range(20000):
        text = _candidate(tier, rng)
        if text in used or is_true(text):
            continue
        found = moves(text)
        if len(found) != 1:
            continue
        solution, options = next(iter(found.items()))
        move = options[0]
        if tier_errors(text, move, tier):
            continue
        used.add(text)
        (i, s), (j, t) = move
        data = {"version": VERSION, "tier": tier, "level": index + 1, "equation": text,
                "move": {"from": [i, s], "to": [j, t]}, "thinking_seconds": thinking}
        return RoundSpec(index, "matchstick", data, solution)
    raise RuntimeError(f"could not find a matchstick puzzle for tier {tier}")


def generate(seed: int, difficulty: str = "hard") -> VideoSpec:
    difficulty = difficulty if difficulty in MATCH_THINKING else "hard"
    rng = random.Random(f"{VERSION}:{seed}:{difficulty}")
    used: set[str] = set()
    rounds = tuple(make_round(index, index, rng, MATCH_THINKING[difficulty][index], used) for index in range(LEVELS))
    from ..config import PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION
    stable_id = sha256(f"{VERSION}:{seed}:{difficulty}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "matchstick", seed, difficulty, "matchsticks", rounds, PUZZLE_FIT_INTRO_DURATION,
                     matchstick_average_round(difficulty), PUZZLE_FIT_OUTRO_DURATION)


def errors(data: dict, answer: str, difficulty: str | None) -> list[str]:
    if data.get("version") != VERSION:
        return ["unsupported matchstick version"]
    try:
        text = data["equation"]
        tier = int(data["tier"])
        move = (tuple(data["move"]["from"]), tuple(data["move"]["to"]))
        symbols(text)
    except (KeyError, TypeError, ValueError):
        return ["matchstick round data is malformed"]
    problems = []
    if is_true(text):
        problems.append("matchstick equation is already true")
    found = moves(text)
    if len(found) != 1:
        problems.append(f"matchstick equation must have exactly one solution, found {len(found)}")
    elif answer not in found or move not in found[answer]:
        problems.append("matchstick answer or move does not solve the equation")
    else:
        problems += tier_errors(text, move, tier)
    if difficulty in MATCH_THINKING and float(data.get("thinking_seconds", -1)) != MATCH_THINKING[difficulty][tier]:
        problems.append("matchstick thinking time does not match its level")
    return problems
