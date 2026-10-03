"""YouTube long-form Brain Test (16:9): all ten games in one video of about 9 minutes 30 seconds.

Thirteen game segments in four blocks, one score check after every block but the last, then the final score:

  Block 1  Cup Shuffle, Puzzle Fit, Quick Math (Shape Equations)
  Block 2  Cube Count, Matchstick Math, Mate in 1
  Block 3  Memory Challenge, Puzzle Fit, Mate in 1, Quick Math (Missing Signs)
  Block 4  Cube Count, Find the Exit, Line Follow (the finale)

Quick Math always closes its block (it is the hardest for most viewers), no two similar games follow each other, and
the longest, hardest game comes last. Every game opens with a how-to card and a 3-2-1 countdown (`ARE YOU READY?` for the
games that flash something). Each game is exactly the Shorts game (its own levels, timers and hints) on a stage between
a left panel (game, how to play, level) and a right panel (score sheet, `+1 POINT` toast, up next). Scoring: one point
per level or puzzle; Memory counts 1 point for 6+ of its 8 questions and Puzzle Fit 1 point for all three pieces. Mate in
1 gets a 15 s timer and then shows the move.

The video's number (`BRAIN TEST #7`) is the count of saved Brain Tests plus one: Drafts never use up a number.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from datetime import datetime
from functools import lru_cache
from hashlib import sha256
import json
import logging
import math
from pathlib import Path
import random
import shutil
import time
from typing import Callable
from uuid import uuid4

import numpy as np
from PIL import Image, ImageDraw

from .config import (AUDIO_RATE, CHESS_LONG_ENTRANCE, CHESS_LONG_REVEAL, CHESS_LONG_THINKING, DARK_THEMES, DATA_DIR, FPS,
                     OUTPUT_DIR, PUZZLE_FIT_PALETTE as PALETTE, THEME_CHOICES, ensure_directories)
from .longform import (QUALITIES, _check, _clamp, _edge_fade, _ease, _landscape_background, _pointer, _rgb, _rounded_mask,
                       _stage, _surface, _text, _text_left, _title3d, _up_next)
from .models import VideoSpec

LOGGER = logging.getLogger(__name__)

VERSION = "braintest_v1"
PUZZLE_TYPE = "longform_brain_test"
STAGE_ROWS = (95.0, 1650.0)


@dataclass(frozen=True)
class GameDef:
    kind: str  # the Shorts puzzle type
    label: str
    short: str  # a short name for the intro tiles
    steps: tuple[str, str, str]
    color: str
    toast: str = "RIGHT?  +1 POINT"
    rows: tuple[float, float] = STAGE_ROWS  # rows of the 1080x1920 frame shown on the stage
    ready: bool = False  # the card asks ARE YOU READY? (something flashes or is shown for a moment)


GAMES: dict[str, GameDef] = {
    "cup": GameDef("cup_shuffle", "CUP SHUFFLE", "Cup Shuffle", ("Watch where the ball is", "Follow that cup as they swap", "Pick its number"), "#3DA9FF", ready=True),
    "fit": GameDef("puzzle_fit", "PUZZLE FIT", "Puzzle Fit", ("Find the 3 missing pieces", "The options are tilted", "Answer like A4 B1 C6"), "#7C5CFF",
                   "ALL 3 RIGHT?  +1 POINT", rows=(95.0, 1815.0)),
    "shapes": GameDef("quick_math", "SHAPE EQUATIONS", "Quick Math", ("Find each shape's value", "Solve the last line", "× and ÷ come first"), "#2EE6C5"),
    "cube": GameDef("cube_count", "CUBE COUNT", "Cube Count", ("Cubes flash for a moment", "Count them all, hidden too", "Say the total"), "#FFB547", ready=True),
    "match": GameDef("matchstick", "MATCHSTICK MATH", "Matchstick Math", ("Move exactly 1 match", "Make the equation true", "Only one move works"), "#FF8A3D"),
    "chess": GameDef("chess_mate", "MATE IN 1", "Mate in 1", ("Find the one winning move", "It checkmates the king", "You have 15 seconds"), "#F0D9B5"),
    "memory": GameDef("memory_challenge", "MEMORY CHALLENGE", "Memory", ("Memorize every shape", "Find where each one was", "Name what vanished"), "#FF6FB5",
                      "ALL RIGHT?  +1 POINT", ready=True),
    "signs": GameDef("quick_math", "MISSING SIGNS", "Quick Math", ("Fill the boxes with + − × ÷", "Make the equation true", "× and ÷ come first"), "#FFC24B"),
    "exit": GameDef("find_the_exit", "FIND THE EXIT", "Find the Exit", ("Find the one open exit", "Only one path reaches it", "Trace it with your eyes"), "#3DF08F"),
    "line": GameDef("line_follow", "LINE FOLLOW", "Line Follow", ("Follow the glowing line", "Find where it ends", "It crosses the other lines"), "#FF5F6D",
                    rows=(95.0, 1810.0)),
}
GAME_COUNT = 10  # Quick Math counts twice (two formats)
SEQUENCE = (("cup", 1), ("fit", 1), ("shapes", 1),
            ("cube", 1), ("match", 1), ("chess", 1),
            ("memory", 1), ("fit", 2), ("chess", 2), ("signs", 1),
            ("cube", 2), ("exit", 1), ("line", 1))
BLOCK_SIZES = (3, 3, 4, 3)
POINTS = {"cup": 3, "fit": 1, "shapes": 3, "cube": 4, "match": 3, "chess": 1, "memory": 3, "signs": 3, "exit": 4, "line": 5}  # levels per game


def expected_points() -> int:
    """The score out of which the video is played (34), known without building any puzzle."""
    return sum(POINTS[key] for key, _ in SEQUENCE)
CHAPTER_NAMES = {"shapes": "Quick Math: Shape Equations", "signs": "Quick Math: Missing Signs"}
CARD_SECONDS = {"intro": 7.0, "first": 5.5, "repeat": 3.5, "checkpoint": 5.0, "final_score": 11.0, "end": 6.0}
COUNTDOWN = 3.0
TOAST_SECONDS = 1.6


@dataclass(frozen=True)
class Slot:
    index: int
    key: str
    spec: VideoSpec
    block: int
    first: bool  # the first time this game appears (a longer how-to card)
    duration: float
    levels: tuple[tuple[float, float], ...]  # (start, duration) of every level, relative to the game's start
    answers: tuple[float, ...]  # when each point is awarded, relative to the game's start

    @property
    def game(self) -> GameDef:
        return GAMES[self.key]

    @property
    def points(self) -> int:
        return len(self.answers)


@dataclass(frozen=True)
class Segment:
    kind: str  # intro, card, game, checkpoint, final_score, end
    start: float
    duration: float
    slot: int = -1  # the game a card or game segment belongs to
    block: int = 0  # the block a checkpoint closes

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class BrainPlan:
    seed: int
    theme: str
    music: bool
    episode: int
    slots: list[Slot]
    segments: list[Segment]
    fingerprint: str
    chapters: list[tuple[float, str]] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return round(self.segments[-1].end, 3)

    @property
    def total_points(self) -> int:
        return sum(slot.points for slot in self.slots)

    @property
    def block_points(self) -> list[int]:
        return [sum(slot.points for slot in self.slots if slot.block == block) for block in range(len(BLOCK_SIZES))]

    @property
    def hero_key(self) -> str:
        """The game the thumbnail features: it rotates with the episode number, so consecutive covers differ."""
        keys = [key for key, _ in SEQUENCE if key not in ("chess",)]
        ordered = list(dict.fromkeys(keys)) + ["chess"]
        return ordered[(self.episode - 1) % len(ordered)]

    def rating_bands(self) -> list[tuple[int, int, str, str]]:
        top = self.total_points
        cuts = [round(top * fraction) for fraction in (.28, .55, .8)]
        names = (("WARMING UP", "#9AA3C7"), ("SHARP MIND", "#3DA9FF"), ("BRAIN MACHINE", "#2EE6C5"), ("UNSTOPPABLE", "#FFC24B"))
        lows = [0, cuts[0] + 1, cuts[1] + 1, cuts[2] + 1]
        highs = [cuts[0], cuts[1], cuts[2], top]
        return [(low, high, name, color) for low, high, (name, color) in zip(lows, highs, names)]

    def metadata(self) -> dict[str, str]:
        variants = (
            f"{GAME_COUNT} GAMES. {self.total_points} Puzzles. How Many Can You Solve? 🧠 Brain Test #{self.episode}",
            f"Can You Finish All 10 Games? 🧠 Brain Test #{self.episode}",
            f"Brain Test #{self.episode} 🧠 {self.total_points} Puzzles, No Calculator, Only Your Brain",
            f"Test Your Brain: 10 Games, {self.total_points} Puzzles 🧠 Brain Test #{self.episode}",
            f"How High Can You Score? 🧠 {self.total_points} Puzzles | Brain Test #{self.episode}",
            f"Math, Memory, Chess and More 🧠 Brain Test #{self.episode}: Can You Score {self.total_points // 2 + 3}+?",
        )
        title = variants[(self.seed + self.episode) % len(variants)]
        chapter_lines = "\n".join(f"{_clock(start)} {name}" for start, name in self.chapters)
        description = (
            f"Brain Test #{self.episode}: 10 different games and {self.total_points} puzzles. Grab a pen and keep your score "
            f"(+1 for every correct answer). Pause anytime.\n\n{chapter_lines}\n\n"
            f"What was your score out of {self.total_points}? Tell us in the comments!\n\n"
            "#braintest #brainteaser #puzzle #mathpuzzle #chess #brainchallenge")
        tags = ("brain test,brain teaser,puzzle challenge,math puzzle,chess puzzle,mate in 1,memory game,matchstick puzzle,"
                "cup game,find the exit,puzzly for you")
        return {"title": title[:100], "description": description, "tags": tags}


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


# ---------------------------------------------------------------- game timing

def _from(schedule: list[tuple[float, float]], intro: float) -> tuple[tuple[float, float], ...]:
    return tuple((start - intro, duration) for start, duration in schedule)


def slot_metrics(key: str, spec: VideoSpec) -> tuple[float, tuple[tuple[float, float], ...], tuple[float, ...]]:
    """(duration, levels, answer times) of a game inside the long video, from the game's own timing."""
    intro = spec.intro_duration
    if key == "chess":
        from .visuals.chess_mate import long_phases
        times = long_phases()
        return times["end"], ((0.0, times["end"]),), (times["think_end"],)
    if key in ("shapes", "signs"):
        from .visuals.quick_math import phases, schedule
        levels = _from(schedule(spec), intro)
        return sum(d for _, d in levels), levels, tuple(start + phases(item)["answer"] for (start, _), item in zip(levels, spec.rounds))
    if key == "exit":
        from .config import EXIT_HARD_ENTRANCE, EXIT_HARD_TRACE
        from .puzzles.find_the_exit import round_thinking
        from .visuals.find_the_exit import schedule
        levels = _from(schedule(spec), intro)
        return (sum(d for _, d in levels), levels,
                tuple(start + EXIT_HARD_ENTRANCE + round_thinking(item.data) + EXIT_HARD_TRACE for (start, _), item in zip(levels, spec.rounds)))
    if key == "line":
        from .visuals.line_follow import phases, schedule
        levels = _from(schedule(spec), intro)
        return sum(d for _, d in levels), levels, tuple(start + phases(item)["arrival"] for (start, _), item in zip(levels, spec.rounds))
    if key == "match":
        from .visuals.matchstick import phases, schedule
        levels = _from(schedule(spec), intro)
        return sum(d for _, d in levels), levels, tuple(start + phases(item)["answer"] for (start, _), item in zip(levels, spec.rounds))
    if key == "cup":
        from .visuals.cup_shuffle import phases, schedule
        levels = _from(schedule(spec), intro)
        return sum(d for _, d in levels), levels, tuple(start + phases(item)["reveal_end"] for (start, _), item in zip(levels, spec.rounds))
    if key == "cube":
        from .visuals.cube_count import phases, schedule
        levels = _from(schedule(spec), intro)
        return (sum(d for _, d in levels), levels,
                tuple(start + phases(item)["count_end"] for (start, _), item in zip(levels, spec.rounds)))
    if key == "memory":
        from .visuals.memory_levels import phases, schedule
        levels = _from(schedule(spec), intro)
        return (sum(d for _, d in levels), levels,
                tuple(start + phases(item)["questions_end"] for (start, _), item in zip(levels, spec.rounds)))
    from .visuals.puzzle_fit_v12 import phases  # puzzle fit
    return spec.round_duration, ((0.0, spec.round_duration),), (phases(spec.rounds[0])["shine"],)


