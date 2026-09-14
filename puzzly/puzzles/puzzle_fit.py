from __future__ import annotations

from hashlib import sha256
import random

from ..config import DEFAULT_ROUNDS, INTRO_DURATION, OUTRO_DURATION, round_duration, thinking_duration
from ..models import RoundSpec, VideoSpec

CARD_BOUNDS = ((110, 1150, 370, 1490), (410, 1150, 670, 1490), (710, 1150, 970, 1490))
HARD_CARD_BOUNDS = ((110, 1150, 490, 1390), (590, 1150, 970, 1390),
                    (110, 1410, 490, 1650), (590, 1410, 970, 1650))
SLOT_EDGES = (
    (0, 1, -1, 0),
    (0, 0, 1, -1),
    (1, -1, 0, 0),
    (-1, 0, 0, 1),
)
PIECE_COLORS = ("accent", "coral", "success", "lavender")


def candidate_card_bounds(difficulty: str) -> tuple[tuple[int, int, int, int], ...]:
    return HARD_CARD_BOUNDS if difficulty == "hard" else CARD_BOUNDS


def visual_state(local_time: float, difficulty: str = "easy") -> str:
    thinking_end = 0.35 + thinking_duration("puzzle_fit", difficulty)
    if local_time < 0.35:
        return "choices"
    if local_time < thinking_end:
        return "thinking"
    if local_time < thinking_end + 0.20:
        return "highlight"
    if local_time < thinking_end + 0.90:
        return "moving"
    return "solved"


def board_edges(rows: int, columns: int, rng: random.Random) -> list[list[int]]:
    pieces = [[0, 0, 0, 0] for _ in range(rows * columns)]
    for row in range(rows):
        for column in range(columns):
            index = row * columns + column
            if column + 1 < columns:
                sign = rng.choice((-1, 1))
                pieces[index][1], pieces[index + 1][3] = sign, -sign
            if row + 1 < rows:
                sign = rng.choice((-1, 1))
                pieces[index][2], pieces[index + columns][0] = sign, -sign
    return pieces


def _decoys(correct: tuple[int, int, int, int], difficulty: str, rng: random.Random, count: int) -> list[tuple[int, int, int, int]]:
    candidates: list[tuple[int, int, int, int]] = []
    attempts = 0
    while len(candidates) < count and attempts < 200:
        attempts += 1
        values = list(correct)
        changes = 2 if difficulty == "easy" else 1
        for position in rng.sample(range(4), changes):
            options = [-1, 0, 1] if difficulty != "hard" else [-1, 1]
            options = [value for value in options if value != values[position]]
            values[position] = rng.choice(options)
        candidate = tuple(values)
        if candidate != correct and candidate not in candidates:
            candidates.append(candidate)
    if len(candidates) != count:
        raise RuntimeError("Could not create unique puzzle-piece decoys")
    return candidates


def generate(seed: int, difficulty: str = "easy", theme: str = "interlocking", round_count: int | None = None) -> VideoSpec:
    difficulty = difficulty if difficulty in ("easy", "medium", "hard") else "easy"
    count = round_count or DEFAULT_ROUNDS["puzzle_fit"]
    rng = random.Random(f"puzzle_fit_v5:{seed}:{difficulty}:{theme}:{count}")
    rounds: list[RoundSpec] = []
    used: set[str] = set()
    for index in range(count):
        for _ in range(100):
            rows, columns = rng.choice(((2, 2), (2, 3), (3, 3)))
            pieces = board_edges(rows, columns, rng)
            hole_slot = rng.randrange(rows * columns)
            color_rotation = rng.randrange(4)
            key = str((rows, columns, pieces, hole_slot, color_rotation))
            if key in used:
                continue
            used.add(key)
            correct = tuple(pieces[hole_slot])
            candidate_count = 4 if difficulty == "hard" else 3
            candidates = [correct, *_decoys(correct, difficulty, rng, candidate_count - 1)]
            rng.shuffle(candidates)
            correct_index = candidates.index(correct)
            colors = [PIECE_COLORS[(slot + color_rotation) % 4] for slot in range(rows * columns)]
            rounds.append(RoundSpec(index, "puzzle_fit", {
                "board_kind": "jigsaw", "rows": rows, "columns": columns, "hole_slot": hole_slot,
                "hole_edges": list(correct), "piece_edges": pieces,
                "piece_colors": colors, "candidates": [list(edges) for edges in candidates],
                "correct_index": correct_index, "candidate_cards": [list(bounds) for bounds in candidate_card_bounds(difficulty)],
            }, correct_index))
            break
        else:
            raise RuntimeError("Could not create a unique puzzle-fit round")
    stable_id = sha256(f"puzzle_fit_v7:{seed}:{difficulty}:{theme}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "puzzle_fit", seed, difficulty, "interlocking", tuple(rounds),
                     INTRO_DURATION, round_duration("puzzle_fit", difficulty), OUTRO_DURATION)
