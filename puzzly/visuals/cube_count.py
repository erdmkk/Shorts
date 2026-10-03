"""Cube Count in the "Puzzly for You" look: lit isometric board, cube drop-in, flash, hide, and stack-by-stack count.

Levels come in four formats (`mode`): the classic flash (`grid`), cubes that rain down and vanish as they land (`rain`), a
train of towers that sweeps across the screen (`sweep`), and a colour rain where only one colour counts (`rain_color`). Every
level has its own length (`phases(item)["duration"]`, `schedule(spec)`)."""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw

from ..config import (CUBE_BUILD, CUBE_COLORS, CUBE_COUNT_UP, CUBE_HIDE, CUBE_LEAD, CUBE_REPLAY_SPEED, CUBE_RETURN, CUBE_THINKING,
                      cube_lead, cube_mode, cube_round)
from ..models import RoundSpec, VideoSpec
from ..puzzles.cube_count import (FLIGHT_FADE, SWEEP_Y, cube_faces, cubes_in, draw_order, drop_width as drop_size, geometry, project,
                                  size_of, stack_order, sweep_geo, sweep_stacks, train_width)
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .puzzle_fit import PALETTE, _background, _clamp, _level_header, _rgb, _snap_burst, _text, _timer, active_theme, draw_puzzle_fit_outro
from .text import fitted_font, font

HOOK_TEXT = "COUNT THE CUBES."
QUESTION = "How many cubes?"
EDGE = "#0B1020"
EDGE_RGB = (11, 16, 32)
COVER_TIME = 0.6
# Fixed concept cluster for the intro and cover: never the real board.
INTRO_STACKS = ({"cell": [0, 0], "height": 3}, {"cell": [1, 0], "height": 1}, {"cell": [0, 1], "height": 2},
                {"cell": [1, 1], "height": 2}, {"cell": [2, 1], "height": 1}, {"cell": [1, 2], "height": 1})


def _mix(color: str, other: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    base = _rgb(color)
    return tuple(round(a + (b - a) * amount) for a, b in zip(base, other))


def face_colors(color_id: str) -> dict[str, tuple[int, int, int]]:
    from ..palette import object_color
    base = object_color(CUBE_COLORS.get(color_id, CUBE_COLORS["violet"]))
    return {"top": _mix(base, (255, 255, 255), .38), "left": _rgb(base), "right": _mix(base, (0, 0, 0), .32)}


def phases(source: VideoSpec | RoundSpec) -> dict[str, float]:
    """A level's moments in seconds from its start. A video stands for its first (classic) level."""
    item = source.rounds[0] if isinstance(source, VideoSpec) else source
    data = item.data
    mode = cube_mode(data)
    if mode in ("rain", "rain_color"):
        visible = cube_lead(data) + float(data["rain_seconds"])
        replay = float(data["rain_seconds"]) / CUBE_REPLAY_SPEED + .3  # the answer replays the rain, numbering the cubes
    elif mode == "sweep":
        visible, replay = CUBE_LEAD + float(data["sweep_seconds"]), CUBE_COUNT_UP
    else:
        visible, replay = CUBE_BUILD + float(data["visible_seconds"]), CUBE_COUNT_UP
    hide_end = visible + CUBE_HIDE
    think_end = hide_end + CUBE_THINKING
    count_start = think_end + CUBE_RETURN
    return {"visible_end": visible, "hide_end": hide_end, "think_end": think_end,
            "count_start": count_start, "count_end": count_start + replay, "duration": cube_round(data)}


def schedule(spec: VideoSpec) -> list[tuple[float, float]]:
    """(start, duration) of every level; the formats last different times."""
    result, start = [], spec.intro_duration
    for item in spec.rounds:
        duration = cube_round(item.data)
        result.append((start, duration))
        start += duration
    return result


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
          lift: float = 0.0, top: bool = True, width: int = 3, size: int = 1, edge: str | tuple = EDGE) -> None:
    """One cube, or a big block (size 2): a single box with no inner edges."""
    faces = cube_faces(geo, i, j, k, size)
    shift = lambda points: [(x * scale, (y - lift) * scale) for x, y in points]
    for name in ("left", "right") + (("top",) if top else ()):
        draw.polygon(shift(faces[name]), fill=colors[name], outline=edge, width=width)