def estimated_duration() -> float:
    """A typical video length in seconds, from the games' own timing (no puzzle is generated)."""
    from .config import (EXIT_HARD_LEVEL_THINKING, LINE_THINKING, cube_default_video, memory_levels_total, exit_hard_round, fit_round, line_round, matchstick_average_round,
                         quick_math_round, quick_math_tiers, round_duration, CUP_LEVELS, cup_average_round)
    qm = sum(quick_math_round("hard", tier) for tier in quick_math_tiers(3))
    chess = CHESS_LONG_ENTRANCE + CHESS_LONG_THINKING + CHESS_LONG_REVEAL
    cups = 3 * cup_average_round([{"swaps": [0] * level["swaps"], "swap_seconds": level["swap_seconds"],
                                   "thinking_seconds": level["thinking"]} for level in CUP_LEVELS])
    durations = {"cup": cups, "fit": fit_round("hard"), "shapes": qm, "signs": qm, "cube": cube_default_video("hard"),
                 "match": 3 * matchstick_average_round("hard"), "chess": chess, "memory": memory_levels_total(),
                 "exit": sum(exit_hard_round(v) for v in EXIT_HARD_LEVEL_THINKING[:4]), "line": sum(line_round(v) for v in LINE_THINKING)}
    seen, total = set(), CARD_SECONDS["intro"] + CARD_SECONDS["final_score"] + CARD_SECONDS["end"]
    for key, _ in SEQUENCE:
        total += durations[key] + (CARD_SECONDS["repeat"] if key in seen else CARD_SECONDS["first"])
        seen.add(key)
    return total + (len(BLOCK_SIZES) - 1) * CARD_SECONDS["checkpoint"]


