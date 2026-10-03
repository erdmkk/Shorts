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
DEFAULT_ROUNDS = {"quick_math": 3, "missing_number": 5, "puzzle_fit": 1}  # Puzzle Fit V12: one big picture
DEFAULT_ROUNDS.update({"find_the_exit": 4, "line_follow": 5})  # Line Follow: level 1 to 5, each one harder
DEFAULT_ROUNDS["memory_challenge"] = 1
DEFAULT_ROUNDS["flash_count"] = 4
DEFAULT_ROUNDS["lucky_pick"] = 1
DEFAULT_ROUNDS["hidden_motion_hunt"] = 1
DEFAULT_ROUNDS["bounce_arena"] = 1
DEFAULT_ROUNDS["cube_count"] = 4
DEFAULT_ROUNDS["chess_mate"] = 1
DEFAULT_ROUNDS["matchstick"] = 3
DEFAULT_ROUNDS["cup_shuffle"] = 3
DEFAULT_ROUNDS["shade_spot"] = 4
DEFAULT_ROUNDS["mind_mix"] = 3
DEFAULT_ROUNDS["laser_maze"] = 4
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
# Games that show something for a moment (a flash, a memorize window, a ball under a cup) get a READY screen after the hook:
# `You will count the cubes.` `ARE YOU READY?` and a 3-2-1 countdown, so the viewer never misses the start.
READY_SECONDS = 3.0
READY_GAMES = ("cube_count", "cup_shuffle", "memory_challenge", "flash_count", "shade_spot")
READY_INTRO_DURATION = PUZZLE_FIT_INTRO_DURATION + READY_SECONDS
PUZZLE_FIT_OUTRO_DURATION = 3.6  # the shared end card: 2 s longer than before (it was 1.6 s) so viewers can read it and follow
# The accounts shown on the end card (icon + handle rows). Change the handles here.
SOCIAL_HANDLES = (("youtube", "@puzzlyforyou"), ("instagram", "@puzzlyforyou"))
PUZZLE_FIT_ENTRANCE = 0.35
PUZZLE_FIT_ELIMINATION = 0.55
PUZZLE_FIT_MOVE = 0.45
PUZZLE_FIT_THINKING = 5.0  # seconds to find the fitting piece, every difficulty
PUZZLE_FIT_ROUND_EXTRA = 2.2  # entrance, elimination, fly-in, snap, and solved hold
# Find the Exit Hard (Puzzly for You look): larger deceptive mazes, glowing route trace, shared hook/outro timing.
# Line Follow (Puzzly for You look): level 1..5 thinking times; entrance, glowing trace, and solved hold.
LINE_THINKING = (5.0, 6.0, 7.0, 8.0, 10.0)  # Weave V8
LINE_THINKING_V7 = (7.0, 9.0, 11.0, 13.0, 15.0)  # older weave_v7 and tangle_v4 records keep their own times
LINE_ENTRANCE, LINE_TRACE, LINE_HOLD = 0.35, 2.4, 0.9
# Shade Spot (the user's idea: two grids of nearly the same colours, find the one tile that changed). Produced only in Hard.
# DIFFICULTY IS TUNED HERE: per tier the grid size, `delta` (how far the odd tile's colour is from its original, in OKLab; about
# 0.02 is the least an eye notices side by side) and the thinking time. A made video stores its own, so retuning never changes it.
SHADE_LEVELS = (
    {"grid": 3, "delta": 0.11, "thinking": 5.0},
    {"grid": 4, "delta": 0.08, "thinking": 6.0},
    {"grid": 4, "delta": 0.055, "thinking": 8.0},
    {"grid": 5, "delta": 0.04, "thinking": 10.0},
)
SHADE_TIERS = {3: (0, 2, 3), 4: (0, 1, 2, 3), 5: (0, 1, 2, 2, 3)}  # level tiers by the number of levels of a video
SHADE_DELTA_TOLERANCE = 0.12  # the odd tile's measured difference may be this share off its level's delta (8-bit rounding)
SHADE_ENTRANCE = 0.5
SHADE_REVEAL = 2.0  # the other tiles dim, the two odd tiles pop and the answer shows
SHADE_HOLD = 0.8


