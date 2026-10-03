"""YouTube long-form video (16:9): a Quick Math brain test built from the Shorts games.

About nine minutes, all generated locally:
  intro -> ROUND 1 Shape Equations (10) -> ROUND 2 Missing Signs (10) -> LUCKY BREAK (Bounce Arena, +1 bonus)
  -> ROUND 3 final round, the hardest levels of both (10) -> FINAL SCORE (?/31) -> end card.
Every round opens with a how-to card and closes with a score card, so viewers always know what to do, what comes next,
and how to count their points (one point per correct answer, kept by the viewer). During a game the puzzle plays on a
centred stage (the Shorts frame, cropped) with a left panel (round, how to play, puzzle n/10) and a right panel
(scoreboard, "+1 point" toast, up next). Levels, timers and difficulty are exactly the Shorts settings.
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
from PIL import Image, ImageDraw, ImageFilter

from .config import (AUDIO_RATE, DARK_THEMES, THEME_CHOICES, glow_strength, DATA_DIR, FPS, OUTPUT_DIR, PUZZLE_FIT_PALETTE as PALETTE, RenderQuality,
                     ensure_directories, quick_math_average_round)
from .models import RoundSpec, VideoSpec

LOGGER = logging.getLogger(__name__)

VERSION = "longform_quick_math_v1"
PUZZLE_TYPE = "longform_quick_math"
ROUND_SIZE = 10
BEST_SCORE = 3 * ROUND_SIZE + 1  # three rounds plus the lucky bonus point
QUALITIES = {  # landscape profiles; the stage renders the Shorts frames at their own size, so no supersampling
    "draft": RenderQuality((960, 540), 1, 15, "ultrafast", 28),
    "final": RenderQuality((1920, 1080), 1, 30, "medium", 18),
}
CARD_SECONDS = {"intro": 7.0, "round_intro": 6.5, "round_end": 5.5, "luck_intro": 6.0, "luck_end": 4.5,
                "final_score": 11.0, "end": 6.0}
STAGE_TOP, STAGE_HEIGHT = 50.0, 980.0  # logical 1920x1080 px
PORTRAIT_ROWS = (95.0, 1650.0)  # rows of the 1080x1920 Shorts frame shown on the stage
RATINGS = ((0, 10, "WARMING UP", "#9AA3C7"), (11, 18, "SHARP MIND", "#3DA9FF"), (19, 25, "MATH MACHINE", "#2EE6C5"),
           (26, BEST_SCORE, "UNSTOPPABLE", "#FFC24B"))
HOW_TO = {
    "shapes": ("Find each shape's value", "Solve the last line", "× and ÷ come first"),
    "operators": ("Fill the boxes with + − × ÷", "Make the equation true", "× and ÷ come first"),
    "mixed": ("Shapes: find each value", "Signs: fill the boxes", "Only the hardest levels"),
    "luck": ("Pick a ball before time runs out", "Last ball in the ring wins", "Yours wins = +1 bonus"),
}


@dataclass(frozen=True)
class Segment:
    kind: str  # intro, round_intro, round, round_end, luck_intro, luck, luck_end, final_score, end
    start: float
    duration: float
    title: str = ""
    round_no: int = 0  # 1..3 for rounds, 0 otherwise
    spec: VideoSpec | None = None
    fmt: str = ""  # shapes, operators, mixed, luck

    @property
    def end(self) -> float:
        return self.start + self.duration


@dataclass
class LongformPlan:
    seed: int
    theme: str
    music: bool
    segments: list[Segment]
    rounds: list[VideoSpec]
    luck: VideoSpec
    hero: dict
    fingerprint: str
    chapters: list[tuple[float, str]] = field(default_factory=list)

    @property
    def total_duration(self) -> float:
        return round(self.segments[-1].end, 3)

    @property
    def puzzle_count(self) -> int:
        return sum(spec.round_count for spec in self.rounds)

    def metadata(self) -> dict[str, str]:
        title = f"TEST YOUR MATH BRAIN 🧠 {self.puzzle_count} Puzzles, No Calculator | Can You Score 25+?"
        chapter_lines = "\n".join(f"{_clock(start)} {name}" for start, name in self.chapters)
        description = (
            f"{self.puzzle_count} math puzzles in 3 rounds, plus a lucky break. No calculator: grab a pen and keep your score "
            f"(+1 for every correct answer, +1 bonus if your ball wins). Pause anytime.\n\n{chapter_lines}\n\n"
            f"What was your score out of {BEST_SCORE}? Tell us in the comments!\n\n"
            "#math #brainteaser #puzzle #mathpuzzle #brainchallenge")
        tags = "math puzzle,brain test,math challenge,brain teaser,no calculator,mental math,puzzly for you"
        return {"title": title, "description": description, "tags": tags}


def _clock(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


# ---------------------------------------------------------------- plan

def _retag(spec: VideoSpec, metadata: dict) -> VideoSpec:
    return replace(spec, metadata={**spec.metadata, **metadata})


def _final_round(seed: int, metadata: dict) -> VideoSpec:
    """The hardest levels (tiers 2-3) of both formats, alternating, easiest first."""
    from .puzzles import quick_math
    shapes = [item for item in quick_math.generate(seed, "hard", "shapes", round_count=ROUND_SIZE).rounds if item.data["tier"] >= 2]
    signs = [item for item in quick_math.generate(seed + 1, "hard", "operators", round_count=ROUND_SIZE).rounds
             if item.data["tier"] >= 2]
    ordered = []
    for pair in zip(sorted(shapes, key=lambda item: item.data["tier"]), sorted(signs, key=lambda item: item.data["tier"])):
        ordered.extend(pair)
    rounds = tuple(replace(item, index=index) for index, item in enumerate(ordered[:ROUND_SIZE]))
    stable_id = sha256(f"{VERSION}:final:{seed}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "quick_math", seed, "hard", "numbers", rounds, 1.0,
                     quick_math_average_round("hard", [item.data["tier"] for item in rounds]), 1.6, "mixed", metadata=metadata)


def build_plan(seed: int, background: str = "random", music: bool = False) -> LongformPlan:
    from .puzzles import bounce_arena, quick_math
    from .validation import round_errors
    from .visuals.quick_math import schedule
    rng = random.Random(f"{VERSION}:{seed}")
    # The theme has its own generator, so choosing a background never changes the puzzles of a seed.
    theme = background if background in DARK_THEMES else random.Random(f"{VERSION}:theme:{seed}").choice(sorted(THEME_CHOICES))
    metadata = {"background": theme, **({"music": "on"} if music else {})}
    seeds = [rng.randrange(2**31) for _ in range(4)]
    rounds = [
        _retag(quick_math.generate(seeds[0], "hard", "shapes", round_count=ROUND_SIZE), metadata),
        _retag(quick_math.generate(seeds[1], "hard", "operators", round_count=ROUND_SIZE), metadata),
        _final_round(seeds[2], metadata),
    ]
    luck = _retag(bounce_arena.generate(seeds[3]), metadata)
    fingerprints = [item.fingerprint() for spec in rounds for item in spec.rounds]
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("a puzzle repeats inside the long-form video")
    for spec in rounds:
        for item in spec.rounds:
            problems = round_errors(item, "hard")
            if problems:
                raise ValueError(f"invalid long-form puzzle: {problems}")
    if round_errors(luck.rounds[0], None):
        raise ValueError("invalid lucky break")
    names = ("SHAPE EQUATIONS", "MISSING SIGNS", "FINAL ROUND")
    formats = ("shapes", "operators", "mixed")
    segments: list[Segment] = []
    clock = 0.0

    def add(kind: str, duration: float, **extra) -> None:
        nonlocal clock
        segments.append(Segment(kind, round(clock, 4), round(duration, 4), **extra))
        clock += duration

    def play(number: int) -> None:
        spec = rounds[number - 1]
        levels = schedule(spec)
        add("round_intro", CARD_SECONDS["round_intro"], title=names[number - 1], round_no=number, spec=spec, fmt=formats[number - 1])
        add("round", sum(duration for _, duration in levels), title=names[number - 1], round_no=number, spec=spec, fmt=formats[number - 1])
        add("round_end", CARD_SECONDS["round_end"], title=names[number - 1], round_no=number, spec=spec, fmt=formats[number - 1])

    add("intro", CARD_SECONDS["intro"], title="Intro & how to play")
    play(1)
    play(2)
    add("luck_intro", CARD_SECONDS["luck_intro"], title="LUCKY BREAK", spec=luck, fmt="luck")
    add("luck", float(luck.round_duration), title="LUCKY BREAK", spec=luck, fmt="luck")
    add("luck_end", CARD_SECONDS["luck_end"], title="LUCKY BREAK", spec=luck, fmt="luck")
    play(3)
    add("final_score", CARD_SECONDS["final_score"], title="Final score")
    add("end", CARD_SECONDS["end"], title="Thanks for playing")
    chapters = [(0.0, "Intro & how to play")]
    for position, segment in enumerate(segments):
        name = {"round_intro": f"Round {segment.round_no}: {segment.title.title()}", "luck_intro": "Lucky Break: Bounce Arena",
                "final_score": "Final Score"}.get(segment.kind)
        if name:
            start = segment.start
            if start - chapters[-1][0] < 10:  # YouTube chapters must last at least 10 s: start at the game itself
                start = segments[position + 1].start
            chapters.append((start, name))
    fingerprint = sha256(json.dumps([VERSION, fingerprints, luck.fingerprint()]).encode()).hexdigest()[:20]
    hero = rounds[0].rounds[-1].data  # the hardest Shape Equations board of round 1 (the thumbnail shows it, never its answer)
    return LongformPlan(seed, theme, music, segments, rounds, luck, hero, fingerprint, chapters)


def estimated_duration() -> float:
    """A typical video length in seconds (rounds depend on their level mix; the lucky break on physics)."""
    from .config import quick_math_round
    from .config import quick_math_tiers
    shapes = sum(quick_math_round("hard", tier) for tier in quick_math_tiers(ROUND_SIZE))
    final = 3 * quick_math_round("hard", 2) * 2 + 2 * quick_math_round("hard", 3) * 2
    return 2 * shapes + final + 22.0 + sum(CARD_SECONDS.values()) + 2 * CARD_SECONDS["round_intro"] + 2 * CARD_SECONDS["round_end"]


# ---------------------------------------------------------------- drawing helpers

def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _ease(value: float) -> float:
    value = _clamp(value)
    return 1 - (1 - value) ** 3


@lru_cache(maxsize=8)
def _landscape_background(size: tuple[int, int], theme: str) -> Image.Image:
    width, height = size
    top, bottom, glow = (np.array(_rgb(value), np.float32) for value in DARK_THEMES.get(theme, DARK_THEMES["violet"]))
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    t = (y / max(1, height - 1))[..., None]
    rgb = top * (1 - t) + bottom * t
    scale = width / 1920
    for gx, gy, radius, strength in ((960, 470, 760, glow_strength(theme, .42)), (300, 900, 520, glow_strength(theme, .14)),
                                     (1650, 200, 480, glow_strength(theme, .12))):
        d = np.hypot(x - gx * scale, y - gy * scale) / (radius * scale)
        rgb += (glow - top) * (np.exp(-d * d) * strength)[..., None]
    vignette = np.hypot(x / width - .5, (y / height - .5) * .9)
    rgb *= (1 - np.clip(vignette - .32, 0, 1) * .7)[..., None]
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(image, "RGBA")
    step, radius = 54 * scale, max(1, round(1.6 * scale))
    for row in range(int(height / step) + 1):
        for column in range(int(width / step) + 1):
            px, py = column * step + (step / 2 if row % 2 else 0), row * step
            draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=(255, 255, 255, 16))
    return image


def _text(image, center, text, size, fill, scale, opacity=1.0, zoom=1.0, weight="bold"):
    from .visuals.puzzle_fit import _text as draw_text
    from .visuals.text import font
    draw_text(image, (center[0] * scale, center[1] * scale), text, font(max(4, round(size * scale)), weight), fill, opacity, zoom)


def _text_left(image, left, center_y, text, size, fill, scale, weight="bold", opacity=1.0):
    from .visuals.text import font
    face = font(max(4, round(size * scale)), weight)
    ImageDraw.Draw(image, "RGBA").text((left * scale, center_y * scale), text, font=face,
                                       fill=_rgb(fill) + (round(255 * opacity),), anchor="lm")


def _surface(image, box, radius, fill, scale, outline=None, width=2.0, alpha=235):
    from .visuals.effects import rounded_surface
    x1, y1, x2, y2 = (value * scale for value in box)
    rounded_surface(image, (x1, y1, x2, y2), radius * scale, _rgb(fill) + (alpha,),
                    outline=(_rgb(outline) + (255,)) if outline else None, width=max(1, round(width * scale)) if outline else 0)


def _check(image, center, size, color, scale):
    x, y, r = center[0] * scale, center[1] * scale, size * scale
    ImageDraw.Draw(image).line(((x - r, y), (x - r * .3, y + r * .7), (x + r, y - r * .7)), fill=_rgb(color),
                               width=max(2, round(r * .35)), joint="curve")


# ---------------------------------------------------------------- stage and panels

def _stage(image: Image.Image, draw_portrait: Callable[[tuple[int, int]], Image.Image], scale: float,
           rows: tuple[float, float] = PORTRAIT_ROWS) -> None:
    """The Shorts frame on a glowing rounded stage in the middle of the 16:9 frame (`rows` of it are shown)."""
    factor = STAGE_HEIGHT / (rows[1] - rows[0])
    portrait_w, portrait_h = max(2, round(1080 * factor * scale)), max(2, round(1920 * factor * scale))
    frame = draw_portrait((portrait_w, portrait_h)).convert("RGB")
    top = round(rows[0] * factor * scale)
    height = round(STAGE_HEIGHT * scale)
    crop = frame.crop((0, top, portrait_w, top + height))
    x, y = round(960 * scale - portrait_w / 2), round(STAGE_TOP * scale)
    radius = round(34 * scale)
    image.paste(Image.new("RGB", image.size, (0, 0, 0)), (0, 0), _stage_shadow(image.size, (x, y, portrait_w, height), radius, scale))
    image.paste(crop, (x, y), _rounded_mask(crop.size, radius))
    ImageDraw.Draw(image).rounded_rectangle((x, y, x + crop.width - 1, y + crop.height - 1), radius=radius,
                                            outline=_rgb(PALETTE["surface_edge"]), width=max(1, round(3 * scale)))


@lru_cache(maxsize=4)
def _stage_shadow(size: tuple[int, int], box: tuple[int, int, int, int], radius: int, scale: float) -> Image.Image:
    x, y, width, height = box
    shadow = Image.new("L", size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x - 6 * scale, y + 10 * scale, x + width + 6 * scale, y + height + 22 * scale),
                                             radius=radius, fill=190)
    return shadow.filter(ImageFilter.GaussianBlur(max(1, 22 * scale)))


def _level_at(spec: VideoSpec, local: float) -> tuple[int, float]:
    from .visuals.quick_math import schedule
    starts = [start - spec.intro_duration for start, _ in schedule(spec)]
    index = max(0, bisect_right(starts, local) - 1)
    return index, local - starts[index]


def _scoreboard(image, plan: LongformPlan, active: str, scale: float, toast: float = 0.0) -> None:
    """Right panel: the viewer's score sheet (blank lines they fill themselves), the +1 toast, and what comes next."""
    rows = (("r1", "ROUND 1", ROUND_SIZE), ("r2", "ROUND 2", ROUND_SIZE), ("luck", "LUCKY BREAK", 1),
            ("r3", "ROUND 3", ROUND_SIZE), ("total", "TOTAL", BEST_SCORE))
    order = [key for key, _, _ in rows]
    _surface(image, (1340, 90, 1850, 700), 30, PALETTE["surface"], scale, PALETTE["surface_edge"], 2.5, 225)
    _text(image, (1595, 140), "YOUR SCORE", 40, PALETTE["text_light"], scale)
    _text(image, (1595, 186), "+1 for every correct answer", 26, PALETTE["text_muted"], scale, weight="semibold")
    for index, (key, label, best) in enumerate(rows):
        y = 262 + index * 84
        current = key == active
        done = active in order and order.index(key) < order.index(active) and key != "total"
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
        _surface(image, (1395, 664 - 30 * pop, 1795, 664 + 30 * pop), 30, PALETTE["success"], scale, alpha=250)
        if pop > .5:
            _text(image, (1595, 662), "RIGHT?  +1 POINT", 32, PALETTE["background"], scale)