# ---------------------------------------------------------------- plan

def _make_spec(key: str, occurrence: int, seed: int, metadata: dict) -> VideoSpec:
    from .generator import generate_spec
    game = GAMES[key]
    kwargs = {"operation": "operators"} if key == "signs" else ({"operation": "shapes"} if key == "shapes" else {})
    difficulty = ("medium" if occurrence == 1 else "hard") if key == "chess" else "hard"  # the second mate is the harder one
    spec = generate_spec(game.kind, seed, difficulty, **kwargs)
    return replace(spec, metadata={**spec.metadata, **metadata, "captions": "off"})  # the long video has its own panels


def episode_number(history=None) -> int:
    """`BRAIN TEST #n`: saved Brain Tests plus one. Drafts are not in the history, so they never use up a number."""
    from .history import HistoryStore
    history = history or HistoryStore()
    return 1 + sum(1 for record in history.records() if record.puzzle_type == PUZZLE_TYPE and record.output_filename)


def build_plan(seed: int, background: str = "random", music: bool = False, episode: int = 1,
               progress: Callable[[str], None] | None = None) -> BrainPlan:
    rng = random.Random(f"{VERSION}:{seed}")
    # The tone has its own generator, so choosing a background never changes the puzzles of a seed.
    theme = background if background in DARK_THEMES and background != "random" else random.Random(f"{VERSION}:theme:{seed}").choice(sorted(THEME_CHOICES))
    metadata = {"background": theme, **({"music": "on"} if music else {})}
    slots: list[Slot] = []
    seen_games: set[str] = set()
    fingerprints: set[str] = set()
    block, in_block = 0, 0
    for index, (key, occurrence) in enumerate(SEQUENCE):
        if progress:
            progress(f"Oyunlar hazırlanıyor {index + 1}/{len(SEQUENCE)}: {GAMES[key].label}")
        for _ in range(20):
            spec = _make_spec(key, occurrence, rng.randrange(2**31), metadata)
            keys = {item.fingerprint() for item in spec.rounds}
            if not keys & fingerprints:
                break
        else:
            raise ValueError(f"could not build a distinct {key} puzzle")
        fingerprints |= keys
        duration, levels, answers = slot_metrics(key, spec)
        slots.append(Slot(index, key, spec, block, key not in seen_games, duration, levels, answers))
        seen_games.add(key)
        in_block += 1
        if in_block == BLOCK_SIZES[block]:
            block, in_block = block + 1, 0
    segments: list[Segment] = []
    clock = 0.0

    def add(kind: str, duration: float, **extra) -> None:
        nonlocal clock
        segments.append(Segment(kind, round(clock, 4), round(duration, 4), **extra))
        clock += duration

    add("intro", CARD_SECONDS["intro"])
    chapters: list[tuple[float, str]] = []
    for slot in slots:
        card = CARD_SECONDS["first" if slot.first else "repeat"]
        chapters.append((0.0 if slot.index == 0 else clock, f"{slot.index + 1}. {CHAPTER_NAMES.get(slot.key, slot.game.short)}"))
        add("card", card, slot=slot.index, block=slot.block)
        add("game", slot.duration, slot=slot.index, block=slot.block)
        last_in_block = slot.index == max(other.index for other in slots if other.block == slot.block)
        if last_in_block and slot.block < len(BLOCK_SIZES) - 1:
            add("checkpoint", CARD_SECONDS["checkpoint"], slot=slot.index, block=slot.block)
    chapters.append((clock, "Final Score"))
    add("final_score", CARD_SECONDS["final_score"])
    add("end", CARD_SECONDS["end"])
    fingerprint = sha256(json.dumps([VERSION, sorted(fingerprints)]).encode()).hexdigest()[:20]
    return BrainPlan(seed, theme, music, episode, slots, segments, fingerprint, chapters)


