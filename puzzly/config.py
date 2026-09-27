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
ROUND_DURATIONS = {"quick_math": 5.7, "missing_number": 5.8, "puzzle_fit": 6.2}
DEFAULT_ROUNDS = {"quick_math": 3, "missing_number": 5, "puzzle_fit": 5}
DEFAULT_ROUNDS.update({"find_the_exit": 4, "line_follow": 5})  # Line Follow: level 1 to 5, each one harder
DEFAULT_ROUNDS["memory_challenge"] = 1
DEFAULT_ROUNDS["flash_count"] = 4
DEFAULT_ROUNDS["lucky_pick"] = 1
DEFAULT_ROUNDS["hidden_motion_hunt"] = 1
DEFAULT_ROUNDS["bounce_arena"] = 1
DEFAULT_ROUNDS["cube_count"] = 4
PATH_TYPES = ("find_the_exit", "line_follow")
# Quick Math, Shape Equations format (Puzzly for You look): rows enter, think, reveal each shape's value, then the answer.
QUICK_MATH_ENTRANCE = 0.5
# Thinking time grows with the level tier (0-3) and never exceeds 15 s; a pause hint covers anyone who needs longer.
QUICK_MATH_THINKING = {"easy": (10.0, 12.0, 15.0, 15.0), "medium": (9.0, 11.0, 14.0, 15.0), "hard": (8.0, 10.0, 13.0, 15.0)}
QUICK_MATH_TIERS = 4
QUICK_MATH_HINT_AT = 0.5  # trap levels reveal one clue halfway through the thinking time
QUICK_MATH_PAUSE_HINT = 5.0  # the pause hint appears this many seconds before the time runs out
QUICK_MATH_SOLVE = 1.05
QUICK_MATH_ANSWER = 0.45
QUICK_MATH_HOLD = 1.0
# Puzzle Fit (adult "Puzzly for You" pilot): hook intro, elimination reveal, and score-question outro.
PUZZLE_FIT_INTRO_DURATION = 1.0
PUZZLE_FIT_OUTRO_DURATION = 1.6
PUZZLE_FIT_ENTRANCE = 0.35
PUZZLE_FIT_ELIMINATION = 0.55
PUZZLE_FIT_MOVE = 0.45
PUZZLE_FIT_THINKING = 5.0  # seconds to find the fitting piece, every difficulty
PUZZLE_FIT_ROUND_EXTRA = 2.2  # entrance, elimination, fly-in, snap, and solved hold
# Find the Exit Hard (Puzzly for You look): larger deceptive mazes, glowing route trace, shared hook/outro timing.
# Line Follow (Puzzly for You look): level 1..5 thinking times; entrance, glowing trace, and solved hold.
LINE_THINKING = (7.0, 9.0, 11.0, 13.0, 15.0)
LINE_ENTRANCE, LINE_TRACE, LINE_HOLD = 0.35, 2.4, 0.9


def line_round(thinking: float) -> float:
    return round(LINE_ENTRANCE + thinking + LINE_TRACE + LINE_HOLD, 3)


def line_average_round(count: int) -> float:
    tiers = [0, 2, 4] if count <= 3 else [min(index, 4) for index in range(count)]
    return round(sum(line_round(LINE_THINKING[tier]) for tier in tiers) / max(1, count), 4)


EXIT_HARD_THINKING = 8.0  # older videos (no per-level time stored) think this long on every level
EXIT_HARD_LEVEL_THINKING = (5.0, 6.0, 7.0, 8.0, 9.0)  # level 1..5: bigger mazes get more time
EXIT_HARD_ENTRANCE = 0.35
EXIT_HARD_TRACE = 1.6
EXIT_HARD_HOLD = 0.9


def exit_hard_round(thinking: float) -> float:
    return round(EXIT_HARD_ENTRANCE + thinking + EXIT_HARD_TRACE + EXIT_HARD_HOLD, 3)


