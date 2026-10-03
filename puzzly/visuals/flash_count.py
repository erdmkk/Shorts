"""Flash Count, number flash, in the "Puzzly for You" look.

The video opens on a 2 s ARE YOU READY? screen (no timer). Each level: a screen card with one empty slot per digit
(GET READY), the number flashes for a split second, the slots show "?" while the timer runs, then the digits drop into
their slots one by one and the whole number lights up green. The cover shows its own random number, never a level's.
"""
from __future__ import annotations

from functools import lru_cache
import random

from PIL import Image, ImageDraw, ImageFont

from ..config import FLASH_READY, FLASH_REVEAL, FLASH_THINKING, flash_round_duration
from ..models import VideoSpec
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .puzzle_fit import (PALETTE, _background, _clamp, _level_header, _rgb, _snap_burst, _text, _timer, active_theme,
                         draw_puzzle_fit_outro)
from .text import WINDOWS_FONTS, display_font, fitted_font, font

HOOK_TEXT = "BLINK AND YOU MISS IT."  # the READY screen (ready.py) asks ARE YOU READY? after it
QUESTION = "What was the number?"
CARD = (60, 690, 1020, 1030)
ROW_Y = 860
SLOT_GAP = 18
EPS = 1e-6  # frame times are k / fps; keep a flash that starts on a frame boundary on that frame


def phases(data: dict) -> dict[str, float]:
    flash_end = FLASH_READY + float(data["visible_seconds"])
    think_end = flash_end + FLASH_THINKING
    reveal_end = think_end + FLASH_REVEAL
    return {"flash_start": FLASH_READY, "flash_end": flash_end, "think_end": think_end,
            "reveal_end": reveal_end, "end": flash_round_duration("hard")}


def flash_state(local: float, data: dict) -> str:
    times = phases(data)
    local += EPS
    for name, until in (("ready", "flash_start"), ("flash", "flash_end"), ("thinking", "think_end"),
                        ("reveal", "reveal_end")):
        if local < times[until]:
            return name
    return "solved"


@lru_cache(maxsize=16)
def digit_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(WINDOWS_FONTS / "seguibl.ttf"), size=size)
    except OSError:
        return font(size)


def slots(digits: int) -> list[tuple[float, float, float, float]]:
    """Logical boxes of the digit slots, centred on the card."""
    width = min(140.0, (800 - (digits - 1) * SLOT_GAP) / digits)
    height = 196.0
    total = digits * width + (digits - 1) * SLOT_GAP
    left = 540 - total / 2
    return [(left + index * (width + SLOT_GAP), ROW_Y - height / 2, left + index * (width + SLOT_GAP) + width, ROW_Y + height / 2)
            for index in range(digits)]


def _box(box, scale: float) -> tuple[float, float, float, float]:
    return tuple(value * scale for value in box)


def _card(image: Image.Image, scale: float, opacity: float = 1.0) -> None:
    rounded_surface(image, _box(CARD, scale), 56 * scale, PALETTE["surface"], PALETTE["surface_edge"], 3 * scale,
                    shadow=True, opacity=round(255 * opacity))


def _slot(image: Image.Image, box, scale: float, fill: str, edge: str, opacity: float = 1.0) -> None:
    rounded_surface(image, _box(box, scale), 26 * scale, fill, edge, 3 * scale, opacity=round(255 * opacity))


def _digit(image: Image.Image, box, value: str, scale: float, color: str, opacity: float = 1.0, zoom: float = 1.0) -> None:
    center = ((box[0] + box[2]) / 2 * scale, (box[1] + box[3]) / 2 * scale - 6 * scale)
    _text(image, center, value, digit_font(round((box[3] - box[1]) * .72 * scale)), color, opacity, zoom)


def _brackets(image: Image.Image, boxes, scale: float, strength: float) -> None:
    """Focus brackets around the slot row: look here."""
    if strength <= 0:
        return
    x1, y1, x2, y2 = boxes[0][0] - 34, boxes[0][1] - 30, boxes[-1][2] + 34, boxes[-1][3] + 30
    arm, width = 46, max(2, round(6 * scale))
    color = _rgb(PALETTE["accent"]) + (round(255 * strength),)
    draw = ImageDraw.Draw(image, "RGBA")
    for cx, cy, dx, dy in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
        draw.line([((cx + dx * arm) * scale, cy * scale), (cx * scale, cy * scale), (cx * scale, (cy + dy * arm) * scale)],
                  fill=color, width=width, joint="curve")


