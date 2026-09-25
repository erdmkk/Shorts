from __future__ import annotations

PUZZLE_LABELS = {
    "quick_math": "Quick Math",
    "missing_number": "Missing Number",
    "puzzle_fit": "Puzzle Fit",
    "find_the_exit": "Find the Exit",
    "memory_challenge": "Memory Challenge",
    "flash_count": "Flash Count",
    "lucky_pick": "Lucky Pick",
    "hidden_motion_hunt": "Hidden Motion Hunt",
    "bounce_arena": "Bounce Arena",
    "cube_count": "Cube Count",
    "line_follow": "Line Follow",
}

ACTIVE_PUZZLE_TYPES = (
    "quick_math", "missing_number", "puzzle_fit", "find_the_exit", "memory_challenge", "flash_count", "lucky_pick",
    "hidden_motion_hunt", "bounce_arena", "cube_count",
)
MIXED_PUZZLE_TYPES = tuple(kind for kind in ACTIVE_PUZZLE_TYPES if kind not in ("hidden_motion_hunt", "bounce_arena"))
EXPERIMENTAL_PUZZLE_TYPES = ("line_follow",)
SUPPORTED_PUZZLE_TYPES = ACTIVE_PUZZLE_TYPES + EXPERIMENTAL_PUZZLE_TYPES


def active_type_labels() -> dict[str, str]:
    return {PUZZLE_LABELS[kind]: kind for kind in ACTIVE_PUZZLE_TYPES}