def _footprint(image: Image.Image, geo: dict[str, float], cell: list[int], scale: float, color: tuple[int, int, int],
               alpha: int, grow: float, size: int = 1) -> None:
    """Diamond around a stack's base on the floor: contact shadow at rest, glowing frame while counting."""
    i, j = cell
    s = size
    center = project(geo, i + s / 2, j + s / 2, 0)
    corners = [project(geo, i, j, 0), project(geo, i + s, j, 0), project(geo, i + s, j + s, 0), project(geo, i, j + s, 0)]
    grow = 1 + (grow - 1) / s  # the same margin around a big block
    points = [((center[0] + (x - center[0]) * grow) * scale, (center[1] + (y - center[1]) * grow) * scale) for x, y in corners]
    ImageDraw.Draw(image, "RGBA").polygon(points, fill=color + (alpha,))


def _cubes(image: Image.Image, geo: dict[str, float], stacks: list[dict], colors: dict, scale: float,
           lifts: dict[tuple[int, int], float] | None = None, glow: dict[int, float] | None = None) -> None:
    for stack_index, stack in enumerate(stacks):
        if (lifts or {}).get((stack_index, 0), 0.0) is None:
            continue
        if glow and stack_index in glow:
            _footprint(image, geo, stack["cell"], scale, _rgb(PALETTE["accent"]), round(150 * glow[stack_index]), 1.32, size_of(stack))
        _footprint(image, geo, stack["cell"], scale, (4, 6, 16), 110, 1.14, size_of(stack))
    draw = ImageDraw.Draw(image)
    width = max(2, round(2.6 * scale))
    for stack_index, level in draw_order(stacks):
        lift = (lifts or {}).get((stack_index, level), 0.0)
        if lift is None:
            continue
        i, j = stacks[stack_index]["cell"]
        _cube(draw, geo, i, j, level, colors, scale, lift, top=True, width=width, size=size_of(stacks[stack_index]))


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
    from ..palette import active
    key = f"{spec.id}:{item.fingerprint()}:{active()}"  # the cached cube layers are painted in the object palette
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
    order = stack_order(stacks)
    slot = CUBE_COUNT_UP / max(1, len(order))
    elapsed = local - times["count_start"]
    if elapsed < 0:
        return 0, None
    done = min(len(order), int(elapsed / slot) + 1)
    counted = sum(cubes_in(stacks[index]) for index in order[:done])  # a big block counts as one
    current = order[done - 1] if elapsed < CUBE_COUNT_UP else None
    return counted, current


def _stack_label(image: Image.Image, geo: dict[str, float], stack: dict, scale: float, strength: float, active: bool) -> None:
    i, j = stack["cell"]
    half = size_of(stack) / 2
    x, y = project(geo, i + half, j + half, stack["height"])
    y -= geo["cube_h"] * .55
    radius = 30 if active else 24
    draw = ImageDraw.Draw(image, "RGBA")
    fill = _rgb(PALETTE["accent"] if active else PALETTE["surface"]) + (round(235 * strength),)
    draw.ellipse(((x - radius) * scale, (y - radius) * scale, (x + radius) * scale, (y + radius) * scale),
                 fill=fill, outline=_rgb(PALETTE["text_light"]) + (round(200 * strength),), width=max(1, round(3 * scale)))
    _text(image, (x * scale, y * scale), str(cubes_in(stack)), font(round((34 if active else 28) * scale)),
          PALETTE["background"] if active else PALETTE["text_light"], strength)


