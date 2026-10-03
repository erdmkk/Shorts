"""Shade Spot in the Puzzly for You look: two stacked grids of nearly the same colours, one tile differs.

A level fades its two grids in (0.5 s), thinks (the numeric timer), then the other tiles dim, the two odd tiles pop (the
original above, the changed one below) and the answer shows (`IT'S B3`). Tiles are drawn in their exact colours on neutral
cards, so nothing around them shifts how a shade looks. The creator's object palette is ignored for this game.
"""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw

from ..config import PUZZLE_FIT_PALETTE as PALETTE, SHADE_ENTRANCE, SHADE_HOLD, SHADE_REVEAL, shade_round
from ..models import RoundSpec, VideoSpec
from ..puzzles.shade_spot import label
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .puzzle_fit import _background, _level_header, _snap_burst, _text, _timer, active_theme, draw_puzzle_fit_outro
from .text import fitted_font, font

PROMPT = "SPOT THE DIFFERENCE."
HOOK_TEXT = "SPOT THE DIFFERENCE."
OUTRO_QUESTION = "How many did you spot?"
CARD = 540.0  # the side of each grid card (logical 1080x1920 pixels)
CARD_X = (1080 - CARD) / 2
CARD_TOPS = (436.0, 1016.0)  # the original grid above, the changed one below
PAD = 18.0
GAPS = {3: 14.0, 4: 11.0, 5: 9.0}
CARD_FILL, CARD_EDGE = "#14161D", "#2A2E3C"  # neutral, so the tiles' colours are not tinted by what surrounds them
PROMPT_Y, LETTERS_Y, NOTE_Y = 330.0, 410.0, 1636.0
LABEL_COLOR = "#D5DAEE"
COVER_TIME = 0.6
# The concept pair of the hook and the end of the cover: violets with an obvious pink odd tile, never a real level.
CONCEPT = {"grid": 3, "odd": 6, "odd_color": "#C23FD2",
           "tiles": ["#A455E8", "#7B25E0", "#5B35C8", "#6C4DDC", "#4A22D8", "#7656D4", "#6A45D6", "#6F55D8", "#5030DA"]}
_ROUNDS: dict[str, RoundSpec] = {}


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------- timing

def phases(item: RoundSpec) -> dict[str, float]:
    think_end = SHADE_ENTRANCE + float(item.data["thinking_seconds"])
    return {"think_end": think_end, "answer": think_end + .45, "reveal_end": think_end + SHADE_REVEAL,
            "duration": shade_round(item.data)}


def schedule(spec: VideoSpec) -> list[tuple[float, float]]:
    """(start, duration) of every level; later levels think longer."""
    result, start = [], spec.intro_duration
    for item in spec.rounds:
        duration = shade_round(item.data)
        result.append((start, duration))
        start += duration
    return result


# ---------------------------------------------------------------- geometry

def tile_box(card: int, grid: int, index: int, grow: float = 0.0) -> tuple[float, float, float, float]:
    gap = GAPS[grid]
    tile = (CARD - 2 * PAD - gap * (grid - 1)) / grid
    row, column = divmod(index, grid)
    x1 = CARD_X + PAD + column * (tile + gap)
    y1 = CARD_TOPS[card] + PAD + row * (tile + gap)
    return x1 - grow, y1 - grow, x1 + tile + grow, y1 + tile + grow


def tile_colors(data: dict, card: int) -> list[str]:
    colors = list(data["tiles"])
    if card == 1:
        colors[data["odd"]] = data["odd_color"]
    return colors


def _draw_tile(image: Image.Image, box: tuple[float, float, float, float], color: str, scale: float, grid: int,
               outline: str | None = None, width: float = 0) -> None:
    radius = (box[2] - box[0]) * .18
    rounded_surface(image, tuple(value * scale for value in box), radius * scale, _rgb(color) + (255,),
                    _rgb(outline) + (255,) if outline else None, width * scale)


def _grids(image: Image.Image, data: dict, scale: float, labels: bool = True) -> None:
    """Both cards with their tiles, and the column letters and row numbers that name a spot."""
    grid = data["grid"]
    for card in (0, 1):
        top = CARD_TOPS[card]
        rounded_surface(image, tuple(value * scale for value in (CARD_X, top, CARD_X + CARD, top + CARD)), 34 * scale,
                        CARD_FILL, CARD_EDGE, 3 * scale, shadow=True)
        for index, color in enumerate(tile_colors(data, card)):
            _draw_tile(image, tile_box(card, grid, index), color, scale, grid)
    if not labels:
        return
    small = font(round(34 * scale))
    for column in range(grid):
        box = tile_box(0, grid, column)
        _text(image, ((box[0] + box[2]) / 2 * scale, LETTERS_Y * scale), chr(65 + column), small, LABEL_COLOR)
    for card in (0, 1):
        for row in range(grid):
            box = tile_box(card, grid, row * grid)
            _text(image, ((CARD_X - 26) * scale, (box[1] + box[3]) / 2 * scale), str(row + 1), small, LABEL_COLOR)