def _up_next(image, text: str, scale: float) -> None:
    _surface(image, (1340, 730, 1850, 880), 30, PALETTE["surface"], scale, PALETTE["surface_edge"], 2.5, 225)
    _text(image, (1595, 776), "UP NEXT", 26, PALETTE["text_muted"], scale)
    _text(image, (1595, 830), text, 34, PALETTE["text_light"], scale)


def _next_label(plan: LongformPlan, segment: Segment) -> str:
    later = [item for item in plan.segments if item.start >= segment.end]
    for item in later:
        if item.kind == "round_intro":
            return f"ROUND {item.round_no}: {item.title}"
        if item.kind == "luck_intro":
            return "LUCKY BREAK"
        if item.kind == "final_score":
            return "YOUR FINAL SCORE"
    return "THE END"


def _how_to_panel(image, segment: Segment, scale: float, level: int = 0, total: int = 0, pulse: float = 0.0,
                  local: float = 0.0) -> None:
    """Left panel: round, how to play, and progress."""
    heading = "LUCKY BREAK" if segment.fmt == "luck" else f"ROUND {segment.round_no} / 3"
    title = "BOUNCE ARENA" if segment.fmt == "luck" else segment.title
    _surface(image, (70, 90, 580, 880), 30, PALETTE["surface"], scale, PALETTE["surface_edge"], 2.5, 225)
    _text(image, (325, 150), heading, 30, PALETTE["accent"], scale)
    from .visuals.text import fitted_font
    face_size = fitted_font(title, round(440 * scale), round(52 * scale), max(4, round(30 * scale))).size / scale
    _text(image, (325, 212), title, face_size, PALETTE["text_light"], scale)
    _text(image, (325, 300), "HOW TO PLAY", 24, PALETTE["text_muted"], scale)
    for index, step in enumerate(HOW_TO[segment.fmt]):
        y = 362 + index * 78
        _surface(image, (106, y - 26, 158, y + 26), 26, PALETTE["primary"], scale, alpha=255)
        _text(image, (132, y - 2), str(index + 1), 28, PALETTE["text_light"], scale)
        step_size = fitted_font(step, round(370 * scale), round(27 * scale), max(4, round(20 * scale))).size / scale
        _text_left(image, 178, y, step, step_size, PALETTE["text_light"], scale, weight="semibold")
    if total:
        _text(image, (325, 648), f"PUZZLE {level + 1} / {total}", 36, PALETTE["text_light"], scale)
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
        _text(image, (325, 800), "Pause anytime", 26, PALETTE["text_muted"], scale, weight="semibold")
    else:
        from .config import BOUNCE_SELECTION_DURATION
        data = segment.spec.rounds[0].data
        if local < BOUNCE_SELECTION_DURATION:
            prompt, color = "Pick your ball NOW", PALETTE["warning"]
        elif local < BOUNCE_SELECTION_DURATION + float(data["simulation_duration"]):
            prompt, color = "Is your ball still in?", PALETTE["text_light"]
        else:
            prompt, color = "Did your ball win?", PALETTE["success"]
        _text(image, (325, 700), prompt, 34, color, scale)
        _text(image, (325, 760), "+1 bonus if it survives", 26, PALETTE["text_muted"], scale, weight="semibold")


