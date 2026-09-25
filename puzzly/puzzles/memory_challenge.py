from __future__ import annotations

from hashlib import sha256
import random
from dataclasses import asdict, dataclass
from typing import Any

from ..config import (MEMORY_GRID_QUESTIONS, MEMORY_GRID_TOKENS, MEMORY_MEMORIZE, MEMORY_THINKING_DURATION,
                      PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION, round_duration)
from ..memory_colors import (COLOR_LEVEL_THEMES, DEFAULT_GRID_COLOR_LEVEL, GRID_COLORS, GRID_PALETTE_IDS, grid_palette,
                             grid_palette_errors, infer_color_level)
from ..models import RoundSpec, VideoSpec

SHAPES = ("circle", "triangle", "square", "star", "hexagon", "heart", "diamond", "pentagon")


@dataclass(frozen=True)
class MemoryToken:
    shape: str
    color_id: str
    color_value: str
    position: int


MEMORY_SHAPES = SHAPES + ("cross", "moon")  # nine per board; pentagon and hexagon never share a board
GRID_LAYOUT = "grid3"


def generate(seed: int, difficulty: str = "easy", theme: str = "memory_tokens", round_count: int | None = None) -> VideoSpec:
    if round_count not in (None, 1):
        raise ValueError("Memory Challenge uses one fixed board")
    difficulty = difficulty if difficulty in MEMORY_MEMORIZE else "easy"
    level = COLOR_LEVEL_THEMES.get(theme, DEFAULT_GRID_COLOR_LEVEL)  # colour similarity chosen in the UI
    rng = random.Random(f"memory_grid_v1:{seed}:{difficulty}")
    excluded = rng.choice(("pentagon", "hexagon"))
    shapes = [shape for shape in MEMORY_SHAPES if shape != excluded]
    rng.shuffle(shapes)
    variant = rng.randrange(len(GRID_PALETTE_IDS[level]))
    colors = list(grid_palette(level, variant))
    rng.shuffle(colors)
    tokens = [asdict(MemoryToken(shape, color.id, color.value, position))
              for position, (shape, color) in enumerate(zip(shapes, colors), start=1)]
    order = list(range(1, MEMORY_GRID_TOKENS + 1))
    rng.shuffle(order)
    timed, final = order[:MEMORY_GRID_QUESTIONS], order[-1]
    data = {"layout": GRID_LAYOUT, "tokens": tokens, "question_order": timed, "final_position": final,
            "memorization_seconds": MEMORY_MEMORIZE[difficulty], "thinking_seconds": MEMORY_THINKING_DURATION,
            "timed_question_count": MEMORY_GRID_QUESTIONS, "palette_variant": variant,
            "color_level": level}
    board = RoundSpec(0, "memory_challenge", data, {"question_order": timed, "final_position": final})
    stable_id = sha256(f"memory_grid_v1:{seed}:{difficulty}:{level}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "memory_challenge", seed, difficulty, "memory_tokens", (board,),
                     PUZZLE_FIT_INTRO_DURATION, round_duration("memory_challenge", difficulty), PUZZLE_FIT_OUTRO_DURATION)


def errors(data: dict[str, Any], answer: Any, difficulty: str | None = None) -> list[str]:
    result: list[str] = []
    difficulty = difficulty if difficulty in MEMORY_MEMORIZE else "easy"
    tokens = data.get("tokens", [])
    questions = data.get("question_order", [])
    final = data.get("final_position")
    shapes = [token.get("shape") for token in tokens]
    color_ids = [token.get("color_id") for token in tokens]
    positions = [token.get("position") for token in tokens]
    count = MEMORY_GRID_TOKENS
    if data.get("layout") != GRID_LAYOUT:
        result.append("memory board must use the 3x3 grid layout")
    if len(tokens) != count or len(set(shapes)) != count or any(shape not in MEMORY_SHAPES for shape in shapes):
        result.append("memory board must contain nine unique supported shapes")
    if {"pentagon", "hexagon"} <= set(shapes):
        result.append("pentagon and hexagon are too similar to share a board")
    if len(set(color_ids)) != count or any(color_id not in GRID_COLORS for color_id in color_ids):
        result.append("memory board must contain nine unique valid colors")
    if positions != list(range(1, count + 1)):
        result.append("memory token positions must be unique and ordered 1 to 9")
    if len(questions) != MEMORY_GRID_QUESTIONS or len(set(questions)) != MEMORY_GRID_QUESTIONS or any(
            position not in positions for position in questions):
        result.append("memory board must contain eight unique timed questions")
    if final not in positions or final in questions or set(questions) | {final} != set(positions):
        result.append("memory final automatic reveal is invalid")
    if answer != {"question_order": questions, "final_position": final}:
        result.append("memory answer data is inconsistent")
    if data.get("memorization_seconds") != MEMORY_MEMORIZE[difficulty] or data.get("thinking_seconds") != MEMORY_THINKING_DURATION:
        result.append("memory timing metadata is invalid")
    if not result:
        values = [GRID_COLORS[color_id] for color_id in color_ids]
        level = data.get("color_level", infer_color_level(color_ids))
        if level not in GRID_PALETTE_IDS:
            result.append("memory colour similarity level is invalid")
        else:
            result.extend(grid_palette_errors(values, level))
    return result
