"""Matchstick equations frames (Puzzly for You look): wooden matches on a dark card, one of them moves in the reveal.

Level timeline: 0.5 s entrance, thinking (numeric timer, `MOVE 1 MATCH.` pill above the card, `Make it true.` under it),
then the solving stick glows, lifts, flies along an arc to its new slot and settles (1.3 s), the card turns green with
a check and a burst (0.45 s), and a 1.0 s hold. Every stick is a supersampled sprite, so edges stay smooth.
"""
from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image, ImageDraw, ImageFilter

from ..config import (MATCH_ANSWER, MATCH_DEFAULT_FRAME, MATCH_ENTRANCE, MATCH_FRAMES, MATCH_HOLD, MATCH_MOVE,
                      PUZZLE_FIT_PALETTE as PALETTE)
from ..models import RoundSpec, VideoSpec
from ..puzzles.matchstick import DIGITS, OPERATORS, symbols
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .puzzle_fit import _level_header, _text, _timer, active_theme, draw_puzzle_fit_outro
from .surfaces import table
from .text import font

PROMPT = "MOVE 1 MATCH."
GOAL = "Make it true."
HOOK_TEXT = "MOVE ONE MATCH."
OUTRO_QUESTION = "How many did you solve?"
CENTER_Y = 930
COVER_TIME = 0.6
WOOD, WOOD_EDGE = (233, 200, 145), (150, 104, 56)
# Stick look, tunable in one place. Kept calm on purpose: bright, large red heads meeting at every joint made the digits
# hard to focus on, so heads are small and muted, sticks leave wider gaps at the joints, the wood has no highlight
# stripe, and empty slots are very faint.
STYLE = {"head": .56, "head_fill": (150, 62, 48), "head_edge": (92, 36, 28), "head_light": (184, 104, 86),
         "share": .80, "thick": .13, "stripe": False, "ghost": 9}
GAP = .42  # space between symbols, in stick lengths


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def frame_for(spec: VideoSpec) -> str:
    """The frame/timer colour: the creator's choice stored in metadata (outside the fingerprint), else the default."""
    chosen = spec.metadata.get("frame")
    return MATCH_FRAMES[chosen if chosen in MATCH_FRAMES else MATCH_DEFAULT_FRAME][1]


def _table(size: tuple[int, int]) -> Image.Image:
    """A dark wood table under a lamp over the card, in the video's background tone."""
    return table(size, active_theme(), "wood", (540, CENTER_Y)).convert("RGBA")


# ---------------------------------------------------------------- timing

def phases(item: RoundSpec) -> dict[str, float]:
    think_end = MATCH_ENTRANCE + float(item.data["thinking_seconds"])
    move_end = think_end + MATCH_MOVE
    return {"think_end": think_end, "move_end": move_end, "answer": move_end, "hold": move_end + MATCH_ANSWER}


def level_duration(item: RoundSpec) -> float:
    return round(phases(item)["hold"] + MATCH_HOLD, 3)


def schedule(spec: VideoSpec) -> list[tuple[float, float]]:
    """(start, duration) of every level; harder levels think longer."""
    result, start = [], spec.intro_duration
    for item in spec.rounds:
        duration = level_duration(item)
        result.append((start, duration))
        start += duration
    return result


# ---------------------------------------------------------------- geometry

def _segment_line(kind: str, segment: str, length: float) -> tuple[tuple[float, float], tuple[float, float]]:
    """Segment endpoints inside a symbol box (width L, height 2L), origin top-left."""
    L = length
    if kind == "op":
        return ((0, L), (L, L)) if segment == "h" else ((L / 2, L * .5), (L / 2, L * 1.5))
    return {"a": ((0, 0), (L, 0)), "b": ((L, 0), (L, L)), "c": ((L, L), (L, 2 * L)), "d": ((0, 2 * L), (L, 2 * L)),
            "e": ((0, L), (0, 2 * L)), "f": ((0, 0), (0, L)), "g": ((0, L), (L, L))}[segment]


def layout(text: str) -> dict:
    """Stick length and the left edge of every symbol, centred on x 540 and fitting x 110-970."""
    count = len(text)
    length = min(150.0, 860 / (count + GAP * (count - 1)))
    width = length * (count + GAP * (count - 1))
    left = 540 - width / 2
    return {"length": length, "lefts": [left + index * length * (1 + GAP) for index in range(count)],
            "top": CENTER_Y - length}


def slot_pose(text: str, index: int, segment: str) -> tuple[float, float, float, float]:
    """Centre x, centre y, angle (0 = horizontal, 90 = vertical) and length of a stick slot, in logical pixels."""
    geo = layout(text)
    kind = "op" if text[index] in OPERATORS else "digit"
    (x1, y1), (x2, y2) = _segment_line(kind, segment, geo["length"])
    x0, y0 = geo["lefts"][index], geo["top"]
    angle = 0.0 if y1 == y2 else 90.0
    return x0 + (x1 + x2) / 2, y0 + (y1 + y2) / 2, angle, geo["length"]


