"""Flash Count, number flash: a number flashes for a split second; after 3 s of thinking the viewer sees what it was.

Every video gets harder as it goes: the number grows from 4 to 6 digits over the levels (FLASH_DIGITS). The game is
produced only in Hard; the number stays on screen FLASH_VISIBLE by its length (0.2 s, 0.3 s for 6 digits). Numbers avoid easy chunks, so they
have to be read, not recognised: no repeated neighbours (5 5), no three-step runs (3 4 5, 9 8 7), no digit more than
twice, and never a leading zero.
"""
from __future__ import annotations

from hashlib import sha256
import random
from typing import Any

from ..config import (DEFAULT_ROUNDS, FLASH_DIGITS, FLASH_INTRO, FLASH_THINKING, FLASH_VISIBLE, PUZZLE_FIT_OUTRO_DURATION,
                      round_duration)
from ..models import RoundSpec, VideoSpec

FORMAT = "number_flash"
VERSION = "number_flash_v1"


def level_tier(index: int, count: int) -> int:
    """Opening, middle, or final tier of a level (the same split Cube Count uses)."""
    if count <= 1:
        return 2
    fraction = index / (count - 1)
    return 0 if fraction < 0.34 else (1 if fraction < 0.75 else 2)


def number_errors(number: Any, digits: int | None = None) -> list[str]:
    if not isinstance(number, str) or not number.isdigit():
        return ["flash number must be a string of digits"]
    if digits is not None and len(number) != digits:
        return ["flash number has the wrong length for its level"]
    if number[0] == "0":
        return ["flash number must not start with zero"]
    values = [int(digit) for digit in number]
    if any(a == b for a, b in zip(values, values[1:])):
        return ["flash number must not repeat a digit side by side"]
    if any(b - a == c - b and abs(b - a) == 1 for a, b, c in zip(values, values[1:], values[2:])):
        return ["flash number must not contain a counting run"]
    if any(number.count(digit) > 2 for digit in set(number)):
        return ["flash number uses a digit too often"]
    return []


def make_number(digits: int, rng: random.Random, taken: set[str]) -> str:
    for _ in range(10_000):
        number = str(rng.randint(1, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(digits - 1))
        if number not in taken and not number_errors(number, digits):
            return number
    raise RuntimeError("Could not create a flash number")


def generate(seed: int, difficulty: str = "easy", theme: str = FORMAT, round_count: int | None = None) -> VideoSpec:
    difficulty = "hard"  # the only difficulty this game is produced in, whatever was asked for
    count = round_count or DEFAULT_ROUNDS["flash_count"]
    if count not in (3, 4, 5):
        raise ValueError("Flash Count uses 3, 4, or 5 levels")
    rng = random.Random(f"{VERSION}:{seed}:{difficulty}:{count}")
    rounds, taken = [], set()
    for index in range(count):
        tier = level_tier(index, count)
        number = make_number(FLASH_DIGITS[tier], rng, taken)
        taken.add(number)
        rounds.append(RoundSpec(index, "flash_count", {
            "format": FORMAT, "version": VERSION, "number": number, "level": index + 1, "tier": tier,
            "visible_seconds": FLASH_VISIBLE[len(number)], "thinking_seconds": FLASH_THINKING,
        }, number))
    stable_id = sha256(f"{VERSION}:{seed}:{difficulty}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "flash_count", seed, difficulty, FORMAT, tuple(rounds),
                     FLASH_INTRO, round_duration("flash_count", difficulty), PUZZLE_FIT_OUTRO_DURATION)


def errors(data: dict[str, Any], answer: Any, difficulty: str | None = None) -> list[str]:
    if data.get("format") != FORMAT:
        return ["flash count round is not a number flash"]
    tier = data.get("tier")
    if tier not in (0, 1, 2):
        return ["flash level tier is invalid"]
    result = number_errors(data.get("number"), FLASH_DIGITS[tier])
    if answer != data.get("number"):
        result.append("flash answer must be the number shown")
    if data.get("visible_seconds") != FLASH_VISIBLE[FLASH_DIGITS[tier]] or data.get("thinking_seconds") != FLASH_THINKING:
        result.append("flash timing is invalid")
    return result