def _round_frame(plan: LongformPlan, segment: Segment, local: float, size: tuple[int, int]) -> Image.Image:
    from .visuals.puzzle_fit import use_theme
    from .visuals.quick_math import draw_operators_round, draw_quick_math_round, phases
    scale = size[0] / 1920
    spec = segment.spec
    image = _landscape_background(size, plan.theme).copy()
    index, level_local = _level_at(spec, local)
    item = spec.rounds[index]
    use_theme(spec)
    painter = draw_operators_round if item.data.get("format") == "operators" else draw_quick_math_round
    _stage(image, lambda portrait: painter(spec, index, level_local, portrait), scale)
    times = phases(item)
    _how_to_panel(image, segment, scale, index, spec.round_count, abs(math.sin(local * 3)))
    toast = level_local - times["answer"] if level_local >= times["answer"] else 0.0
    _scoreboard(image, plan, f"r{segment.round_no}", scale, toast)
    _up_next(image, _next_label(plan, segment) if index == spec.round_count - 1 else f"PUZZLE {index + 2} / {spec.round_count}", scale)
    return _edge_fade(image, plan, segment, local, size)


def _luck_frame(plan: LongformPlan, segment: Segment, local: float, size: tuple[int, int]) -> Image.Image:
    from .visuals.bounce_arena import draw_bounce_round
    from .visuals.puzzle_fit import use_theme
    scale = size[0] / 1920
    image = _landscape_background(size, plan.theme).copy()
    use_theme(segment.spec)
    _stage(image, lambda portrait: draw_bounce_round(segment.spec, min(local, segment.spec.round_duration - 1e-3), portrait), scale)
    _how_to_panel(image, segment, scale, local=local)
    _scoreboard(image, plan, "luck", scale)
    _up_next(image, _next_label(plan, segment), scale)
    return _edge_fade(image, plan, segment, local, size)


