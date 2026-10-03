"""Line Follow (Weave V7) in the Puzzly for You look: the figure's line through a board full of identical cables.

Every line is drawn as a lit cable with a dark casing, all in the same colour, so the eye has to follow it. At every
crossing one line is redrawn on top (chosen per crossing, never always the same line), and the casing makes over and
under unmistakable without cutting gaps into the lines. Only the figure's line reaches the figure; every other line
stops at a plain rounded loose end. The reveal traces the figure's line with a neon trail up to its target.
"""
from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
import math

from PIL import Image, ImageDraw, ImageFilter

from ..config import LINE_ENTRANCE, LINE_TRACE, PUZZLE_FIT_PALETTE as PALETTE, line_round
from ..models import RoundSpec, VideoSpec
from ..palette import object_color
from ..puzzles.line_weave import BOTTOM_Y, crossings_of, is_weave, line_points
from .easing import ease_in_out, ease_out_cubic
from .effects import rounded_surface
from .find_the_exit import _glow_disc, _symbol, _trail
from .paths import trace_points
from .puzzle_fit import _background, _clamp, _level_header, _rgb, _snap_burst, _text, _timer, active_theme, draw_puzzle_fit_outro
from .text import fitted_font, font

HOOK_TEXT = "WHERE DOES IT LEAD?"
CORE, CASING, GLOW = "#DCE2FF", "#0A0E22", "#5B6BD9"
FIGURE = "#2EE6C5"
TRAIL = "#2EE6C5"
TARGET_COLORS = ("#FFC24B", "#B69CFF", "#FF7A45", "#3DF08F", "#3DA9FF", "#FF6FB5", "#FFE066")
LINE_WIDTH = 7.5  # the cable core, logical px
CASING_WIDTH = 12.5
OVER_REACH = 16.0  # the piece of the top line redrawn over a crossing
CARD = (40, 272, 1040, 1790)
SUPERSAMPLE = 2  # the cables are drawn at twice the frame size and scaled down: smooth edges at every size
COVER_TIME = 0.6


def phases(item: RoundSpec) -> dict[str, float]:
    think_end = LINE_ENTRANCE + float(item.data["thinking_seconds"])
    return {"think_end": think_end, "arrival": think_end + LINE_TRACE}


def schedule(spec: VideoSpec) -> list[tuple[float, float]]:
    """(start, duration) of every level; bigger tangles get more thinking time and last longer."""
    result, start = [], spec.intro_duration
    for item in spec.rounds:
        duration = line_round(float(item.data["thinking_seconds"]))
        result.append((start, duration))
        start += duration
    return result


def answer_line(data: dict) -> dict:
    return next(line for line in data["lines"] if line.get("kind") == "answer")


# ---------------------------------------------------------------- static board

_ROUNDS: dict[str, dict] = {}


def _piece(points, arc: float, reach: float) -> list[tuple[float, float]]:
    """The part of a sampled line within `reach` of arc length `arc` (samples are 5 px apart)."""
    step = math.dist(points[0], points[1]) if len(points) > 1 else 5.0
    centre = arc / max(step, 1e-6)
    first, last = max(0, math.floor(centre - reach / step)), min(len(points) - 1, math.ceil(centre + reach / step))
    return points[first:last + 1]


def _top_of(data: dict, number: int, crossing: dict) -> int:
    """Which of the two lines is on top at a crossing: a fixed coin flip per crossing (so no line is always under)."""
    digest = sha256(f"{data['lines'][0]['controls'][3]}:{number}".encode()).digest()
    return digest[0] % 2


def _cables(layer: Image.Image, data: dict, scale: float) -> None:
    lines = [line_points(line) for line in data["lines"]]
    draw = ImageDraw.Draw(layer)

    def stroke(points, width: float, color: str, caps: bool) -> None:
        scaled = [(x * scale, y * scale) for x, y in points]
        if len(scaled) < 2:
            return
        w = max(2, round(width * scale))
        draw.line(scaled, fill=_rgb(color), width=w, joint="curve")
        if caps:
            for x, y in (scaled[0], scaled[-1]):
                draw.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=_rgb(color))

    for points in lines:
        stroke(points, CASING_WIDTH, CASING, True)
        stroke(points, LINE_WIDTH, CORE, True)
    for number, crossing in enumerate(crossings_of(data)):
        which = _top_of(data, number, crossing)
        line_index, arc = crossing["lines"][which], crossing["arcs"][which]
        # The top line over the crossing: its casing, then a slightly longer core that hides the casing's cut ends.
        stroke(_piece(lines[line_index], arc, OVER_REACH), CASING_WIDTH, CASING, False)
        stroke(_piece(lines[line_index], arc, OVER_REACH + 8), LINE_WIDTH, CORE, False)


