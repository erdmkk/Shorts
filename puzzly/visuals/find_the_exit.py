"""Find the Exit Hard in the "Puzzly for You" look: lit 3D maze, glowing exit portals, and a neon route trace."""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..config import EXIT_HARD_ENTRANCE, EXIT_HARD_TRACE, exit_hard_round
from ..models import RoundSpec, VideoSpec
from .easing import ease_in_out, ease_out_cubic
from .effects import rounded_surface
from .paths import trace_points
from .puzzle_fit import (PALETTE, _background, _clamp, _level_header, _rgb, _snap_burst, _text, _timer,
                         draw_puzzle_fit_outro, active_theme)
from .text import fitted_font, font

HOOK_TEXT = "ONLY ONE EXIT IS OPEN."
EXIT_COLORS = ("#FFC24B", "#B69CFF", "#FF7A45", "#4BE08A")  # star, moon, sun, diamond: equal brightness so none stands out
WALL_TOP = "#6F7FE8"
WALL_BOTTOM = "#3A47A8"
WALL_RIM = "#C9D2FF"
FLOOR = "#0F1530"
FLOOR_ALT = "#121A38"
TRAIL = "#2EE6C5"
MAZE_BOX = (100, 400, 980, 1400)  # logical area for the grid itself
COVER_TIME = 0.6


def maze_geometry(data: dict) -> dict[str, float]:
    rows, columns = data["rows"], data["columns"]
    cell = min((MAZE_BOX[2] - MAZE_BOX[0]) / columns, (MAZE_BOX[3] - MAZE_BOX[1]) / rows)
    left = 540 - columns * cell / 2
    top = MAZE_BOX[1]
    return {"cell": cell, "left": left, "top": top, "right": left + columns * cell, "bottom": top + rows * cell,
            "wall": max(10.0, cell * .19)}


def cell_center(geometry: dict[str, float], columns: int, node: int) -> tuple[float, float]:
    row, column = divmod(node, columns)
    return geometry["left"] + (column + .5) * geometry["cell"], geometry["top"] + (row + .5) * geometry["cell"]


def exit_point(geometry: dict[str, float], columns: int, node: int) -> tuple[float, float]:
    return cell_center(geometry, columns, node)[0], geometry["top"] - geometry["cell"] * .62


def start_point(geometry: dict[str, float], columns: int, node: int) -> tuple[float, float]:
    return cell_center(geometry, columns, node)[0], geometry["bottom"] + geometry["cell"] * .55


def wall_segments(data: dict, geometry: dict[str, float]) -> list[tuple[float, float, float, float]]:
    rows, columns = data["rows"], data["columns"]
    edges = {tuple(edge) for edge in data["edges"]}
    cell, left, top = geometry["cell"], geometry["left"], geometry["top"]
    segments = []
    for row in range(rows):
        for column in range(columns):
            node = row * columns + column
            x, y = left + column * cell, top + row * cell
            if row == 0 and node not in data["exits"]:
                segments.append((x, y, x + cell, y))
            if column == 0:
                segments.append((x, y, x, y + cell))
            if column == columns - 1 or (node, node + 1) not in edges:
                segments.append((x + cell, y, x + cell, y + cell))
            if row == rows - 1:
                if node != data["start"]:
                    segments.append((x, y + cell, x + cell, y + cell))
            elif (node, node + columns) not in edges:
                segments.append((x, y + cell, x + cell, y + cell))
    return segments


# ---------------------------------------------------------------- static round layer

_ROUNDS: dict[str, RoundSpec] = {}


def _wall_mask(segments, scale: float, size: tuple[int, int], width: float) -> Image.Image:
    high = Image.new("L", (size[0] * 2, size[1] * 2), 0)
    draw = ImageDraw.Draw(high)
    w = max(2, round(width * scale * 2))
    radius = w / 2
    for x1, y1, x2, y2 in segments:
        a, b = (x1 * scale * 2, y1 * scale * 2), (x2 * scale * 2, y2 * scale * 2)
        draw.line((a, b), fill=255, width=w)
        for px, py in (a, b):
            draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=255)
    return high.resize(size, Image.Resampling.LANCZOS)


def _vertical_gradient(size: tuple[int, int], top: str, bottom: str, y0: float, y1: float) -> Image.Image:
    height = size[1]
    ramp = np.clip((np.arange(height, dtype=np.float32) - y0) / max(1.0, y1 - y0), 0, 1)[:, None]
    colors = np.array(_rgb(top), np.float32) * (1 - ramp) + np.array(_rgb(bottom), np.float32) * ramp
    column = colors.astype(np.uint8)[:, None, :]
    return Image.fromarray(np.repeat(column, size[0], axis=1))