# ---------------------------------------------------------------- panels (drawn on the 1920x1080 frame)

def _level_at(slot: Slot, local: float) -> int:
    return max(0, bisect_right([start for start, _ in slot.levels], local) - 1)


def _next_label(plan: BrainPlan, slot: Slot) -> str:
    following = [other for other in plan.slots if other.index == slot.index + 1]
    if not following:
        return "YOUR FINAL SCORE"
    return "SCORE CHECK" if following[0].block != slot.block else following[0].game.label


def _left_panel(image, plan: BrainPlan, slot: Slot, level: int, scale: float, pulse: float) -> None:
    from .visuals.text import fitted_font
    game = slot.game
    _surface(image, (70, 90, 580, 880), 30, PALETTE["surface"], scale, PALETTE["surface_edge"], 2.5, 225)
    _text(image, (325, 150), f"GAME {slot.index + 1} / {len(plan.slots)}", 30, PALETTE["accent"], scale)
    face_size = fitted_font(game.label, round(440 * scale), round(52 * scale), max(4, round(28 * scale))).size / scale
    _text(image, (325, 212), game.label, face_size, PALETTE["text_light"], scale)
    _text(image, (325, 300), "HOW TO PLAY", 24, PALETTE["text_muted"], scale)
    for index, step in enumerate(game.steps):
        y = 362 + index * 78
        _surface(image, (106, y - 26, 158, y + 26), 26, PALETTE["primary"], scale, alpha=255)
        _text(image, (132, y - 2), str(index + 1), 28, PALETTE["text_light"], scale)
        size = fitted_font(step, round(370 * scale), round(27 * scale), max(4, round(19 * scale))).size / scale
        _text_left(image, 178, y, step, size, PALETTE["text_light"], scale, weight="semibold")
    total = len(slot.levels)
    if total > 1:
        _text(image, (325, 648), f"LEVEL {level + 1} / {total}", 36, PALETTE["text_light"], scale)
        gap = 40
        start = 325 - gap * (total - 1) / 2
        draw = ImageDraw.Draw(image, "RGBA")
        for index in range(total):
            x, y = (start + index * gap) * scale, 712 * scale
            r = (11 + (4 * pulse if index == level else 0)) * scale
            if index < level:
                draw.ellipse((x - r, y - r, x + r, y + r), fill=_rgb(PALETTE["accent"]) + (255,))
            elif index == level:
                draw.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, 255), width=max(2, round(4 * scale)))
            else:
                draw.ellipse((x - r, y - r, x + r, y + r), fill=_rgb(PALETTE["surface_edge"]) + (255,))
    else:
        _text(image, (325, 648), "ONE PUZZLE", 36, PALETTE["text_light"], scale)
    _text(image, (325, 800), "Pause anytime", 26, PALETTE["text_muted"], scale, weight="semibold")


def _scoreboard(image, plan: BrainPlan, active: int, scale: float, toast: float = 0.0, toast_text: str = "") -> None:
    """Right panel: the viewer's score sheet by block, the +1 toast, and what comes next."""
    maxima = plan.block_points
    _surface(image, (1340, 90, 1850, 700), 30, PALETTE["surface"], scale, PALETTE["surface_edge"], 2.5, 225)
    _text(image, (1595, 140), "YOUR SCORE", 40, PALETTE["text_light"], scale)
    _text(image, (1595, 186), "+1 for every correct answer", 26, PALETTE["text_muted"], scale, weight="semibold")
    rows = [(f"BLOCK {index + 1}", maxima[index]) for index in range(len(maxima))] + [("TOTAL", plan.total_points)]
    for index, (label, best) in enumerate(rows):
        y = 262 + index * 84
        current = index == active
        done = index < active and label != "TOTAL"
        if current:
            _surface(image, (1370, y - 32, 1820, y + 32), 20, "#1F2A55", scale, PALETTE["accent"], 3, 255)
        color = PALETTE["accent"] if current else (PALETTE["text_light"] if done else PALETTE["text_muted"])
        _text_left(image, 1420, y, label, 28, color, scale)
        ImageDraw.Draw(image).line(((1618 * scale, (y + 16) * scale), (1712 * scale, (y + 16) * scale)),
                                   fill=_rgb(PALETTE["surface_edge"]), width=max(1, round(3 * scale)))
        _text_left(image, 1722, y, f"/ {best}", 28, color, scale)
        if done:
            _check(image, (1393, y), 11, PALETTE["success"], scale)
    if toast > 0:
        pop = _ease(toast / .25)
        _surface(image, (1385, 664 - 30 * pop, 1805, 664 + 30 * pop), 30, PALETTE["success"], scale, alpha=250)
        if pop > .5:
            _text(image, (1595, 662), toast_text, 30 if len(toast_text) <= 18 else 25, PALETTE["background"], scale)