def shade_round(data: dict) -> float:
    """One level's length from its stored thinking time."""
    return round(SHADE_ENTRANCE + float(data["thinking_seconds"]) + SHADE_REVEAL + SHADE_HOLD, 3)


def shade_average_round(datas: list[dict]) -> float:
    """Levels last different times; VideoSpec keeps their average so the total duration stays exact."""
    return round(sum(shade_round(data) for data in datas) / len(datas), 4)


def line_round(thinking: float) -> float:
    return round(LINE_ENTRANCE + thinking + LINE_TRACE + LINE_HOLD, 3)


def line_average_round(count: int) -> float:
    tiers = [0, 2, 4] if count <= 3 else [min(index, 4) for index in range(count)]
    return round(sum(line_round(LINE_THINKING[tier]) for tier in tiers) / max(1, count), 4)


EXIT_HARD_THINKING = 8.0  # older videos (no per-level time stored) think this long on every level
EXIT_HARD_LEVEL_THINKING = (6.0, 7.0, 8.0, 9.0, 10.0)  # level 1..5 (10x12 .. 16x20): bigger mazes get more time
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
# Cube Count formats (the user's idea: every level counts differently). A video mixes the classic flash (`grid`), cubes that
# rain down and vanish as they land (`rain`), a train of towers that sweeps across the screen (`sweep`), and a rain of several
# colours where only one colour counts (`rain_color`). SPEED IS TUNED HERE (the user retunes it after watching): a made video
# stores its own fall and sweep times, so retuning never changes existing videos.
CUBE_MODES = {3: ("grid", "sweep", "rain_color"), 4: ("grid", "rain", "sweep", "rain_color"),
              5: ("grid", "rain", "sweep", "grid", "rain_color")}
CUBE_RAIN = {"easy": {"interval": 0.42, "fall": 0.55}, "medium": {"interval": 0.32, "fall": 0.50},
             "hard": {"interval": 0.24, "fall": 0.45}}  # seconds between landings (about) and one cube's fall
CUBE_RAIN_MIN_GAP = 0.15  # no two cubes land closer than this (about four frames), so every one can be counted
CUBE_SWEEP = {"easy": 5.0, "medium": 3.8, "hard": 2.8}  # seconds for the train of towers to cross the screen
CUBE_LEAD = 0.6  # a rain or sweep level opens on the empty board
CUBE_TARGET_INTRO = 2.0  # a colour rain first shows the counted colour for this long: its cube zooms in and out
CUBE_TARGET_RANGE = (0.0, 4.0)  # accepted stored intro times


def cube_lead(data: dict) -> float:
    """Seconds before the first cube of a rain or sweep level appears (a colour rain adds its counted-colour intro)."""
    return CUBE_LEAD + float(data.get("intro_seconds", 0.0))
CUBE_REPLAY_SPEED = 2.0  # the answer replays the rain this many times faster, numbering every cube
CUBE_RAIN_SOUND = {"easy": True, "medium": True, "hard": False}  # a soft tick as each cube lands (off in Hard: it would count for you)
CUBE_FALL_RANGE = (0.2, 1.2)  # accepted stored fall times
CUBE_SWEEP_RANGE = (1.5, 8.0)  # accepted stored sweep times


def cube_mode(data: dict) -> str:
    return data.get("mode", "grid")


def cube_round(data: dict) -> float:
    """One level's length from its own stored timing, so retuning the speeds never changes a made video."""
    mode = cube_mode(data)
    tail = CUBE_HIDE + CUBE_THINKING + CUBE_RETURN
    if mode in ("rain", "rain_color"):
        rain = float(data["rain_seconds"])
        return round(cube_lead(data) + rain + tail + rain / CUBE_REPLAY_SPEED + 0.3 + CUBE_HOLD, 3)
    if mode == "sweep":
        return round(CUBE_LEAD + float(data["sweep_seconds"]) + tail + CUBE_COUNT_UP + CUBE_HOLD, 3)
    return round(CUBE_BUILD + float(data["visible_seconds"]) + tail + CUBE_COUNT_UP + CUBE_HOLD, 3)


