"""Laser Maze frames (Puzzly for You look): a laser enters a square board of two-sided mirrors and the viewer says which numbered
receiver the beam ends in.

Level timeline (`phases`): a 0.5 s entrance, thinking (only a short stub of the beam leaves the emitter, so the way in is clear
but the way through is not), then the beam runs its whole path (it turns 90 degrees at every mirror, with a flash at each
bounce) and lights the receiver it ends in, then the answer hold. The beam only ever runs along cell middles, so its drawing
is axis-aligned and always crisp. Receivers are numbered clockwise from the top left; viewers comment a number.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFilter

from ..config import LASER_ENTRANCE, PUZZLE_FIT_PALETTE as PALETTE, laser_round
from ..models import RoundSpec, VideoSpec
from ..puzzles.laser_maze import port_cell
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .puzzle_fit import _background, _level_header, _snap_burst, _text, _timer, active_theme, draw_puzzle_fit_outro
from .text import fitted_font, font

PROMPT_WATCH = "FOLLOW THE LASER."
PROMPT_GUESS = "WHERE DOES IT END?"
COMMENT = "Comment the number ↓"
HOOK_TEXT = "FOLLOW THE LASER."
BOARD = 760.0  # the square board (logical 1080x1920)
BOARD_X, BOARD_Y = 160.0, 600.0
CARD = (44, 480, 1036, 1480)  # the dark card behind the board, emitter and receivers
PROMPT_Y = 390.0
COMMENT_Y = 1560.0
OUT = 62.0  # how far outside the board a receiver's centre sits
RECEIVER_R = 30.0
EMITTER_LENGTH = 70.0
STUB = .55  # the thinking-time beam, in cells
BEAM_RED = "#FF3D5A"
BEAM_CORE = "#FFE6EA"
COVER_TIME = .6
OUTLINE = (11, 16, 32)


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------- timing

def phases(item: RoundSpec) -> dict[str, float]:
    data = item.data
    think_end = LASER_ENTRANCE + float(data["thinking_seconds"])
    trace_end = think_end + float(data["trace_seconds"])
    return {"think_end": think_end, "trace_end": trace_end, "hold_end": laser_round(data)}


def schedule(spec: VideoSpec) -> list[tuple[float, float]]:
    """(start, duration) of every level; later levels have bigger boards and longer beams."""
    result, start = [], spec.intro_duration
    for item in spec.rounds:
        duration = laser_round(item.data)
        result.append((start, duration))
        start += duration
    return result


# ---------------------------------------------------------------- geometry (logical px)

def cell_size(data: dict) -> float:
    return BOARD / data["n"]


def cell_center(data: dict, row: int, column: int) -> tuple[float, float]:
    cell = cell_size(data)
    return BOARD_X + (column + .5) * cell, BOARD_Y + (row + .5) * cell


def port_point(data: dict, port: int, offset: float) -> tuple[float, float]:
    """The point `offset` px outside the board in front of a port."""
    (row, column), direction = port_cell(data["n"], port)
    x, y = cell_center(data, row, column)
    reach = cell_size(data) / 2 + offset
    return x - direction[1] * reach, y - direction[0] * reach


def receiver_points(data: dict) -> list[tuple[float, float]]:
    return [port_point(data, port, OUT) for port in data["receivers"]]


def beam_points(data: dict) -> list[tuple[float, float]]:
    """The beam's corners: out of the emitter's nozzle, to the middle of every mirror cell it turns in, into the receiver."""
    points = [port_point(data, data["entry"], OUT - EMITTER_LENGTH / 2 - 8)]
    points += [cell_center(data, *data["path"][index]) for index in data["hits"]]
    points.append(port_point(data, data["exit"], OUT - RECEIVER_R))
    return points


def _lengths(points: list[tuple[float, float]]) -> list[float]:
    total, result = 0.0, [0.0]
    for first, second in zip(points, points[1:]):
        total += math.dist(first, second)
        result.append(total)
    return result


def beam_until(points: list[tuple[float, float]], distance: float) -> list[tuple[float, float]]:
    """The beam's polyline from the nozzle up to `distance` along it."""
    lengths = _lengths(points)
    result = [points[0]]
    for index in range(1, len(points)):
        if lengths[index] <= distance:
            result.append(points[index])
            continue
        span = lengths[index] - lengths[index - 1]
        t = _clamp((distance - lengths[index - 1]) / span) if span else 0.0
        first, second = points[index - 1], points[index]
        result.append((first[0] + (second[0] - first[0]) * t, first[1] + (second[1] - first[1]) * t))
        break
    return result


