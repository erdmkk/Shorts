from __future__ import annotations

from hashlib import sha256
import random

from ..models import VideoSpec
from ..visuals.layout import grid_positions

SUPPORTED_THEMES = ("fish", "apple", "star", "balloon", "flower", "shapes")


def generate(seed: int, difficulty: str = "easy", theme: str = "fish") -> VideoSpec:
    if theme not in SUPPORTED_THEMES:
        theme = "fish"
    rng = random.Random(seed)
    count = rng.randint(3, 7) if difficulty == "easy" else rng.randint(6, 10)
    positions = grid_positions(count)
    stable_id = sha256(f"counting:{seed}:{difficulty}:{theme}".encode()).hexdigest()[:12]
    return VideoSpec(
        id=f"PZ-{stable_id}", puzzle_type="counting", seed=seed,
        difficulty=difficulty, theme=theme,
        question_data={"count": count, "positions": positions},
        answer_data={"answer": count},
    )