def _all_slots(text: str) -> list[tuple[int, str]]:
    result = []
    for index, char in enumerate(text):
        if char.isdigit():
            result += [(index, segment) for segment in "abcdefg"]
        elif char in OPERATORS:
            result += [(index, segment) for segment in "hv"]
    return result


def _sticks_of(text: str) -> set[tuple[int, str]]:
    result = set()
    for index, (kind, sticks) in enumerate(symbols(text)):
        result |= {(index, segment) for segment in sticks}
    return result


# ---------------------------------------------------------------- stick sprites

@lru_cache(maxsize=64)
def stick_sprite(length_px: int, glow: bool = False) -> Image.Image:
    """A horizontal wooden match, head on the right, drawn at 3x and shrunk (the canvas has room for a glow)."""
    k = 3
    thick = max(3, round(length_px * STYLE["thick"]))
    pad = thick * 2
    w, h = (length_px + 2 * pad) * k, (thick * 4 + 2 * pad) * k
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    cy = h / 2
    x1, x2 = pad * k, (pad + length_px) * k
    t = thick * k
    if glow:
        halo = Image.new("L", (w, h), 0)
        ImageDraw.Draw(halo).rounded_rectangle((x1 - t, cy - t * 1.4, x2 + t, cy + t * 1.4), radius=t, fill=200)
        image.paste(_rgb(PALETTE["warning"]) + (255,), (0, 0), halo.filter(ImageFilter.GaussianBlur(t)))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((x1, cy - t / 2, x2 - t * .6, cy + t / 2), radius=t / 2, fill=WOOD_EDGE)
    draw.rounded_rectangle((x1 + k, cy - t / 2 + k, x2 - t * .6 - k, cy + t / 2 - k * 1.5), radius=t / 2, fill=WOOD)
    if STYLE["stripe"]:
        draw.line(((x1 + t, cy - t * .15), (x2 - t * 1.4, cy - t * .15)), fill=(250, 226, 184), width=max(1, round(t * .18)))
    head_r = t * STYLE["head"]
    if head_r > 0:
        hx = x2 - head_r * .9
        draw.ellipse((hx - head_r * 1.15, cy - head_r, hx + head_r * 1.15, cy + head_r), fill=STYLE["head_edge"])
        draw.ellipse((hx - head_r * 1.05, cy - head_r * .9, hx + head_r * 1.05, cy + head_r * .88), fill=STYLE["head_fill"])
        draw.ellipse((hx - head_r * .6, cy - head_r * .6, hx + head_r * .05, cy - head_r * .05), fill=STYLE["head_light"])
    return image.resize((w // k, h // k), Image.Resampling.LANCZOS)


def _paste_stick(image: Image.Image, center: tuple[float, float], angle: float, length: float, scale: float,
                 glow: bool = False, lift: float = 0.0) -> None:
    sprite = stick_sprite(max(4, round(length * STYLE["share"] * scale)), glow)
    if angle:
        sprite = sprite.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    if lift:
        grown = sprite.resize((max(1, round(sprite.width * (1 + .12 * lift))), max(1, round(sprite.height * (1 + .12 * lift)))),
                              Image.Resampling.BICUBIC)
        shadow = Image.new("RGBA", grown.size, (0, 0, 0, 0))
        shadow.putalpha(grown.getchannel("A").point(lambda v: v * 2 // 5))
        offset = round(18 * lift * scale)
        image.alpha_composite(shadow, (round(center[0] * scale - grown.width / 2 + offset),
                                       round(center[1] * scale - grown.height / 2 + offset)))
        sprite = grown
    image.alpha_composite(sprite, (round(center[0] * scale - sprite.width / 2), round(center[1] * scale - sprite.height / 2)))


def _ghost(image: Image.Image, text: str, slot: tuple[int, str], scale: float, strength: float = 1.0) -> None:
    x, y, angle, length = slot_pose(text, *slot)
    half = length * .4 * scale
    draw = ImageDraw.Draw(image, "RGBA")
    dx, dy = (half, 0) if angle == 0 else (0, half)
    draw.line(((x * scale - dx, y * scale - dy), (x * scale + dx, y * scale + dy)), fill=(255, 255, 255, round(STYLE["ghost"] * strength)),
              width=max(1, round(length * .1 * scale)))


def _equals(image: Image.Image, text: str, scale: float) -> None:
    geo = layout(text)
    index = text.index("=")
    L = geo["length"]
    x = geo["lefts"][index] + L / 2
    for offset in (-.24, .24):
        _paste_stick(image, (x, geo["top"] + L + offset * L), 0.0, L, scale)


# ---------------------------------------------------------------- board

def card_box(text: str) -> tuple[float, float, float, float]:
    L = layout(text)["length"]
    return 80, CENTER_Y - L - 90, 1000, CENTER_Y + L + 90


def draw_equation(image: Image.Image, text: str, scale: float, hidden: tuple[int, str] | None = None,
                  extra: tuple[int, str] | None = None, solved: float = 0.0, ghosts: bool = True, glow: tuple | None = None,
                  frame: str | None = None) -> None:
    """The card with every stick of `text` (minus `hidden`, plus `extra`) and faint empty slots."""
    x1, y1, x2, y2 = card_box(text)
    edge = PALETTE["success"] if solved > 0 else (frame or PALETTE["surface_edge"])
    rounded_surface(image, (x1 * scale, y1 * scale, x2 * scale, y2 * scale), 44 * scale, _rgb(PALETTE["surface"]) + (235,),
                    outline=_rgb(edge) + (255,), width=max(1, round((3 + 3 * solved) * scale)))
    present = _sticks_of(text)
    if hidden:
        present.discard(hidden)
    if extra:
        present.add(extra)
    if ghosts:  # drawn on their own layer: semi-transparent lines drawn straight onto the frame would not blend
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        for slot in _all_slots(text):
            if slot not in present:
                _ghost(layer, text, slot, scale)
        image.alpha_composite(layer)
    for slot in sorted(present):
        x, y, angle, length = slot_pose(text, *slot)
        _paste_stick(image, (x, y), angle, length, scale, glow=slot == glow)
    _equals(image, text, scale)


def _prompt(image: Image.Image, y: float, scale: float, opacity: float = 1.0, pulse: float = 0.0, text: str = PROMPT,
            color: str | None = None) -> None:
    if opacity <= 0:
        return
    face = font(round((62 + 5 * pulse) * scale))
    width = ImageDraw.Draw(image).textlength(text, font=face) + 100 * scale
    height = 104 * scale
    x = 540 * scale - width / 2
    rounded_surface(image, (x, y * scale - height / 2, x + width, y * scale + height / 2), height / 2,
                    _rgb(color or PALETTE["accent"]) + (round(255 * opacity),))
    _text(image, (540 * scale, (y - 2) * scale), text, face, PALETTE["background"], opacity)


def _burst(image: Image.Image, center: tuple[float, float], since: float, scale: float) -> None:
    if since < 0 or since > .6:
        return
    progress = ease_out_cubic(since / .6)
    alpha = round(230 * (1 - progress))
    draw = ImageDraw.Draw(image, "RGBA")
    radius = (60 + 170 * progress) * scale
    draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
                 outline=_rgb(PALETTE["success"]) + (alpha,), width=max(2, round(8 * (1 - progress) * scale) + 1))
    for index in range(12):
        angle = index / 12 * math.tau + .2
        distance = (50 + 190 * progress) * scale
        px, py = center[0] + math.cos(angle) * distance, center[1] + math.sin(angle) * distance
        dot = max(1, round((8 - 5 * progress) * scale))
        color = PALETTE["warning"] if index % 3 == 0 else (PALETTE["accent"] if index % 3 == 1 else PALETTE["text_light"])
        draw.ellipse((px - dot, py - dot, px + dot, py + dot), fill=_rgb(color) + (alpha,))


def _moving_stick(image: Image.Image, text: str, item: RoundSpec, progress: float, scale: float) -> None:
    """Lift (first 20 %), fly along an arc while turning to the new direction, then settle (last 12 %)."""
    source, target = tuple(item.data["move"]["from"]), tuple(item.data["move"]["to"])
    sx, sy, sa, length = slot_pose(text, *source)
    tx, ty, ta, _ = slot_pose(text, *target)
    if progress < .2:
        lift, travel = ease_out_cubic(progress / .2), 0.0
    elif progress < .88:
        lift, travel = 1.0, ease_in_out((progress - .2) / .68)
    else:
        lift, travel = 1 - ease_out_cubic((progress - .88) / .12), 1.0
    arc = math.sin(travel * math.pi) * min(130.0, 50 + abs(tx - sx) * .2)
    x, y = sx + (tx - sx) * travel, sy + (ty - sy) * travel - arc - 26 * lift
    turn = ta - sa
    _paste_stick(image, (x, y), sa + turn * travel, length, scale, glow=True, lift=lift)


def _solved_line(image: Image.Image, text: str, answer: str, scale: float, opacity: float) -> None:
    """The true equation in green under the card, with a drawn check mark."""
    label = answer.replace("-", " − ").replace("+", " + ").replace("=", " = ")
    face = font(round(56 * scale))
    y = (card_box(text)[3] + 80) * scale
    width = ImageDraw.Draw(image).textlength(label, font=face)
    x = 540 * scale - (width + 70 * scale) / 2
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.text((x, y), label, font=face, fill=_rgb(PALETTE["success"]), anchor="lm")
    cx, r = x + width + 40 * scale, 22 * scale
    draw.line(((cx - r, y), (cx - r * .3, y + r * .7), (cx + r, y - r * .8)), fill=_rgb(PALETTE["success"]),
              width=max(2, round(9 * scale)), joint="curve")
    if opacity < 1:
        layer.putalpha(layer.getchannel("A").point(lambda v: round(v * opacity)))
    image.alpha_composite(layer)


def _below(image: Image.Image, text: str, label: str, color: str, scale: float, opacity: float = 1.0) -> None:
    y = card_box(text)[3] + 80
    _text(image, (540 * scale, y * scale), label, font(round(52 * scale)), color, opacity)


# ---------------------------------------------------------------- frames

def draw_matchstick_round(spec: VideoSpec, index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    image = _table(size).copy()
    item = spec.rounds[index]
    frame = frame_for(spec)
    text = item.data["equation"]
    times = phases(item)
    thinking = float(item.data["thinking_seconds"])
    source, target = tuple(item.data["move"]["from"]), tuple(item.data["move"]["to"])
    prompt_y = card_box(text)[1] - 88
    _level_header(image, index + 1, spec.round_count, 1.0, scale)
    if local < times["think_end"]:
        remaining = times["think_end"] - local
        _timer(image, min(thinking, remaining), thinking, _clamp(local / .25), scale, accent=frame)
        _prompt(image, prompt_y, scale, _clamp(local / .2), abs(math.sin(local * math.pi)) * (1 if remaining < 3 else 0),
                color=frame)
        appear = ease_out_cubic(_clamp(local / MATCH_ENTRANCE))
        board = Image.new("RGBA", size, (0, 0, 0, 0))
        draw_equation(board, text, scale, frame=frame)
        if appear < 1:
            board.putalpha(board.getchannel("A").point(lambda v: round(v * appear)))
        image.alpha_composite(board, (0, round(40 * (1 - appear) * scale)))
        _below(image, text, GOAL, PALETTE["text_light"], scale, _clamp((local - .3) / .3))
    elif local < times["move_end"]:
        _text(image, (540 * scale, prompt_y * scale), "SOLUTION", font(round(52 * scale)), PALETTE["text_muted"])
        draw_equation(image, text, scale, hidden=source, frame=frame)
        _moving_stick(image, text, item, (local - times["think_end"]) / MATCH_MOVE, scale)
    else:
        solved = _clamp((local - times["answer"]) / MATCH_ANSWER)
        _text(image, (540 * scale, prompt_y * scale), "SOLUTION", font(round(52 * scale)), PALETTE["text_muted"])
        draw_equation(image, text, scale, hidden=source, extra=target, solved=solved)
        pop = ease_out_back(solved)
        _solved_line(image, text, item.answer, scale, solved)
        if pop:
            _burst(image, (540 * scale, CENTER_Y * scale), local - times["answer"], scale)
    if local < .2 and index > 0:
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (round(200 * (1 - _clamp(local / .2))),))
        image.alpha_composite(overlay)
    return image


def draw_matchstick_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook: the real level-1 equation (never its answer) under `MOVE ONE MATCH.`."""
    scale = size[0] / 1080
    image = _table(size).copy()
    item = spec.rounds[0]
    frame = frame_for(spec)
    pop = ease_out_back(_clamp(t / .3))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, font(round(78 * scale)), PALETTE["text_light"], _clamp(t / .15), max(.5, pop))
    _text(image, (540 * scale, 232 * scale), f"{spec.round_count} LEVELS · EACH ONE HARDER", font(round(40 * scale)),
          frame, _clamp((t - .15) / .25))
    _prompt(image, card_box(item.data["equation"])[1] - 88, scale, _clamp((t - .1) / .2), color=frame)
    draw_equation(image, item.data["equation"], scale, frame=frame)
    _below(image, item.data["equation"], GOAL, PALETTE["text_light"], scale)
    return image


def draw_matchstick_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        return draw_matchstick_intro(spec, t, size).convert("RGB")
    levels = schedule(spec)
    rounds_end = levels[-1][0] + levels[-1][1]
    if t >= rounds_end:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size, OUTRO_QUESTION)
    index = max(position for position, (start, _) in enumerate(levels) if t >= start)
    return draw_matchstick_round(spec, index, t - levels[index][0], size).convert("RGB")