# ---------------------------------------------------------------- static board

_STATIC: dict[tuple, Image.Image] = {}
SS = 2  # the board is painted at 2x and shrunk once


def _board_layer(data: dict, size: tuple[int, int], theme: str) -> Image.Image:
    """The dark card with the floor grid and the mirrors, on the video's background."""
    scale = size[0] / 1080
    image = _background(size, 960.0, theme).copy().convert("RGBA")
    box = tuple(value * scale for value in CARD)
    rounded_surface(image, box, 56 * scale, PALETTE["surface"], PALETTE["surface_edge"], 3 * scale, shadow=True)
    x1, y1, x2, y2 = (round(value) for value in box)
    ss = SS
    layer = Image.new("RGBA", ((x2 - x1) * ss, (y2 - y1) * ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    n, cell = data["n"], cell_size(data)

    def at(x: float, y: float) -> tuple[float, float]:
        return (x * scale - x1) * ss, (y * scale - y1) * ss

    # The floor: a faint checker and thin grid lines.
    for row in range(n):
        for column in range(n):
            left, top = at(BOARD_X + column * cell, BOARD_Y + row * cell)
            right, bottom = at(BOARD_X + (column + 1) * cell, BOARD_Y + (row + 1) * cell)
            tint = _rgb(PALETTE["accent"]) + ((16 if (row + column) % 2 else 6),)
            draw.rectangle((left, top, right, bottom), fill=tint)
    line = _rgb(PALETTE["surface_edge"]) + (190,)
    for index in range(n + 1):
        a, b = at(BOARD_X + index * cell, BOARD_Y), at(BOARD_X + index * cell, BOARD_Y + BOARD)
        draw.line((a, b), fill=line, width=max(1, round(2 * scale * ss)))
        a, b = at(BOARD_X, BOARD_Y + index * cell), at(BOARD_X + BOARD, BOARD_Y + index * cell)
        draw.line((a, b), fill=line, width=max(1, round(2 * scale * ss)))
    draw.rectangle((*at(BOARD_X, BOARD_Y), *at(BOARD_X + BOARD, BOARD_Y + BOARD)), outline=_rgb(PALETTE["accent"]) + (170,),
                   width=max(2, round(4 * scale * ss)))
    for row, column, kind in data["mirrors"]:
        _mirror(layer, data, row, column, kind, at, scale * ss)
    image.alpha_composite(layer.resize((x2 - x1, y2 - y1), Image.Resampling.LANCZOS), (x1, y1))
    return image


def _mirror(layer: Image.Image, data: dict, row: int, column: int, kind: str, at, unit: float) -> None:
    """A two-sided mirror: a glossy slanted bar with a dark edge, reaching most of the way across its cell."""
    cell = cell_size(data)
    cx, cy = cell_center(data, row, column)
    half = cell * .36
    if kind == "/":
        a, b = at(cx - half, cy + half), at(cx + half, cy - half)
    else:
        a, b = at(cx - half, cy - half), at(cx + half, cy + half)
    thick = max(7.0, cell * .115) * unit
    draw = ImageDraw.Draw(layer)
    shadow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).line((a[0] + thick * .25, a[1] + thick * .45, b[0] + thick * .25, b[1] + thick * .45),
                                fill=(0, 0, 0, 150), width=round(thick * 1.5))
    layer.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(thick * .5)))
    draw.line((a, b), fill=OUTLINE + (255,), width=round(thick * 1.45))
    draw.line((a, b), fill=_rgb("#B9CCFF") + (255,), width=round(thick))
    draw.line((a, b), fill=_rgb("#EFF4FF") + (255,), width=max(1, round(thick * .38)))
    for end in (a, b):  # rounded caps
        r = thick * .72
        draw.ellipse((end[0] - r, end[1] - r, end[0] + r, end[1] + r), fill=OUTLINE + (255,))
        r = thick * .5
        draw.ellipse((end[0] - r, end[1] - r, end[0] + r, end[1] + r), fill=_rgb("#B9CCFF") + (255,))


def _static(item: RoundSpec, size: tuple[int, int], theme: str) -> Image.Image:
    key = (item.fingerprint(), size, theme)
    if key not in _STATIC:
        if len(_STATIC) > 6:
            _STATIC.clear()
        _STATIC[key] = _board_layer(item.data, size, theme).convert("RGB")
    return _STATIC[key]


