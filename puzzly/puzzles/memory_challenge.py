from __future__ import annotations

from hashlib import sha256
import random
from dataclasses import asdict, dataclass
from typing import Any

from ..config import DIFFICULTY_THEMES, MEMORY_INTRO_DURATION, MEMORY_ROUND_DURATION, OUTRO_DURATION
from ..memory_colors import COLORS, PALETTE_IDS, palette, palette_errors
from ..models import RoundSpec, VideoSpec

SHAPES = ("circle", "triangle", "square", "star", "hexagon", "heart", "diamond", "pentagon")
TOKEN_COUNT = 5
TIMED_QUESTIONS = 4


@dataclass(frozen=True)
class MemoryToken:
    shape: str
    color_id: str
    color_value: str
    position: int


def generate(seed: int, difficulty: str = "easy", theme: str = "memory_tokens", round_count: int | None = None) -> VideoSpec:
    if round_count not in (None, 1):
        raise ValueError("Memory Challenge uses one fixed board")
    difficulty = difficulty if difficulty in PALETTE_IDS else "easy"
    rng = random.Random(f"memory_challenge_v6_1:{seed}:{difficulty}")
    for _ in range(100):
        shapes = rng.sample(SHAPES, TOKEN_COUNT)
        if not ({"pentagon", "hexagon"} <= set(shapes)):
            break
    colors = list(palette(difficulty, rng.randrange(len(PALETTE_IDS[difficulty])))); rng.shuffle(colors)
    tokens = [asdict(MemoryToken(shape, color.id, color.value, position))
              for position, (shape, color) in enumerate(zip(shapes, colors), start=1)]
    question_order = list(range(1, TOKEN_COUNT + 1)); rng.shuffle(question_order)
    timed, final = question_order[:TIMED_QUESTIONS], question_order[-1]
    data = {"tokens": tokens, "question_order": timed, "final_position": final,
            "memorization_seconds": 3.0, "thinking_seconds": 3.0, "timed_question_count": TIMED_QUESTIONS}
    board = RoundSpec(0, "memory_challenge", data, {"question_order": timed, "final_position": final})
    stable_id = sha256(f"memory_challenge_v6_1:{seed}:{difficulty}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "memory_challenge", seed, difficulty, "memory_tokens", (board,),
                     MEMORY_INTRO_DURATION, MEMORY_ROUND_DURATION, OUTRO_DURATION)


def errors(data: dict[str, Any], answer: Any, difficulty: str | None = None) -> list[str]:
    result: list[str] = []; tokens = data.get("tokens", []); questions = data.get("question_order", []); final = data.get("final_position")
    shapes = [token.get("shape") for token in tokens]; color_ids = [token.get("color_id") for token in tokens]
    positions = [token.get("position") for token in tokens]
    if len(tokens) != TOKEN_COUNT or len(set(shapes)) != TOKEN_COUNT or any(shape not in SHAPES for shape in shapes):
        result.append("memory board must contain five unique supported shapes")
    if len(color_ids) != TOKEN_COUNT or len(set(color_ids)) != TOKEN_COUNT or any(color_id not in COLORS for color_id in color_ids):
        result.append("memory board must contain five unique valid colors")
    if positions != list(range(1, TOKEN_COUNT + 1)):
        result.append("memory token positions must be unique and ordered 1 to 5")
    if len(questions) != TIMED_QUESTIONS or len(set(questions)) != TIMED_QUESTIONS or any(position not in positions for position in questions):
        result.append("memory board must contain four unique timed questions")
    if final not in positions or final in questions or set(questions) | {final} != set(positions):
        result.append("memory final automatic reveal is invalid")
    if answer != {"question_order": questions, "final_position": final}:
        result.append("memory answer data is inconsistent")
    if data.get("memorization_seconds") != 3.0 or data.get("thinking_seconds") != 3.0:
        result.append("memory timing metadata is invalid")
    if difficulty and not result:
        values = [COLORS[color_id] for color_id in color_ids]
        backgrounds = [item[key] for item in DIFFICULTY_THEMES.values() for key in ("background", "background_2")]
        result.extend(palette_errors(values, difficulty, backgrounds))
    return result