def exit_hard_average_round(count: int) -> float:
    """Levels last different times; VideoSpec keeps their average so the total duration stays exact."""
    thinking = [EXIT_HARD_LEVEL_THINKING[min(index, len(EXIT_HARD_LEVEL_THINKING) - 1)] for index in range(count)]
    return round(sum(exit_hard_round(value) for value in thinking) / max(1, count), 4)
# Cube Count (Puzzly for You look): cubes drop in, flash, vanish, then are counted stack by stack.
CUBE_BUILD = 0.6
CUBE_VISIBLE = {"easy": 2.5, "medium": 2.0, "hard": 0.3}
CUBE_HIDE = 0.3
CUBE_THINKING = 3.0
CUBE_RETURN = 0.4
CUBE_COUNT_UP = 1.3
CUBE_HOLD = 0.9
# Every new video uses sky blue; the other ids stay valid so earlier manifests can still be re-rendered.
CUBE_COLORS = {"violet": "#6E7BFF", "teal": "#1FC8B0", "coral": "#FF6B6B", "amber": "#FFB547", "sky": "#3FA7FF",
               "green": "#3DD68C", "yellow": "#FFD23F", "pink": "#FF6FB5"}
CUBE_COLOR_ID = "sky"  # older single-colour videos; new videos pick a colour per round from CUBE_ROUND_COLORS
CUBE_ROUND_COLORS = ("sky", "green", "yellow", "coral", "violet", "amber", "pink", "teal")
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
# Memory Challenge 3x3 grid (Puzzly for You look): nine tokens, eight timed questions, ninth auto-revealed.
MEMORY_GRID_TOKENS = 9
MEMORY_GRID_QUESTIONS = 8
MEMORY_MEMORIZE = {"easy": 8.0, "medium": 7.0, "hard": 7.0}
MEMORY_GRID_COVER = 0.6


def memory_round_duration(difficulty: str | None) -> float:
    memorize = MEMORY_MEMORIZE.get(difficulty or "easy", MEMORY_MEMORIZE["easy"])
    return round(MEMORY_BOARD_ENTRANCE + memorize + MEMORY_GRID_COVER + MEMORY_GRID_QUESTIONS * MEMORY_QUESTION_DURATION
                 + MEMORY_FINAL_DELAY + MEMORY_FINAL_FLIP + MEMORY_COMPLETED_HOLD, 3)
# Flash Count, number flash (Puzzly for You look): a 2 s ARE YOU READY? screen opens the video; each level is get
# ready, the number flashes, think, then the digits drop into their slots one by one. Every phase is a whole number of
# 30 fps frames. Produced only in Hard.
FLASH_INTRO = 2.0
FLASH_READY = 0.9
FLASH_VISIBLE = {4: 0.2, 5: 0.2, 6: 0.3}  # seconds the number is on screen, by its digit count
FLASH_THINKING = 3.0
FLASH_REVEAL = 1.0
FLASH_HOLD = 0.9
FLASH_DIGITS = (4, 5, 6)  # digits on the opening, middle, and final level tier
LUCKY_INTRO_DURATION = 1.25
LUCKY_APPEARANCE_DURATION = 0.25
LUCKY_SELECTION_DURATION = 5.0
LUCKY_WINNER_HOLD = 1.70
LUCKY_ROUND_DURATION = 21.9  # typical neon-maze timeline; the real one is per video
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
BOUNCE_SELECTION_DURATION = 5.0
BOUNCE_WINNER_HOLD = 1.5
BOUNCE_CTA_DURATION = 1.7


def flash_round_duration(difficulty: str | None) -> float:
    """Every level lasts the same; a shorter flash leaves a slightly longer solved hold."""
    return round(FLASH_READY + max(FLASH_VISIBLE.values()) + FLASH_THINKING + FLASH_REVEAL + FLASH_HOLD, 3)