EDGE_FADE = .3


def _edge_fade(image: Image.Image, plan: LongformPlan, segment: Segment, local: float, size: tuple[int, int]) -> Image.Image:
    """Soft 0.3 s fade from and to the plain background, so games never hard-cut against the cards."""
    amount = _clamp(min(local, segment.duration - local) / EDGE_FADE)
    return image if amount >= 1 else Image.blend(_landscape_background(size, plan.theme), image, amount)


# ---------------------------------------------------------------- cards (static layer drawn once at 2x, then animated)

CARD_2X = (3840, 2160)


def _title3d(image, center, text, size, top, bottom, glow, depth=22, max_width=1700) -> None:
    from .covers import fitted, text3d
    text3d(image, (center[0] * 2, center[1] * 2), text, fitted(text, max_width, size), top, bottom, depth * 2, glow=glow)


@lru_cache(maxsize=16)
def _card_static(plan_key: str, segment_index: int, size: tuple[int, int]) -> Image.Image:
    from .visuals.puzzle_fit import use_theme
    plan = _PLANS[plan_key]
    segment = plan.segments[segment_index]
    use_theme(plan.rounds[0])  # cards drawn after the lucky break must not keep its palette
    image = _landscape_background(CARD_2X, plan.theme).convert("RGBA")
    glow = DARK_THEMES.get(plan.theme, DARK_THEMES["violet"])[2]
    s = 2.0  # logical 1920x1080 -> 2x
    kind = segment.kind
    accent, gold = PALETTE["accent"], "#FFC24B"
    if kind == "intro":
        _title3d(image, (960, 250), "TEST YOUR", 190, "#FFFFFF", "#CDD3EE", glow)
        _title3d(image, (960, 450), "MATH BRAIN", 230, accent, "#7C5CFF", accent)
        _text(image, (960, 640), f"{plan.puzzle_count} PUZZLES  ·  3 ROUNDS  ·  1 LUCKY BREAK", 46, PALETTE["text_light"], s)
        chips = (("ROUND 1", "Shape Equations"), ("ROUND 2", "Missing Signs"), ("BREAK", "Bounce Arena"), ("ROUND 3", "Final Round"))
        for index, (label, name) in enumerate(chips):
            x = 330 + index * 420
            _surface(image, (x - 185, 730, x + 185, 850), 28, PALETTE["surface"], s, PALETTE["surface_edge"], 2.5, 235)
            _text(image, (x, 770), "LUCKY BREAK" if label == "BREAK" else label, 28, gold if label == "BREAK" else accent, s)
            _text(image, (x, 814), name, 30, PALETTE["text_light"], s, weight="semibold")
        _text(image, (960, 935), "No calculator. Grab a pen and keep your score: +1 for every correct answer.", 34,
              PALETTE["text_muted"], s, weight="semibold")
    elif kind == "round_intro":
        from .visuals.puzzle_fit import use_theme
        from .visuals.quick_math import draw_operators_round, draw_quick_math_round
        spec = segment.spec
        first = spec.rounds[0]
        use_theme(spec)
        painter = draw_operators_round if first.data.get("format") == "operators" else draw_quick_math_round
        _text(image, (560, 170), f"ROUND {segment.round_no} / 3", 50, accent, s)
        _title3d(image, (560, 300), segment.title, 150, "#FFFFFF", "#CDD3EE", glow, max_width=1000)
        _text(image, (560, 430), "HOW TO PLAY", 32, PALETTE["text_muted"], s)
        for index, step in enumerate(HOW_TO[segment.fmt]):
            y = 510 + index * 100
            _surface(image, (190, y - 36, 262, y + 36), 36, PALETTE["primary"], s, alpha=255)
            _text(image, (226, y - 3), str(index + 1), 38, PALETTE["text_light"], s)
            _text_left(image, 295, y, step, 44, PALETTE["text_light"], s, weight="semibold")
        _text(image, (560, 850), f"{spec.round_count} puzzles  ·  +1 point each  ·  pause anytime", 36, gold, s)
        preview = _preview(painter, spec, 1.2)
        image.paste(preview, (round(1240 * s), round(80 * s)), _rounded_mask(preview.size, round(34 * s)))
    elif kind == "round_end":
        _title3d(image, (960, 230), f"ROUND {segment.round_no} COMPLETE", 150, "#FFFFFF", "#CDD3EE", glow)
        _text(image, (960, 380), "How many did you get?", 60, PALETTE["text_light"], s)
        _surface(image, (660, 440, 1260, 640), 40, PALETTE["surface"], s, accent, 4, 240)
        ImageDraw.Draw(image).line(((760 * s, 590 * s), (960 * s, 590 * s)), fill=_rgb(accent), width=round(8 * s))
        _text(image, (1090, 540), f"/ {segment.spec.round_count}", 110, PALETTE["text_light"], s)
        _text(image, (960, 710), "Write it down. You'll add it all up at the end!", 40, gold, s)
        _text(image, (960, 880), f"UP NEXT:  {_next_label(plan, segment)}", 46, PALETTE["text_muted"], s)
    elif kind == "luck_intro":
        _text(image, (960, 170), "BREAK TIME", 52, gold, s)
        _title3d(image, (960, 320), "LUCKY BREAK", 200, gold, "#FF8A3D", gold)
        _text(image, (960, 490), "Now let's see how lucky you are!", 62, PALETTE["text_light"], s)
        for index, step in enumerate(HOW_TO["luck"]):
            y = 610 + index * 92
            _surface(image, (560, y - 34, 628, y + 34), 34, PALETTE["primary"], s, alpha=255)
            _text(image, (594, y - 3), str(index + 1), 36, PALETTE["text_light"], s)
            _text_left(image, 660, y, step, 44, PALETTE["text_light"], s, weight="semibold")
        _text(image, (960, 950), "+1 BONUS POINT if your ball survives", 44, accent, s)
    elif kind == "luck_end":
        from .visuals.bounce_arena import ball_sprite
        data = segment.spec.rounds[0].data
        ball = ball_sprite(data["colors"][int(data["winner"])], round(300 * s))
        image.alpha_composite(ball, (round(960 * s - ball.width / 2), round(430 * s - ball.height / 2)))
        _title3d(image, (960, 150), "DID YOUR BALL WIN?", 130, "#FFFFFF", "#CDD3EE", glow)
        _text(image, (960, 690), "If this was your pick: +1 BONUS POINT", 56, accent, s)
        _text(image, (960, 880), f"UP NEXT:  {_next_label(plan, segment)}", 46, PALETTE["text_muted"], s)
    elif kind == "final_score":
        _title3d(image, (960, 150), "FINAL SCORE", 170, gold, "#FF8A3D", gold)
        parts = ("ROUND 1", "ROUND 2", "BONUS", "ROUND 3")
        for index, label in enumerate(parts):
            x = 330 + index * 330
            _surface(image, (x - 140, 270, x + 140, 390), 26, PALETTE["surface"], s, PALETTE["surface_edge"], 2.5, 240)
            _text(image, (x, 330), label, 36, PALETTE["text_light"], s)
            if index < 3:
                _text(image, (x + 165, 330), "+", 50, PALETTE["text_muted"], s)
        _text(image, (1585, 330), f"= ? / {BEST_SCORE}", 70, accent, s)
        for index, (low, high, label, color) in enumerate(RATINGS):
            y = 480 + index * 105
            _surface(image, (520, y - 42, 1400, y + 42), 30, PALETTE["surface"], s, color, 3, 240)
            _text_left(image, 570, y, f"{low}–{high}", 44, color, s)
            _text_left(image, 820, y, label, 48, PALETTE["text_light"], s)
        _text(image, (960, 960), "Comment your score below!", 50, PALETTE["text_light"], s)
    elif kind == "end":
        _title3d(image, (960, 260), "THANKS FOR PLAYING", 170, "#FFFFFF", "#CDD3EE", glow)
        _text(image, (960, 420), "Want another brain test? More on the channel.", 52,
              PALETTE["text_light"], s)
        _surface(image, (640, 520, 1280, 660), 70, "#FF3B5C", s, alpha=255)
        ImageDraw.Draw(image).ellipse((700 * s, 555 * s, 770 * s, 625 * s), outline=(255, 255, 255), width=round(8 * s))
        ImageDraw.Draw(image).line(((713 * s, 590 * s), (757 * s, 590 * s)), fill=(255, 255, 255), width=round(8 * s))
        ImageDraw.Draw(image).line(((735 * s, 568 * s), (735 * s, 612 * s)), fill=(255, 255, 255), width=round(8 * s))
        _text(image, (1010, 588), "SUBSCRIBE", 70, "#FFFFFF", s)
        _text(image, (960, 800), "Comment your final score and challenge a friend!", 44, "#FFC24B", s)
        from .branding import draw_profile_mark
        from .visuals.text import font
        brand_width = ImageDraw.Draw(image).textlength("Puzzly for You", font=font(round(46 * s))) / s
        left = 960 - (80 + 20 + brand_width) / 2  # mark, gap, name: centred as one group
        draw_profile_mark(image, (round((left + 40) * s), round(930 * s)), round(80 * s), PALETTE)
        _text_left(image, left + 100, 930, "Puzzly for You", 46, PALETTE["text_muted"], s)
    return image.convert("RGB").resize(size, Image.Resampling.LANCZOS)


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _preview(painter, spec: VideoSpec, local: float) -> Image.Image:
    """A 2x stage-sized preview of a round's first puzzle (for the how-to card)."""
    height = round(920 * 2)
    factor = height / (PORTRAIT_ROWS[1] - PORTRAIT_ROWS[0])
    frame = painter(spec, 0, local, (round(1080 * factor), round(1920 * factor))).convert("RGB")
    top = round(PORTRAIT_ROWS[0] * factor)
    return frame.crop((0, top, frame.width, top + height))


