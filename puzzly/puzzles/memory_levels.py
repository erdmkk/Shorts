"""Memory Challenge V8: three levels, a board that grows and a question that changes.

Level 1 is a 2x2 board (`where`: the cards flip face down and the viewer finds where a shape was). Level 2 is a 3x2 board
(`vanish`: the board stays face up and one shape disappears, so the viewer names it). Level 3 is the full 3x3 board
(`where` again, with the shortest question timer). The shapes are plain geometry (no hearts, moons, or stars), every shape
and every colour on a board is different, and the creator's colour-similarity choice (`colors_N`) still decides how close
the colours are. `puzzly/config.py: MEMORY_LEVELS` holds the tuning.
"""
from __future__ import annotations

from hashlib import sha256
import random
from typing import Any

from ..config import (MEMORY_LEVELS, MEMORY_LEVEL_TIERS, PUZZLE_FIT_OUTRO_DURATION, READY_INTRO_DURATION, memory_average_round)
from ..memory_colors import (COLOR_LEVEL_THEMES, DEFAULT_GRID_COLOR_LEVEL, GRID_COLORS, GRID_COLOR_RULES, GRID_MIN_LIGHTNESS,
                             GRID_PALETTE_IDS, grid_palette, perceptual_distance)
from ..models import RoundSpec, VideoSpec

VERSION = "memory_v8"
LAYOUT = "levels_v8"
SHAPES_V8 = ("circle", "triangle", "square", "diamond", "hexagon", "pentagon", "cross", "ring", "semicircle", "parallelogram")
KINDS = ("where", "vanish")
MEMORIZE_RANGE = (2.0, 8.0)
THINKING_RANGE = (2.0, 6.0)


def make_level(index: int, tier: int, level_data: dict, shapes: list[str], colors: list, variant: int, color_level: int,
               rng: random.Random) -> RoundSpec:
    count = level_data["rows"] * level_data["cols"]
    picked_shapes = rng.sample(shapes, count)
    picked_colors = rng.sample(colors, count)
    tokens = [{"shape": shape, "color_id": color.id, "color_value": color.value, "position": position}
              for position, (shape, color) in enumerate(zip(picked_shapes, picked_colors), start=1)]
    questions = rng.sample(range(1, count + 1), level_data["questions"])
    data = {"version": VERSION, "layout": LAYOUT, "kind": level_data["kind"], "level": index + 1, "tier": tier,
            "rows": level_data["rows"], "cols": level_data["cols"], "tokens": tokens, "questions": questions,
            "question_count": level_data["questions"], "memorize_seconds": level_data["memorize"],
            "thinking_seconds": level_data["thinking"], "palette_variant": variant, "color_level": color_level}
    return RoundSpec(index, "memory_challenge", data, {"questions": questions})


def make_hard_level(rng: random.Random, color_level: int = DEFAULT_GRID_COLOR_LEVEL) -> RoundSpec:
    """The hardest level (the full 3x3 `where` board) on its own, for the Mind Mix video."""
    excluded = rng.choice(("pentagon", "hexagon"))
    shapes = [shape for shape in SHAPES_V8 if shape != excluded]
    variant = rng.randrange(len(GRID_PALETTE_IDS[color_level]))
    return make_level(0, len(MEMORY_LEVELS) - 1, MEMORY_LEVELS[-1], shapes, list(grid_palette(color_level, variant)), variant,
                      color_level, rng)


def generate(seed: int, theme: str = "memory_tokens", round_count: int | None = None) -> VideoSpec:
    count = round_count or 3
    if count not in MEMORY_LEVEL_TIERS:
        raise ValueError("Memory Challenge has three levels")
    color_level = COLOR_LEVEL_THEMES.get(theme, DEFAULT_GRID_COLOR_LEVEL)  # colour similarity chosen in the UI
    rng = random.Random(f"memory_v8:{seed}:{color_level}")
    excluded = rng.choice(("pentagon", "hexagon"))  # too alike to share a board
    shapes = [shape for shape in SHAPES_V8 if shape != excluded]
    variant = rng.randrange(len(GRID_PALETTE_IDS[color_level]))
    colors = list(grid_palette(color_level, variant))
    rounds = tuple(make_level(index, tier, MEMORY_LEVELS[tier], shapes, colors, variant, color_level, rng)
                   for index, tier in enumerate(MEMORY_LEVEL_TIERS[count]))
    stable_id = sha256(f"memory_v8:{seed}:{color_level}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "memory_challenge", seed, "hard", "memory_tokens", rounds, READY_INTRO_DURATION,
                     memory_average_round([item.data for item in rounds]), PUZZLE_FIT_OUTRO_DURATION)


def errors(data: dict[str, Any], answer: Any, difficulty: str | None = None) -> list[str]:
    result: list[str] = []
    tokens = data.get("tokens", [])
    questions = data.get("questions", [])
    rows, cols = data.get("rows"), data.get("cols")
    if data.get("version") != VERSION or data.get("layout") != LAYOUT or data.get("kind") not in KINDS:
        return ["memory level metadata is invalid"]
    if rows not in (2, 3) or cols not in (2, 3) or len(tokens) != rows * cols:
        return ["memory level board must be 2x2, 2x3, 3x2 or 3x3 with a token on every card"]
    count = len(tokens)
    shapes = [token.get("shape") for token in tokens]
    color_ids = [token.get("color_id") for token in tokens]
    if len(set(shapes)) != count or any(shape not in SHAPES_V8 for shape in shapes):
        result.append("memory level shapes must be unique and supported")
    if {"pentagon", "hexagon"} <= set(shapes):
        result.append("pentagon and hexagon are too similar to share a board")
    if len(set(color_ids)) != count or any(color_id not in GRID_COLORS for color_id in color_ids):
        result.append("memory level colours must be unique and valid")
    if [token.get("position") for token in tokens] != list(range(1, count + 1)):
        result.append("memory token positions must be ordered 1 to n")
    if (not questions or len(set(questions)) != len(questions) or any(position not in range(1, count + 1) for position in questions)
            or data.get("question_count") != len(questions) or len(questions) > count - 1):
        result.append("memory questions must be distinct positions of the board")
    if answer != {"questions": questions}:
        result.append("memory answer data is inconsistent")
    memorize, thinking = data.get("memorize_seconds"), data.get("thinking_seconds")
    if not isinstance(memorize, (int, float)) or not MEMORIZE_RANGE[0] <= memorize <= MEMORIZE_RANGE[1] \
            or not isinstance(thinking, (int, float)) or not THINKING_RANGE[0] <= thinking <= THINKING_RANGE[1]:
        result.append("memory timing is out of range")
    level = data.get("color_level")
    if level not in GRID_PALETTE_IDS:
        result.append("memory colour similarity level is invalid")
    elif not result:
        values = [GRID_COLORS[color_id] for color_id in color_ids]
        closest = min(perceptual_distance(a, b) for index, a in enumerate(values) for b in values[index + 1:])
        if closest < GRID_COLOR_RULES[level]["min_distance"] - 1e-9 or any(color.lightness < GRID_MIN_LIGHTNESS for color in values):
            result.append("memory colours do not meet their separation or brightness rules")
    return result