def cube_default_video(difficulty: str | None) -> float:
    """A default four-level video's levels (an estimate for the UI, from typical cube counts), in seconds."""
    rain = CUBE_RAIN.get(difficulty or "hard", CUBE_RAIN["hard"])
    typical = {"rain": 13, "rain_color": 16}
    total = 0.0
    for mode in CUBE_MODES[DEFAULT_ROUNDS["cube_count"]]:
        if mode in typical:
            data = {"mode": mode, "rain_seconds": (typical[mode] - 1) * rain["interval"] + rain["fall"]}
        elif mode == "sweep":
            data = {"mode": mode, "sweep_seconds": CUBE_SWEEP.get(difficulty or "hard", CUBE_SWEEP["hard"])}
        else:
            data = {"mode": "grid", "visible_seconds": CUBE_VISIBLE.get(difficulty or "hard", CUBE_VISIBLE["hard"])}
        total += cube_round(data)
    return round(total, 3)


def cube_average_round(datas: list[dict]) -> float:
    """Levels last different times; VideoSpec keeps their average so the total duration stays exact."""
    return round(sum(cube_round(data) for data in datas) / len(datas), 4)
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
# Memory Challenge V8 (the user's request: Memory felt lifeless and static, so it became three levels): a board that grows
# (2x2 -> 3x2 -> 3x3), and a question that changes. `where`: the cards flip face down and the viewer finds where a shape was.
# `vanish`: the board stays face up and one shape disappears, so the viewer names it. TUNE THE LEVELS HERE; a made video
# stores its own `memorize_seconds`, `thinking_seconds` and question count, so retuning never changes it.
MEMORY_LEVELS = (
    {"rows": 2, "cols": 2, "kind": "where", "memorize": 3.0, "thinking": 2.5, "questions": 2},
    {"rows": 2, "cols": 3, "kind": "vanish", "memorize": 4.0, "thinking": 3.5, "questions": 2},
    {"rows": 3, "cols": 3, "kind": "where", "memorize": 5.0, "thinking": 3.0, "questions": 3},
)
MEMORY_LEVEL_TIERS = {3: (0, 1, 2)}
MEMORY_V8_ENTRANCE = 0.4
MEMORY_V8_COVER = 0.6  # `where`: the cards flip face down
MEMORY_V8_WHERE_EXTRA = 1.2  # per `where` question besides thinking: 0.25 entrance, 0.25 highlight, 0.45 flip, 0.25 hold
MEMORY_V8_VANISH = (0.45, 0.9, 0.3)  # per `vanish` question besides thinking: the card vanishes, it returns, a short hold
MEMORY_V8_FINALE = {"where": 1.3, "vanish": 0.9}  # the last cards flip open (where), then a held, glowing full board


def memory_question_length(data: dict) -> float:
    if data["kind"] == "where":
        return float(data["thinking_seconds"]) + MEMORY_V8_WHERE_EXTRA
    return float(data["thinking_seconds"]) + sum(MEMORY_V8_VANISH)


def memory_level_round(data: dict) -> float:
    """One level's length from its stored timing, so retuning MEMORY_LEVELS never changes a made video."""
    start = MEMORY_V8_ENTRANCE + float(data["memorize_seconds"]) + (MEMORY_V8_COVER if data["kind"] == "where" else 0.0)
    return round(start + data["question_count"] * memory_question_length(data) + MEMORY_V8_FINALE[data["kind"]], 3)


def memory_average_round(datas: list[dict]) -> float:
    """Levels last different times; VideoSpec keeps their average so the total duration stays exact."""
    return round(sum(memory_level_round(data) for data in datas) / len(datas), 4)


def memory_levels_total() -> float:
    """All three levels of a default video (the levels' lengths do not depend on the seed)."""
    return round(sum(memory_level_round({"kind": level["kind"], "memorize_seconds": level["memorize"],
                                         "thinking_seconds": level["thinking"], "question_count": level["questions"]})
                     for level in MEMORY_LEVELS), 3)


