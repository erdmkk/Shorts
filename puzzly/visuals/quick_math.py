"""Quick Math formats (Shape Equations, Missing Operators): Puzzly for You look with a clear prompt right above the board."""
from __future__ import annotations

from functools import lru_cache
import math

import numpy as np
from PIL import Image, ImageDraw

from ..branding import draw_brand_mark

from ..config import (PUZZLE_FIT_PALETTE as PALETTE, QUICK_MATH_ANSWER, QUICK_MATH_ENTRANCE, QUICK_MATH_HINT_AT,
                      QUICK_MATH_PAUSE_HINT, QUICK_MATH_SOLVE, quick_math_round)
from ..models import RoundSpec, VideoSpec
from .easing import ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .memory import token_image
from .puzzle_fit import _background, _level_header, _text, _timer, draw_puzzle_fit_outro
from .text import draw_cta, fitted_font, font

PROMPT = "SOLVE IT."
PAUSE_HINT = "Pause if you need more time"
PAUSE_Y = 1500
HOOK_TEXT = "NO CALCULATOR."
OUTRO_QUESTION = "How many did you solve?"
ROW_HEIGHT = 158
TOKEN = 108
GROUP_CENTER_Y = 930  # prompt, board, and solution sit together in the middle of the screen
COVER_TIME = 0.6


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def phases(item: RoundSpec) -> dict[str, float]:
    think_end = QUICK_MATH_ENTRANCE + float(item.data["thinking_seconds"])
    return {"hint": QUICK_MATH_ENTRANCE + float(item.data["thinking_seconds"]) * QUICK_MATH_HINT_AT,
            "think_end": think_end, "answer": think_end + QUICK_MATH_SOLVE,
            "hold": think_end + QUICK_MATH_SOLVE + QUICK_MATH_ANSWER}


def schedule(spec: VideoSpec) -> list[tuple[float, float]]:
    """(start, duration) of every level; levels last longer as they get harder."""
    result, start = [], spec.intro_duration
    for item in spec.rounds:
        duration = quick_math_round(spec.difficulty, item.data["tier"])
        result.append((start, duration))
        start += duration
    return result


def _pause_hint(image: Image.Image, remaining: float, local: float, scale: float) -> None:
    """Near the end of the timer, invite anyone who needs longer to pause instead of scrolling away."""
    opacity = _clamp((QUICK_MATH_PAUSE_HINT - remaining) / .4)
    if opacity <= 0:
        return
    face = font(round(40 * scale))
    draw = ImageDraw.Draw(image)
    text_width = draw.textlength(PAUSE_HINT, font=face)
    icon = 34 * scale
    gap = 20 * scale
    pad_x, height = 40 * scale, 84 * scale
    width = icon + gap + text_width + pad_x * 2
    x1, y = 540 * scale - width / 2, PAUSE_Y * scale
    glow = .75 + .25 * abs(math.sin(local * math.pi))
    rounded_surface(image, (x1, y - height / 2, x1 + width, y + height / 2), height / 2,
                    _rgb(PALETTE["surface"]) + (round(235 * opacity),), outline=_rgb(PALETTE["warning"]) + (round(255 * opacity * glow),),
                    width=max(1, round(3 * scale)))
    bar_w, bar_h = icon * .32, icon
    bx = x1 + pad_x
    for offset in (0, icon * .56):  # the pause symbol, drawn so it never depends on the font
        rounded_surface(image, (bx + offset, y - bar_h / 2, bx + offset + bar_w, y + bar_h / 2), bar_w / 2,
                        _rgb(PALETTE["warning"]) + (round(255 * opacity),))
    _text(image, (bx + icon + gap + text_width / 2, y - 3 * scale), PAUSE_HINT, face, PALETTE["text_light"], opacity)


def card_top(item: RoundSpec) -> float:
    height = 70 + ROW_HEIGHT * (len(item.data["clues"]) + 1)
    return GROUP_CENTER_Y - height / 2


def card_bottom(item: RoundSpec) -> float:
    return card_top(item) + 40 + ROW_HEIGHT * (len(item.data["clues"]) + 1) + 30


def prompt_y(item: RoundSpec) -> float:
    return card_top(item) - 88