@lru_cache(maxsize=3)
def _board(key: str, size: tuple[int, int], theme: str) -> Image.Image:
    """The background with both grids, static for the whole level."""
    image = _background(size, 960, theme).copy()
    _grids(image, _ROUNDS[key].data, size[0] / 1080)
    return image


def _register(spec: VideoSpec, index: int) -> str:
    from ..palette import active
    item = spec.rounds[index]
    key = f"{spec.id}:{item.fingerprint()}:{active()}"
    _ROUNDS[key] = item
    return key


# ---------------------------------------------------------------- pieces of the frame

def _prompt(image: Image.Image, scale: float, opacity: float = 1.0, text: str = PROMPT, color: str | None = None) -> None:
    if opacity <= 0:
        return
    face = fitted_font(text, round(860 * scale), round(58 * scale))
    width = ImageDraw.Draw(image).textlength(text, font=face) + 100 * scale
    height = 100 * scale
    y = PROMPT_Y * scale
    rounded_surface(image, (540 * scale - width / 2, y - height / 2, 540 * scale + width / 2, y + height / 2), height / 2,
                    _rgb(color or PALETTE["accent"]) + (round(255 * opacity),))
    _text(image, (540 * scale, y - 2 * scale), text, face, PALETTE["background"], opacity)


def example_spot(answer: str, grid: int) -> str:
    """A spot to show in `Comment its spot, like B3`: never the real answer."""
    for candidate in ("B2", "C1", "A3"):
        if candidate != answer:
            return candidate
    return "B2"


def _reveal(image: Image.Image, item: RoundSpec, since: float, scale: float) -> None:
    """The other tiles dim, the two odd tiles pop with a green outline, and the answer appears."""
    data = item.data
    grid, odd = data["grid"], data["odd"]
    dim = ease_in_out(_clamp(since / .3))
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    area = (CARD_X - 36, CARD_TOPS[0] - 20, CARD_X + CARD + 20, CARD_TOPS[1] + CARD + 20)  # only the two grids dim
    ImageDraw.Draw(overlay).rounded_rectangle(tuple(value * scale for value in area), radius=40 * scale,
                                               fill=(4, 6, 16, round(185 * dim)))
    holes = ImageDraw.Draw(overlay)
    for card in (0, 1):
        box = tile_box(card, grid, odd, 4)
        holes.rounded_rectangle(tuple(value * scale for value in box), radius=(box[2] - box[0]) * .2 * scale, fill=(0, 0, 0, 0))
    image.paste(overlay, (0, 0), overlay)
    pop = ease_out_back(_clamp((since - .1) / .35))
    grow = 12 * pop
    for card in (0, 1):
        _draw_tile(image, tile_box(card, grid, odd, grow), tile_colors(data, card)[odd], scale, grid,
                   PALETTE["success"], 6)
    answer = _clamp((since - .45) / .3)
    if answer > 0:
        text = f"IT'S {item.answer}"
        face = font(round(72 * scale))
        width = ImageDraw.Draw(image).textlength(text, font=face) + 110 * scale
        height = 112 * scale
        zoom = .6 + .4 * ease_out_back(answer)
        w, h, y = width * zoom, height * zoom, NOTE_Y * scale
        rounded_surface(image, (540 * scale - w / 2, y - h / 2, 540 * scale + w / 2, y + h / 2), h / 2,
                        _rgb(PALETTE["success"]) + (round(255 * answer),))
        _text(image, (540 * scale, y - 2 * scale), text, face, PALETTE["background"], answer, zoom)
        box = tile_box(1, grid, odd)
        _snap_burst(image, ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), box[2] - box[0], since - .45, scale)


# ---------------------------------------------------------------- frames