# Flash Count, number flash (Puzzly for You look): a 2 s ARE YOU READY? screen opens the video; each level is get
# ready, the number flashes, think, then the digits drop into their slots one by one. Every phase is a whole number of
# 30 fps frames. Produced only in Hard.
FLASH_INTRO = 4.0  # 1.0 s hook + the 3.0 s READY screen (it was a 2.0 s ARE YOU READY? screen)
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
# Puzzle Fit V12: one big picture with three missing pieces and six tilted options.
FIT_THINKING = {"easy": 28.0, "medium": 24.0, "hard": 20.0}
FIT_ENTRANCE = 0.5
FIT_CLEAR = 0.4  # the traps dim
FIT_PLACE = 0.9  # each missing piece flies in, straightens and clicks (A, then B, then C)
FIT_SHINE = 0.7  # the finished picture shines
FIT_HOLD = 1.6


def fit_round(difficulty: str | None) -> float:
    thinking = FIT_THINKING.get(difficulty or "hard", FIT_THINKING["hard"])
    return round(FIT_ENTRANCE + thinking + FIT_CLEAR + 3 * FIT_PLACE + FIT_SHINE + FIT_HOLD, 3)


# Cup Shuffle: follow the ball under the cup. Three levels with 3, 4 and 5 cups. TUNE THE SPEED HERE: `swaps` is how many
# times two cups trade places and `swap_seconds` how long one swap takes (smaller = faster). Every video stores the values
# it was made with, so retuning never changes videos that already exist.
CUP_LEVELS = (
    {"cups": 3, "swaps": 6, "swap_seconds": 0.45, "thinking": 4.0},
    {"cups": 4, "swaps": 9, "swap_seconds": 0.32, "thinking": 4.0},
    {"cups": 5, "swaps": 12, "swap_seconds": 0.3, "thinking": 4.0},
)
CUP_SWAP_SECONDS_RANGE = (0.15, 1.5)  # accepted by validation
CUP_ENTRANCE = 0.5  # the cups drop in
CUP_LIFT = 0.45  # the ball's cup lifts to show it ...
CUP_SHOW = 1.1  # ... stays up ...
CUP_LOWER = 0.45  # ... and comes back down
CUP_REVEAL = 0.55  # the answer cup lifts
CUP_ANSWER = 0.5  # burst and green cup
CUP_HOLD = 1.0


def cup_round(data: dict) -> float:
    """Length of one level, from the speed stored in its own data."""
    shuffle = len(data["swaps"]) * float(data["swap_seconds"])
    return round(CUP_ENTRANCE + CUP_LIFT + CUP_SHOW + CUP_LOWER + shuffle + float(data["thinking_seconds"])
                 + CUP_REVEAL + CUP_ANSWER + CUP_HOLD, 3)


def cup_average_round(datas: list[dict]) -> float:
    """Levels last different times; VideoSpec keeps their average so the total duration stays exact."""
    return round(sum(cup_round(data) for data in datas) / len(datas), 4)


# Matchstick equations: three levels per video, each harder, with more thinking time (never over 15 s).
MATCH_THINKING = {"easy": (14.0, 15.0, 15.0), "medium": (12.0, 14.0, 15.0), "hard": (10.0, 12.0, 15.0)}
MATCH_ENTRANCE = 0.5
MATCH_MOVE = 1.3  # the stick lifts, flies to its new slot, and settles
MATCH_ANSWER = 0.45  # the equation turns green with a burst
MATCH_HOLD = 1.0
# Frame and timer colour of Matchstick Math (UI: Çerçeve rengi): card outline, instruction pill, timer while time is
# plentiful (it still turns warning/danger near the end), hook subtitle, and the cover's pill.
MATCH_FRAMES = {"teal": ("Turkuaz", "#2EE6C5"), "amber": ("Amber", "#FFB547"), "violet": ("Lavanta", "#9B7BFF"),
                "blue": ("Mavi", "#3DA9FF"), "pink": ("Pembe", "#FF6FB5"), "lime": ("Limon", "#A6E35D")}
MATCH_DEFAULT_FRAME = "teal"


def matchstick_round(difficulty: str | None, tier: int) -> float:
    thinking = MATCH_THINKING.get(difficulty or "hard", MATCH_THINKING["hard"])[tier]
    return round(MATCH_ENTRANCE + thinking + MATCH_MOVE + MATCH_ANSWER + MATCH_HOLD, 3)