# ---------------------------------------------------------------- pieces

RULE_BADGE = "× ÷ FIRST"


def _prompt_group(image: Image.Image, text: str, y: float, fill: str, ink: str, rule_color: str, rule_fill: str,
                  scale: float, opacity: float, pulse: float, rule: bool) -> None:
    """The instruction pill sits right above the board. Trap levels add a small rule reminder beside it."""
    if opacity <= 0:
        return
    draw = ImageDraw.Draw(image)
    face = font(round((62 + 5 * pulse) * scale))
    width = draw.textlength(text, font=face) + 100 * scale
    height = 104 * scale
    badge_face = font(round(40 * scale))
    badge_w = draw.textlength(RULE_BADGE, font=badge_face) + 56 * scale if rule else 0
    gap = 20 * scale if rule else 0
    x = 540 * scale - (width + gap + badge_w) / 2
    y *= scale
    rounded_surface(image, (x, y - height / 2, x + width, y + height / 2), height / 2, _rgb(fill) + (round(255 * opacity),))
    _text(image, (x + width / 2, y - 2 * scale), text, face, ink, opacity)
    if rule:
        bx = x + width + gap
        badge_h = 78 * scale
        rounded_surface(image, (bx, y - badge_h / 2, bx + badge_w, y + badge_h / 2), badge_h / 2, _rgb(rule_fill) + (round(240 * opacity),),
                        outline=_rgb(rule_color) + (round(255 * opacity),), width=max(2, round(4 * scale)))
        _text(image, (bx + badge_w / 2, y - 2 * scale), RULE_BADGE, badge_face, rule_color, opacity)


def _prompt(image: Image.Image, item: RoundSpec, scale: float, opacity: float = 1.0, pulse: float = 0.0) -> None:
    """The instruction sits right above the board as a large solid pill, so nobody misses it."""
    _prompt_group(image, PROMPT, prompt_y(item), PALETTE["accent"], PALETTE["background"], PALETTE["warning"], PALETTE["surface"],
                  scale, opacity, pulse, item.data["tier"] >= 2)


def _hint_chip(image: Image.Image, item: RoundSpec, amount: float, scale: float) -> None:
    """Halfway through a trap level, one shape's value appears under the board."""
    if amount <= 0:
        return
    entry = next(shape for shape in item.data["shapes"] if shape["name"] == item.data["hint_shape"])
    zoom = max(.05, ease_out_back(amount))
    y = (card_bottom(item) + 80) * scale
    tag_face, face = font(round(34 * scale)), font(round(50 * scale))
    chip_w, chip_h = 380 * scale * zoom, 100 * scale * zoom
    x1 = 540 * scale - chip_w / 2
    rounded_surface(image, (x1, y - chip_h / 2, x1 + chip_w, y + chip_h / 2), chip_h / 2, _rgb(PALETTE["surface"]) + (245,),
                    outline=_rgb(PALETTE["warning"]) + (255,), width=max(2, round(4 * scale)))
    _text(image, (x1 + 75 * scale * zoom, y - 3 * scale), "HINT", tag_face, PALETTE["warning"], min(1.0, amount * 2), zoom)
    size = max(2, round(58 * scale * zoom))
    sprite = token_image(entry["shape"], entry["color"], size)
    image.paste(sprite, (round(x1 + 175 * scale * zoom - size / 2), round(y - size / 2)), sprite)
    _text(image, (x1 + 280 * scale * zoom, y - 3 * scale), f"= {entry['value']}", face, PALETTE["text_light"], min(1.0, amount * 2), zoom)


def _row_items(terms: list, shapes: dict, tail: str | None) -> list[tuple[str, object]]:
    items: list[tuple[str, object]] = []
    for term in terms:
        items.append(("shape", shapes[term]) if isinstance(term, str) and term.startswith("s") else ("op", term))
    items.append(("op", "="))
    if tail is not None:
        items.append(("number", tail))
    return items