def draw_shade_round(spec: VideoSpec, index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[index]
    data = item.data
    key = _register(spec, index)
    times = phases(item)
    thinking = float(data["thinking_seconds"])
    appear = ease_out_cubic(_clamp(local / SHADE_ENTRANCE))
    board = _board(key, size, active_theme())
    image = board.copy() if appear >= 1 else Image.blend(_background(size, 960, active_theme()), board, appear)
    _level_header(image, data.get("level", index + 1), spec.round_count, 1.0, scale)
    if local < times["think_end"]:
        _timer(image, min(thinking, times["think_end"] - local), thinking, _clamp(local / .25), scale)
        _prompt(image, scale, _clamp(local / .25))
        _text(image, (540 * scale, NOTE_Y * scale), f"Comment its spot, like {example_spot(item.answer, data['grid'])} ↓",
              font(round(40 * scale)), PALETTE["text_muted"], _clamp((local - .3) / .3))
    else:
        since = local - times["think_end"]
        _timer(image, 0.001, 1, 1 - _clamp(since / .25), scale)
        _prompt(image, scale, 1.0, "FOUND IT.", PALETTE["success"])
        _reveal(image, item, since, scale)
    if local < .2 and index > 0:
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (round(200 * (1 - _clamp(local / .2))),))
        image.paste(overlay, (0, 0), overlay)
    return image


def draw_shade_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook: a fixed concept pair (violets with an obvious odd tile), never a real level."""
    scale = size[0] / 1080
    image = _background(size, 960, active_theme()).copy()
    _grids(image, CONCEPT, scale, labels=False)
    from .ready import hook_end
    fade = 1 - _clamp((t - (hook_end(spec) - .22)) / .22)
    pop = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .18)))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(940 * scale), round(84 * scale)),
          PALETTE["text_light"], fade * _clamp(t / .08 + .3), pop)
    _text(image, (540 * scale, 232 * scale), f"{spec.round_count} LEVELS · EACH ONE HARDER", font(round(40 * scale)),
          PALETTE["accent"], fade * _clamp((t - .15) / .2))
    return image


# ---------------------------------------------------------------- the cover card

COVER_SIZE = (1000, 500)  # logical size of the card content: the two grids side by side, so each is as large as possible
COVER_BOOST = 1.35  # the cover's colours are livelier than the puzzle's (the same boost for both grids, so a difference stays)


def _boosted(color: str) -> str:
    from ..puzzles.shade_spot import hex_to_lab, lab_to_hex
    lightness, a, b = hex_to_lab(color)
    for factor in (COVER_BOOST, 1.2, 1.1, 1.0):
        result = lab_to_hex(lightness, a * factor, b * factor)
        if result:
            return result
    return color


def cover_card(spec: VideoSpec, supersample: int = 2) -> Image.Image:
    """The cover's card face: level 1's two grids side by side as glossy tiles on a dark panel (a small spoiler is accepted,
    like on every other cover). Drawn at `supersample` pixels per logical pixel."""
    k = supersample
    data = spec.rounds[0].data
    grid = data["grid"]
    width, height = COVER_SIZE
    image = Image.new("RGB", (width * k, height * k), "#0E1018")
    side, gap, pad = 440.0, 56.0, 12.0
    left = (width - 2 * side - gap) / 2
    top = (height - side) / 2
    for card in (0, 1):
        x0 = left + card * (side + gap)
        rounded_surface(image, tuple(value * k for value in (x0, top, x0 + side, top + side)), 40 * k, CARD_FILL, CARD_EDGE, 4 * k)
        tile_gap = 10.0
        tile = (side - 2 * pad - 2 * 6 - tile_gap * (grid - 1)) / grid
        for index, color in enumerate(tile_colors(data, card)):
            row, column = divmod(index, grid)
            x1 = x0 + pad + 6 + column * (tile + tile_gap)
            y1 = top + pad + 6 + row * (tile + tile_gap)
            box = tuple(value * k for value in (x1, y1, x1 + tile, y1 + tile))
            rounded_surface(image, box, tile * .18 * k, _rgb(_boosted(color)) + (255,))
            shine = Image.new("RGBA", image.size, (0, 0, 0, 0))
            ImageDraw.Draw(shine).rounded_rectangle((box[0] + tile * .08 * k, box[1] + tile * .07 * k, box[2] - tile * .08 * k,
                                                      box[1] + tile * .36 * k), radius=tile * .12 * k, fill=(255, 255, 255, 34))
            image.paste(shine, (0, 0), shine)
    return image


def draw_shade_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        from .ready import HOOK_SECONDS, draw_ready_screen, has_ready
        if has_ready(spec) and t >= HOOK_SECONDS:  # the viewer is told what to do before the first board appears
            return draw_ready_screen(spec, t - HOOK_SECONDS, size, _background(size, 960, active_theme())).convert("RGB")
        return draw_shade_intro(spec, t, size).convert("RGB")
    levels = schedule(spec)
    rounds_end = levels[-1][0] + levels[-1][1]
    if t >= rounds_end - 1e-9:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size, OUTRO_QUESTION)
    index = max(position for position, (start, _) in enumerate(levels) if t >= start - 1e-9)
    return draw_shade_round(spec, index, t - levels[index][0], size).convert("RGB")