def _draw_grid(spec: VideoSpec, round_index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[round_index]
    data = item.data
    key = _register(spec, round_index)
    geo = geometry(data["grid"])
    colors = face_colors(data["color_id"])
    stacks = data["stacks"]
    times = phases(item)
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
        order = stack_order(stacks)
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
    _fade_overlays(image, spec, round_index, local, size, times["duration"])
    return image


def draw_cube_round(spec: VideoSpec, round_index: int, local: float, size: tuple[int, int]) -> Image.Image:
    mode = cube_mode(spec.rounds[round_index].data)
    if mode in ("rain", "rain_color"):
        return _draw_rain(spec, round_index, local, size)
    if mode == "sweep":
        return _draw_sweep(spec, round_index, local, size)
    return _draw_grid(spec, round_index, local, size)


# ---------------------------------------------------------------- shared pieces of the new formats

def _pill(image: Image.Image, text: str, y: float, scale: float, opacity: float = 1.0) -> None:
    """A short instruction on a solid pill above the play area."""
    if opacity <= 0:
        return
    face = fitted_font(text, round(860 * scale), round(56 * scale))
    width = ImageDraw.Draw(image).textlength(text, font=face) + 90 * scale
    height = 92 * scale
    rounded_surface(image, (540 * scale - width / 2, y * scale - height / 2, 540 * scale + width / 2, y * scale + height / 2), height / 2,
                    _rgb(PALETTE["accent"]) + (round(255 * opacity),))
    _text(image, (540 * scale, y * scale - 2 * scale), text, face, PALETTE["background"], opacity)


def _swatch(image: Image.Image, center: tuple[float, float], radius: float, colors: dict) -> None:
    """A small flat cube icon in a colour of the video (the colour a colour rain counts)."""
    cx, cy, w = center[0], center[1], radius * .87
    draw = ImageDraw.Draw(image)
    edge = max(2, round(radius / 14))
    draw.polygon([(cx, cy - radius), (cx + w, cy - radius / 2), (cx, cy), (cx - w, cy - radius / 2)], fill=colors["top"], outline=EDGE, width=edge)
    draw.polygon([(cx - w, cy - radius / 2), (cx, cy), (cx, cy + radius), (cx - w, cy + radius / 2)], fill=colors["left"], outline=EDGE, width=edge)
    draw.polygon([(cx + w, cy - radius / 2), (cx, cy), (cx, cy + radius), (cx + w, cy + radius / 2)], fill=colors["right"], outline=EDGE, width=edge)


def _target_chip(image: Image.Image, color_id: str, y: float, scale: float, opacity: float = 1.0, zoom: float = 1.0,
                 pulse: float = 1.0) -> None:
    """`COUNT ONLY` and a cube of the counted colour: a colour rain needs no words to say which cubes count. `zoom` enlarges
    the whole chip (its introduction) and `pulse` the cube alone."""
    if opacity <= 0:
        return
    unit = scale * zoom
    text = "COUNT ONLY"
    face = font(round(56 * unit))
    text_width = ImageDraw.Draw(image).textlength(text, font=face)
    width = text_width + 250 * unit
    height = 104 * unit
    rounded_surface(image, (540 * scale - width / 2, y * scale - height / 2, 540 * scale + width / 2, y * scale + height / 2), height / 2,
                    _rgb(PALETTE["accent"]) + (round(255 * opacity),))
    left = 540 * scale - width / 2 + 50 * unit
    _text(image, (left + text_width / 2, y * scale - 2 * unit), text, face, PALETTE["background"], opacity)
    _swatch(image, (540 * scale + width / 2 - 78 * unit, y * scale), 40 * unit * pulse, face_colors(color_id))


def _fade_overlays(image: Image.Image, spec: VideoSpec, round_index: int, local: float, size: tuple[int, int], duration: float) -> None:
    if local < CUBE_BUILD + .2 and round_index > 0:
        alpha = round(200 * (1 - ease_out_cubic(_clamp(local / .3))))
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (alpha,))
        image.paste(overlay, (0, 0), overlay)
    transition_start = duration - .2
    if local > transition_start and round_index < spec.round_count - 1:
        alpha = round(200 * ease_in_out((local - transition_start) / .2))
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (alpha,))
        image.paste(overlay, (0, 0), overlay)


def _question_and_total(image: Image.Image, local: float, times: dict[str, float], counted: int | None, scale: float) -> None:
    """`How many cubes?` while thinking, then the running total, popped in green at the end."""
    if times["hide_end"] <= local < times["count_start"]:
        _text(image, (540 * scale, 1480 * scale), QUESTION, fitted_font(QUESTION, round(900 * scale), round(76 * scale)),
              PALETTE["text_light"], _clamp((local - times["hide_end"]) / .2))
    if local >= times["count_start"] and counted is not None:
        final = local >= times["count_end"]
        pop = 1 + .25 * (1 - ease_out_cubic(_clamp((local - times["count_end"]) / .3))) if final else 1.0
        _text(image, (540 * scale, 1480 * scale), str(counted), font(round(130 * scale)),
              PALETTE["success"] if final else PALETTE["text_light"], 1.0, pop)
        if final:
            _snap_burst(image, (540, 1480), 150, local - times["count_end"], scale)