def matchstick_average_round(difficulty: str | None) -> float:
    """Levels last different times; VideoSpec keeps their average so the total duration stays exact."""
    return round(sum(matchstick_round(difficulty, tier) for tier in range(3)) / 3, 4)


# Chess: Mate in 1. One static position for the whole video; the answer is never shown.
CHESS_DURATION = 30.0
# Long video (Brain Test): a mate-in-1 gets a timer, then the move is shown on the board.
CHESS_LONG_ENTRANCE = 0.5
CHESS_LONG_THINKING = 15.0
CHESS_LONG_REVEAL = 6.0
CHESS_DATASET = ASSETS_DIR / "chess" / "mate_in_1.csv"
# Board colours the creator can pick (UI: Tahta rengi): (label, light square, dark square). Every dark square stays a
# mid tone, so near-black pieces and white pieces both stand out on every square.
CHESS_BOARDS = {
    "wood": ("Klasik ahşap", "#F0D9B5", "#B58863"),
    "green": ("Turnuva yeşili", "#EEEED2", "#769656"),
    "blue": ("Buz mavisi", "#DEE3E6", "#8CA2AD"),
    "violet": ("Lavanta", "#E8E1F2", "#9A83BE"),
    "coral": ("Mercan", "#F3E0D4", "#C98A73"),
    "teal": ("Deniz yeşili", "#DCEDE9", "#6FA39C"),
}
CHESS_DEFAULT_BOARD = "wood"
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
BOUNCE_CTA_DURATION = 3.7  # its end card, 2 s longer like the others (it was 1.7 s)


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
    if puzzle_type == "chess_mate":
        return CHESS_DURATION
    if puzzle_type == "laser_maze":  # the average level of a default-length video (a made video stores its own)
        return laser_default_average()
    if puzzle_type == "mind_mix":  # the average section of a default video (a made video stores its own)
        return mix_average_round(mix_default_sections())
    if puzzle_type == "shade_spot":  # the average of a default video's levels (a made video stores its own)
        return shade_average_round([{"thinking_seconds": SHADE_LEVELS[tier]["thinking"]}
                                    for tier in SHADE_TIERS[DEFAULT_ROUNDS["shade_spot"]]])
    if puzzle_type == "cup_shuffle":  # the average of a default video's three levels (a made video stores its own)
        return cup_average_round([{"swaps": [0] * level["swaps"], "swap_seconds": level["swap_seconds"],
                                   "thinking_seconds": level["thinking"]} for level in CUP_LEVELS])
    if puzzle_type == "matchstick":
        return matchstick_average_round(difficulty)
    if puzzle_type == "lucky_pick":
        return LUCKY_ROUND_DURATION
    if puzzle_type == "flash_count":
        return flash_round_duration(difficulty)
    if puzzle_type == "memory_challenge":  # the three levels together (a made video stores one entry per level)
        return memory_levels_total()
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
    "crimson": ("#13070C", "#27101A", "#B02A55"),  # retired from the choices; kept so older records still render
    "gold": ("#100D05", "#231D08", "#A8841C"),
    "emerald": ("#04130B", "#0A2616", "#1E9E5A"),
    "ember": ("#130B06", "#2A160A", "#C2601C"),
    "plum": ("#10061A", "#22103A", "#9B2FC2"),
    # Vivid tones (the user's request: "the videos are mostly dark, add liveliness"). The edges stay as dark as ever, and the
    # colour toward the middle is bright and saturated: `THEME_GLOW` makes the centre glow that much stronger.
    "lemon": ("#161104", "#2B2205", "#FFEB5C"),
    "tangerine": ("#180B03", "#2E1505", "#FF8A1F"),
    "pink": ("#180614", "#2E0A26", "#FF3FA4"),
    "cyan": ("#031318", "#052A33", "#12D6FF"),
    "lime": ("#0A1503", "#142A06", "#9BFF3D"),
}
THEME_GLOW = {"lemon": 2.3, "tangerine": 1.7, "pink": 1.7, "cyan": 1.7, "lime": 1.6}  # x the centre glow of the normal tones