def _game_frame(plan: BrainPlan, segment: Segment, local: float, size: tuple[int, int]) -> Image.Image:
    from .renderer import render_frame
    from .visuals.chess_mate import draw_chess_long
    from .visuals.puzzle_fit import use_theme
    slot = plan.slots[segment.slot]
    scale = size[0] / 1920
    image = _landscape_background(size, plan.theme).copy()
    use_theme(slot.spec)
    spot = min(local, slot.duration - 1e-3)
    if slot.key == "chess":
        painter = lambda portrait: draw_chess_long(slot.spec, spot, portrait)
    else:
        painter = lambda portrait: render_frame(slot.spec, slot.spec.intro_duration + spot, portrait)
    _stage(image, painter, scale, slot.game.rows)
    level = _level_at(slot, local)
    _left_panel(image, plan, slot, level, scale, abs(math.sin(local * 3)))
    toast = 0.0
    for moment in slot.answers:
        if 0 <= local - moment < TOAST_SECONDS:
            toast = local - moment
    _scoreboard(image, plan, slot.block, scale, toast, slot.game.toast)
    _up_next(image, _next_label(plan, slot) if level == len(slot.levels) - 1 else f"LEVEL {level + 2} / {len(slot.levels)}", scale)
    return _edge_fade(image, plan, segment, local, size)


# ---------------------------------------------------------------- cards (static layer drawn once at 2x, then animated)

CARD_2X = (3840, 2160)
_PLANS: dict[str, BrainPlan] = {}


def _preview(slot: Slot) -> Image.Image:
    """A 2x stage-sized picture of the game (its hook frame, never an answer), for the how-to card."""
    from .renderer import render_frame
    from .visuals.chess_mate import draw_chess_long
    rows = slot.game.rows
    height = round(920 * 2)
    factor = height / (rows[1] - rows[0])
    size = (round(1080 * factor), round(1920 * factor))
    frame = (draw_chess_long(slot.spec, 3.0, size) if slot.key == "chess" else render_frame(slot.spec, .6, size)).convert("RGB")
    top = round(rows[0] * factor)
    return frame.crop((0, top, frame.width, top + height))


def _plan_key(plan: BrainPlan) -> str:
    return f"{plan.fingerprint}:{plan.theme}:{plan.episode}"