def _draw_row(image: Image.Image, items: list, center_y: float, scale: float, opacity: float,
              question: dict | None = None) -> None:
    op_face, number_face = font(round(80 * scale)), font(round(90 * scale))
    answer_face = font(round(96 * scale))
    draw = ImageDraw.Draw(image)
    gap = 22 * scale
    token = TOKEN * scale
    widths = []
    for kind, value in items:
        if kind == "shape":
            widths.append(token)
        elif kind == "op":
            widths.append(draw.textlength(str(value), font=op_face))
        else:
            widths.append(max(draw.textlength(str(value), font=number_face), token))
    if question is not None:
        answer_width = draw.textlength(str(question["answer"]), font=answer_face) if question["reveal"] > 0 else 0
        widths.append(max(token * 1.15, answer_width))
    total = sum(widths) + gap * (len(widths) - 1)
    shrink = min(1.0, 860 * scale / total)
    x = 540 * scale - total * shrink / 2
    for (kind, value), width in zip(items, widths):
        cx = x + width * shrink / 2
        if kind == "shape":
            size = max(2, round(token * shrink))
            sprite = token_image(value["shape"], value["color"], size)
            if opacity < 1:
                sprite = sprite.copy()
                sprite.putalpha(sprite.getchannel("A").point(lambda alpha: round(alpha * opacity)))
            image.paste(sprite, (round(cx - size / 2), round(center_y - size / 2)), sprite)
        elif kind == "op":
            _text(image, (cx, center_y - 4 * scale), str(value), op_face, PALETTE["text_muted"] if value != "=" else PALETTE["text_light"], opacity)
        else:
            _text(image, (cx, center_y - 4 * scale), str(value), number_face, PALETTE["text_light"], opacity)
        x += (width + gap) * shrink
    if question is not None:
        cx = x + widths[-1] * shrink / 2
        box = token * 1.15 * shrink / 2
        reveal = question["reveal"]
        if reveal <= 0:
            pulse = question["pulse"]
            color = _rgb(PALETTE["primary"])
            rounded_surface(image, (cx - box, center_y - box, cx + box, center_y + box), 22 * scale,
                            color + (round(255 * opacity),))
            _text(image, (cx, center_y - 4 * scale), "?", font(round((80 + 8 * pulse) * scale)), PALETTE["text_light"], opacity)
        else:
            zoom = max(.3, ease_out_back(reveal))
            _text(image, (cx, center_y - 4 * scale), str(question["answer"]), answer_face, PALETTE["success"], 1.0, zoom * shrink)


def _burst(image: Image.Image, center: tuple[float, float], since: float, scale: float) -> None:
    if since < 0 or since > .6:
        return
    progress = ease_out_cubic(since / .6)
    alpha = round(230 * (1 - progress))
    draw = ImageDraw.Draw(image, "RGBA")
    radius = (50 + 150 * progress) * scale
    draw.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius),
                 outline=_rgb(PALETTE["success"]) + (alpha,), width=max(2, round(8 * (1 - progress) * scale) + 1))
    for index in range(12):
        angle = index / 12 * math.tau + .2
        distance = (40 + 170 * progress) * scale
        px, py = center[0] + math.cos(angle) * distance, center[1] + math.sin(angle) * distance
        dot = max(1, round((8 - 5 * progress) * scale))
        color = PALETTE["warning"] if index % 3 == 0 else (PALETTE["accent"] if index % 3 == 1 else PALETTE["text_light"])
        draw.ellipse((px - dot, py - dot, px + dot, py + dot), fill=_rgb(color) + (alpha,))


def _chips(image: Image.Image, item: RoundSpec, shown: float, scale: float) -> None:
    """Solution path: each shape's value appears in solving order."""
    shapes = item.data["shapes"]
    count = len(shapes)
    face = font(round(50 * scale))
    chip_w, chip_h, gap = 250 * scale, 100 * scale, 24 * scale
    total = count * chip_w + (count - 1) * gap
    y = (card_bottom(item) + 80) * scale
    x = 540 * scale - total / 2
    for index, entry in enumerate(shapes):
        amount = _clamp(shown * count - index)
        if amount <= 0:
            break
        zoom = ease_out_back(amount)
        cx = x + chip_w / 2
        half_w, half_h = chip_w / 2 * zoom, chip_h / 2 * zoom
        rounded_surface(image, (cx - half_w, y - half_h, cx + half_w, y + half_h), half_h,
                        _rgb(PALETTE["surface"]) + (240,), outline=_rgb(PALETTE["surface_edge"]) + (255,),
                        width=max(1, round(3 * scale)))
        size = max(2, round(58 * scale * zoom))
        sprite = token_image(entry["shape"], entry["color"], size)
        image.paste(sprite, (round(cx - 52 * scale * zoom - size / 2), round(y - size / 2)), sprite)
        _text(image, (cx + 38 * scale * zoom, y - 3 * scale), f"= {entry['value']}", face, PALETTE["text_light"], min(1.0, amount * 2), zoom)
        x += chip_w + gap


