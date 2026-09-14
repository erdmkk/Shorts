from __future__ import annotations

from hashlib import sha256
import random

from ..config import DEFAULT_ROUNDS, INTRO_DURATION, OUTRO_DURATION, ROUND_DURATIONS
from ..models import RoundSpec, VideoSpec

FAMILIES = ("addition", "subtraction", "multiplication")
FAMILY_CYCLES = {
    "easy": ("addition", "addition", "addition", "addition", "subtraction"),
    "medium": ("addition", "addition", "subtraction", "subtraction", "multiplication"),
    "hard": ("addition", "subtraction", "subtraction", "multiplication", "multiplication"),
}
RULE_VALUES = {
    "easy": {"addition": (1, 2, 3, 4, 5), "subtraction": (1, 2, 3)},
    "medium": {"addition": (3, 4, 5, 6, 8, 10), "subtraction": (3, 5, 6, 7, 10), "multiplication": (2,)},
    "hard": {"addition": (7, 9, 10, 12, 15, 20), "subtraction": (7, 9, 10, 12, 15, 20), "multiplication": (2, 3, 4, 5)},
}


def _family_schedule(rng: random.Random, difficulty: str, count: int) -> list[str]:
    cycle = FAMILY_CYCLES[difficulty]
    schedule = [cycle[index % len(cycle)] for index in range(count)]
    rng.shuffle(schedule)
    return schedule


def _sequence(rng: random.Random, difficulty: str, family: str, value: int) -> tuple[int, ...]:
    if family == "addition":
        maximum = {"easy": 40, "medium": 120, "hard": 300}[difficulty]
        start = rng.randint(1, maximum - 4 * value)
        return tuple(start + offset * value for offset in range(5))
    if family == "subtraction":
        final_max = {"easy": 12, "medium": 50, "hard": 180}[difficulty]
        final = rng.randint(0, final_max)
        return tuple(final + (4 - offset) * value for offset in range(5))
    maximum_start = max(1, 999 // (value ** 4))
    if difficulty == "medium":
        maximum_start = min(maximum_start, 5)
    start = rng.randint(1, maximum_start)
    return tuple(start * value ** offset for offset in range(5))


def generate(seed: int, difficulty: str = "easy", theme: str = "numbers", round_count: int | None = None) -> VideoSpec:
    difficulty = difficulty if difficulty in ("easy", "medium", "hard") else "easy"
    count = round_count or DEFAULT_ROUNDS["missing_number"]
    rng = random.Random(f"missing_number_v7:{seed}:{difficulty}:{count}")
    schedule = _family_schedule(rng, difficulty, count)
    rounds: list[RoundSpec] = []
    used_sequences: set[tuple[int, ...]] = set()
    used_rules: set[tuple[str, int]] = set()
    hidden_positions: set[int] = set()
    for index, family in enumerate(schedule):
        values = RULE_VALUES[difficulty][family]
        for attempt in range(200):
            rule_value = rng.choice(values)
            sequence = _sequence(rng, difficulty, family, rule_value)
            hidden = rng.randint(1, 3)
            if index == count - 1 and len(hidden_positions) == 1:
                hidden = rng.choice([position for position in range(1, 4) if position not in hidden_positions])
            if sequence in used_sequences or ((family, rule_value) in used_rules and attempt < 150):
                continue
            used_sequences.add(sequence)
            used_rules.add((family, rule_value))
            hidden_positions.add(hidden)
            shown = list(sequence)
            shown[hidden] = None
            signed_step = rule_value if family == "addition" else (-rule_value if family == "subtraction" else None)
            rounds.append(RoundSpec(index, "missing_number", {
                "sequence": list(sequence), "shown": shown, "hidden_index": hidden,
                "sequence_family": family, "step_or_ratio": rule_value, "step": signed_step,
            }, sequence[hidden]))
            break
        else:
            raise RuntimeError("Could not create a unique sequence")
    stable_id = sha256(f"missing_number_v7:{seed}:{difficulty}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "missing_number", seed, difficulty, "numbers", tuple(rounds),
                     INTRO_DURATION, ROUND_DURATIONS["missing_number"], OUTRO_DURATION)