_PLANS: dict[str, LongformPlan] = {}


def _card_frame(plan: LongformPlan, segment_index: int, local: float, size: tuple[int, int]) -> Image.Image:
    segment = plan.segments[segment_index]
    key = f"{plan.fingerprint}:{plan.theme}"  # the same puzzles on another background are a different card
    _PLANS[key] = plan
    static = _card_static(key, segment_index, size)
    appear = _ease(local / .45)
    fade_out = _clamp((segment.duration - local) / .3)
    zoom = .965 + .035 * appear
    frame = static
    if zoom < .999:
        width, height = size
        scaled = static.resize((max(2, round(width * zoom)), max(2, round(height * zoom))), Image.Resampling.BILINEAR)
        frame = _landscape_background(size, plan.theme).copy()
        frame.paste(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
        frame = Image.blend(_landscape_background(size, plan.theme), frame, appear)
    else:
        frame = static.copy()
    scale = size[0] / 1920
    if segment.kind in ("round_intro", "intro") and segment.duration - local <= 3.0:
        remaining = max(1, math.ceil(segment.duration - local - 1e-6))
        beat = (segment.duration - local) % 1.0
        label = str(remaining)
        if segment.kind == "round_intro":  # under the how-to steps, clear of the preview
            _surface(frame, (400, 915, 720, 1015), 50, PALETTE["accent"], scale, alpha=255)
            _text(frame, (515, 963), "STARTS IN", 34, PALETTE["background"], scale)
            _text(frame, (660, 962), label, 60, PALETTE["background"], scale, zoom=.85 + .3 * beat)
        else:  # the intro hands over to round 1's own how-to card
            _text(frame, (960, 1030), "ROUND 1 IS NEXT", 40, PALETTE["accent"], scale, zoom=.95 + .1 * beat)
    if segment.kind == "end" and local >= 1.2:  # a finger taps the subscribe button, which flashes and ripples
        travel = _ease((local - 1.2) / .5)
        press = .92 if 1.7 <= local < 1.85 else 1.0
        x, y = (755 + 320 * (1 - travel)) * scale, (612 + 240 * (1 - travel)) * scale  # the fingertip, from the right
        draw = ImageDraw.Draw(frame, "RGBA")
        if local >= 1.7:
            ripple = _ease((local - 1.7) / .6)
            r = (30 + 170 * ripple) * scale
            draw.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, round(220 * (1 - ripple))),
                         width=max(2, round(6 * (1 - ripple) * scale) + 1))
        _pointer(frame, (x, y), .8 * press * scale)
    if fade_out < 1:
        frame = Image.blend(_landscape_background(size, plan.theme), frame, fade_out)
    return frame