def draw_board(image: Image.Image, spec: VideoSpec, item: RoundSpec, local: float, scale: float, hook: bool = False) -> None:
    data = item.data
    shapes = {entry["name"]: entry for entry in data["shapes"]}
    rows = len(data["clues"]) + 1
    top, bottom = card_top(item) * scale, card_bottom(item) * scale
    rounded_surface(image, (80 * scale, top, 1000 * scale, bottom), 44 * scale, _rgb(PALETTE["surface"]) + (235,),
                    outline=_rgb(PALETTE["surface_edge"]) + (255,), width=max(1, round(3 * scale)))
    times = phases(item)
    for row, clue in enumerate(data["clues"]):
        appear = 1.0 if hook else ease_out_cubic(_clamp((local - row * .08) / .3))
        y = (card_top(item) + 40 + ROW_HEIGHT * (row + .5) + 30 * (1 - appear)) * scale
        _draw_row(image, _row_items(clue["terms"], shapes, str(clue["result"])), y, scale, appear)
    # Question row, set apart by a divider and an accent outline.
    appear = 1.0 if hook else ease_out_cubic(_clamp((local - (rows - 1) * .08) / .3))
    qy = (card_top(item) + 40 + ROW_HEIGHT * (rows - .5)) * scale
    divider = (card_top(item) + 40 + ROW_HEIGHT * (rows - 1)) * scale
    ImageDraw.Draw(image, "RGBA").line(((130 * scale, divider), (950 * scale, divider)), fill=_rgb(PALETTE["surface_edge"]) + (255,),
                                       width=max(1, round(3 * scale)))
    remaining = times["think_end"] - local
    pulse = abs(math.sin(local * math.pi * 1.2)) if not hook else 0.0
    reveal = 0.0 if hook else _clamp((local - times["answer"]) / QUICK_MATH_ANSWER)
    _draw_row(image, _row_items(data["question"]["terms"], shapes, None), qy, scale, appear,
              {"answer": item.answer, "reveal": reveal, "pulse": pulse if remaining > 0 else 0.0})
    if not hook and local >= times["answer"]:
        _burst(image, (540 * scale, qy), local - times["answer"], scale)


# ---------------------------------------------------------------- frames

def draw_quick_math_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    image = _background(size, 760).copy()
    item = spec.rounds[0]
    pop = ease_out_back(_clamp(t / .3))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, font(round(78 * scale)), PALETTE["text_light"], _clamp(t / .15), max(.5, pop))
    _text(image, (540 * scale, 232 * scale), f"{spec.round_count} LEVELS · EACH ONE HARDER", font(round(40 * scale)),
          PALETTE["accent"], _clamp((t - .15) / .25))
    _prompt(image, item, scale, _clamp((t - .1) / .2))
    draw_board(image, spec, item, 0.0, scale, hook=True)
    return image


