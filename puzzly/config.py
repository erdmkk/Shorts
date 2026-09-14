from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
AUDIO_DIR = ASSETS_DIR / "audio" / "generated"
BRANDING_DIR = ASSETS_DIR / "branding"
MEMORY_OBJECTS_DIR = ASSETS_DIR / "objects" / "memory"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
LOG_DIR = ROOT / "logs"
HISTORY_PATH = DATA_DIR / "history.json"
GENERATION_HISTORY_PATH = DATA_DIR / "generation_history.sqlite"
HIDDEN_MOTION_BACKGROUNDS_DIR = DATA_DIR / "hidden_motion_backgrounds"
HIDDEN_MOTION_LAYOUTS_DIR = DATA_DIR / "hidden_motion_layouts"
HIDDEN_MOTION_OBJECTS_DIR = DATA_DIR / "hidden_motion_objects"

FPS = 30
AUDIO_RATE = 48_000


@dataclass(frozen=True)
class RenderQuality:
    output_size: tuple[int, int]
    supersampling: int
    internal_visual_fps: int
    encoder_preset: str
    crf: int

    @property
    def internal_size(self) -> tuple[int, int]:
        return self.output_size[0] * self.supersampling, self.output_size[1] * self.supersampling


RENDER_QUALITIES = {
    "draft": RenderQuality((540, 960), 1, 15, "ultrafast", 28),
    "final": RenderQuality((1080, 1920), 2, 30, "medium", 17),
}
QUALITY_SIZES = {name: settings.output_size for name, settings in RENDER_QUALITIES.items()}
INTRO_DURATION = 1.3
OUTRO_DURATION = 0.9
THINKING_DURATION = 4.0
ROUND_DURATIONS = {"quick_math": 5.7, "missing_number": 5.8, "puzzle_fit": 6.0}
DEFAULT_ROUNDS = {"quick_math": 5, "missing_number": 5, "puzzle_fit": 5}
DEFAULT_ROUNDS.update({"find_the_exit": 4, "line_follow": 4})
DEFAULT_ROUNDS["memory_challenge"] = 1
DEFAULT_ROUNDS["flash_count"] = 4
DEFAULT_ROUNDS["lucky_pick"] = 1
DEFAULT_ROUNDS["hidden_motion_hunt"] = 1
PATH_TYPES = ("find_the_exit", "line_follow")
LINE_FOLLOW_FINAL_PATH_SCALE = 4
MEMORY_INTRO_DURATION = 1.5
MEMORY_BOARD_ENTRANCE = 0.3
MEMORY_MEMORIZATION_DURATION = 3.0
MEMORY_COVER_DURATION = 0.5
MEMORY_TARGET_ENTRANCE = 0.25
MEMORY_THINKING_DURATION = 3.0
MEMORY_ANSWER_HIGHLIGHT = 0.25
MEMORY_ANSWER_FLIP = 0.45
MEMORY_ANSWER_HOLD = 0.20
MEMORY_QUESTION_DURATION = MEMORY_TARGET_ENTRANCE + MEMORY_THINKING_DURATION + MEMORY_ANSWER_HIGHLIGHT + MEMORY_ANSWER_FLIP + MEMORY_ANSWER_HOLD
MEMORY_FINAL_DELAY = 0.4
MEMORY_FINAL_FLIP = 0.55
MEMORY_COMPLETED_HOLD = 1.25
MEMORY_ROUND_DURATION = (MEMORY_BOARD_ENTRANCE + MEMORY_MEMORIZATION_DURATION + MEMORY_COVER_DURATION
                         + 4 * MEMORY_QUESTION_DURATION + MEMORY_FINAL_DELAY + MEMORY_FINAL_FLIP + MEMORY_COMPLETED_HOLD)
FLASH_INTRO_DURATION = 1.5
FLASH_APPEARANCE_DURATION = 0.2
FLASH_VISIBLE_DURATIONS = {"easy": 1.20, "medium": 0.90, "hard": 0.65}
FLASH_HIDE_DURATION = 0.25
FLASH_THINKING_DURATION = 3.0
FLASH_REVEAL_DURATION = 0.25
FLASH_SOLVED_HOLD = 1.0
LUCKY_INTRO_DURATION = 1.25
LUCKY_APPEARANCE_DURATION = 0.25
LUCKY_SELECTION_DURATION = 5.0
LUCKY_WINNER_HOLD = 1.70
LUCKY_ROUND_DURATION = 21.1
HIDDEN_MOTION_DURATION = 18.0
HIDDEN_MOTION_OBJECT_COUNT = 7
HIDDEN_MOTION_TIER_COUNTS = {"easy": 2, "medium": 2, "hard": 3}
HIDDEN_MOTION_DIAMETER_RANGES = {"easy": (50, 60), "medium": (34, 44), "hard": (20, 28)}
HIDDEN_MOTION_SAFE_BOUNDS = (100, 110, 980, 1810)
HIDDEN_MOTION_MIN_GAP = 44
HIDDEN_MOTION_MANUAL_SIZE_RANGE = (1, 120)
HIDDEN_MOTION_JUMP_RANGE = (2, 40)
HIDDEN_MOTION_SPEED_RANGE = (0.25, 3.0)
HIDDEN_MOTION_MAX_OBJECTS = 20