def _pointer(image: Image.Image, tip: tuple[float, float], scale: float) -> None:
    """A white pointing hand whose index fingertip sits exactly on ``tip``; the hand trails down to the right."""
    x, y = tip
    draw = ImageDraw.Draw(image, "RGBA")
    outline, fill, width = _rgb(PALETTE["background"]) + (230,), (255, 255, 255, 245), max(1, round(4 * scale))

    def box(cx, cy, w, h):
        return (x + (cx - w / 2) * scale, y + (cy - h / 2) * scale, x + (cx + w / 2) * scale, y + (cy + h / 2) * scale)

    shadow = (0, 0, 0, 90)
    draw.rounded_rectangle(box(14, 104, 96, 110), radius=round(34 * scale), fill=shadow)
    draw.rounded_rectangle(box(0, 52, 34, 104), radius=round(17 * scale), fill=fill, outline=outline, width=width)  # index
    for dx, top in ((32, 70), (58, 78), (82, 90)):  # curled fingers
        draw.rounded_rectangle(box(dx, top + 18, 30, 46), radius=round(15 * scale), fill=fill, outline=outline, width=width)
    draw.rounded_rectangle(box(40, 128, 104, 86), radius=round(30 * scale), fill=fill, outline=outline, width=width)  # palm
    draw.rounded_rectangle(box(-4, 106, 30, 60), radius=round(15 * scale), fill=fill, outline=outline, width=width)  # thumb
    draw.rounded_rectangle(box(0, 54, 26, 96), radius=round(13 * scale), fill=fill)  # index over the palm seam