def draw_quick_math_round(spec: VideoSpec, index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    image = _background(size, 760).copy()
    item = spec.rounds[index]
    times = phases(item)
    _level_header(image, index + 1, spec.round_count, 1.0, scale)
    thinking = float(item.data["thinking_seconds"])
    if local < times["think_end"]:
        remaining = times["think_end"] - local
        _timer(image, min(thinking, remaining), thinking, _clamp(local / .25), scale)
        _prompt(image, item, scale, 1.0, abs(math.sin(local * math.pi)) * (1 if remaining < 3 else 0))
        _pause_hint(image, remaining, local, scale)
    else:
        _text(image, (540 * scale, prompt_y(item) * scale), "SOLUTION", font(round(52 * scale)), PALETTE["text_muted"])
    draw_board(image, spec, item, local, scale)
    if item.data.get("hint_shape") and times["hint"] <= local < times["think_end"]:
        _hint_chip(image, item, _clamp((local - times["hint"]) / .35), scale)
    if local >= times["think_end"]:
        _chips(image, item, _clamp((local - times["think_end"]) / QUICK_MATH_SOLVE), scale)
    if local >= times["answer"] and item.data["tier"] >= 2:
        note_y = (card_bottom(item) + 175) * scale
        _text(image, (540 * scale, note_y), f"Left to right gives {item.data['left_to_right']}. × and ÷ come first!",
              font(round(38 * scale)), PALETTE["warning"], _clamp((local - times["answer"] - .2) / .3))
    return image


# ---------------------------------------------------------------- Missing Operators format (teal and amber theme)

OPS_PALETTE = {
    "background": "#021417", "background_2": "#06262B", "glow": "#0E8C86", "surface": "#0A2A30",
    "surface_edge": "#1D525A", "slot": "#0F3940", "accent": "#FFB547", "text_light": "#FFFFFF",
    "text_muted": "#8DB9BD", "success": "#3DF08F", "primary": "#FFB547", "outline": "#03171A",
}
OPS_PROMPT = "FILL THE SIGNS."
OPS_HOOK = "FIND THE MISSING SIGNS."
OPS_BOARD_HEIGHT = 500
OPS_SLOT = 128


@lru_cache(maxsize=4)
def _ops_background(size: tuple[int, int]) -> Image.Image:
    width, height = size
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    top, bottom, glow = (np.array(_rgb(OPS_PALETTE[key]), dtype=np.float32) for key in ("background", "background_2", "glow"))
    t = (y / max(1, height - 1))[..., None]
    rgb = top * (1 - t) + bottom * t
    scale = width / 1080
    for gy, strength, color in ((820, .42, glow), (1450, .06, np.array(_rgb(OPS_PALETTE["accent"]), np.float32))):
        distance = np.hypot(x - width / 2, y - gy * scale) / (600 * scale)
        rgb += (color - top) * (np.exp(-distance * distance) * strength)[..., None]
    vignette = np.hypot((x / width - .5) * 1.2, y / height - .5)
    rgb *= (1 - np.clip(vignette - .35, 0, 1) * .6)[..., None]
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(image, "RGBA")
    step, radius = 60 * scale, max(1, round(2 * scale))
    for row in range(int(height / step) + 1):  # a faint plus-sign grid instead of dots
        for column in range(int(width / step) + 1):
            px, py = column * step + (step / 2 if row % 2 else 0), row * step
            if abs(px - width / 2) < 400 * scale and 250 * scale < py < 1600 * scale:
                continue
            draw.line(((px - radius * 2, py), (px + radius * 2, py)), fill=(255, 255, 255, 20), width=radius)
            draw.line(((px, py - radius * 2), (px, py + radius * 2)), fill=(255, 255, 255, 20), width=radius)
    return image


def _ops_board_top() -> float:
    return GROUP_CENTER_Y - OPS_BOARD_HEIGHT / 2 - 40


def _ops_prompt(image: Image.Image, item: RoundSpec, scale: float, opacity: float = 1.0, pulse: float = 0.0) -> None:
    _prompt_group(image, OPS_PROMPT, _ops_board_top() - 88, OPS_PALETTE["accent"], OPS_PALETTE["background"],
                  OPS_PALETTE["success"], OPS_PALETTE["surface"], scale, opacity, pulse, item.data["tier"] >= 2)


def _ops_slot(image: Image.Image, center: tuple[float, float], size: float, scale: float, op: str | None,
              reveal: float, pulse: float, opacity: float) -> None:
    half = size / 2
    cx, cy = center
    if op is None or reveal <= 0:
        glow = .55 + .45 * pulse
        rounded_surface(image, (cx - half, cy - half, cx + half, cy + half), 24 * scale, _rgb(OPS_PALETTE["slot"]) + (round(255 * opacity),),
                        outline=_rgb(OPS_PALETTE["accent"]) + (round(255 * opacity * glow),), width=max(2, round(5 * scale)))
        _text(image, (cx, cy - 4 * scale), "?", font(round(64 * scale)), OPS_PALETTE["text_muted"], opacity * .8)
        return
    flip = ease_out_back(reveal)  # the tile flips open to show its sign
    squash = max(.06, min(1.0, flip))
    rounded_surface(image, (cx - half, cy - half * squash, cx + half, cy + half * squash), 24 * scale,
                    _rgb(OPS_PALETTE["accent"]) + (255,))
    if squash > .5:
        _text(image, (cx, cy - 6 * scale), op, font(round(88 * scale)), OPS_PALETTE["background"], 1.0, squash)


def _ops_board(image: Image.Image, item: RoundSpec, local: float, scale: float, hook: bool = False) -> None:
    data = item.data
    numbers, ops = data["numbers"], data["operators"]
    top = _ops_board_top()
    rounded_surface(image, (70 * scale, top * scale, 1010 * scale, (top + OPS_BOARD_HEIGHT) * scale), 44 * scale,
                    _rgb(OPS_PALETTE["surface"]) + (240,), outline=_rgb(OPS_PALETTE["surface_edge"]) + (255,),
                    width=max(1, round(3 * scale)))
    times = phases(item)
    number_face = font(round(134 * scale))
    draw = ImageDraw.Draw(image)
    slot = OPS_SLOT * scale
    gap = 22 * scale
    widths = []
    for position, number in enumerate(numbers):
        widths.append(draw.textlength(str(number), font=number_face))
        if position < len(ops):
            widths.append(slot)
    total = sum(widths) + gap * (len(widths) - 1)
    shrink = min(1.0, 880 * scale / total)
    x = 540 * scale - total * shrink / 2
    row_y = (top + 170) * scale
    appear = 1.0 if hook else ease_out_cubic(_clamp(local / .35))
    remaining = times["think_end"] - local
    pulse = abs(math.sin(local * math.pi * 1.4)) if remaining > 0 and not hook else 0.0
    solve = 0.0 if hook else _clamp((local - times["think_end"]) / QUICK_MATH_SOLVE)
    for index, width in enumerate(widths):
        cx = x + width * shrink / 2
        if index % 2 == 0:
            _text(image, (cx, row_y - 6 * scale), str(numbers[index // 2]), number_face, OPS_PALETTE["text_light"], appear, shrink)
        else:
            slot_index = index // 2
            reveal = _clamp(solve * len(ops) - slot_index) if solve > 0 else 0.0
            hinted = not hook and slot_index == data.get("hint_slot") and local >= times["hint"]
            if hinted:  # halfway through a trap level this sign opens by itself
                reveal = max(reveal, _clamp((local - times["hint"]) / .35))
            _ops_slot(image, (cx, row_y), slot * shrink, scale, ops[slot_index], reveal, pulse, appear)
            if hinted and local < times["think_end"]:
                tag_y = row_y - slot * shrink / 2 - 34 * scale
                tag_w, tag_h = 104 * scale, 44 * scale
                rounded_surface(image, (cx - tag_w / 2, tag_y - tag_h / 2, cx + tag_w / 2, tag_y + tag_h / 2), tag_h / 2,
                                _rgb(OPS_PALETTE["success"]) + (255,))
                _text(image, (cx, tag_y - 2 * scale), "HINT", font(round(28 * scale)), OPS_PALETTE["background"])
        x += (width + gap) * shrink
    # The target sits on its own line, big, so the goal is clear at a glance.
    target_y = (top + 375) * scale
    answered = not hook and local >= times["answer"]
    color = OPS_PALETTE["success"] if answered else OPS_PALETTE["accent"]
    _text(image, (540 * scale, target_y), f"= {data['target']}", font(round(136 * scale)), color, appear)
    if answered:
        since = local - times["answer"]
        zoom = ease_out_back(_clamp(since / QUICK_MATH_ANSWER))
        cx, cy, r = 820 * scale, target_y, 40 * scale * zoom
        ImageDraw.Draw(image).line(((cx - r, cy), (cx - r * .3, cy + r * .7), (cx + r, cy - r * .7)),
                                   fill=_rgb(OPS_PALETTE["success"]), width=max(2, round(12 * scale)), joint="curve")
        _burst(image, (540 * scale, target_y), since, scale)


def _ops_legend(image: Image.Image, item: RoundSpec, scale: float) -> None:
    """The signs this level may use, right under the board."""
    allowed = item.data["allowed_ops"]
    y = (_ops_board_top() + OPS_BOARD_HEIGHT + 95) * scale
    face = font(round(42 * scale))
    tile, gap = 96 * scale, 20 * scale
    label_w = ImageDraw.Draw(image).textlength("USE", font=face) + 26 * scale
    total = label_w + len(allowed) * tile + (len(allowed) - 1) * gap
    x = 540 * scale - total / 2
    _text(image, (x + label_w / 2 - 13 * scale, y - 2 * scale), "USE", face, OPS_PALETTE["text_muted"])
    x += label_w
    for op in allowed:
        rounded_surface(image, (x, y - tile / 2, x + tile, y + tile / 2), 16 * scale, _rgb(OPS_PALETTE["slot"]) + (255,),
                        outline=_rgb(OPS_PALETTE["surface_edge"]) + (255,), width=max(1, round(3 * scale)))
        _text(image, (x + tile / 2, y - 5 * scale), op, font(round(66 * scale)), OPS_PALETTE["accent"])
        x += tile + gap


def draw_operators_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    image = _ops_background(size).copy()
    item = spec.rounds[0]
    pop = ease_out_back(_clamp(t / .3))
    _text(image, (540 * scale, 150 * scale), OPS_HOOK, fitted_font(OPS_HOOK, round(960 * scale), round(76 * scale)),
          OPS_PALETTE["text_light"], _clamp(t / .15), max(.5, pop))
    _text(image, (540 * scale, 232 * scale), f"{spec.round_count} LEVELS · EACH ONE HARDER", font(round(40 * scale)),
          OPS_PALETTE["accent"], _clamp((t - .15) / .25))
    _ops_prompt(image, item, scale, _clamp((t - .1) / .2))
    _ops_board(image, item, 0.0, scale, hook=True)
    _ops_legend(image, item, scale)
    return image


def draw_operators_round(spec: VideoSpec, index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    image = _ops_background(size).copy()
    item = spec.rounds[index]
    times = phases(item)
    _level_header(image, index + 1, spec.round_count, 1.0, scale)
    thinking = float(item.data["thinking_seconds"])
    if local < times["think_end"]:
        remaining = times["think_end"] - local
        _timer(image, min(thinking, remaining), thinking, _clamp(local / .25), scale)
        _ops_prompt(image, item, scale, 1.0, abs(math.sin(local * math.pi)) * (1 if remaining < 3 else 0))
        _pause_hint(image, remaining, local, scale)
    else:
        _text(image, (540 * scale, (_ops_board_top() - 88) * scale), "SOLUTION", font(round(52 * scale)), OPS_PALETTE["text_muted"])
    _ops_board(image, item, local, scale)
    _ops_legend(image, item, scale)
    if local >= times["answer"] and item.data["tier"] >= 2:
        note_y = (_ops_board_top() + OPS_BOARD_HEIGHT + 205) * scale
        _text(image, (540 * scale, note_y), f"Left to right gives {item.data['left_to_right']}. × and ÷ come first!",
              font(round(38 * scale)), OPS_PALETTE["accent"], _clamp((local - times["answer"] - .2) / .3))
    return image


def draw_operators_outro(spec: VideoSpec, local: float, size: tuple[int, int]) -> Image.Image:
    return draw_puzzle_fit_outro(spec, local, size, palette=OPS_PALETTE, background=_ops_background(size))


def draw_quick_math_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    operators = spec.rounds[0].data.get("format") == "operators"
    if t < spec.intro_duration:
        return (draw_operators_intro if operators else draw_quick_math_intro)(spec, t, size)
    levels = schedule(spec)
    rounds_end = levels[-1][0] + levels[-1][1]
    if t >= rounds_end:
        if operators:
            return draw_operators_outro(spec, t - rounds_end, size)
        return draw_puzzle_fit_outro(spec, t - rounds_end, size, OUTRO_QUESTION)
    index = max(position for position, (start, _) in enumerate(levels) if t >= start)
    return (draw_operators_round if operators else draw_quick_math_round)(spec, index, t - levels[index][0], size)
