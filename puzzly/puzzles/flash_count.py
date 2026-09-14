from __future__ import annotations

from hashlib import sha256
import math
import random
from typing import Any

from ..config import DEFAULT_ROUNDS, FLASH_INTRO_DURATION, FLASH_VISIBLE_DURATIONS, OUTRO_DURATION, round_duration
from ..models import RoundSpec, VideoSpec
from .memory_challenge import SHAPES

COLORS = {"yellow": "#DCA915", "blue": "#2874C6", "green": "#319457", "red": "#D9434E",
          "pink": "#D94F8A", "purple": "#7654C5", "orange": "#E86F27", "teal": "#168E91"}
COUNT_RANGE = (5, 10)
COUNT_RANGES = {difficulty: COUNT_RANGE for difficulty in ("easy", "medium", "hard")}
PLAY_FIELD = (145, 315, 935, 1335)
EDGE_GAP = 16
ALIGNMENT_TOLERANCE = 24


def token_size_for_count(count: int) -> int:
    return 176 if count <= 6 else (164 if count <= 8 else 154)


def _layout_metrics(positions: list[tuple[int, int]], min_spacing: float) -> dict[str, float | int]:
    distances = [math.dist(a, b) for index, a in enumerate(positions) for b in positions[index + 1:]]
    xs, ys = [point[0] for point in positions], [point[1] for point in positions]
    pairs = [(a, b) for index, a in enumerate(positions) for b in positions[index + 1:]]
    mid_x, mid_y = (PLAY_FIELD[0] + PLAY_FIELD[2]) / 2, (PLAY_FIELD[1] + PLAY_FIELD[3]) / 2
    return {"minimum_distance": min(distances) if distances else min_spacing,
            "width_coverage": (max(xs) - min(xs)) / (PLAY_FIELD[2] - PLAY_FIELD[0]),
            "height_coverage": (max(ys) - min(ys)) / (PLAY_FIELD[3] - PLAY_FIELD[1]),
            "row_alignments": sum(abs(a[1] - b[1]) < ALIGNMENT_TOLERANCE for a, b in pairs),
            "column_alignments": sum(abs(a[0] - b[0]) < ALIGNMENT_TOLERANCE for a, b in pairs),
            "quadrants": len({(x >= mid_x, y >= mid_y) for x, y in positions})}