# ---------------------------------------------------------------- emitter, beam, receivers

_EMITTER: dict[int, Image.Image] = {}


def _emitter(px: int) -> Image.Image:
    """The laser: a dark housing with a red band and a glowing lens, drawn facing right, `px` pixels long."""
    if px not in _EMITTER:
        ss = 4
        width, height = px * ss, round(px * .66) * ss
        sprite = Image.new("RGBA", (width + 8 * ss, height + 8 * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(sprite)
        box = (4 * ss, 4 * ss, 4 * ss + width, 4 * ss + height)
        d.rounded_rectangle(box, radius=height * .3, fill=OUTLINE + (255,))
        inner = tuple(value + (round(height * .06) if index % 2 == 0 else -round(height * .06)) for index, value in enumerate(box))
        d.rounded_rectangle(inner, radius=height * .26, fill=_rgb("#3A4468") + (255,))
        d.rectangle((box[0] + width * .52, box[1] + height * .12, box[0] + width * .66, box[3] - height * .12), fill=_rgb(BEAM_RED) + (255,))
        d.rounded_rectangle((box[0] + height * .1, box[1] + height * .16, box[0] + width * .45, box[1] + height * .38), radius=height * .08,
                            fill=(255, 255, 255, 60))
        lens = (box[2] - height * .42, box[1] + height * .5 - height * .2, box[2] - height * .02, box[1] + height * .5 + height * .2)
        d.ellipse(lens, fill=_rgb(BEAM_CORE) + (255,), outline=_rgb(BEAM_RED) + (255,), width=round(height * .06))
        _EMITTER[px] = sprite.resize((sprite.width // ss, sprite.height // ss), Image.Resampling.LANCZOS)
    return _EMITTER[px]


def _draw_emitter(image: Image.Image, data: dict, scale: float, pulse: float) -> None:
    (_, _), direction = port_cell(data["n"], data["entry"])
    sprite = _emitter(max(8, round(EMITTER_LENGTH * scale)))
    angle = math.degrees(math.atan2(-direction[0], direction[1]))
    rotated = sprite.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    # The housing sits behind the nozzle: its centre is half a length outside it.
    nozzle = port_point(data, data["entry"], OUT - EMITTER_LENGTH / 2 - 8)
    centre = (nozzle[0] - direction[1] * EMITTER_LENGTH / 2, nozzle[1] - direction[0] * EMITTER_LENGTH / 2)
    image.alpha_composite(rotated, (round(centre[0] * scale - rotated.width / 2), round(centre[1] * scale - rotated.height / 2)))
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    r = (18 + 6 * pulse) * scale
    gx, gy = nozzle[0] * scale, nozzle[1] * scale
    ImageDraw.Draw(glow).ellipse((gx - r, gy - r, gx + r, gy + r), fill=_rgb(BEAM_RED) + (150,))
    image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10 * scale)))


def _draw_beam(image: Image.Image, polyline: list[tuple[float, float]], scale: float, strength: float, head: bool) -> None:
    """A neon beam with bloom along an axis-aligned polyline (logical px)."""
    if len(polyline) < 2 or strength <= 0:
        return
    xs, ys = [p[0] for p in polyline], [p[1] for p in polyline]
    pad = 60
    x1, y1 = max(0, math.floor((min(xs) - pad) * scale)), max(0, math.floor((min(ys) - pad) * scale))
    x2, y2 = min(image.width, math.ceil((max(xs) + pad) * scale)), min(image.height, math.ceil((max(ys) + pad) * scale))
    if x2 <= x1 or y2 <= y1:
        return
    local = [((x * scale - x1), (y * scale - y1)) for x, y in polyline]
    width, height = x2 - x1, y2 - y1
    small = 4
    bloom = Image.new("RGBA", (max(1, width // small), max(1, height // small)), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bloom)
    sp = [(x / small, y / small) for x, y in local]
    bd.line(sp, fill=_rgb(BEAM_RED) + (round(235 * strength),), width=max(2, round(30 * scale / small)), joint="curve")
    for x, y in (sp[0], sp[-1]):
        r = 15 * scale / small
        bd.ellipse((x - r, y - r, x + r, y + r), fill=_rgb(BEAM_RED) + (round(235 * strength),))
    bloom = bloom.filter(ImageFilter.GaussianBlur(max(1.0, 9 * scale / small))).resize((width, height), Image.Resampling.BILINEAR)
    image.alpha_composite(bloom, (x1, y1))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for stroke, color in ((15 * scale, _rgb(BEAM_RED)), (6.5 * scale, _rgb(BEAM_CORE))):
        w = max(2, round(stroke))
        ld.line(local, fill=color + (round(255 * strength),), width=w, joint="curve")
        for x, y in local:  # round joints and caps
            ld.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=color + (round(255 * strength),))
    image.alpha_composite(layer, (x1, y1))
    if head:
        x, y = local[-1]
        r = 15 * scale
        flare = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(flare).ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, 255))
        image.alpha_composite(flare.filter(ImageFilter.GaussianBlur(max(1.0, 3 * scale))), (x1, y1))


def _bounce_flash(image: Image.Image, point: tuple[float, float], since: float, scale: float) -> None:
    if since < 0 or since > .35:
        return
    progress = ease_out_cubic(since / .35)
    draw = ImageDraw.Draw(image, "RGBA")
    cx, cy = point[0] * scale, point[1] * scale
    r = (14 + 30 * progress) * scale
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=_rgb(BEAM_CORE) + (round(230 * (1 - progress)),), width=max(2, round(5 * (1 - progress) * scale) + 1))