def quick_math_thinking(difficulty: str | None, tier: int) -> float:
    return QUICK_MATH_THINKING.get(difficulty or "hard", QUICK_MATH_THINKING["hard"])[tier]


def quick_math_tiers(count: int) -> list[int]:
    """Level tiers for a video: always starts at tier 0 and ends at the hardest tier."""
    last = QUICK_MATH_TIERS - 1
    return [0 if count <= 1 else round(index * last / (count - 1)) for index in range(count)]


def quick_math_round(difficulty: str | None, tier: int) -> float:
    return round(QUICK_MATH_ENTRANCE + quick_math_thinking(difficulty, tier) + QUICK_MATH_SOLVE
                 + QUICK_MATH_ANSWER + QUICK_MATH_HOLD, 3)


def quick_math_average_round(difficulty: str | None, tiers: list[int]) -> float:
    """Levels last different times; VideoSpec keeps their average so the total duration stays exact."""
    return round(sum(quick_math_round(difficulty, tier) for tier in tiers) / len(tiers), 4)


def thinking_duration(puzzle_type: str, difficulty: str | None) -> float:
    if puzzle_type == "lucky_pick":
        return LUCKY_SELECTION_DURATION
    if puzzle_type == "flash_count":
        return FLASH_THINKING
    if puzzle_type == "memory_challenge":
        return MEMORY_THINKING_DURATION
    if puzzle_type == "puzzle_fit":
        return PUZZLE_FIT_THINKING
    if puzzle_type == "find_the_exit" and difficulty == "hard":
        return EXIT_HARD_THINKING
    if puzzle_type == "cube_count":
        return CUBE_THINKING
    if puzzle_type == "quick_math":  # level 1; later levels get longer (quick_math_thinking)
        return quick_math_thinking(difficulty, 0)
    if puzzle_type == "line_follow":  # level 1; later levels get longer (LINE_THINKING)
        return LINE_THINKING[0]
    return {"easy": 5.0, "medium": 6.0, "hard": 7.0}[difficulty] if puzzle_type in PATH_TYPES else THINKING_DURATION


def round_duration(puzzle_type: str, difficulty: str | None) -> float:
    if puzzle_type == "hidden_motion_hunt":
        return HIDDEN_MOTION_DURATION
    if puzzle_type == "lucky_pick":
        return LUCKY_ROUND_DURATION
    if puzzle_type == "flash_count":
        return flash_round_duration(difficulty)
    if puzzle_type == "memory_challenge":
        return memory_round_duration(difficulty)
    if puzzle_type == "find_the_exit" and difficulty == "hard":  # the average level of a default-length video
        return exit_hard_average_round(DEFAULT_ROUNDS["find_the_exit"])
    if puzzle_type == "cube_count":
        return round(CUBE_BUILD + CUBE_VISIBLE.get(difficulty or "easy", CUBE_VISIBLE["easy"]) + CUBE_HIDE + CUBE_THINKING
                     + CUBE_RETURN + CUBE_COUNT_UP + CUBE_HOLD, 3)
    if puzzle_type == "line_follow":  # the average level of a default-length video
        return line_average_round(DEFAULT_ROUNDS["line_follow"])
    if puzzle_type in PATH_TYPES:
        return thinking_duration(puzzle_type, difficulty) + 2.3
    if puzzle_type == "quick_math":  # the average level of a default-length video
        return quick_math_average_round(difficulty, quick_math_tiers(DEFAULT_ROUNDS["quick_math"]))
    if puzzle_type == "puzzle_fit":
        return round(PUZZLE_FIT_THINKING + PUZZLE_FIT_ROUND_EXTRA, 3)
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