@lru_cache(maxsize=24)
def _card_static(plan_key: str, index: int, size: tuple[int, int]) -> Image.Image:
    from .visuals.end_card import instagram_icon, youtube_icon
    from .visuals.puzzle_fit import use_theme
    plan = _PLANS[plan_key]
    segment = plan.segments[index]
    use_theme(plan.slots[0].spec)
    image = _landscape_background(CARD_2X, plan.theme).convert("RGBA")
    s = 2.0
    glow = DARK_THEMES.get(plan.theme, DARK_THEMES["violet"])[2]
    accent, gold = PALETTE["accent"], "#FFC24B"
    kind = segment.kind
    if kind == "intro":
        _title3d(image, (960, 210), f"{GAME_COUNT} GAMES.", 150, "#FFFFFF", "#CDD3EE", glow, max_width=1500)
        _title3d(image, (860, 420), "BRAIN TEST", 230, accent, "#7C5CFF", accent, max_width=1400)
        _surface(image, (1500, 90, 1840, 250), 44, "#FFC24B", s, alpha=255)
        _text(image, (1670, 172), f"#{plan.episode}", 120, PALETTE["background"], s)
        _text(image, (960, 590), f"{plan.total_points} PUZZLES  ·  {len(BLOCK_SIZES)} BLOCKS  ·  ONE FINAL SCORE", 46, PALETTE["text_light"], s)
        names = [game for game in GAMES.values() if game.label != "MISSING SIGNS"]
        for number, game in enumerate(names):
            x = 350 + (number % 5) * 305
            y = 725 + (number // 5) * 125
            _surface(image, (x - 140, y - 46, x + 140, y + 46), 24, PALETTE["surface"], s, PALETTE["surface_edge"], 2.5, 235)
            ImageDraw.Draw(image, "RGBA").rounded_rectangle(((x - 140) * s, (y - 46) * s, (x - 122) * s, (y + 46) * s), radius=10 * s,
                                                            fill=_rgb(game.color) + (255,))
            _text(image, (x + 8, y - 2), game.short, 31, PALETTE["text_light"], s, weight="semibold")
        _text(image, (960, 960), "Grab a pen and keep your score: +1 for every correct answer.", 36, PALETTE["text_muted"], s, weight="semibold")
    elif kind == "card":
        slot = plan.slots[segment.slot]
        game = slot.game
        use_theme(slot.spec)
        _text(image, (600, 130), f"GAME {slot.index + 1} / {len(plan.slots)}", 50, accent, s)
        _title3d(image, (600, 290), game.label, 140, "#FFFFFF", "#CDD3EE", glow, max_width=1080)
        _text(image, (600, 430), "HOW TO PLAY", 32, PALETTE["text_muted"], s)
        for number, step in enumerate(game.steps):
            y = 510 + number * 100
            _surface(image, (140, y - 36, 212, y + 36), 36, PALETTE["primary"], s, alpha=255)
            _text(image, (176, y - 3), str(number + 1), 38, PALETTE["text_light"], s)
            _text_left(image, 245, y, step, 42, PALETTE["text_light"], s, weight="semibold")
        count = len(slot.levels)
        info = f"{count} levels  ·  +1 point each" if count > 1 else "1 puzzle  ·  +1 point"
        _text(image, (600, 850), info, 38, gold, s)
        preview = _preview(slot)
        image.paste(preview, (round(1240 * s), round(80 * s)), _rounded_mask(preview.size, round(34 * s)))
    elif kind == "checkpoint":
        block = segment.block
        _title3d(image, (960, 230), f"BLOCK {block + 1} COMPLETE", 150, "#FFFFFF", "#CDD3EE", glow, max_width=1700)
        _text(image, (960, 390), "How many did you get?", 60, PALETTE["text_light"], s)
        _surface(image, (660, 450, 1260, 650), 40, PALETTE["surface"], s, accent, 4, 240)
        ImageDraw.Draw(image).line(((760 * s, 600 * s), (960 * s, 600 * s)), fill=_rgb(accent), width=round(8 * s))
        _text(image, (1090, 550), f"/ {plan.block_points[block]}", 110, PALETTE["text_light"], s)
        _text(image, (960, 730), "Write it down. You'll add it all up at the end!", 40, gold, s)
        following = plan.slots[segment.slot + 1]
        _text(image, (960, 900), f"UP NEXT:  {following.game.label}", 46, PALETTE["text_muted"], s)
    elif kind == "final_score":
        _title3d(image, (960, 150), "FINAL SCORE", 170, gold, "#FF8A3D", gold)
        maxima = plan.block_points
        for number in range(len(maxima)):
            x = 250 + number * 300
            _surface(image, (x - 130, 270, x + 130, 390), 26, PALETTE["surface"], s, PALETTE["surface_edge"], 2.5, 240)
            _text(image, (x, 316), f"BLOCK {number + 1}", 32, PALETTE["text_light"], s)
            _text(image, (x, 358), f"/ {maxima[number]}", 30, PALETTE["text_muted"], s)
            _text(image, (x + 150, 330), "+" if number < len(maxima) - 1 else "=", 50, PALETTE["text_muted"], s)
        _text(image, (1620, 330), f"? / {plan.total_points}", 76, accent, s)
        for number, (low, high, label, color) in enumerate(plan.rating_bands()):
            y = 480 + number * 105
            _surface(image, (520, y - 42, 1400, y + 42), 30, PALETTE["surface"], s, color, 3, 240)
            _text_left(image, 570, y, f"{low}–{high}", 44, color, s)
            _text_left(image, 820, y, label, 48, PALETTE["text_light"], s)
        _text(image, (960, 960), "Comment your score below!", 50, PALETTE["text_light"], s)
    elif kind == "end":
        _title3d(image, (960, 200), "THANKS FOR PLAYING", 170, "#FFFFFF", "#CDD3EE", glow)
        _text(image, (960, 372), "Want another brain test? A new one is coming soon.", 50, PALETTE["text_light"], s)
        _surface(image, (640, 450, 1280, 590), 70, "#FF3B5C", s, alpha=255)
        d = ImageDraw.Draw(image)
        d.ellipse((700 * s, 485 * s, 770 * s, 555 * s), outline=(255, 255, 255), width=round(8 * s))
        d.line(((713 * s, 520 * s), (757 * s, 520 * s)), fill=(255, 255, 255), width=round(8 * s))
        d.line(((735 * s, 498 * s), (735 * s, 542 * s)), fill=(255, 255, 255), width=round(8 * s))
        _text(image, (1010, 518), "SUBSCRIBE", 70, "#FFFFFF", s)
        from .config import SOCIAL_HANDLES
        handles = dict(SOCIAL_HANDLES)
        yt, ig = youtube_icon(round(64 * s)), instagram_icon(round(66 * s))
        image.alpha_composite(yt, (round(560 * s), round(698 * s - yt.height / 2)))
        _text_left(image, 640, 700, handles.get("youtube", "@puzzlyforyou"), 46, "#FFFFFF", s)
        image.alpha_composite(ig, (round(1030 * s), round(700 * s - ig.height / 2)))
        _text_left(image, 1104, 700, handles.get("instagram", "@puzzlyforyou"), 46, "#FFFFFF", s)
        _text(image, (960, 830), "Comment your final score and challenge a friend!", 44, gold, s)
        from .branding import draw_profile_mark
        from .visuals.text import font
        brand_width = ImageDraw.Draw(image).textlength("Puzzly for You", font=font(round(46 * s))) / s
        left = 960 - (80 + 20 + brand_width) / 2
        draw_profile_mark(image, (round((left + 40) * s), round(950 * s)), round(80 * s), PALETTE)
        _text_left(image, left + 100, 950, "Puzzly for You", 46, PALETTE["text_muted"], s)
    return image.convert("RGB").resize(size, Image.Resampling.LANCZOS)


def _countdown(frame: Image.Image, segment: Segment, local: float, ready: bool, scale: float) -> None:
    """A big 3-2-1 ring over the preview for the last three seconds of a card, under `ARE YOU READY?` or `STARTS IN`."""
    from .visuals.puzzle_fit import _outro_glow
    from .visuals.easing import ease_out_back
    remaining = segment.duration - local
    if remaining > COUNTDOWN:
        return
    elapsed = COUNTDOWN - remaining
    number = max(1, 3 - int(elapsed))
    phase = elapsed - int(elapsed)
    cx, cy, ring = 1560 * scale, 600 * scale, 235 * scale
    appear = _clamp(elapsed / .25)
    _surface(frame, (1240, 80, 1879, 1000), 34, PALETTE["surface"], scale, PALETTE["accent"], 4, round(252 * appear))  # covers the preview
    glow = _outro_glow(max(4, round(ring * 1.05)), PALETTE["accent"])
    faded = glow.copy()
    faded.putalpha(glow.getchannel("A").point(lambda value: round(value * (.55 + .35 * (1 - phase)) * appear)))
    frame.paste(faded, (round(cx - faded.width / 2), round(cy - faded.height / 2)), faded)
    draw = ImageDraw.Draw(frame, "RGBA")
    width = max(4, round(22 * scale))
    draw.ellipse((cx - ring, cy - ring, cx + ring, cy + ring), fill=_rgb(PALETTE["background"]) + (240,),
                 outline=_rgb(PALETTE["surface_edge"]) + (255,), width=width)
    draw.arc((cx - ring, cy - ring, cx + ring, cy + ring), -90, -90 + 360 * (1 - phase), fill=_rgb(PALETTE["accent"]) + (255,), width=width)
    zoom = 1 + .3 * (1 - ease_out_back(_clamp(phase / .4)))
    _text(frame, (1560, 610), str(number), 320, PALETTE["warning"] if number == 1 else PALETTE["text_light"], scale, appear, max(.4, zoom))
    label = "ARE YOU READY?" if ready else "STARTS IN"
    _surface(frame, (1290, 130, 1830, 240), 55, PALETTE["accent"], scale, alpha=round(255 * appear))
    _text(frame, (1560, 185), label, 54, PALETTE["background"], scale, appear)


def _card_frame(plan: BrainPlan, index: int, local: float, size: tuple[int, int]) -> Image.Image:
    segment = plan.segments[index]
    _PLANS[_plan_key(plan)] = plan
    static = _card_static(_plan_key(plan), index, size)
    appear = _ease(local / .45)
    fade_out = _clamp((segment.duration - local) / .3)
    zoom = .965 + .035 * appear
    background = _landscape_background(size, plan.theme)
    if zoom < .999:
        width, height = size
        scaled = static.resize((max(2, round(width * zoom)), max(2, round(height * zoom))), Image.Resampling.BILINEAR)
        frame = background.copy()
        frame.paste(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
        frame = Image.blend(background, frame, appear)
    else:
        frame = static.copy()
    scale = size[0] / 1920
    if segment.kind == "card":
        _countdown(frame, segment, local, plan.slots[segment.slot].game.ready, scale)
    if segment.kind == "end" and local >= 1.2:  # a finger taps the subscribe button, which ripples
        draw = ImageDraw.Draw(frame, "RGBA")
        travel = _ease((local - 1.2) / .5)
        press = .92 if 1.7 <= local < 1.85 else 1.0
        x, y = (755 + 320 * (1 - travel)) * scale, (533 + 240 * (1 - travel)) * scale
        if local >= 1.7:
            ripple = _ease((local - 1.7) / .6)
            r = (30 + 170 * ripple) * scale
            draw.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, round(220 * (1 - ripple))),
                         width=max(2, round(6 * (1 - ripple) * scale) + 1))
        _pointer(frame, (x, y), .8 * press * scale)
    if fade_out < 1:
        frame = Image.blend(background, frame, fade_out)
    return frame