@lru_cache(maxsize=5)
def _round_layer(round_key: str, size: tuple[int, int], theme: str = "violet") -> Image.Image:
    round_spec = _ROUNDS[round_key]
    data = round_spec.data
    scale = size[0] / 1080
    geometry = maze_geometry(data)
    columns = data["columns"]
    image = _background(size, 900, theme).copy()
    s = lambda values: tuple(value * scale for value in values)
    card = (geometry["left"] - 44, geometry["top"] - geometry["cell"] * 1.25, geometry["right"] + 44, geometry["bottom"] + geometry["cell"] * 1.15)
    rounded_surface(image, s(card), 60 * scale, PALETTE["surface"], PALETTE["surface_edge"], 3 * scale, shadow=True)
    # Floor: faint checker tiles lit from the exits above.
    draw = ImageDraw.Draw(image)
    cell = geometry["cell"]
    for row in range(data["rows"]):
        for column in range(columns):
            x, y = geometry["left"] + column * cell, geometry["top"] + row * cell
            draw.rectangle(s((x, y, x + cell, y + cell)), fill=FLOOR if (row + column) % 2 else FLOOR_ALT)
    light = Image.new("L", size, 0)
    light_draw = ImageDraw.Draw(light)
    for node in data["exits"]:
        cx, cy = exit_point(geometry, columns, node)
        radius = cell * 2.4
        light_draw.ellipse(s((cx - radius, geometry["top"] - radius * .5, cx + radius, geometry["top"] + radius * 1.4)), fill=90)
    light = light.filter(ImageFilter.GaussianBlur(cell * .9 * scale))
    image.paste(Image.new("RGB", size, "#8C7BFF"), (0, 0), light.point(lambda value: value * 45 // 255))
    # Walls: blurred drop shadow, gradient body lit from the top, and a bright rim on the lit edges.
    mask = _wall_mask(wall_segments(data, geometry), scale, size, geometry["wall"])
    offset = max(2, round(geometry["wall"] * .55 * scale))
    shadow = ImageChops.offset(mask, offset, round(offset * 1.4)).filter(ImageFilter.GaussianBlur(offset * 1.2))
    image.paste(Image.new("RGB", size, (0, 0, 0)), (0, 0), shadow.point(lambda value: value * 170 // 255))
    body = _vertical_gradient(size, WALL_TOP, WALL_BOTTOM, geometry["top"] * scale, geometry["bottom"] * scale)
    image.paste(body, (0, 0), mask)
    bevel = max(1, round(geometry["wall"] * .22 * scale))
    rim = ImageChops.subtract(mask, ImageChops.offset(mask, bevel, bevel))
    image.paste(Image.new("RGB", size, WALL_RIM), (0, 0), rim.point(lambda value: value * 150 // 255))
    dark = ImageChops.subtract(mask, ImageChops.offset(mask, -bevel, -bevel))
    image.paste(Image.new("RGB", size, "#1E255E"), (0, 0), dark.point(lambda value: value * 160 // 255))
    return image


# ---------------------------------------------------------------- markers

def _glow_disc(image: Image.Image, center: tuple[float, float], radius: float, color: str, strength: float) -> None:
    if strength <= 0:
        return
    pad = int(radius * 2)
    size = (pad * 2, pad * 2)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse((pad - radius, pad - radius, pad + radius, pad + radius), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius * .55)).point(lambda value: round(value * min(1.0, strength)))
    image.paste(Image.new("RGB", size, color), (round(center[0] - pad), round(center[1] - pad)), mask)


def _symbol(draw: ImageDraw.ImageDraw, index: int, x: float, y: float, radius: float, color, cutout) -> None:
    if index == 0:
        points = [(x + math.sin(i * math.pi / 5) * radius * (1 if i % 2 == 0 else .46),
                   y - math.cos(i * math.pi / 5) * radius * (1 if i % 2 == 0 else .46)) for i in range(10)]
        draw.polygon(points, fill=color)
    elif index == 1:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
        draw.ellipse((x - radius * .2, y - radius * 1.1, x + radius * 1.15, y + radius * .4), fill=cutout)
    elif index == 3:  # diamond (levels with four exits)
        draw.polygon([(x, y - radius), (x + radius * .78, y), (x, y + radius), (x - radius * .78, y)], fill=color)
    else:
        draw.ellipse((x - radius * .6, y - radius * .6, x + radius * .6, y + radius * .6), fill=color)
        for i in range(8):
            angle = i * math.pi / 4
            draw.line((x + math.cos(angle) * radius * .78, y + math.sin(angle) * radius * .78,
                       x + math.cos(angle) * radius * 1.12, y + math.sin(angle) * radius * 1.12),
                      fill=color, width=max(2, round(radius * .16)))


def _exit_portal(image: Image.Image, index: int, center: tuple[float, float], radius: float, glow: float, dim: float) -> None:
    from ..palette import object_color
    color = object_color(EXIT_COLORS[index])
    _glow_disc(image, center, radius * 1.7, color, .55 * glow * (1 - dim))
    draw = ImageDraw.Draw(image)
    x, y = center
    ring = radius * 1.18
    fill = tuple(round(channel * (1 - .65 * dim)) for channel in _rgb("#1B2350"))
    draw.ellipse((x - ring, y - ring, x + ring, y + ring), fill=fill,
                 outline=tuple(round(c * (1 - .6 * dim)) for c in _rgb(color)), width=max(2, round(radius * .12)))
    symbol_color = tuple(round(c * (1 - .6 * dim)) for c in _rgb(color))
    _symbol(draw, index, x, y, radius * .72, symbol_color, fill)


def _start_orb(image: Image.Image, center: tuple[float, float], radius: float, local: float) -> None:
    pulse = .5 + .5 * math.sin(local * 5)
    _glow_disc(image, center, radius * (1.6 + .25 * pulse), TRAIL, .7)
    draw = ImageDraw.Draw(image)
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=TRAIL, outline=PALETTE["text_light"], width=max(2, round(radius * .12)))
    tip = radius * .5
    draw.polygon([(x - tip, y + tip * .55), (x, y - tip * .75), (x + tip, y + tip * .55)], fill=PALETTE["background"])


# ---------------------------------------------------------------- trace

def _trail(image: Image.Image, points: list[tuple[float, float]], width: float, scale: float) -> None:
    if len(points) < 2:
        return
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    pad = width * 4
    left, top = int(min(xs) - pad), int(min(ys) - pad)
    right, bottom = int(max(xs) + pad), int(max(ys) + pad)
    size = (max(1, right - left), max(1, bottom - top))
    local = [(x - left, y - top) for x, y in points]
    # Bloom at quarter resolution keeps the glow cheap at Final size.
    quarter = (max(1, size[0] // 4), max(1, size[1] // 4))
    bloom = Image.new("L", quarter, 0)
    ImageDraw.Draw(bloom).line([(x / 4, y / 4) for x, y in local], fill=255, width=max(1, round(width * 1.6 / 4)), joint="curve")
    bloom = bloom.filter(ImageFilter.GaussianBlur(max(1.0, width / 4))).resize(size, Image.Resampling.BILINEAR)
    image.paste(Image.new("RGB", size, TRAIL), (left, top), bloom.point(lambda value: value * 150 // 255))
    core = Image.new("L", size, 0)
    core_draw = ImageDraw.Draw(core)
    core_draw.line(local, fill=255, width=max(2, round(width)), joint="curve")
    for x, y in (local[0], local[-1]):
        r = width / 2
        core_draw.ellipse((x - r, y - r, x + r, y + r), fill=255)
    image.paste(Image.new("RGB", size, TRAIL), (left, top), core)
    highlight = Image.new("L", size, 0)
    ImageDraw.Draw(highlight).line(local, fill=255, width=max(1, round(width * .35)), joint="curve")
    image.paste(Image.new("RGB", size, "#D9FFF7"), (left, top), highlight.point(lambda value: value * 200 // 255))


# ---------------------------------------------------------------- frames

def _round_image(spec: VideoSpec, round_index: int, size: tuple[int, int]) -> Image.Image:
    round_spec = spec.rounds[round_index]
    key = f"{spec.id}:{round_spec.fingerprint()}"
    _ROUNDS[key] = round_spec
    return _round_layer(key, size, active_theme()).copy()


def _draw_markers(image: Image.Image, round_spec: RoundSpec, local: float, scale: float, arrival: float | None) -> None:
    data = round_spec.data
    geometry = maze_geometry(data)
    columns = data["columns"]
    radius = min(34.0, geometry["cell"] * .36) * scale
    for index, node in enumerate(data["exits"]):
        x, y = exit_point(geometry, columns, node)
        dim = 0.0 if arrival is None or index == round_spec.answer else _clamp(arrival / .3)
        glow = 1.0 + (.8 * (1 - _clamp(arrival / .8)) if arrival is not None and index == round_spec.answer else 0)
        _exit_portal(image, index, (x * scale, y * scale), radius, glow, dim)
    sx, sy = start_point(geometry, columns, data["start"])
    _start_orb(image, (sx * scale, sy * scale), radius * .82, local)


def route_polyline(round_spec: RoundSpec) -> list[tuple[float, float]]:
    data = round_spec.data
    geometry = maze_geometry(data)
    columns = data["columns"]
    return ([start_point(geometry, columns, data["start"])] + [cell_center(geometry, columns, node) for node in data["route"]]
            + [exit_point(geometry, columns, data["exits"][round_spec.answer])])


def schedule(spec: VideoSpec) -> list[tuple[float, float]]:
    """(start, duration) of every level; bigger mazes get more thinking time, so later levels last longer."""
    from ..puzzles.find_the_exit import round_thinking
    result, start = [], spec.intro_duration
    for item in spec.rounds:
        duration = exit_hard_round(round_thinking(item.data))
        result.append((start, duration))
        start += duration
    return result


def draw_exit_hard_round(spec: VideoSpec, round_index: int, local: float, size: tuple[int, int]) -> Image.Image:
    from ..puzzles.find_the_exit import round_thinking
    scale = size[0] / 1080
    image = _round_image(spec, round_index, size)
    round_spec = spec.rounds[round_index]
    thinking = round_thinking(round_spec.data)
    think_end = EXIT_HARD_ENTRANCE + thinking
    arrival_at = think_end + EXIT_HARD_TRACE
    arrival = local - arrival_at if local >= arrival_at else None
    if local >= think_end:
        progress = ease_in_out(_clamp((local - think_end) / EXIT_HARD_TRACE))
        traced = [(x * scale, y * scale) for x, y in trace_points(route_polyline(round_spec), progress)]
        geometry = maze_geometry(round_spec.data)
        _trail(image, traced, geometry["cell"] * .2 * scale, scale)
        hx, hy = traced[-1]
        _glow_disc(image, (hx, hy), geometry["cell"] * .32 * scale, "#FFFFFF", .9)
    _draw_markers(image, round_spec, local, scale, arrival)
    if arrival is not None:
        geometry = maze_geometry(round_spec.data)
        ex, ey = exit_point(geometry, round_spec.data["columns"], round_spec.data["exits"][round_spec.answer])
        _snap_burst(image, (ex, ey), geometry["cell"] * 1.1, arrival, scale)
    header = _clamp(local / .25)
    _level_header(image, round_spec.data.get("level", round_index + 1), spec.round_count, header, scale)
    if local < think_end:
        remaining = thinking if local < .35 else think_end - local
        _timer(image, remaining, thinking, header * (_clamp(local / .3) if local < .35 else 1), scale)
    else:
        _timer(image, .001, 1, 1 - _clamp((local - think_end) / .25), scale)
    if round_index > 0 and local < .3:
        alpha = round(200 * (1 - ease_out_cubic(local / .3)))
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (alpha,))
        image.paste(overlay, (0, 0), overlay)
    transition_start = exit_hard_round(thinking) - .2
    if local > transition_start and round_index < spec.round_count - 1:
        alpha = round(200 * ease_in_out((local - transition_start) / .2))
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (alpha,))
        image.paste(overlay, (0, 0), overlay)
    return image


def draw_exit_hard_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook: level one's real maze is on screen from the first frame under a bold challenge line."""
    scale = size[0] / 1080
    image = _round_image(spec, 0, size)
    _draw_markers(image, spec.rounds[0], t - spec.intro_duration, scale, None)
    fade = 1 - _clamp((t - (spec.intro_duration - .22)) / .22)
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .18)))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(940 * scale), round(78 * scale)),
          PALETTE["text_light"], fade * _clamp(t / .08 + .3), slam)
    subtitle = f"{spec.round_count} LEVELS · EACH ONE HARDER"
    _text(image, (540 * scale, 232 * scale), subtitle, font(round(34 * scale)), PALETTE["accent"], fade * _clamp((t - .15) / .2))
    return image


def draw_exit_hard_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        return draw_exit_hard_intro(spec, t, size)
    levels = schedule(spec)
    rounds_end = levels[-1][0] + levels[-1][1]
    if t >= rounds_end:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size)
    round_index = max(index for index, (start, _) in enumerate(levels) if t >= start)
    return draw_exit_hard_round(spec, round_index, t - levels[round_index][0], size)


def uses_exit_hard_look(spec: VideoSpec) -> bool:
    return spec.puzzle_type == "find_the_exit" and bool(spec.rounds) and spec.rounds[0].data.get("layout") == "deceptive_v2"