def layout_errors(positions: list[list[int]] | list[tuple[int, int]], token_size: int) -> list[str]:
    result: list[str] = []
    if any(len(point) != 2 for point in positions):
        return ["flash positions must be coordinate pairs"]
    points = [tuple(point) for point in positions]
    radius = token_size / 2
    if any(not (PLAY_FIELD[0] + radius <= x <= PLAY_FIELD[2] - radius and
                PLAY_FIELD[1] + radius <= y <= PLAY_FIELD[3] - radius) for x, y in points):
        result.append("flash token is outside the safe play field")
    if any(math.dist(a, b) < token_size + EDGE_GAP for index, a in enumerate(points) for b in points[index + 1:]):
        result.append("flash tokens overlap or touch")
    if len(points) >= 3:
        metrics = _layout_metrics(points, token_size + EDGE_GAP)
        if metrics["width_coverage"] < .48 or metrics["height_coverage"] < .48:
            result.append("flash layout coverage is too small")
        if metrics["quadrants"] < (3 if len(points) < 6 else 4):
            result.append("flash layout is not balanced across the play field")
        max_alignments = max(1, len(points) // 3)
        if metrics["row_alignments"] > max_alignments or metrics["column_alignments"] > max_alignments:
            result.append("flash layout has excessive row or column alignment")
    return result


def _scatter(rng: random.Random, count: int, token_size: int) -> list[list[int]]:
    radius = token_size / 2
    x_min, x_max = math.ceil(PLAY_FIELD[0] + radius), math.floor(PLAY_FIELD[2] - radius)
    y_min, y_max = math.ceil(PLAY_FIELD[1] + radius), math.floor(PLAY_FIELD[3] - radius)
    minimum = token_size + EDGE_GAP
    for _ in range(300):
        points: list[tuple[int, int]] = []
        for _ in range(1600):
            candidate = (rng.randint(x_min, x_max), rng.randint(y_min, y_max))
            if all(math.dist(candidate, existing) >= minimum for existing in points):
                points.append(candidate)
                if len(points) == count:
                    break
        if len(points) == count and not layout_errors(points, token_size):
            return [[x, y] for x, y in points]
    raise RuntimeError("Could not produce a balanced Flash Count scatter layout")


def _counts(rng: random.Random, difficulty: str, count: int) -> list[int]:
    pool = list(range(COUNT_RANGE[0], COUNT_RANGE[1] + 1))
    values = [rng.choice(pool)]
    while len(values) < count:
        values.append(rng.choice([value for value in pool if value != values[-1]]))
    return values


def generate(seed: int, difficulty: str = "easy", theme: str = "geometric_tokens", round_count: int | None = None) -> VideoSpec:
    difficulty = difficulty if difficulty in COUNT_RANGES else "easy"
    count = round_count or DEFAULT_ROUNDS["flash_count"]
    if count not in (3, 4, 5):
        raise ValueError("Flash Count uses 3, 4, or 5 rounds")
    rng = random.Random(f"flash_count_v9:{seed}:{difficulty}")
    shape_id, color_id = rng.choice(SHAPES), rng.choice(tuple(COLORS))
    rounds, seen = [], set()
    for index, displayed_count in enumerate(_counts(rng, difficulty, count)):
        token_size = token_size_for_count(displayed_count)
        for _ in range(100):
            positions = _scatter(rng, displayed_count, token_size)
            identity = displayed_count, tuple(tuple(point) for point in positions)
            if identity not in seen:
                seen.add(identity)
                break
        data = {"shape_id": shape_id, "color_id": color_id, "color_value": COLORS[color_id],
                "displayed_count": displayed_count, "positions": positions, "token_size": token_size,
                "play_field": list(PLAY_FIELD), "visible_seconds": FLASH_VISIBLE_DURATIONS[difficulty],
                "thinking_seconds": 3.0}
        rounds.append(RoundSpec(index, "flash_count", data, displayed_count))
    stable_id = sha256(f"flash_count_v9:{seed}:{difficulty}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "flash_count", seed, difficulty, "geometric_tokens", tuple(rounds),
                     FLASH_INTRO_DURATION, round_duration("flash_count", difficulty), OUTRO_DURATION)


def errors(data: dict[str, Any], answer: Any, difficulty: str | None = None) -> list[str]:
    result: list[str] = []
    count, positions = data.get("displayed_count"), data.get("positions", [])
    shape_id, color_id, token_size = data.get("shape_id"), data.get("color_id"), data.get("token_size")
    if shape_id not in SHAPES:
        result.append("flash shape is unsupported")
    if color_id not in COLORS or data.get("color_value") != COLORS.get(color_id):
        result.append("flash color identity is invalid")
    if not isinstance(count, int) or len(positions) != count or answer != count:
        result.append("flash displayed count and answer must match")
    if not isinstance(count, int) or token_size != token_size_for_count(count):
        result.append("flash token size is invalid")
    elif isinstance(positions, list):
        result.extend(layout_errors(positions, token_size))
    if data.get("play_field") != list(PLAY_FIELD):
        result.append("flash play field is invalid")
    expected_visible = FLASH_VISIBLE_DURATIONS.get(difficulty) if difficulty else None
    if ((expected_visible is not None and data.get("visible_seconds") != expected_visible)
            or data.get("visible_seconds") not in FLASH_VISIBLE_DURATIONS.values()
            or data.get("thinking_seconds") != 3.0):
        result.append("flash timing metadata is invalid")
    return result