# ---------------------------------------------------------------- frames, audio, render

def segment_at(plan: BrainPlan, t: float) -> tuple[int, Segment]:
    starts = [segment.start for segment in plan.segments]
    index = max(0, min(len(plan.segments) - 1, bisect_right(starts, t) - 1))
    return index, plan.segments[index]


def render_frame(plan: BrainPlan, t: float, size: tuple[int, int]) -> Image.Image:
    t = max(0.0, min(plan.total_duration - 1 / FPS, t))
    index, segment = segment_at(plan, t)
    local = t - segment.start
    if segment.kind == "game":
        return _game_frame(plan, segment, local, size)
    return _card_frame(plan, index, local, size)


def timeline_audio(plan: BrainPlan) -> np.ndarray:
    from .audio import finalize_mix, sound_library, timeline_audio as spec_audio
    audio = np.zeros((round(plan.total_duration * AUDIO_RATE), 2), dtype=np.float64)
    sounds = sound_library()
    fade = .35 if plan.music else .008  # game audio (and its music) must never click in or out at a cut

    def faded(piece: np.ndarray) -> np.ndarray:
        piece = np.array(piece, dtype=np.float64)
        length = min(len(piece) // 2, round(fade * AUDIO_RATE))
        if length > 1:
            ramp = np.sin(np.linspace(0.0, math.pi / 2, length)) ** 2
            ramp = ramp[:, None] if piece.ndim == 2 else ramp
            piece[:length] *= ramp
            piece[-length:] *= ramp[::-1]
        return piece

    def place(at: float, sound: np.ndarray, gain: float = 1.0) -> None:
        start = max(0, int(at * AUDIO_RATE))
        end = min(start + len(sound), len(audio))
        if end > start:
            piece = sound[:end - start] * gain
            audio[start:end] += piece if piece.ndim == 2 else piece[:, None]

    for segment in plan.segments:
        if segment.kind == "game":
            slot = plan.slots[segment.slot]
            length = round(segment.duration * AUDIO_RATE)
            if slot.key == "chess":
                from .visuals.chess_mate import long_phases
                times = long_phases()
                mixed = np.zeros((length, 2), dtype=np.float64)
                music = spec_audio(slot.spec)[:length]  # silent unless the music is on
                mixed[:len(music)] += music

                def put(at_time: float, name: str) -> None:
                    at = int(at_time * AUDIO_RATE)
                    piece = sounds[name][:max(0, length - at)]
                    mixed[at:at + len(piece)] += piece[:, None] if piece.ndim == 1 else piece

                for remaining in (3.0, 2.0, 1.0):  # clock ticks over the last three seconds
                    put(times["think_end"] - remaining, "pulse")
                put(times["think_end"], "transition_whoosh")
                put(times["arrow_end"], "answer_ding")
                put(times["arrow_end"] + .15, "sparkle")
                place(segment.start, faded(mixed))
            else:
                begin = round(slot.spec.intro_duration * AUDIO_RATE)
                place(segment.start, faded(spec_audio(slot.spec)[begin:begin + length]))
        else:
            place(segment.start + .05, sounds["intro_pop"])
            place(segment.end - .3, sounds["transition_whoosh"])
            if segment.kind == "card":
                for remaining in (3.0, 2.0, 1.0):
                    place(segment.end - remaining, sounds["pulse"])
            elif segment.kind == "intro":
                place(segment.end - 1.0, sounds["pulse"])
            elif segment.kind == "checkpoint":
                place(segment.start + .35, sounds["answer_ding"])
            elif segment.kind == "final_score":
                place(segment.start + .4, sounds["answer_ding"])
                place(segment.start + .7, sounds["sparkle"])
    return finalize_mix(audio)


def render_video(plan: BrainPlan, output_path: Path, quality: str = "draft",
                 progress: Callable[[float], None] | None = None) -> float:
    from moviepy import AudioArrayClip, VideoClip
    from .audio import ensure_sound_effects
    settings = QUALITIES[quality]
    ensure_directories()
    ensure_sound_effects()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cache: OrderedDict[int, np.ndarray] = OrderedDict()
    total_keys = math.ceil(plan.total_duration * settings.internal_visual_fps)

    def frame_at(t: float) -> np.ndarray:
        key = min(math.floor(t * settings.internal_visual_fps), total_keys - 1)
        if key not in cache:
            cache[key] = np.asarray(render_frame(plan, key / settings.internal_visual_fps, settings.output_size).convert("RGB"))
            while len(cache) > 3:
                cache.popitem(last=False)
            if progress and key % 30 == 0:
                progress(key / max(1, total_keys))
        return cache[key]

    started = time.perf_counter()
    video = VideoClip(frame_function=frame_at, duration=plan.total_duration).with_fps(FPS)
    audio = AudioArrayClip(timeline_audio(plan), fps=AUDIO_RATE)
    final = video.with_audio(audio)
    try:
        final.write_videofile(str(output_path), fps=FPS, codec="libx264", audio_codec="aac", audio_fps=AUDIO_RATE,
                              pixel_format="yuv420p", preset=settings.encoder_preset,
                              ffmpeg_params=["-crf", str(settings.crf), "-movflags", "+faststart", "-ar", str(AUDIO_RATE)],
                              logger=None)
    finally:
        final.close(); audio.close(); video.close()
    elapsed = time.perf_counter() - started
    LOGGER.info("Rendered Brain Test #%s %s duration=%.1fs in %.1fs", plan.episode, output_path, plan.total_duration, elapsed)
    return elapsed


def render_thumbnail(plan: BrainPlan) -> Image.Image:
    from .braintest_cover import render_braintest_thumbnail
    return render_braintest_thumbnail(plan)


def write_text(plan: BrainPlan, path: Path) -> None:
    meta = plan.metadata()
    path.write_text(f"TITLE\n{meta['title']}\n\nDESCRIPTION\n{meta['description']}\n\nTAGS\n{meta['tags']}\n\n"
                    f"SEED\n{plan.seed} (background {plan.theme}, music {'on' if plan.music else 'off'})\n"
                    f"BRAIN TEST NUMBER\n#{plan.episode}\n", encoding="utf-8")


def produce(seed: int | None = None, quality: str = "draft", background: str = "random", music: bool = False,
            history=None, output_root: Path | None = None, progress: Callable[[float], None] | None = None,
            planning: Callable[[str], None] | None = None) -> dict:
    """Render a Brain Test. Draft: a temporary preview (not in history, and it does not use up a number). Final: saved to
    output/longform with its thumbnail and title/description/chapters text, and committed to the generation history."""
    from .history import HistoryStore
    ensure_directories()
    history = history or HistoryStore()
    known = history.load()
    episode = episode_number(history)
    rng = random.Random()
    plan = None
    for _ in range(10):
        candidate_seed = seed if seed is not None else rng.randrange(2**31)
        candidate = build_plan(candidate_seed, background, music, episode, planning)
        if candidate.fingerprint not in known or quality == "draft":
            plan = candidate
            break
        if seed is not None:
            raise ValueError("This seed's Brain Test was already produced; pick another seed.")
    if plan is None:
        raise RuntimeError("Could not find an unused Brain Test")
    root = output_root or OUTPUT_DIR
    if quality == "draft":
        folder = (DATA_DIR / "longform_previews" if output_root is None else root / "previews") / uuid4().hex
        video, thumb, text = folder / "braintest_preview.mp4", folder / "braintest_preview.jpg", folder / "braintest_preview.txt"
        try:
            elapsed = render_video(plan, video, "draft", progress)
            render_thumbnail(plan).save(thumb, format="JPEG", quality=92, optimize=True)
            write_text(plan, text)
        except BaseException:  # includes a Streamlit stop: never leave half a preview behind
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return {"plan": plan, "video": video, "thumbnail": thumb, "text": text, "elapsed": elapsed, "sequence": None, "episode": episode}
    folder = root / "longform"
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f".puzzly-{uuid4().hex}"
    temp_video, temp_thumb = temporary.with_suffix(".mp4"), temporary.with_suffix(".jpg")
    paths: dict[str, Path] = {}

    def finalize_files(sequence_no: int) -> tuple[str, str]:
        stem = f"PZ_{sequence_no:04d}_{PUZZLE_TYPE}"
        video, thumb, text = folder / f"{stem}.mp4", folder / f"{stem}.jpg", folder / f"{stem}.txt"
        if video.exists() or thumb.exists():
            raise FileExistsError(f"Output already exists for sequence {sequence_no}")
        temp_video.replace(video)
        paths["video"] = video
        temp_thumb.replace(thumb)
        paths["thumbnail"] = thumb
        write_text(plan, text)
        paths["text"] = text
        return video.name, thumb.name

    spec_json = json.dumps({"version": VERSION, "seed": plan.seed, "background": plan.theme, "music": plan.music, "episode": episode})
    try:
        elapsed = render_video(plan, temp_video, "final", progress)
        render_thumbnail(plan).save(temp_thumb, format="JPEG", quality=92, optimize=True)
        record = history.commit_success(puzzle_type=PUZZLE_TYPE, difficulty="hard", seed=plan.seed,
                                        fingerprint=plan.fingerprint, finalize_files=finalize_files,
                                        spec_json=spec_json, quality="final")
    except BaseException:
        temp_video.unlink(missing_ok=True)
        temp_thumb.unlink(missing_ok=True)
        for path in paths.values():
            path.unlink(missing_ok=True)
        raise
    return {"plan": plan, "elapsed": elapsed, "sequence": record.sequence_no, "episode": episode, **paths}