# Dark background tones for the Puzzly for You games: one is picked per video (see visuals.puzzle_fit.background_theme).
DARK_THEMES = {
    "violet": ("#0B1020", "#161C36", "#5B3FD9"),
    "ocean": ("#07111F", "#0C2036", "#1D63D8"),
    "teal": ("#041416", "#08292B", "#0E8C86"),
    "crimson": ("#13070C", "#27101A", "#B02A55"),
    "emerald": ("#04130B", "#0A2616", "#1E9E5A"),
    "ember": ("#130B06", "#2A160A", "#C2601C"),
    "plum": ("#10061A", "#22103A", "#9B2FC2"),
}
# Cube colours that would blend into a background tone.
THEME_CLASHING_CUBES = {"violet": ("violet",), "ocean": ("sky", "violet"), "teal": ("teal", "green"),
                        "crimson": ("coral", "pink"), "emerald": ("green", "teal"), "ember": ("amber", "yellow", "coral"),
                        "plum": ("violet", "pink")}


def dark_theme_for(puzzle_type: str, seed: int) -> str:
    """The dark background tone of a video: random per video, fixed for all of its frames and its cover."""
    import random
    return random.Random(f"background_theme:{puzzle_type}:{seed}").choice(sorted(DARK_THEMES))


PUZZLE_FIT_PALETTE = {
    "background": "#0B1020", "background_2": "#161C36", "glow": "#5B3FD9",
    "surface": "#171E3B", "surface_edge": "#2E3866", "hole": "#0A0E1F",
    "outline": "#060913", "primary": "#7C5CFF", "accent": "#2EE6C5",
    "warning": "#FFC24B", "danger": "#FF4D6D", "success": "#3DF08F",
    "text_light": "#FFFFFF", "text_muted": "#9AA3C7",
}
# Vivid artwork palettes that are cut into jigsaw pieces; every one stays readable on the dark theme.
PUZZLE_FIT_ART_PALETTES = (
    ("#FF5F6D", "#FFC371", "#7C5CFF", "#2EE6C5"),
    ("#00C6FF", "#0072FF", "#F7797D", "#FBD786"),
    ("#F857A6", "#FF5858", "#FFC24B", "#3DF08F"),
    ("#7F7FD5", "#86A8E7", "#91EAE4", "#FF7EB3"),
    ("#11998E", "#38EF7D", "#FFE259", "#FF6A88"),
    ("#FC466B", "#3F5EFB", "#FDBB2D", "#22C1C3"),
)

LUCKY_PALETTE = {"background": "#F3F4FF", "background_2": "#E8F7F5", "surface": "#FFFDFC",
                 "primary": "#4B8FD8", "secondary": "#35A6C8", "accent": "#FFD166",
                 "success": "#58C995", "coral": "#FF7C77", "lavender": "#A58BE8",
                 "outline": "#304657", "text_dark": "#263D4A", "text_light": "#FFFFFF",
                 "background_accent": "#B8B4E8", "background_accent_2": "#A7DCD4"}


def palette_for(difficulty: str, variant: int = 0) -> dict[str, str]:
    palette = dict(PALETTES[variant % len(PALETTES)])
    palette.update(DIFFICULTY_THEMES.get(difficulty, DIFFICULTY_THEMES["easy"]))
    return palette


def intro_outro(puzzle_type: str, difficulty: str | None) -> tuple[float, float]:
    """Intro/outro for round-based games; the Puzzly for You look uses the hook intro and score-question outro."""
    if puzzle_type == "flash_count":
        return FLASH_INTRO, PUZZLE_FIT_OUTRO_DURATION
    if puzzle_type in ("puzzle_fit", "cube_count", "memory_challenge", "lucky_pick", "quick_math", "line_follow") or (
            puzzle_type == "find_the_exit" and difficulty == "hard"):
        return PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION
    return INTRO_DURATION, OUTRO_DURATION


def ensure_directories() -> None:
    for path in (AUDIO_DIR, BRANDING_DIR, DATA_DIR, HIDDEN_MOTION_BACKGROUNDS_DIR,
                 HIDDEN_MOTION_LAYOUTS_DIR, HIDDEN_MOTION_OBJECTS_DIR, OUTPUT_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
