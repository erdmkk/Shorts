"""Cube Count in the "Puzzly for You" look: lit isometric board, cube drop-in, flash, hide, and stack-by-stack count."""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw

from ..config import (CUBE_BUILD, CUBE_COLORS, CUBE_COUNT_UP, CUBE_HIDE, CUBE_RETURN, CUBE_THINKING)
from ..models import RoundSpec, VideoSpec
from ..puzzles.cube_count import cube_faces, draw_order, geometry, project
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .puzzle_fit import PALETTE, _background, _clamp, _level_header, _rgb, _snap_burst, _text, _timer, active_theme, draw_puzzle_fit_outro
from .text import fitted_font, font

HOOK_TEXT = "COUNT THE CUBES."
QUESTION = "How many cubes?"
EDGE = "#0B1020"
COVER_TIME = 0.6
# Fixed concept cluster for the intro and cover: never the real board.
INTRO_STACKS = ({"cell": [0, 0], "height": 3}, {"cell": [1, 0], "height": 1}, {"cell": [0, 1], "height": 2},
                {"cell": [1, 1], "height": 2}, {"cell": [2, 1], "height": 1}, {"cell": [1, 2], "height": 1})


def _mix(color: str, other: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    base = _rgb(color)
    return tuple(round(a + (b - a) * amount) for a, b in zip(base, other))


def face_colors(color_id: str) -> dict[str, tuple[int, int, int]]:
    base = CUBE_COLORS.get(color_id, CUBE_COLORS["violet"])
    return {"top": _mix(base, (255, 255, 255), .38), "left": _rgb(base), "right": _mix(base, (0, 0, 0), .32)}


def phases(spec: VideoSpec) -> dict[str, float]:
    visible = CUBE_BUILD + spec.rounds[0].data["visible_seconds"]
    hide_end = visible + CUBE_HIDE
    think_end = hide_end + CUBE_THINKING
    count_start = think_end + CUBE_RETURN
    return {"visible_end": visible, "hide_end": hide_end, "think_end": think_end,
            "count_start": count_start, "count_end": count_start + CUBE_COUNT_UP}


# ---------------------------------------------------------------- drawing primitives

def _platform(image: Image.Image, geo: dict[str, float], scale: float) -> None:
    grid = int(geo["grid"])
    draw = ImageDraw.Draw(image)
    s = lambda point: (point[0] * scale, point[1] * scale)
    thick = geo["thickness"]
    corner_right, corner_bottom, corner_left = project(geo, grid, 0, 0), project(geo, grid, grid, 0), project(geo, 0, grid, 0)
    down = lambda point: (point[0], point[1] + thick)
    draw.polygon([s(corner_right), s(corner_bottom), s(down(corner_bottom)), s(down(corner_right))], fill="#161C3A")
    draw.polygon([s(corner_left), s(corner_bottom), s(down(corner_bottom)), s(down(corner_left))], fill="#10152C")
    for i in range(grid):
        for j in range(grid):
            tile = [project(geo, i, j, 0), project(geo, i + 1, j, 0), project(geo, i + 1, j + 1, 0), project(geo, i, j + 1, 0)]
            draw.polygon([s(point) for point in tile], fill="#1E2750" if (i + j) % 2 else "#222C58", outline="#2E3866")


def _cube(draw: ImageDraw.ImageDraw, geo: dict[str, float], i: int, j: int, k: int, colors: dict, scale: float,
          lift: float = 0.0, top: bool = True, width: int = 3) -> None:
    faces = cube_faces(geo, i, j, k)
    shift = lambda points: [(x * scale, (y - lift) * scale) for x, y in points]
    for name in ("left", "right") + (("top",) if top else ()):
        draw.polygon(shift(faces[name]), fill=colors[name], outline=EDGE, width=width)


def _footprint(image: Image.Image, geo: dict[str, float], cell: list[int], scale: float, color: tuple[int, int, int],
               alpha: int, grow: float) -> None:
    """Diamond around a stack's base on the floor: contact shadow at rest, glowing frame while counting."""
    i, j = cell
    center = project(geo, i + .5, j + .5, 0)
    corners = [project(geo, i, j, 0), project(geo, i + 1, j, 0), project(geo, i + 1, j + 1, 0), project(geo, i, j + 1, 0)]
    points = [((center[0] + (x - center[0]) * grow) * scale, (center[1] + (y - center[1]) * grow) * scale) for x, y in corners]
    ImageDraw.Draw(image, "RGBA").polygon(points, fill=color + (alpha,))


def _cubes(image: Image.Image, geo: dict[str, float], stacks: list[dict], colors: dict, scale: float,
           lifts: dict[tuple[int, int], float] | None = None, glow: dict[int, float] | None = None) -> None:
    for stack_index, stack in enumerate(stacks):
        if (lifts or {}).get((stack_index, 0), 0.0) is None:
            continue
        if glow and stack_index in glow:
            _footprint(image, geo, stack["cell"], scale, _rgb(PALETTE["accent"]), round(150 * glow[stack_index]), 1.32)
        _footprint(image, geo, stack["cell"], scale, (4, 6, 16), 110, 1.14)
    draw = ImageDraw.Draw(image)
    width = max(2, round(2.6 * scale))
    for stack_index, level in draw_order(stacks):
        lift = (lifts or {}).get((stack_index, level), 0.0)
        if lift is None:
            continue
        i, j = stacks[stack_index]["cell"]
        _cube(draw, geo, i, j, level, colors, scale, lift, top=True, width=width)


_ROUNDS: dict[str, RoundSpec] = {}


@lru_cache(maxsize=4)
def _board_layer(key: str, size: tuple[int, int], theme: str = "violet") -> Image.Image:
    item = _ROUNDS[key]
    scale = size[0] / 1080
    image = _background(size, 860, theme).copy()
    _platform(image, geometry(item.data["grid"]), scale)
    return image


@lru_cache(maxsize=4)
def _rest_layer(key: str, size: tuple[int, int], theme: str = "violet") -> Image.Image:
    item = _ROUNDS[key]
    image = _board_layer(key, size, theme).copy()
    _cubes(image, geometry(item.data["grid"]), item.data["stacks"], face_colors(item.data["color_id"]), size[0] / 1080)
    return image


def _register(spec: VideoSpec, round_index: int) -> str:
    item = spec.rounds[round_index]
    key = f"{spec.id}:{item.fingerprint()}"
    _ROUNDS[key] = item
    return key


def _drop_lifts(stacks: list[dict], progress_time: float, total_time: float, height: float) -> dict:
    """Cubes fall in one after another, bottom first, in painter order."""
    order = draw_order(stacks)
    step = total_time * .7 / max(1, len(order))
    lifts = {}
    for position, cube in enumerate(order):
        local = (progress_time - position * step) / (total_time * .3)
        if local <= 0:
            lifts[cube] = None
        else:
            lifts[cube] = height * (1 - ease_out_back(_clamp(local)))
    return lifts


# ---------------------------------------------------------------- frames

def _count_state(stacks: list[dict], local: float, times: dict[str, float]) -> tuple[int, int | None]:
    """(cubes counted so far, stack currently highlighted)."""
    order = sorted(range(len(stacks)), key=lambda index: (sum(stacks[index]["cell"]), stacks[index]["cell"][0]))
    slot = CUBE_COUNT_UP / max(1, len(order))
    elapsed = local - times["count_start"]
    if elapsed < 0:
        return 0, None
    done = min(len(order), int(elapsed / slot) + 1)
    counted = sum(stacks[index]["height"] for index in order[:done])
    current = order[done - 1] if elapsed < CUBE_COUNT_UP else None
    return counted, current


def _stack_label(image: Image.Image, geo: dict[str, float], stack: dict, scale: float, strength: float, active: bool) -> None:
    i, j = stack["cell"]
    x, y = project(geo, i + .5, j + .5, stack["height"])
    y -= geo["cube_h"] * .55
    radius = 30 if active else 24
    draw = ImageDraw.Draw(image, "RGBA")
    fill = _rgb(PALETTE["accent"] if active else PALETTE["surface"]) + (round(235 * strength),)
    draw.ellipse(((x - radius) * scale, (y - radius) * scale, (x + radius) * scale, (y + radius) * scale),
                 fill=fill, outline=_rgb(PALETTE["text_light"]) + (round(200 * strength),), width=max(1, round(3 * scale)))
    _text(image, (x * scale, y * scale), str(stack["height"]), font(round((34 if active else 28) * scale)),
          PALETTE["background"] if active else PALETTE["text_light"], strength)


def draw_cube_round(spec: VideoSpec, round_index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[round_index]
    data = item.data
    key = _register(spec, round_index)
    geo = geometry(data["grid"])
    colors = face_colors(data["color_id"])
    stacks = data["stacks"]
    times = phases(spec)
    header = _clamp(local / .25)
    if local < CUBE_BUILD:
        image = _board_layer(key, size, active_theme()).copy()
        _cubes(image, geo, stacks, colors, scale, _drop_lifts(stacks, local, CUBE_BUILD, 260))
    elif local < times["visible_end"]:
        image = _rest_layer(key, size, active_theme()).copy()
    elif local < times["hide_end"]:
        # Cubes dissolve into the board.
        amount = ease_in_out((local - times["visible_end"]) / CUBE_HIDE)
        image = Image.blend(_rest_layer(key, size, active_theme()), _board_layer(key, size, active_theme()), amount)
    elif local < times["think_end"]:
        image = _board_layer(key, size, active_theme()).copy()
        remaining = times["think_end"] - local
        pulse = 1 + .04 * math.sin(local * 6)
        _text(image, (540 * scale, geo["origin_y"] * scale + 150 * scale), "?", font(round(230 * scale)),
              PALETTE["accent"], .9, pulse)
        _timer(image, remaining, CUBE_THINKING, 1.0, scale)
    elif local < times["count_start"]:
        image = _board_layer(key, size, active_theme()).copy()
        _cubes(image, geo, stacks, colors, scale, _drop_lifts(stacks, local - times["think_end"], CUBE_RETURN, 140))
    else:
        counted, current = _count_state(stacks, local, times)
        order = sorted(range(len(stacks)), key=lambda index: (sum(stacks[index]["cell"]), stacks[index]["cell"][0]))
        slot = CUBE_COUNT_UP / max(1, len(order))
        glow = {index: (1.0 if index == current else .45) for position, index in enumerate(order)
                if local - times["count_start"] - position * slot >= 0}
        image = _board_layer(key, size, active_theme()).copy()
        _cubes(image, geo, stacks, colors, scale, glow=glow)
        for position, index in enumerate(order):
            started = local - times["count_start"] - position * slot
            if started >= 0:
                _stack_label(image, geo, stacks[index], scale, _clamp(started / .12), index == current)
    _level_header(image, data.get("level", round_index + 1), spec.round_count, header, scale)
    question_y = 1480
    if times["hide_end"] <= local < times["count_start"]:
        _text(image, (540 * scale, question_y * scale), QUESTION, fitted_font(QUESTION, round(900 * scale), round(76 * scale)),
              PALETTE["text_light"], _clamp((local - times["hide_end"]) / .2))
    if local >= times["count_start"]:
        counted, _ = _count_state(stacks, local, times)
        final = local >= times["count_end"]
        pop = 1 + .25 * (1 - ease_out_cubic(_clamp((local - times["count_end"]) / .3))) if final else 1.0
        color = PALETTE["success"] if final else PALETTE["text_light"]
        _text(image, (540 * scale, question_y * scale), str(counted), font(round(130 * scale)), color, 1.0, pop)
        if final:
            _snap_burst(image, (540, question_y), 150, local - times["count_end"], scale)
    if local < CUBE_BUILD + .2 and round_index > 0:
        alpha = round(200 * (1 - ease_out_cubic(_clamp(local / .3))))
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (alpha,))
        image.paste(overlay, (0, 0), overlay)
    transition_start = spec.round_duration - .2
    if local > transition_start and round_index < spec.round_count - 1:
        alpha = round(200 * ease_in_out((local - transition_start) / .2))
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (alpha,))
        image.paste(overlay, (0, 0), overlay)
    return image