# ---------------------------------------------------------------- frames, audio, render

def segment_at(plan: LongformPlan, t: float) -> tuple[int, Segment]:
    starts = [segment.start for segment in plan.segments]
    index = max(0, min(len(plan.segments) - 1, bisect_right(starts, t) - 1))
    return index, plan.segments[index]


def render_frame(plan: LongformPlan, t: float, size: tuple[int, int]) -> Image.Image:
    t = max(0.0, min(plan.total_duration - 1 / FPS, t))
    index, segment = segment_at(plan, t)
    local = t - segment.start
    if segment.kind == "round":
        return _round_frame(plan, segment, local, size)
    if segment.kind == "luck":
        return _luck_frame(plan, segment, local, size)
    return _card_frame(plan, index, local, size)


def timeline_audio(plan: LongformPlan) -> np.ndarray:
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
        start = max(0, int(at * AUDIO_RATE)); end = min(start + len(sound), len(audio))
        if end > start:
            piece = sound[:end - start] * gain
            audio[start:end] += piece if piece.ndim == 2 else piece[:, None]

    for segment in plan.segments:
        if segment.kind == "round":
            source = spec_audio(segment.spec)
            begin = round(segment.spec.intro_duration * AUDIO_RATE)
            place(segment.start, faded(source[begin:begin + round(segment.duration * AUDIO_RATE)]))
        elif segment.kind == "luck":
            place(segment.start, faded(spec_audio(segment.spec)[:round(segment.duration * AUDIO_RATE)]))
        else:
            place(segment.start + .05, sounds["intro_pop"])
            place(segment.end - .3, sounds["transition_whoosh"])
            if segment.kind == "round_intro":
                for remaining in (3.0, 2.0, 1.0):
                    place(segment.end - remaining, sounds["pulse"])
            elif segment.kind == "intro":
                place(segment.end - 1.0, sounds["pulse"])
            elif segment.kind in ("round_end", "luck_end"):
                place(segment.start + .35, sounds["answer_ding"])
            elif segment.kind == "final_score":
                place(segment.start + .4, sounds["answer_ding"])
                place(segment.start + .7, sounds["sparkle"])
            elif segment.kind == "luck_intro":
                for index in range(3):
                    place(segment.start + .8 + index * .12, sounds["object_pop"])
    return finalize_mix(audio)