def _think(image: Image.Image, local: float, times: dict[str, float], scale: float, y: float) -> None:
    remaining = times["think_end"] - local
    pulse = 1 + .04 * math.sin(local * 6)
    _text(image, (540 * scale, y * scale), "?", font(round(230 * scale)), PALETTE["accent"], .9, pulse)
    _timer(image, remaining, CUBE_THINKING, 1.0, scale)


# ---------------------------------------------------------------- rain: cubes fall from above and vanish as they land

RAIN_HEIGHT = 640.0  # a cube starts this far above where it lands (under the level header)
BADGE_HOLD = 0.55  # in the answer replay, a counted cube stays this long (replay seconds) under its number


def _tinted(colors: dict, alpha: int) -> dict:
    return {name: tuple(value) + (alpha,) for name, value in colors.items()}


def _rain_layer(image: Image.Image, item: RoundSpec, geo: dict, scale: float, clock: float, replay: bool) -> list[tuple[int, dict, float]]:
    """Draw every cube of the rain that is in the air or still fading at `clock` (rain seconds); returns the ones drawn."""
    data = item.data
    fall = float(data["fall"])
    target = data.get("target")
    live = []
    for number, drop in enumerate(item.data["drops"]):
        tau = clock - drop["at"]
        counted = target is None or drop["color"] == target
        stay = BADGE_HOLD if replay and counted else FLIGHT_FADE
        if 0 <= tau <= fall + stay:
            live.append((number, drop, tau))
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    width = max(2, round(2.6 * scale))
    for number, drop, tau in sorted(live, key=lambda entry: (entry[1]["cell"][0] + entry[1]["cell"][1] + drop_size(entry[1]), entry[1]["at"])):
        size = drop_size(drop)
        i, j = drop["cell"]
        counted = target is None or drop["color"] == target
        colors = face_colors(drop["color"])
        if tau < fall:  # falling: it speeds up, and leaves a faint streak
            lift = RAIN_HEIGHT * (1 - (tau / fall) ** 2)
            alpha = round((255 if counted or not replay else 110) * _clamp(tau / fall * 5))  # fades in as it appears
            faces = cube_faces(geo, i, j, 0, size)
            top_x = sum(point[0] for point in faces["top"]) / 4
            top_y = min(point[1] for point in faces["top"]) - lift
            half = geo["tile_w"] * .22 * size
            for step in range(4):
                draw.rectangle(((top_x - half) * scale, (top_y - 150 + step * 36) * scale, (top_x + half) * scale, (top_y - 150 + (step + 1) * 36) * scale),
                               fill=tuple(colors["top"]) + (round(16 + step * 14),))
            _cube(draw, geo, i, j, 0, _tinted(colors, alpha), scale, lift, True, width, size, edge=EDGE_RGB + (alpha,))
        else:
            since = tau - fall
            if replay and counted:
                alpha = 255 if since < BADGE_HOLD - .2 else round(255 * (1 - (since - (BADGE_HOLD - .2)) / .2))
            else:
                alpha = round((110 if replay else 255) * (1 - since / FLIGHT_FADE))
            glow = _clamp(1 - since / FLIGHT_FADE)
            _footprint(layer, geo, [i, j], scale, _rgb(PALETTE["accent"]), round(170 * glow), 1.25, size)
            if alpha > 0:
                _cube(draw, geo, i, j, 0, _tinted(colors, max(0, alpha)), scale, 0.0, True, width, size, edge=EDGE_RGB + (max(0, alpha),))
    if image.mode == "RGBA":
        image.alpha_composite(layer)
    else:
        image.paste(layer, (0, 0), layer)
    return live


def _number_badge(image: Image.Image, geo: dict, drop: dict, number: int, alpha: float, scale: float) -> None:
    size = drop_size(drop)
    i, j = drop["cell"]
    x, y = project(geo, i + size / 2, j + size / 2, 1)
    y -= geo["cube_h"] * .45
    radius = 27
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse(((x - radius) * scale, (y - radius) * scale, (x + radius) * scale, (y + radius) * scale),
                 fill=_rgb(PALETTE["accent"]) + (round(240 * alpha),), outline=_rgb(PALETTE["text_light"]) + (round(220 * alpha),), width=max(1, round(3 * scale)))
    _text(image, (x * scale, y * scale), str(number), font(round(32 * scale)), PALETTE["background"], alpha)