def draw_flash_round(spec: VideoSpec, round_index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[round_index]
    data = item.data
    number = data["number"]
    boxes = slots(len(number))
    times = phases(data)
    state = flash_state(local, data)
    image = _background(size, ROW_Y, active_theme()).copy()
    _card(image, scale)
    header = _clamp(local / .25)
    _level_header(image, data.get("level", round_index + 1), spec.round_count, header, scale)
    surface, edge = PALETTE["surface"], PALETTE["surface_edge"]
    if state == "ready":
        # Empty slots (the viewer knows how many digits are coming) under pulsing focus brackets.
        for box in boxes:
            _slot(image, box, scale, PALETTE["hole"], edge, _clamp(local / .2))
        _brackets(image, boxes, scale, .55 + .45 * abs(((local / FLASH_READY) * 3) % 2 - 1))
        dots = min(3, int(local / FLASH_READY * 3) + 1)
        _text(image, (540 * scale, 610 * scale), "GET READY" + " ." * dots, font(round(44 * scale)), PALETTE["text_muted"], header)
    elif state == "flash":
        for box, value in zip(boxes, number):
            _slot(image, box, scale, PALETTE["hole"], edge)
            _digit(image, box, value, scale, PALETTE["text_light"])
    elif state == "thinking":
        for box in boxes:
            _slot(image, box, scale, PALETTE["hole"], edge)
            _digit(image, box, "?", scale, PALETTE["accent"], .55 + .1 * abs(((local * 1.6) % 2) - 1))
        _timer(image, times["think_end"] - local, FLASH_THINKING, 1.0, scale)
    else:
        step = FLASH_REVEAL / len(number)
        solved = state == "solved"
        for position, (box, value) in enumerate(zip(boxes, number)):
            since = local - times["think_end"] - position * step
            if since < 0:
                _slot(image, box, scale, PALETTE["hole"], edge)
                _digit(image, box, "?", scale, PALETTE["accent"], .55)
                continue
            fill = PALETTE["success"] if solved else PALETTE["primary"]
            _slot(image, box, scale, fill, PALETTE["text_light"])
            ink = PALETTE["background"] if solved else PALETTE["text_light"]
            _digit(image, box, value, scale, ink, 1.0, 1 + .35 * (1 - ease_out_back(_clamp(since / .22))))
        if solved:
            _snap_burst(image, (540, ROW_Y), 260, local - times["reveal_end"], scale)
    if state in ("thinking", "reveal"):
        fade = _clamp((local - times["flash_end"]) / .2) * (1 - _clamp((local - times["think_end"]) / .25))
        _text(image, (540 * scale, 1150 * scale), QUESTION, fitted_font(QUESTION, round(900 * scale), round(72 * scale)),
              PALETTE["text_light"], fade)
    if state == "solved":
        pop = 1 + .2 * (1 - ease_out_cubic(_clamp((local - times["reveal_end"]) / .3)))
        _text(image, (540 * scale, 1150 * scale), "Did you get it?", font(round(64 * scale)), PALETTE["success"],
              _clamp((local - times["reveal_end"]) / .15), pop)
    if local < .3 and round_index > 0:
        alpha = round(200 * (1 - ease_out_cubic(_clamp(local / .3))))
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (alpha,))
        image.paste(overlay, (0, 0), overlay)
    transition_start = spec.round_duration - .2
    if local > transition_start and round_index < spec.round_count - 1:
        alpha = round(200 * ease_in_out((local - transition_start) / .2))
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (alpha,))
        image.paste(overlay, (0, 0), overlay)
    return image


def cover_number(spec: VideoSpec) -> str:
    """The cover's own random number: drawn separately from the game, never one of its levels."""
    from ..puzzles.flash_count import make_number
    return make_number(4, random.Random(f"flash_cover:{spec.id}"), {item.data["number"] for item in spec.rounds})


def draw_cover_card(spec: VideoSpec, size: tuple[int, int]) -> Image.Image:
    """The number card for the 3D cover, showing cover_number (no spoiler from the game)."""
    scale = size[0] / 1080
    image = _background(size, ROW_Y, active_theme()).copy()
    _card(image, scale)
    number = cover_number(spec)
    boxes = slots(len(number))
    for box, value in zip(boxes, number):
        _slot(image, box, scale, PALETTE["hole"], PALETTE["surface_edge"])
        _digit(image, box, value, scale, PALETTE["text_light"])
    _brackets(image, boxes, scale, .9)
    return image


def draw_flash_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """ARE YOU READY? screen before the first level: empty slots under pulsing focus brackets, no timer, no number."""
    scale = size[0] / 1080
    image = _background(size, ROW_Y, active_theme()).copy()
    _card(image, scale, _clamp(t / .25))
    boxes = slots(4)
    for box in boxes:
        _slot(image, box, scale, PALETTE["hole"], PALETTE["surface_edge"], _clamp(t / .25))
    _brackets(image, boxes, scale, .55 + .45 * abs((t * 1.5) % 2 - 1))
    from .ready import hook_end
    fade = 1 - _clamp((t - (hook_end(spec) - .25)) / .25)
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .2)))
    _text(image, (540 * scale, 520 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(940 * scale), round(96 * scale)),
          PALETTE["text_light"], fade * _clamp(t / .08 + .3), slam)
    subtitle = f"{spec.round_count} LEVELS · ONE BLINK EACH"
    _text(image, (540 * scale, 1150 * scale), subtitle, display_font(round(44 * scale)), PALETTE["accent"],
          fade * _clamp((t - .3) / .3))
    return image

def draw_flash_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        from .ready import HOOK_SECONDS, draw_ready_screen, has_ready
        if has_ready(spec) and t >= HOOK_SECONDS:
            return draw_ready_screen(spec, t - HOOK_SECONDS, size)
        return draw_flash_intro(spec, t, size)
    rounds_end = spec.intro_duration + spec.round_count * spec.round_duration
    if t >= rounds_end:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size)
    elapsed = t - spec.intro_duration
    round_index = min(spec.round_count - 1, int((elapsed + EPS) / spec.round_duration))
    return draw_flash_round(spec, round_index, elapsed - round_index * spec.round_duration, size)