def _draw_receivers(image: Image.Image, data: dict, scale: float, opacity: float, answer: int | None, solved: float,
                    local_since_arrival: float) -> None:
    """Numbered sockets (clockwise from the top left); at the reveal the right one lights green and the others dim."""
    if opacity <= 0:
        return
    for index, (x, y) in enumerate(receiver_points(data)):
        right = answer is not None and index == answer
        dim = answer is not None and not right
        r = RECEIVER_R * (1 + .16 * solved * ease_out_back(_clamp(local_since_arrival / .4)) if right else 1) * scale
        fill = PALETTE["success"] if right else PALETTE["surface"]
        edge = PALETTE["success"] if right else PALETTE["accent"]
        alpha = round(255 * opacity * (.35 if dim else 1.0))
        box = (x * scale - r, y * scale - r, x * scale + r, y * scale + r)
        if right and solved > 0:
            glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
            gr = r * 1.9
            ImageDraw.Draw(glow).ellipse((x * scale - gr, y * scale - gr, x * scale + gr, y * scale + gr),
                                         fill=_rgb(PALETTE["success"]) + (round(150 * solved),))
            image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14 * scale)))
        rounded_surface(image, box, r, _rgb(fill) + (alpha,), _rgb(edge) + (alpha,), max(2.0, 4 * scale))
        _text(image, (x * scale, y * scale - 2 * scale), str(index + 1), font(round(38 * scale)),
              PALETTE["background"] if right else PALETTE["text_light"], alpha / 255)


def _prompt(image: Image.Image, text: str, scale: float, opacity: float = 1.0, pulse: float = 0.0, color: str | None = None) -> None:
    if opacity <= 0:
        return
    face = fitted_font(text, round(860 * scale), round((60 + 5 * pulse) * scale))
    width = ImageDraw.Draw(image).textlength(text, font=face) + 100 * scale
    height = 100 * scale
    y = PROMPT_Y * scale
    rounded_surface(image, (540 * scale - width / 2, y - height / 2, 540 * scale + width / 2, y + height / 2), height / 2,
                    _rgb(color or PALETTE["accent"]) + (round(255 * opacity),))
    _text(image, (540 * scale, y - 2 * scale), text, face, PALETTE["background"], opacity)


# ---------------------------------------------------------------- frames