def glow_strength(theme: str, base: float) -> float:
    """A background glow's strength for a tone: vivid tones glow harder (capped so the middle never washes out)."""
    return min(.92, base * THEME_GLOW.get(theme, 1.0))
# Cube colours that would blend into a background tone.
THEME_CLASHING_CUBES = {"violet": ("violet",), "ocean": ("sky", "violet"), "teal": ("teal", "green"),
                        "crimson": ("coral", "pink"), "emerald": ("green", "teal"), "ember": ("amber", "yellow", "coral"),
                        "plum": ("violet", "pink"), "gold": ("amber", "yellow"),
                        "lemon": ("yellow", "amber"), "tangerine": ("amber", "coral", "yellow"), "pink": ("pink", "coral"),
                        "cyan": ("sky", "teal"), "lime": ("green", "teal", "yellow")}
# Tones offered in the UI and drawn at random for new videos.
THEME_CHOICES = tuple(theme for theme in DARK_THEMES if theme != "crimson")
# The tones older videos were drawn from. A saved video without a stored tone still gets the same one from its seed.
LEGACY_THEME_CHOICES = ("violet", "ocean", "teal", "gold", "emerald", "ember", "plum")


def dark_theme_for(puzzle_type: str, seed: int) -> str:
    """The tone of a video that never stored one (older videos): random per seed, fixed for its frames and cover. Its pool
    is frozen, so re-rendering an old video never changes its colour."""
    import random
    return random.Random(f"background_theme:{puzzle_type}:{seed}").choice(sorted(LEGACY_THEME_CHOICES))


def fresh_theme_for(puzzle_type: str, seed: int) -> str:
    """The random tone of a NEW video (any tone, vivid ones included). It is stored in the spec's metadata."""
    import random
    return random.Random(f"background_theme_v2:{puzzle_type}:{seed}").choice(sorted(THEME_CHOICES))


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


# Laser Maze (the user's idea after Find the Exit and Line Follow took off: another "trace it with your eyes" game): a laser
# enters a board of mirrors and the viewer says which numbered receiver it ends in. Up to 5 levels, chosen in the UI; the number
# of levels picks the tiers (the last level is always the hardest). DIFFICULTY IS TUNED HERE: per tier the board size, the share
# of cells with a mirror, the bounces of the beam, how many cells it visits, how often it crosses its own path, the receivers,
# and the thinking time. A made video stores its own, so retuning never changes it.
LASER_TIERS = (
    {"n": 5, "density": .42, "bounces": (3, 5), "min_cells": 7, "revisits": 0, "receivers": 4, "thinking": 6.0},
    {"n": 6, "density": .42, "bounces": (5, 8), "min_cells": 10, "revisits": 0, "receivers": 4, "thinking": 7.0},
    {"n": 7, "density": .42, "bounces": (7, 11), "min_cells": 14, "revisits": 1, "receivers": 5, "thinking": 8.0},
    {"n": 8, "density": .42, "bounces": (9, 14), "min_cells": 18, "revisits": 1, "receivers": 5, "thinking": 9.0},
    {"n": 9, "density": .42, "bounces": (11, 18), "min_cells": 22, "revisits": 2, "receivers": 6, "thinking": 10.0},
)
LASER_TIER_SETS = {3: (0, 2, 4), 4: (0, 1, 3, 4), 5: (0, 1, 2, 3, 4)}  # tiers by the number of levels
LASER_ENTRANCE = 0.5
LASER_HOLD = 1.3  # the answer pill and the lit receiver
LASER_TRACE_PER_CELL = 0.14  # seconds of beam per cell it crosses, within the limits below
LASER_TRACE_RANGE = (1.8, 4.0)


def laser_trace_seconds(cells: int) -> float:
    return round(min(LASER_TRACE_RANGE[1], max(LASER_TRACE_RANGE[0], .4 + cells * LASER_TRACE_PER_CELL)), 2)


def laser_round(data: dict) -> float:
    """One level's length from its stored timing: entrance, thinking, the beam's trace, and the hold."""
    return round(LASER_ENTRANCE + float(data["thinking_seconds"]) + float(data["trace_seconds"]) + LASER_HOLD, 3)