def draw_cube_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook with a fixed concept cluster (never the real first board, so the flash stays fair)."""
    scale = size[0] / 1080
    image = _background(size, 860).copy()
    geo = dict(geometry(3))
    geo["origin_y"] += 40
    _platform(image, geo, scale)
    colors = face_colors(spec.rounds[0].data["color_id"])
    _cubes(image, geo, list(INTRO_STACKS), colors, scale, _drop_lifts(list(INTRO_STACKS), t, .55, 220))
    fade = 1 - _clamp((t - (spec.intro_duration - .22)) / .22)
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .18)))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(940 * scale), round(84 * scale)),
          PALETTE["text_light"], fade * _clamp(t / .08 + .3), slam)
    seconds = spec.rounds[0].data["visible_seconds"]
    unit = "SECOND" if seconds == 1 else "SECONDS"
    subtitle = f"{spec.round_count} LEVELS · {seconds:g} {unit} TO LOOK"
    _text(image, (540 * scale, 232 * scale), subtitle, font(round(34 * scale)), PALETTE["accent"], fade * _clamp((t - .15) / .2))
    return image


def draw_cube_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        return draw_cube_intro(spec, t, size)
    rounds_end = spec.intro_duration + spec.round_count * spec.round_duration
    if t >= rounds_end:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size)
    elapsed = t - spec.intro_duration
    round_index = min(spec.round_count - 1, int(elapsed / spec.round_duration))
    return draw_cube_round(spec, round_index, elapsed - round_index * spec.round_duration, size)