def render_video(plan: LongformPlan, output_path: Path, quality: str = "draft",
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
    LOGGER.info("Rendered long-form %s duration=%.1fs in %.1fs", output_path, plan.total_duration, elapsed)
    return elapsed


def render_thumbnail(plan: LongformPlan) -> Image.Image:
    from .longform_cover import render_longform_thumbnail
    from .visuals.puzzle_fit import use_theme
    use_theme(plan.rounds[0])
    return render_longform_thumbnail(plan.theme, plan.hero, plan.puzzle_count, BEST_SCORE)


def write_text(plan: LongformPlan, path: Path) -> None:
    meta = plan.metadata()
    path.write_text(f"TITLE\n{meta['title']}\n\nDESCRIPTION\n{meta['description']}\n\nTAGS\n{meta['tags']}\n\n"
                    f"SEED\n{plan.seed} (background {plan.theme}, music {'on' if plan.music else 'off'})\n", encoding="utf-8")


def produce(seed: int | None = None, quality: str = "draft", background: str = "random", music: bool = False,
            history=None, output_root: Path | None = None,
            progress: Callable[[float], None] | None = None) -> dict:
    """Render a long-form video. Draft: a temporary preview (not in history). Final: saved to output/longform with its
    thumbnail and title/description/chapters text, and committed to the generation history."""
    from .history import HistoryStore
    ensure_directories()
    history = history or HistoryStore()
    known = history.load()
    rng = random.Random()
    plan = None
    for attempt in range(20):
        candidate_seed = seed if seed is not None else rng.randrange(2**31)
        candidate = build_plan(candidate_seed, background, music)
        if candidate.fingerprint not in known or quality == "draft":
            plan = candidate
            break
        if seed is not None:
            raise ValueError("This seed's long-form video was already produced; pick another seed.")
    if plan is None:
        raise RuntimeError("Could not find an unused long-form video")
    root = output_root or OUTPUT_DIR
    if quality == "draft":
        folder = (DATA_DIR / "longform_previews" if output_root is None else root / "previews") / uuid4().hex
        video, thumb, text = folder / "longform_preview.mp4", folder / "longform_preview.jpg", folder / "longform_preview.txt"
        try:
            elapsed = render_video(plan, video, "draft", progress)
            render_thumbnail(plan).save(thumb, format="JPEG", quality=92, optimize=True)
            write_text(plan, text)
        except BaseException:  # includes a Streamlit stop: never leave half a preview behind
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return {"plan": plan, "video": video, "thumbnail": thumb, "text": text, "elapsed": elapsed, "sequence": None}
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

    spec_json = json.dumps({"version": VERSION, "seed": plan.seed, "background": plan.theme, "music": plan.music})
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
    return {"plan": plan, "elapsed": elapsed, "sequence": record.sequence_no, **paths}
