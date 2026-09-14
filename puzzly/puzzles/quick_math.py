from __future__ import annotations

from hashlib import sha256
import random

from ..config import DEFAULT_ROUNDS, INTRO_DURATION, OUTRO_DURATION, ROUND_DURATIONS
from ..models import RoundSpec, VideoSpec

OPERATIONS = ("addition", "subtraction", "multiplication")
SYMBOLS = {"addition": "+", "subtraction": "−", "multiplication": "×"}
POSITIONS = ("result", "right", "left")


def allowed_operations(difficulty: str) -> tuple[str, ...]:
    return ("addition", "subtraction") if difficulty == "easy" else OPERATIONS


def allowed_positions(operation: str, difficulty: str) -> tuple[str, ...]:
    if difficulty == "easy" and operation == "subtraction":
        return ("result",)
    return POSITIONS


def _equation(rng: random.Random, operation: str, difficulty: str) -> tuple[int, int, int]:
    if operation == "addition":
        low, high = {"easy": (1, 9), "medium": (4, 30), "hard": (8, 60)}[difficulty]
        a, b = rng.randint(low, high), rng.randint(low, high)
        return a, b, a + b
    if operation == "subtraction":
        low, high = {"easy": (3, 12), "medium": (10, 60), "hard": (20, 99)}[difficulty]
        a = rng.randint(low, high)
        b = rng.randint(1, a - 1)
        return a, b, a - b
    table_high, factor_high = ((5, 10) if difficulty == "medium" else (9, 12))
    a, b = rng.randint(2, table_high), rng.randint(2, factor_high)
    return a, b, a * b


def _operation_schedule(rng: random.Random, difficulty: str, operation: str, count: int) -> list[str]:
    allowed = allowed_operations(difficulty)
    if operation in allowed:
        return [operation] * count
    cycle = ["addition", "addition", "subtraction"] if difficulty == "easy" else list(allowed)
    schedule = [cycle[index % len(cycle)] for index in range(count)]
    rng.shuffle(schedule)
    return schedule


def generate(seed: int, difficulty: str = "easy", operation: str = "mixed", round_count: int | None = None) -> VideoSpec:
    difficulty = difficulty if difficulty in ("easy", "medium", "hard") else "easy"
    operation = operation if operation in (*OPERATIONS, "mixed") else "mixed"
    if operation not in allowed_operations(difficulty):
        operation = "mixed"
    count = round_count or DEFAULT_ROUNDS["quick_math"]
    rng = random.Random(f"quick_math_v7:{seed}:{difficulty}:{operation}:{count}")
    schedule = _operation_schedule(rng, difficulty, operation, count)
    rounds: list[RoundSpec] = []
    used: set[tuple[str, int, int, str]] = set()
    used_answers: set[int] = set()
    used_templates: set[str] = set()
    for index, selected in enumerate(schedule):
        positions = allowed_positions(selected, difficulty)
        for attempt in range(200):
            a, b, result = _equation(rng, selected, difficulty)
            position = rng.choice(positions)
            if index == count - 1 and len(used_templates) == 1 and len(positions) > 1:
                alternatives = [item for item in positions if item not in used_templates]
                if alternatives:
                    position = rng.choice(alternatives)
            answer = {"left": a, "right": b, "result": result}[position]
            key = (selected, a, b, position)
            if key in used or (answer in used_answers and attempt < 150):
                continue
            used.add(key)
            used_answers.add(answer)
            used_templates.add(position)
            rounds.append(RoundSpec(index, "quick_math", {
                "a": a, "b": b, "result": result, "operation": selected,
                "symbol": SYMBOLS[selected], "unknown_position": position,
                "equation_template": f"{selected}_{position}",
            }, answer))
            break
        else:
            raise RuntimeError("Could not create a unique equation")
    stable_id = sha256(f"quick_math_v7:{seed}:{difficulty}:{operation}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "quick_math", seed, difficulty, "numbers", tuple(rounds),
                     INTRO_DURATION, ROUND_DURATIONS["quick_math"], OUTRO_DURATION, operation)
