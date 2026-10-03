from __future__ import annotations

from hashlib import sha256
import random

from ..config import (DEFAULT_ROUNDS, PUZZLE_FIT_ART_PALETTES, PUZZLE_FIT_ELIMINATION, PUZZLE_FIT_ENTRANCE,
                      PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_MOVE, PUZZLE_FIT_OUTRO_DURATION, round_duration,
                      thinking_duration)
from ..models import RoundSpec, VideoSpec

CARD_BOUNDS = ((110, 1150, 370, 1490), (410, 1150, 670, 1490), (710, 1150, 970, 1490))
BOARD_CARD = (105, 280, 975, 1120)
# Hard: 3x3 grid of nine near-identical candidates below a compact board.
HARD_CARD_BOUNDS = tuple((x1, y1, x1 + 270, y1 + 180) for y1 in (955, 1160, 1365) for x1 in (90, 405, 720))
HARD_BOARD_CARD = (105, 280, 975, 920)
ART_STYLES = ("rings", "stripes", "lowpoly", "waves", "burst")
SLOT_EDGES = (
    (0, 1, -1, 0),
    (0, 0, 1, -1),
    (1, -1, 0, 0),
    (-1, 0, 0, 1),
)
PIECE_COLORS = ("accent", "coral", "success", "lavender")


def candidate_card_bounds(difficulty: str) -> tuple[tuple[int, int, int, int], ...]:
    return HARD_CARD_BOUNDS if difficulty == "hard" else CARD_BOUNDS


def board_card_bounds(difficulty: str) -> tuple[int, int, int, int]:
    return HARD_BOARD_CARD if difficulty == "hard" else BOARD_CARD


def phase_times(difficulty: str) -> dict[str, float]:
    think_end = PUZZLE_FIT_ENTRANCE + thinking_duration("puzzle_fit", difficulty)
    move_start = think_end + PUZZLE_FIT_ELIMINATION
    return {"think_start": PUZZLE_FIT_ENTRANCE, "think_end": think_end,
            "move_start": move_start, "snap": move_start + PUZZLE_FIT_MOVE}


def visual_state(local_time: float, difficulty: str = "easy") -> str:
    times = phase_times(difficulty)
    if local_time < times["think_start"]:
        return "choices"
    if local_time < times["think_end"]:
        return "thinking"
    if local_time < times["move_start"]:
        return "eliminating"
    if local_time < times["snap"]:
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
        changes = 2 if difficulty == "easy" or (difficulty == "hard" and attempts > 80) else 1
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


def _near_miss_decoys(correct: tuple[int, int, int, int], rng: random.Random) -> list[tuple[int, int, int, int]]:
    """Every single-edge variant of the answer: each decoy differs from it by exactly one edge."""
    decoys = []
    for position in range(4):
        for value in (-1, 0, 1):
            if value != correct[position]:
                decoys.append(tuple(value if index == position else edge for index, edge in enumerate(correct)))
    rng.shuffle(decoys)
    return decoys


def _level_tier(index: int, count: int) -> int:
    """0 = opening level, 1 = middle levels, 2 = final level(s): each video gets harder as it goes."""
    if count <= 1:
        return 2
    fraction = index / (count - 1)
    return 0 if fraction < 0.34 else (1 if fraction < 0.75 else 2)


def _level_layouts(difficulty: str, tier: int) -> tuple[tuple[int, int], ...]:
    if difficulty == "hard":
        return ((2, 3),) if tier == 0 else (((2, 3), (3, 3)) if tier == 1 else ((3, 3),))
    return (((2, 2),), ((2, 3),), ((3, 3),))[tier]


def _hole_slots(rows: int, columns: int, difficulty: str, tier: int = 1) -> list[int]:
    slots = list(range(rows * columns))
    if difficulty != "hard":
        return slots
    # Corner holes have two flat sides, which eliminates candidates too quickly on Hard.
    corners = {0, columns - 1, (rows - 1) * columns, rows * columns - 1}
    open_slots = [slot for slot in slots if slot not in corners]
    if tier == 2 and rows == columns == 3:
        return [4]  # Final level: the fully enclosed centre hole has no flat edge at all.
    return open_slots


def generate(seed: int, difficulty: str = "easy", theme: str = "interlocking", round_count: int | None = None) -> VideoSpec:
    """Current Puzzle Fit (V12): one big picture with three missing pieces and six tilted options. See puzzle_fit_v12."""
    from .puzzle_fit_v12 import generate as generate_v12
    return generate_v12(seed, difficulty)


def legacy_generate(seed: int, difficulty: str = "easy", theme: str = "interlocking", round_count: int | None = None) -> VideoSpec:
    """Puzzle Fit V10 (five levels, nine near-identical candidates on Hard). Kept for tests and old records."""
    difficulty = difficulty if difficulty in ("easy", "medium", "hard") else "easy"
    count = round_count or 5  # V10 videos had five levels
    rng = random.Random(f"puzzle_fit_v10:{seed}:{difficulty}:{theme}:{count}")
    rounds: list[RoundSpec] = []
    used: set[str] = set()
    styles = list(ART_STYLES)
    rng.shuffle(styles)
    for index in range(count):
        tier = _level_tier(index, count)
        for _ in range(100):
            rows, columns = rng.choice(_level_layouts(difficulty, tier))
            pieces = board_edges(rows, columns, rng)
            hole_slot = rng.choice(_hole_slots(rows, columns, difficulty, tier))
            color_rotation = rng.randrange(4)
            key = str((rows, columns, pieces, hole_slot, color_rotation))
            if key in used:
                continue
            used.add(key)
            correct = tuple(pieces[hole_slot])
            if difficulty == "hard":
                decoys = _near_miss_decoys(correct, rng)
            else:
                decoys = _decoys(correct, "easy" if tier == 0 and difficulty == "easy" else "medium", rng, 2)
            candidates = [correct, *decoys]
            rng.shuffle(candidates)
            correct_index = candidates.index(correct)
            colors = [PIECE_COLORS[(slot + color_rotation) % 4] for slot in range(rows * columns)]
            rounds.append(RoundSpec(index, "puzzle_fit", {
                "board_kind": "jigsaw", "rows": rows, "columns": columns, "hole_slot": hole_slot,
                "hole_edges": list(correct), "piece_edges": pieces,
                "piece_colors": colors, "candidates": [list(edges) for edges in candidates],
                "correct_index": correct_index, "candidate_cards": [list(bounds) for bounds in candidate_card_bounds(difficulty)],
                "level": index + 1, "art_style": styles[index % len(styles)],
                "art_palette": rng.randrange(len(PUZZLE_FIT_ART_PALETTES)), "art_seed": rng.randrange(1 << 30),
            }, correct_index))
            break
        else:
            raise RuntimeError("Could not create a unique puzzle-fit round")
    stable_id = sha256(f"puzzle_fit_v10:{seed}:{difficulty}:{theme}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "puzzle_fit", seed, difficulty, "interlocking", tuple(rounds),
                     PUZZLE_FIT_INTRO_DURATION, round_duration("puzzle_fit", difficulty), PUZZLE_FIT_OUTRO_DURATION)