@lru_cache(maxsize=6)
def _board(round_key: str, size: tuple[int, int], theme: str) -> Image.Image:
    data = _ROUNDS[round_key]
    scale = size[0] / 1080
    image = _background(size, 900, theme).copy()
    rounded_surface(image, tuple(v * scale for v in CARD), 60 * scale, PALETTE["surface"], PALETTE["surface_edge"], 3 * scale,
                    shadow=True)
    # Soft bloom under the cables, then the cables themselves drawn large and scaled down onto the card.
    left, top, right, bottom = (round(v * scale) for v in CARD)
    bloom = Image.new("L", size, 0)
    bloom_draw = ImageDraw.Draw(bloom)
    for line in data["lines"]:
        bloom_draw.line([(x * scale, y * scale) for x, y in line_points(line)], fill=255,
                        width=max(2, round(LINE_WIDTH * 2.6 * scale)), joint="curve")
    bloom = bloom.filter(ImageFilter.GaussianBlur(9 * scale)).point(lambda v: v * 70 // 255)
    image.paste(Image.new("RGB", size, GLOW), (0, 0), bloom)
    big_scale = scale * SUPERSAMPLE
    card = image.crop((left, top, right, bottom)).resize(((right - left) * SUPERSAMPLE, (bottom - top) * SUPERSAMPLE),
                                                         Image.Resampling.BICUBIC)
    shifted = {**data, "lines": [{**line, "controls": [[x - left / scale, y - top / scale] for x, y in line["controls"]]}
                                 for line in data["lines"]]}
    _cables(card, shifted, big_scale)
    image.paste(card.resize((right - left, bottom - top), Image.Resampling.LANCZOS), (left, top))
    return image


# ---------------------------------------------------------------- markers

def _target(image: Image.Image, index: int, center: tuple[float, float], radius: float, glow: float, dim: float) -> None:
    color = object_color(TARGET_COLORS[index % len(TARGET_COLORS)])
    _glow_disc(image, center, radius * 1.7, color, .5 * glow * (1 - dim))
    draw = ImageDraw.Draw(image)
    x, y = center
    ring = radius * 1.18
    fill = tuple(round(channel * (1 - .65 * dim)) for channel in _rgb("#1B2350"))
    tint = tuple(round(c * (1 - .6 * dim)) for c in _rgb(color))
    draw.ellipse((x - ring, y - ring, x + ring, y + ring), fill=fill, outline=tint, width=max(2, round(radius * .12)))
    r = radius * .72
    kind = index % 7
    if kind < 3:
        _symbol(draw, kind, x, y, r, tint, fill)  # star, moon, sun
    elif kind == 3:  # diamond
        draw.polygon([(x, y - r), (x + r * .8, y), (x, y + r), (x - r * .8, y)], fill=tint)
    elif kind == 4:  # ring
        draw.ellipse((x - r * .75, y - r * .75, x + r * .75, y + r * .75), outline=tint, width=max(2, round(r * .3)))
    elif kind == 5:  # heart
        draw.ellipse((x - r * .8, y - r * .6, x, y + r * .1), fill=tint)
        draw.ellipse((x, y - r * .6, x + r * .8, y + r * .1), fill=tint)
        draw.polygon([(x - r * .78, y - r * .12), (x + r * .78, y - r * .12), (x, y + r * .8)], fill=tint)
    else:  # triangle
        draw.polygon([(x, y - r * .85), (x + r * .85, y + r * .6), (x - r * .85, y + r * .6)], fill=tint)


def _figure(image: Image.Image, center_x: float, scale: float, glow: float = 1.0) -> None:
    """A clean pictogram of a person (head and shoulders), glowing: its line drops into the top of the head."""
    x, top = center_x * scale, (BOTTOM_Y + 4) * scale
    head = 22 * scale
    _glow_disc(image, (x, top + head + 34 * scale), 70 * scale, FIGURE, .55 * glow)
    draw = ImageDraw.Draw(image)
    draw.ellipse((x - head, top, x + head, top + head * 2), fill=_rgb(FIGURE), outline=_rgb("#D9FFF7"), width=max(1, round(2 * scale)))
    shoulders = (x - 48 * scale, top + head * 2 + 10 * scale, x + 48 * scale, top + head * 2 + 104 * scale)
    draw.pieslice(shoulders, 180, 360, fill=_rgb(FIGURE), outline=_rgb("#D9FFF7"), width=max(1, round(2 * scale)))


def _markers(image: Image.Image, data: dict, scale: float, arrival: float | None) -> None:
    radius = (30 if len(data["targets"]) <= 6 else 27) * scale
    for index, (x, y) in enumerate(data["targets"]):
        dim = 0.0 if arrival is None or index == data["correct_index"] else _clamp(arrival / .3)
        glow = 1.0 + (.8 * (1 - _clamp(arrival / .8)) if arrival is not None and index == data["correct_index"] else 0)
        _target(image, index, (x * scale, y * scale), radius, glow, dim)
    _figure(image, data["figure"][0], scale)


def reveal_route(data: dict) -> list[tuple[float, float]]:
    """The figure's line, from the figure up to its target portal (it is stored in that direction)."""
    target = data["targets"][data["correct_index"]]
    return line_points(answer_line(data)) + [(target[0], target[1])]


# ---------------------------------------------------------------- frames

def _board_image(item: RoundSpec, size: tuple[int, int]) -> Image.Image:
    from ..palette import active
    key = f"{item.fingerprint()}:{active()}"
    _ROUNDS[key] = item.data
    return _board(key, size, active_theme()).copy()


def board_for(data: dict, size: tuple[int, int]) -> Image.Image:
    """A finished board with its markers for any round data (the cover draws its own, unrelated tangle)."""
    key = "cover:" + sha256(repr(data["lines"]).encode()).hexdigest()
    _ROUNDS[key] = data
    image = _board(key, size, active_theme()).copy()
    _markers(image, data, size[0] / 1080, None)
    return image


def draw_line_round(spec: VideoSpec, index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[index]
    data = item.data
    image = _board_image(item, size)
    times = phases(item)
    arrival = local - times["arrival"] if local >= times["arrival"] else None
    if local >= times["think_end"]:
        progress = ease_in_out(_clamp((local - times["think_end"]) / LINE_TRACE))
        traced = [(x * scale, y * scale) for x, y in trace_points(reveal_route(data), progress)]
        _trail(image, traced, LINE_WIDTH * 1.3 * scale, scale)
        _glow_disc(image, traced[-1], 20 * scale, "#FFFFFF", .9)
    _markers(image, data, scale, arrival)
    if arrival is not None:
        x, y = data["targets"][data["correct_index"]]
        _snap_burst(image, (x, y), 110, arrival, scale)
    header = _clamp(local / .25)
    _level_header(image, data.get("level", index + 1), spec.round_count, header, scale)
    thinking = float(data["thinking_seconds"])
    if local < times["think_end"]:
        remaining = thinking if local < LINE_ENTRANCE else times["think_end"] - local
        _timer(image, remaining, thinking, header, scale)
    else:
        _timer(image, .001, 1, 1 - _clamp((local - times["think_end"]) / .25), scale)
    duration = line_round(thinking)
    if index > 0 and local < .3:
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (round(200 * (1 - ease_out_cubic(local / .3))),))
        image.paste(overlay, (0, 0), overlay)
    if local > duration - .2 and index < spec.round_count - 1:
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (round(200 * ease_in_out((local - duration + .2) / .2)),))
        image.paste(overlay, (0, 0), overlay)
    return image


def draw_line_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook: level one's real tangle (no answer shown) under a bold question."""
    scale = size[0] / 1080
    image = _board_image(spec.rounds[0], size)
    _markers(image, spec.rounds[0].data, scale, None)
    fade = 1 - _clamp((t - (spec.intro_duration - .22)) / .22)
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .18)))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(940 * scale), round(80 * scale)),
          PALETTE["text_light"], fade * _clamp(t / .08 + .3), slam)
    subtitle = f"{spec.round_count} LEVELS · EACH ONE HARDER"
    _text(image, (540 * scale, 232 * scale), subtitle, font(round(34 * scale)), PALETTE["accent"], fade * _clamp((t - .15) / .2))
    return image


def draw_line_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        return draw_line_intro(spec, t, size)
    levels = schedule(spec)
    rounds_end = levels[-1][0] + levels[-1][1]
    if t >= rounds_end:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size)
    index = max(i for i, (start, _) in enumerate(levels) if t >= start)
    return draw_line_round(spec, index, t - levels[index][0], size)


def uses_line_look(spec: VideoSpec) -> bool:
    return spec.puzzle_type == "line_follow" and bool(spec.rounds) and is_weave(spec.rounds[0].data)