def laser_average_round(datas: list[dict]) -> float:
    return round(sum(laser_round(data) for data in datas) / len(datas), 4)


def laser_default_average(count: int | None = None) -> float:
    """The average level of a video of `count` levels (a made video stores its own timing; the beam's length here is typical)."""
    tiers = LASER_TIER_SETS[count or DEFAULT_ROUNDS["laser_maze"]]
    return laser_average_round([{"thinking_seconds": LASER_TIERS[tier]["thinking"],
                                 "trace_seconds": laser_trace_seconds(round(LASER_TIERS[tier]["n"] * 2.6))} for tier in tiers])


# Mind Mix (the user's idea: Puzzle Fit, Memory Challenge and Shade Spot lost views on their own, so they were paused and
# share one video, one hard level each, like level 3 of their own videos). The levels are always these games' own hardest
# rounds; only the Puzzle Fit timer is shorter (its own video's 20 s was too long), and a short title card opens each game so
# nobody wonders what to do. A made video stores its own section lengths.
MIX_GAMES = ("memory_challenge", "shade_spot", "puzzle_fit")  # easiest to hardest to watch: ezber, farkı bul, parçaları yerleştir
MIX_FIT_THINKING = 12.0  # seconds to match the three pieces (their own video: 20 s)
MIX_SECTION_INTRO = 1.8  # the title card before each game


def mix_sub_length(data: dict) -> float:
    """How long the game's own part of a section lasts, from its stored data."""
    sub = data["sub"]
    if data["game"] == "memory_challenge":
        return memory_level_round(sub)
    if data["game"] == "shade_spot":
        return shade_round(sub)
    return round(FIT_ENTRANCE + float(sub["thinking_seconds"]) + FIT_CLEAR + 3 * FIT_PLACE + FIT_SHINE + FIT_HOLD, 3)


def mix_section_length(data: dict) -> float:
    return round(float(data["intro_seconds"]) + mix_sub_length(data), 3)


def mix_average_round(datas: list[dict]) -> float:
    """Sections last different times; VideoSpec keeps their average so the total duration stays exact."""
    return round(sum(mix_section_length(data) for data in datas) / len(datas), 4)


def mix_default_sections() -> list[dict]:
    """The three sections of a default video (their lengths do not depend on the seed)."""
    memory = MEMORY_LEVELS[2]
    shade = SHADE_LEVELS[-1]
    return [{"game": "memory_challenge", "intro_seconds": MIX_SECTION_INTRO,
             "sub": {"kind": memory["kind"], "memorize_seconds": memory["memorize"], "thinking_seconds": memory["thinking"],
                     "question_count": memory["questions"]}},
            {"game": "shade_spot", "intro_seconds": MIX_SECTION_INTRO, "sub": {"thinking_seconds": shade["thinking"]}},
            {"game": "puzzle_fit", "intro_seconds": MIX_SECTION_INTRO, "sub": {"thinking_seconds": MIX_FIT_THINKING}}]


def intro_outro(puzzle_type: str, difficulty: str | None) -> tuple[float, float]:
    """Intro/outro for round-based games; the Puzzly for You look uses the hook intro and score-question outro."""
    if puzzle_type == "flash_count":
        return FLASH_INTRO, PUZZLE_FIT_OUTRO_DURATION
    if puzzle_type in READY_GAMES:
        return READY_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION
    if puzzle_type in ("puzzle_fit", "cube_count", "memory_challenge", "lucky_pick", "quick_math", "line_follow",
                       "matchstick", "cup_shuffle", "shade_spot", "mind_mix", "laser_maze") or (
            puzzle_type == "find_the_exit" and difficulty == "hard"):
        return PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION
    return INTRO_DURATION, OUTRO_DURATION


def ensure_directories() -> None:
    for path in (AUDIO_DIR, BRANDING_DIR, DATA_DIR, HIDDEN_MOTION_BACKGROUNDS_DIR,
                 HIDDEN_MOTION_LAYOUTS_DIR, HIDDEN_MOTION_OBJECTS_DIR, OUTPUT_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)
