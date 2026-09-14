from __future__ import annotations

from hashlib import sha256
import random

from ..models import VideoSpec

SUPPORTED_THEMES = ("fish", "apple", "shapes")


def generate(seed: int, difficulty: str = "easy", theme: str = "fish") -> VideoSpec:
    if theme not in SUPPORTED_THEMES:
        theme = "fish"
    rng = random.Random(seed)
    odd_index = rng.randrange(9)
    color_variant = rng.randrange(3)
    items = [{"odd": index == odd_index, "variant": color_variant} for index in range(9)]
    stable_id = sha256(f"odd_one_out:{seed}:{difficulty}:{theme}".encode()).hexdigest()[:12]
    return VideoSpec(
        id=f"PZ-{stable_id}", puzzle_type="odd_one_out", seed=seed,
        difficulty=difficulty, theme=theme, question_data={"items": items, "object_count": 9},
        answer_data={"answer_index": odd_index}, odd_index=odd_index,
    )