def _draw_rain(spec: VideoSpec, round_index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[round_index]
    data = item.data
    key = _register(spec, round_index)
    geo = geometry(data["grid"])
    times = phases(item)
    colored = cube_mode(data) == "rain_color"
    lead = cube_lead(data)
    intro = float(data.get("intro_seconds", 0.0))
    image = _board_layer(key, size, active_theme()).copy()
    counted = None
    if lead <= local < times["hide_end"]:  # the rain (its last cubes fade during the hide beat)
        _rain_layer(image, item, geo, scale, local - lead, False)
    elif local < times["count_start"]:
        _think(image, local, times, scale, geo["origin_y"] + 190)
    else:  # the answer replays the rain faster and numbers every counted cube
        clock = (local - times["count_start"]) * CUBE_REPLAY_SPEED
        live = _rain_layer(image, item, geo, scale, clock, True)
        target = data.get("target")
        number = 0
        for index, drop in enumerate(data["drops"]):
            if target is not None and drop["color"] != target:
                continue
            number += 1
            tau = clock - drop["at"]
            if tau >= float(data["fall"]) and any(entry[0] == index for entry in live):
                _number_badge(image, geo, drop, number, _clamp(1 - (tau - float(data["fall"]) - (BADGE_HOLD - .2)) / .2), scale)
        counted = sum(1 for drop in data["drops"] if (target is None or drop["color"] == target)
                      and clock >= drop["at"] + float(data["fall"]))
        if local >= times["count_end"]:
            counted = int(item.answer)
    _level_header(image, data.get("level", round_index + 1), spec.round_count, _clamp(local / .25), scale)
    if colored and local < intro:
        # The counted colour is introduced first: the chip sits big in the middle and its cube zooms in and out twice, then it
        # glides up to its place while the level begins.
        glide = ease_in_out(_clamp((local - (intro - .35)) / .35))
        cycle = intro / 2
        pulse = 1 + .55 * (.5 - .5 * math.cos(2 * math.pi * min(local, intro - .35) / cycle)) * (1 - glide)
        dim = Image.new("RGBA", size, (4, 6, 16, round(120 * (1 - glide))))
        image.paste(dim, (0, 0), dim)
        _target_chip(image, data["target"], 640 + (330 - 640) * glide, scale, 1.0, 1.5 + (1 - 1.5) * glide, pulse)
    elif colored:
        _target_chip(image, data["target"], 330, scale)
    elif local < times["hide_end"]:
        _pill(image, "COUNT EVERY CUBE.", 330, scale, 1 - _clamp((local - times["visible_end"]) / .3))
    _question_and_total(image, local, times, counted, scale)
    _fade_overlays(image, spec, round_index, local, size, times["duration"])
    return image


# ---------------------------------------------------------------- sweep: a train of towers crosses the screen

def train_shift(data: dict, elapsed: float) -> float:
    """Pixels the train's middle is right of the screen's middle, `elapsed` seconds into the sweep (it starts and ends off-screen)."""
    geo = sweep_geo()
    reach = 540 + train_width(data["items"]) * geo["tile_w"] / 2 + 70
    return -reach + 2 * reach * _clamp(elapsed / float(data["sweep_seconds"]))


@lru_cache(maxsize=4)
def _sweep_layer(key: str, size: tuple[int, int], theme: str = "violet") -> Image.Image:
    """The empty conveyor belt the towers ride."""
    scale = size[0] / 1080
    geo = sweep_geo()
    image = _background(size, 860, theme).copy()
    centre = SWEEP_Y * scale
    half = (geo["tile_h"] / 2 + 34) * scale
    rounded_surface(image, (-40 * scale, centre - half, 1120 * scale, centre + half), 30 * scale, (14, 20, 44, 235))
    draw = ImageDraw.Draw(image, "RGBA")
    edge = max(2, round(4 * scale))
    draw.line((0, centre - half, size[0], centre - half), fill=(90, 110, 190, 150), width=edge)
    draw.line((0, centre + half, size[0], centre + half), fill=(4, 6, 16, 200), width=edge)
    return image


def _belt_marks(image: Image.Image, elapsed: float, scale: float) -> None:
    """Chevrons that slide along the belt with the towers."""
    geo = sweep_geo()
    draw = ImageDraw.Draw(image, "RGBA")
    spacing = 110
    offset = (elapsed * 700) % spacing
    y = SWEEP_Y
    for step in range(-1, 12):
        x = step * spacing + offset
        draw.line(((x - 12) * scale, (y - geo["tile_h"] / 2 - 14) * scale, x * scale, (y - geo["tile_h"] / 2 - 4) * scale,
                   (x - 12) * scale, (y - geo["tile_h"] / 2 + 6) * scale), fill=(140, 160, 230, 70), width=max(2, round(4 * scale)))


def _draw_sweep(spec: VideoSpec, round_index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[round_index]
    data = item.data
    key = _register(spec, round_index)
    geo = sweep_geo()
    colors = face_colors(data["color_id"])
    times = phases(item)
    image = _sweep_layer(key, size, active_theme()).copy()
    counted = None
    if local < times["hide_end"]:
        elapsed = local - CUBE_LEAD
        _belt_marks(image, max(0.0, elapsed), scale)
        if 0 <= elapsed <= float(data["sweep_seconds"]):
            _cubes(image, geo, sweep_stacks(data, train_shift(data, elapsed)), colors, scale)
    elif local < times["think_end"]:
        _belt_marks(image, 0.0, scale)
        _think(image, local, times, scale, SWEEP_Y - 230)
    elif local < times["count_start"]:
        _belt_marks(image, 0.0, scale)
        _cubes(image, geo, sweep_stacks(data), colors, scale, _drop_lifts(sweep_stacks(data), local - times["think_end"], CUBE_RETURN, 140))
    else:
        stacks = sweep_stacks(data)
        order = list(range(len(stacks)))  # left to right
        slot = CUBE_COUNT_UP / len(order)
        elapsed = local - times["count_start"]
        done = min(len(order), int(elapsed / slot) + 1)
        current = order[done - 1] if elapsed < CUBE_COUNT_UP else None
        counted = sum(cubes_in(stacks[index]) for index in order[:done])
        glow = {index: (1.0 if index == current else .45) for position, index in enumerate(order) if elapsed - position * slot >= 0}
        _belt_marks(image, 0.0, scale)
        _cubes(image, geo, stacks, colors, scale, glow=glow)
        for position, index in enumerate(order):
            started = elapsed - position * slot
            if started >= 0:
                _stack_label(image, geo, stacks[index], scale, _clamp(started / .12), index == current)
    _level_header(image, data.get("level", round_index + 1), spec.round_count, _clamp(local / .25), scale)
    if local < times["hide_end"]:
        _pill(image, "COUNT EVERY CUBE.", 400, scale, 1 - _clamp((local - times["visible_end"]) / .3))
    _question_and_total(image, local, times, counted, scale)
    _fade_overlays(image, spec, round_index, local, size, times["duration"])
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
    from .ready import hook_end
    fade = 1 - _clamp((t - (hook_end(spec) - .22)) / .22)
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .18)))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(940 * scale), round(84 * scale)),
          PALETTE["text_light"], fade * _clamp(t / .08 + .3), slam)
    seconds = spec.rounds[0].data["visible_seconds"]
    unit = "SECOND" if seconds == 1 else "SECONDS"
    subtitle = f"{spec.round_count} LEVELS · {seconds:g} {unit} TO LOOK"
    if "mode" in spec.rounds[0].data:  # every level counts a different way
        subtitle = f"{spec.round_count} LEVELS · {spec.round_count} WAYS TO COUNT"
    _text(image, (540 * scale, 232 * scale), subtitle, font(round(34 * scale)), PALETTE["accent"], fade * _clamp((t - .15) / .2))
    return image


def draw_cube_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        from .ready import HOOK_SECONDS, draw_ready_screen, has_ready
        if has_ready(spec) and t >= HOOK_SECONDS:
            return draw_ready_screen(spec, t - HOOK_SECONDS, size)
        return draw_cube_intro(spec, t, size)
    levels = schedule(spec)
    rounds_end = levels[-1][0] + levels[-1][1]
    if t >= rounds_end - 1e-9:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size)
    round_index = max(index for index, (start, _) in enumerate(levels) if start <= t + 1e-9)
    return draw_cube_round(spec, round_index, t - levels[round_index][0], size)