def _scene(item: RoundSpec, local: float, size: tuple[int, int], hook: bool = False) -> Image.Image:
    """The board with emitter, beam and receivers at `local` seconds into the level."""
    data = item.data
    scale = size[0] / 1080
    theme = active_theme()
    times = phases(item)
    base = _static(item, size, theme).copy().convert("RGBA")
    if not hook and local < LASER_ENTRANCE:
        empty = _background(size, 960.0, theme).convert("RGBA")
        base = Image.blend(empty, base, ease_out_cubic(_clamp(local / (LASER_ENTRANCE * .8))))
    appear = 1.0 if hook else _clamp(local / LASER_ENTRANCE)
    points = beam_points(data)
    lengths = _lengths(points)
    cell = cell_size(data)
    pulse = abs(math.sin(local * math.pi * 1.5))
    _draw_emitter(base, data, scale, pulse)
    answer, solved, since = None, 0.0, 0.0
    if hook or local < times["think_end"]:
        _draw_beam(base, beam_until(points, cell * STUB), scale, appear * (.8 + .2 * pulse), head=False)
    else:
        progress = _clamp((local - times["think_end"]) / float(data["trace_seconds"]))
        distance = lengths[-1] * ease_in_out(progress) if progress < 1 else lengths[-1]
        _draw_beam(base, beam_until(points, distance), scale, 1.0, head=progress < 1)
        for index, corner in enumerate(points[1:-1], start=1):  # a flash as the head passes each mirror
            if distance >= lengths[index]:
                moment = float(data["trace_seconds"]) * _unease(lengths[index] / lengths[-1])
                _bounce_flash(base, corner, local - times["think_end"] - moment, scale)
        if progress >= 1:
            answer = item.answer - 1
            since = local - times["trace_end"]
            solved = ease_out_cubic(_clamp(since / .35))
    _draw_receivers(base, data, scale, appear, answer, solved, since)
    if answer is not None and since < .9:
        x, y = receiver_points(data)[answer]
        _snap_burst(base, (x, y), 60, since, scale)
    return base


def bounce_times(item: RoundSpec) -> list[float]:
    """Seconds after the beam sets off at which its head reaches each mirror it turns at."""
    lengths = _lengths(beam_points(item.data))
    return [float(item.data["trace_seconds"]) * _unease(length / lengths[-1]) for length in lengths[1:-1]]


def _unease(fraction: float) -> float:
    """The time fraction at which `ease_in_out` has covered `fraction` of the way (found by bisection)."""
    low, high = 0.0, 1.0
    for _ in range(18):
        middle = (low + high) / 2
        if ease_in_out(middle) < fraction:
            low = middle
        else:
            high = middle
    return high


def draw_laser_round(spec: VideoSpec, index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[index]
    data = item.data
    times = phases(item)
    image = _scene(item, local, size)
    _level_header(image, index + 1, spec.round_count, 1.0, scale)
    thinking = float(data["thinking_seconds"])
    if local >= times["trace_end"]:
        _prompt(image, f"IT ENDS AT {item.answer}!", scale, 1.0, 0.0, PALETTE["success"])
    elif local >= times["think_end"]:
        _prompt(image, PROMPT_GUESS, scale, 1.0)
    elif local >= LASER_ENTRANCE:
        remaining = times["think_end"] - local
        _timer(image, min(thinking, remaining), thinking, _clamp((local - LASER_ENTRANCE) / .25), scale)
        _prompt(image, PROMPT_GUESS, scale, _clamp((local - LASER_ENTRANCE) / .2), abs(math.sin(local * math.pi)) * (1 if remaining < 3 else 0))
        _text(image, (540 * scale, COMMENT_Y * scale), COMMENT, font(round(54 * scale)), PALETTE["text_light"],
              _clamp((local - LASER_ENTRANCE) / .3))
    else:
        _prompt(image, PROMPT_WATCH, scale, _clamp(local / .3))
    if local < .2 and index > 0:
        image.alpha_composite(Image.new("RGBA", size, _rgb(PALETTE["background"]) + (round(200 * (1 - _clamp(local / .2))),)))
    return image


def draw_laser_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook: level 1's real board with the laser switched on, under `FOLLOW THE LASER.`."""
    scale = size[0] / 1080
    item = spec.rounds[0]
    image = _scene(item, 0.0, size, hook=True)
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .18)))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(960 * scale), round(84 * scale)),
          PALETTE["text_light"], _clamp(t / .08 + .3), slam)
    _text(image, (540 * scale, 232 * scale), f"{spec.round_count} LEVELS · EACH ONE TRICKIER", font(round(38 * scale)),
          PALETTE["accent"], _clamp((t - .15) / .2))
    _prompt(image, PROMPT_GUESS, scale, _clamp((t - .1) / .2))
    return image


def draw_laser_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        return draw_laser_intro(spec, t, size).convert("RGB")
    levels = schedule(spec)
    rounds_end = levels[-1][0] + levels[-1][1]
    if t >= rounds_end:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size, total=spec.round_count)
    index = max(position for position, (start, _) in enumerate(levels) if t >= start)
    return draw_laser_round(spec, index, t - levels[index][0], size).convert("RGB")