def flash_round_duration(difficulty: str) -> float:
    visible = FLASH_VISIBLE_DURATIONS.get(difficulty, FLASH_VISIBLE_DURATIONS["easy"])
    return (FLASH_APPEARANCE_DURATION + visible + FLASH_HIDE_DURATION + FLASH_THINKING_DURATION
            + FLASH_REVEAL_DURATION + FLASH_SOLVED_HOLD)


def thinking_duration(puzzle_type: str, difficulty: str | None) -> float:
    if puzzle_type == "lucky_pick":
        return LUCKY_SELECTION_DURATION
    if puzzle_type == "flash_count":
        return FLASH_THINKING_DURATION
    if puzzle_type == "memory_challenge":
        return MEMORY_THINKING_DURATION
    if puzzle_type == "puzzle_fit" and difficulty == "hard":
        return THINKING_DURATION + 1.0
    return {"easy": 5.0, "medium": 6.0, "hard": 7.0}[difficulty] if puzzle_type in PATH_TYPES else THINKING_DURATION


def round_duration(puzzle_type: str, difficulty: str | None) -> float:
    if puzzle_type == "hidden_motion_hunt":
        return HIDDEN_MOTION_DURATION
    if puzzle_type == "lucky_pick":
        return LUCKY_ROUND_DURATION
    if puzzle_type == "flash_count":
        return flash_round_duration(difficulty)
    if puzzle_type == "memory_challenge":
        return MEMORY_ROUND_DURATION
    if puzzle_type in PATH_TYPES:
        return thinking_duration(puzzle_type, difficulty) + 2.3
    if puzzle_type == "puzzle_fit" and difficulty == "hard":
        return ROUND_DURATIONS[puzzle_type] + 1.0
    return ROUND_DURATIONS[puzzle_type]

PALETTES = (
    {"background": "#DFF7F2", "background_2": "#CDEDEA", "surface": "#FFFDF7", "primary": "#13A89E", "secondary": "#4D8FE8", "accent": "#FFC84A", "success": "#55C985", "coral": "#FF7B6B", "lavender": "#A58BE8", "outline": "#244653", "text_dark": "#183943", "text_light": "#FFFFFF"},
    {"background": "#FFF1DE", "background_2": "#FDE2D3", "surface": "#FFFDFC", "primary": "#3D8DDB", "secondary": "#11A69A", "accent": "#FFD05A", "success": "#5FC77B", "coral": "#F4776A", "lavender": "#9C8ADE", "outline": "#304657", "text_dark": "#263D4A", "text_light": "#FFFFFF"},
    {"background": "#ECE9FF", "background_2": "#DDE8FF", "surface": "#FFFDFC", "primary": "#7266D8", "secondary": "#35A6C8", "accent": "#FFD166", "success": "#58C995", "coral": "#FF7C77", "lavender": "#A58BE8", "outline": "#34415A", "text_dark": "#29364D", "text_light": "#FFFFFF"},
)

DIFFICULTY_THEMES = {
    "easy": {"background": "#E7F8EF", "background_2": "#D8F1E4", "background_accent": "#91D5B8", "background_accent_2": "#B6E3CF"},
    "medium": {"background": "#E8F3FF", "background_2": "#D9EAFB", "background_accent": "#91BFE8", "background_accent_2": "#B5D5F2"},
    "hard": {"background": "#F9EAF2", "background_2": "#F0DDEC", "background_accent": "#D7A6C5", "background_accent_2": "#E2BBD2"},
}

LUCKY_PALETTE = {"background": "#F3F4FF", "background_2": "#E8F7F5", "surface": "#FFFDFC",
                 "primary": "#4B8FD8", "secondary": "#35A6C8", "accent": "#FFD166",
                 "success": "#58C995", "coral": "#FF7C77", "lavender": "#A58BE8",
                 "outline": "#304657", "text_dark": "#263D4A", "text_light": "#FFFFFF",
                 "background_accent": "#B8B4E8", "background_accent_2": "#A7DCD4"}


def palette_for(difficulty: str, variant: int = 0) -> dict[str, str]:
    palette = dict(PALETTES[variant % len(PALETTES)])
    palette.update(DIFFICULTY_THEMES.get(difficulty, DIFFICULTY_THEMES["easy"]))
    return palette


def ensure_directories() -> None:
    for path in (AUDIO_DIR, BRANDING_DIR, DATA_DIR, HIDDEN_MOTION_BACKGROUNDS_DIR,
                 HIDDEN_MOTION_LAYOUTS_DIR, HIDDEN_MOTION_OBJECTS_DIR, OUTPUT_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
