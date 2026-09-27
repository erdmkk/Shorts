"""Puzzle Fit "Puzzly for You" look: dark theme, artwork-cut pieces, hook intro, level header, and elimination reveal."""
from __future__ import annotations

import math
import random
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter

from ..branding import draw_brand_mark
from ..config import DARK_THEMES, PUZZLE_FIT_ART_PALETTES, dark_theme_for, PUZZLE_FIT_PALETTE as PALETTE, thinking_duration
from ..models import RoundSpec, VideoSpec
from ..puzzles.puzzle_fit import board_card_bounds, phase_times, visual_state
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .jigsaw import piece_points
from .text import fitted_font, font

HOOK_TEXT = "ONLY ONE FITS."
OUTRO_QUESTION = "How many did you get?"
OUTRO_PROMPT = "Comment your score ↓"
BRAND_NAME = "Puzzly for You"
BOB_AMPLITUDE = 6.0
BOB_SPEED = 0.75
HOLE_DASH_WIDTH = 3.0
HOLE_DASH_ALPHA = 150


def _rgb(value: str) -> tuple[int, int, int]:
    return ImageColor.getrgb(value)[:3]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------- geometry

def board_geometry(data: dict, difficulty: str) -> dict[str, float]:
    """Logical (1080x1920) board placement shared by the board, hole, artwork, and snap target."""
    card = board_card_bounds(difficulty)
    rows, columns = data["rows"], data["columns"]
    span = 560 if difficulty == "hard" else 660
    cell = min(span / columns, span / rows)
    left = 540 - columns * cell / 2
    top = (card[1] + card[3]) / 2 - rows * cell / 2
    tab = cell / 7
    return {"cell": cell, "left": left, "top": top, "tab": tab, "margin": tab + 6}


def candidate_half(difficulty: str) -> float:
    return 70 if difficulty == "hard" else 92


def candidate_centers(data: dict) -> list[tuple[float, float]]:
    return [((x1 + x2) / 2, (y1 + y2) / 2) for x1, y1, x2, y2 in data["candidate_cards"]]


def bob_offset(index: int, local: float) -> float:
    """Identical gentle float for every candidate (phase-shifted only), so motion never hints at the answer."""
    return BOB_AMPLITUDE * math.sin(2 * math.pi * BOB_SPEED * local + index * 0.9)


def elimination_order(data: dict) -> list[int]:
    wrong = [index for index in range(len(data["candidates"])) if index != data["correct_index"]]
    random.Random(f"puzzle_fit_elim:{data.get('art_seed', 0)}").shuffle(wrong)
    return wrong


# ---------------------------------------------------------------- artwork

def _palette_array(palette_index: int, palette: str | None = None) -> np.ndarray:
    from ..palette import recolor
    colors = PUZZLE_FIT_ART_PALETTES[palette_index % len(PUZZLE_FIT_ART_PALETTES)]
    return np.array([_rgb(recolor(color, palette)) for color in colors], dtype=np.float32)


def _palette_key(key: str) -> str:
    """Cache keys for anything painted with object colours include the active object palette."""
    from ..palette import active
    return f"{key}:{active()}"


def _cycle(colors: np.ndarray, value: np.ndarray) -> np.ndarray:
    """Smoothly cycle through the palette for any real-valued field."""
    count = len(colors)
    value = np.mod(value, count)
    low = np.floor(value).astype(int) % count
    high = (low + 1) % count
    blend = (value - np.floor(value))[..., None]
    blend = blend * blend * (3 - 2 * blend)
    return colors[low] * (1 - blend) + colors[high] * blend


def artwork(style: str, palette_index: int, art_seed: int, width: int, height: int) -> Image.Image:
    from ..palette import active
    return _artwork(style, palette_index, art_seed, width, height, active())


@lru_cache(maxsize=12)
def _artwork(style: str, palette_index: int, art_seed: int, width: int, height: int, palette: str | None) -> Image.Image:
    """Deterministic resolution-independent abstract artwork that is cut into the round's jigsaw pieces."""
    rng = random.Random(art_seed)
    colors = _palette_array(palette_index, palette)
    v, u = np.mgrid[0:height, 0:width].astype(np.float32)
    u /= max(1, width - 1)
    v /= max(1, height - 1)
    if style == "rings":
        cx, cy = rng.uniform(.2, .8), rng.uniform(.2, .8)
        field = np.hypot(u - cx, v - cy) * rng.uniform(7, 10) + np.arctan2(v - cy, u - cx) * .35
    elif style == "stripes":
        angle = rng.uniform(0, math.pi)
        field = (u * math.cos(angle) + v * math.sin(angle)) * rng.uniform(6, 9) + np.sin(u * 9 + v * 5) * .25
    elif style == "waves":
        frequency, phase = rng.uniform(8, 12), rng.uniform(0, 6)
        field = v * rng.uniform(6, 8) + np.sin(u * frequency + phase) * .8 + np.sin(u * 3.1 + v * 4) * .3
    elif style == "burst":
        cx, cy = rng.uniform(.3, .7), rng.uniform(.3, .7)
        rays = rng.choice((10, 12, 14))
        angle = np.arctan2(v - cy, u - cx)
        field = np.floor((angle / (2 * math.pi) + .5) * rays) + np.hypot(u - cx, v - cy) * 2.2
    else:
        field = None
    if field is not None:
        rgb = _cycle(colors, field)
        rgb *= (0.86 + 0.14 * (1 - v))[..., None]
        return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    # Low-poly mosaic: jittered triangle grid shaded across the palette.
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    steps = 7
    jitter = .32
    points = [[((column + (rng.uniform(-jitter, jitter) if 0 < column < steps else 0)) / steps * width,
                (row + (rng.uniform(-jitter, jitter) if 0 < row < steps else 0)) / steps * height)
               for column in range(steps + 1)] for row in range(steps + 1)]
    offset = rng.uniform(0, 4)
    for row in range(steps):
        for column in range(steps):
            a, b = points[row][column], points[row][column + 1]
            c, d = points[row + 1][column], points[row + 1][column + 1]
            for triangle in ((a, b, d), (a, d, c)) if (row + column) % 2 else ((a, b, c), (b, d, c)):
                mx = sum(p[0] for p in triangle) / 3 / width
                my = sum(p[1] for p in triangle) / 3 / height
                shade = _cycle(colors, np.array(offset + mx * 2.2 + my * 1.6 + rng.uniform(-.25, .25)))
                shade = shade * (0.82 + rng.uniform(0, .18))
                draw.polygon(triangle, fill=tuple(int(max(0, min(255, value))) for value in shade))
    return image


def _round_art(data: dict, geometry: dict[str, float], scale: float) -> Image.Image:
    width = round((data["columns"] * geometry["cell"] + 2 * geometry["margin"]) * scale)
    height = round((data["rows"] * geometry["cell"] + 2 * geometry["margin"]) * scale)
    return artwork(data.get("art_style", "rings"), int(data.get("art_palette", 0)), int(data.get("art_seed", 0)), width, height)


# ---------------------------------------------------------------- piece sprites

@lru_cache(maxsize=256)
def _piece_mask(cell_px: float, margin_px: float, tab_px: float, edges: tuple[int, ...]) -> Image.Image:
    """Antialiased piece silhouette rasterized at 2x and downsampled once."""
    side = round(cell_px + 2 * margin_px)
    high = Image.new("L", (side * 2, side * 2), 0)
    bounds = (margin_px * 2, margin_px * 2, (margin_px + cell_px) * 2, (margin_px + cell_px) * 2)
    ImageDraw.Draw(high).polygon(piece_points(bounds, list(edges), tab_px * 2), fill=255)
    return high.resize((side, side), Image.Resampling.LANCZOS)


def _shift(mask: Image.Image, dx: int, dy: int) -> Image.Image:
    return ImageChops.offset(mask, dx, dy)


def _build_sprite(art: Image.Image, origin: tuple[int, int], mask: Image.Image, scale: float) -> Image.Image:
    """Cut the artwork with a bevelled, outlined jigsaw silhouette."""
    crop = art.crop((origin[0], origin[1], origin[0] + mask.width, origin[1] + mask.height)).convert("RGBA")
    bevel = max(1, round(3 * scale))
    light = ImageChops.subtract(mask, _shift(mask, bevel, bevel))
    dark = ImageChops.subtract(mask, _shift(mask, -bevel, -bevel))
    crop.paste(Image.new("RGBA", crop.size, (255, 255, 255, 255)), (0, 0), light.point(lambda value: value * 90 // 255))
    crop.paste(Image.new("RGBA", crop.size, (0, 0, 0, 255)), (0, 0), dark.point(lambda value: value * 110 // 255))
    stroke = 2 * max(1, round(3.5 * scale)) + 1
    inner = mask.filter(ImageFilter.MinFilter(stroke))
    ring = ImageChops.subtract(mask, inner)
    crop.paste(Image.new("RGBA", crop.size, _rgb(PALETTE["outline"]) + (255,)), (0, 0), ring)
    crop.putalpha(mask)
    return crop


@lru_cache(maxsize=160)
def _sprite(round_key: str, slot: int, edges: tuple[int, ...], data_items: tuple, difficulty: str, scale: float) -> Image.Image:
    data = dict(data_items)
    geometry = board_geometry(data, difficulty)
    art = _round_art(data, geometry, scale)
    row, column = divmod(slot, data["columns"])
    mask = _piece_mask(geometry["cell"] * scale, geometry["margin"] * scale, geometry["tab"] * scale, edges)
    origin = (round(column * geometry["cell"] * scale), round(row * geometry["cell"] * scale))
    return _build_sprite(art, origin, mask, scale)


@lru_cache(maxsize=64)
def _glow_cached(round_key: str, slot: int, edges: tuple[int, ...], data_items: tuple, difficulty: str,
                 scale: float, color: str, radius: int) -> Image.Image:
    sprite = _sprite(round_key, slot, edges, data_items, difficulty, scale)
    alpha = sprite.getchannel("A").filter(ImageFilter.MaxFilter(2 * max(1, radius // 2) + 1)).filter(ImageFilter.GaussianBlur(radius))
    glow = Image.new("RGBA", sprite.size, _rgb(color) + (0,))
    glow.putalpha(alpha)
    return glow


def _data_items(data: dict) -> tuple:
    keys = ("rows", "columns", "art_style", "art_palette", "art_seed")
    return tuple((key, data.get(key)) for key in keys)


def piece_sprite(round_spec: RoundSpec, slot: int, edges: list[int], difficulty: str, scale: float) -> Image.Image:
    return _sprite(_palette_key(round_spec.fingerprint()), slot, tuple(edges), _data_items(round_spec.data), difficulty, round(scale, 4))


def piece_glow(round_spec: RoundSpec, slot: int, edges: list[int], difficulty: str, scale: float, radius: int) -> Image.Image:
    return _glow_cached(_palette_key(round_spec.fingerprint()), slot, tuple(edges), _data_items(round_spec.data), difficulty,
                        round(scale, 4), PALETTE["success"], radius)


def _paste_scaled(image: Image.Image, sprite: Image.Image, center: tuple[float, float], factor: float, opacity: float = 1.0) -> None:
    if factor <= 0 or opacity <= 0:
        return
    width, height = max(1, round(sprite.width * factor)), max(1, round(sprite.height * factor))
    resized = sprite if (width, height) == sprite.size else sprite.resize((width, height), Image.Resampling.LANCZOS)
    if opacity < 1:
        resized = resized.copy()
        resized.putalpha(resized.getchannel("A").point(lambda value: round(value * opacity)))
    image.paste(resized, (round(center[0] - width / 2), round(center[1] - height / 2)), resized)


# ---------------------------------------------------------------- background and static round layer

_ACTIVE_THEME = {"id": "violet"}


def background_theme(spec: VideoSpec) -> str:
    """The dark background tone of a video: the creator's choice or random per video, fixed for its frames and cover."""
    from ..palette import background_for
    return background_for(spec)


def use_theme(spec: VideoSpec) -> None:
    from .. import palette
    _ACTIVE_THEME["id"] = background_theme(spec)
    palette.use(spec)


def active_theme() -> str:
    return _ACTIVE_THEME["id"]


def _background(size: tuple[int, int], glow_y: float, theme: str | None = None) -> Image.Image:
    return _themed_background(size, glow_y, theme or active_theme())


@lru_cache(maxsize=8)
def _themed_background(size: tuple[int, int], glow_y: float, theme: str) -> Image.Image:
    width, height = size
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    top, bottom, glow = (np.array(_rgb(value), dtype=np.float32) for value in DARK_THEMES.get(theme, DARK_THEMES["violet"]))
    t = (y / max(1, height - 1))[..., None]
    rgb = top * (1 - t) + bottom * t
    scale = width / 1080
    distance = np.hypot(x - width / 2, y - glow_y * scale) / (620 * scale)
    rgb += (glow - top) * (np.exp(-distance * distance) * .38)[..., None]
    vignette = np.hypot((x / width - .5) * 1.2, y / height - .5)
    rgb *= (1 - np.clip(vignette - .35, 0, 1) * .55)[..., None]
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    draw = ImageDraw.Draw(image, "RGBA")
    step = 54 * scale
    radius = max(1, round(1.6 * scale))
    for row in range(int(height / step) + 1):
        for column in range(int(width / step) + 1):
            px, py = column * step + (step / 2 if row % 2 else 0), row * step
            if abs(px - width / 2) < 380 * scale and 250 * scale < py < 1620 * scale:
                continue
            draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=(255, 255, 255, 18))
    return image


def _hole_points(geometry: dict[str, float], data: dict, scale: float) -> list[tuple[float, float]]:
    row, column = divmod(data["hole_slot"], data["columns"])
    cell = geometry["cell"]
    x1 = (geometry["left"] + column * cell) * scale
    y1 = (geometry["top"] + row * cell) * scale
    return piece_points((x1, y1, x1 + cell * scale, y1 + cell * scale), data["hole_edges"], geometry["tab"] * scale)


def slot_center(geometry: dict[str, float], data: dict, slot: int) -> tuple[float, float]:
    row, column = divmod(slot, data["columns"])
    cell = geometry["cell"]
    return geometry["left"] + (column + .5) * cell, geometry["top"] + (row + .5) * cell


_ROUNDS: dict[str, RoundSpec] = {}


@lru_cache(maxsize=6)
def _round_layer(round_key: str, difficulty: str, size: tuple[int, int], theme: str = "violet") -> Image.Image:
    """Background, board card, candidate tray, placed pieces, and glowing empty hole: static for the whole round."""
    round_spec = _ROUNDS[round_key]
    scale = size[0] / 1080
    data = round_spec.data
    geometry = board_geometry(data, difficulty)
    card = board_card_bounds(difficulty)
    image = _background(size, (card[1] + card[3]) / 2, theme).copy()
    s = lambda values: tuple(value * scale for value in values)
    # The card hugs the board vertically so 2x2 and 2x3 boards do not float in an oversized frame.
    board_bottom = geometry["top"] + data["rows"] * geometry["cell"]
    card = (card[0], max(card[1], geometry["top"] - 60), card[2], min(card[3], board_bottom + 60))
    rounded_surface(image, s(card), 64 * scale, PALETTE["surface"], PALETTE["surface_edge"], 3 * scale, shadow=True)
    cards = data["candidate_cards"]
    tray = (min(c[0] for c in cards) - 20, min(c[1] for c in cards) - 15, max(c[2] for c in cards) + 20, max(c[3] for c in cards) + 15)
    rounded_surface(image, s(tray), 48 * scale, _rgb(PALETTE["surface"]) + (150,), _rgb(PALETTE["surface_edge"]) + (160,), 2 * scale)
    for slot, edges in enumerate(data["piece_edges"]):
        if slot == data["hole_slot"]:
            continue
        sprite = piece_sprite(round_spec, slot, edges, difficulty, scale)
        cx, cy = slot_center(geometry, data, slot)
        _paste_scaled(image, sprite, (cx * scale, cy * scale), 1.0)
    hole = _hole_points(geometry, data, scale)
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).line(hole + hole[:1], fill=200, width=max(2, round(10 * scale)), joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(16 * scale))
    image.paste(Image.new("RGB", size, PALETTE["accent"]), (0, 0), glow.point(lambda value: value * 45 // 255))
    ImageDraw.Draw(image).polygon(hole, fill=PALETTE["hole"])
    return image


def _dashed_outline(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], color, width: int, phase: float) -> None:
    dash = max(8, width * 5)
    stroke: list[tuple[float, float]] = []
    travelled = phase
    for start, end in zip(points, points[1:] + points[:1]):
        distance = math.dist(start, end)
        steps = max(1, math.ceil(distance / max(1, width / 2)))
        for step in range(steps):
            a, b = step / steps, (step + 1) / steps
            if int((travelled + distance * a) / dash) % 2 == 0:
                stroke.extend(((start[0] + (end[0] - start[0]) * a, start[1] + (end[1] - start[1]) * a),
                               (start[0] + (end[0] - start[0]) * b, start[1] + (end[1] - start[1]) * b)))
            elif stroke:
                draw.line(stroke, fill=color, width=width, joint="curve")
                stroke = []
        travelled += distance
    if stroke:
        draw.line(stroke, fill=color, width=width, joint="curve")


def _hole_dashes(image: Image.Image, points: list[tuple[float, float]], color: str, width: int, phase: float) -> None:
    """Thin semi-transparent marching dashes: drawn opaque into a local mask, then blended once (no dark joints)."""
    pad = width * 2 + 2
    left, top = math.floor(min(p[0] for p in points)) - pad, math.floor(min(p[1] for p in points)) - pad
    right, bottom = math.ceil(max(p[0] for p in points)) + pad, math.ceil(max(p[1] for p in points)) + pad
    mask = Image.new("L", (right - left, bottom - top), 0)
    _dashed_outline(ImageDraw.Draw(mask), [(x - left, y - top) for x, y in points], 255, width, phase)
    mask = mask.point(lambda value: value * HOLE_DASH_ALPHA // 255)
    image.paste(Image.new("RGB", mask.size, color), (left, top), mask)


# ---------------------------------------------------------------- text and HUD

def _text(image: Image.Image, center: tuple[float, float], text: str, face, fill: str, opacity: float = 1.0, zoom: float = 1.0) -> None:
    if opacity <= 0:
        return
    if zoom == 1.0 and opacity >= 1.0:
        ImageDraw.Draw(image).text(center, text, font=face, fill=fill, anchor="mm")
        return
    probe = ImageDraw.Draw(image).textbbox((0, 0), text, font=face, anchor="lt")
    pad = 12
    layer = Image.new("RGBA", (probe[2] + pad * 2, probe[3] + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((pad, pad), text, font=face, fill=fill, anchor="lt")
    layer.putalpha(layer.getchannel("A").point(lambda value: round(value * _clamp(opacity))))
    _paste_scaled(image, layer, center, zoom)


def _level_header(image: Image.Image, level: int, total: int, opacity: float, scale: float) -> None:
    if opacity <= 0:
        return
    big, small = font(round(64 * scale)), font(round(40 * scale))
    draw = ImageDraw.Draw(image)
    label, suffix = f"LEVEL {level}", f"/{total}"
    gap = 14 * scale
    width_big, width_small = draw.textlength(label, font=big), draw.textlength(suffix, font=small)
    start = image.width / 2 - (width_big + gap + width_small) / 2
    y = 150 * scale
    _text(image, (start + width_big / 2, y), label, big, PALETTE["text_light"], opacity)
    _text(image, (start + width_big + gap + width_small / 2, y + 8 * scale), suffix, small, PALETTE["text_muted"], opacity)


def timer_color(remaining_fraction: float) -> str:
    if remaining_fraction > .5:
        return PALETTE["accent"]
    if remaining_fraction > .25:
        return PALETTE["warning"]
    return PALETTE["danger"]


def _timer(image: Image.Image, remaining_seconds: float, total_seconds: float, opacity: float, scale: float,
           show_seconds: bool = True) -> None:
    if opacity <= 0:
        return
    fraction = _clamp(remaining_seconds / total_seconds)
    color = timer_color(fraction)
    pulse = 0.0
    if remaining_seconds < 1.5:
        pulse = abs(math.sin(math.pi * 2 * remaining_seconds))
    x1, x2 = (190 * scale, 820 * scale) if show_seconds else (220 * scale, 860 * scale)  # bar-only timer stays centred
    y, height = 232 * scale, (18 + 8 * pulse) * scale
    track = _rgb(PALETTE["surface_edge"]) + (round(255 * opacity),)
    rounded_surface(image, (x1, y - height / 2, x2, y + height / 2), height / 2, track)
    fill_end = x1 + max(height, (x2 - x1) * fraction)
    rounded_surface(image, (x1, y - height / 2, fill_end, y + height / 2), height / 2, _rgb(color) + (round(255 * opacity),))
    if show_seconds:
        seconds = str(max(1, math.ceil(remaining_seconds - 1e-6)))
        _text(image, (880 * scale, y - 2 * scale), seconds, font(round((48 + 10 * pulse) * scale)), color, opacity)


# ---------------------------------------------------------------- frames

def _draw_candidates(image: Image.Image, round_spec: RoundSpec, local: float, difficulty: str, scale: float,
                     entrance: float = 1.0, skip_correct: bool = False) -> None:
    data = round_spec.data
    times = phase_times(difficulty)
    geometry = board_geometry(data, difficulty)
    factor = 2 * candidate_half(difficulty) / geometry["cell"]
    order = elimination_order(data)
    freeze = min(local, times["think_end"])
    for index, (cx, cy) in enumerate(candidate_centers(data)):
        if skip_correct and index == data["correct_index"]:
            continue
        sprite = piece_sprite(round_spec, data["hole_slot"], data["candidates"][index], difficulty, scale)
        pop = ease_out_back(_clamp((entrance - index * .035) / .6)) if entrance < 1 else 1.0
        opacity, shrink, drop = 1.0, 1.0, 0.0
        if index in order and local >= times["think_end"]:
            start = times["think_end"] + order.index(index) * .04
            progress = ease_in_out(_clamp((local - start) / .22))
            opacity, shrink, drop = 1 - progress, 1 - .55 * progress, 26 * progress
        if index == data["correct_index"] and local >= times["think_end"] + .25:
            glow_amount = _clamp((local - times["think_end"] - .25) / .2)
            glow = piece_glow(round_spec, data["hole_slot"], data["candidates"][index], difficulty, scale, max(4, round(10 * scale)))
            _paste_scaled(image, glow, (cx * scale, (cy + bob_offset(index, freeze)) * scale), factor * pop, glow_amount)
        center = (cx * scale, (cy + bob_offset(index, freeze) + drop) * scale)
        _paste_scaled(image, sprite, center, factor * pop * shrink, opacity)


def _draw_round(image: Image.Image, round_spec: RoundSpec, local: float, spec: VideoSpec, scale: float,
                header_opacity: float, entrance: float) -> None:
    data, difficulty = round_spec.data, spec.difficulty
    times = phase_times(difficulty)
    state = visual_state(local, difficulty)
    geometry = board_geometry(data, difficulty)
    hole_center = slot_center(geometry, data, data["hole_slot"])
    if state != "solved":
        color = PALETTE["accent"] if state in ("choices", "thinking") else PALETTE["success"]
        _hole_dashes(image, _hole_points(geometry, data, scale), color, max(1, round(HOLE_DASH_WIDTH * scale)), local * 70 * scale)
    _draw_candidates(image, round_spec, local, difficulty, scale, entrance, skip_correct=state in ("moving", "solved"))
    factor = 2 * candidate_half(difficulty) / geometry["cell"]
    hole_sprite = piece_sprite(round_spec, data["hole_slot"], data["hole_edges"], difficulty, scale)
    if state == "moving":
        cx, cy = candidate_centers(data)[data["correct_index"]]
        cy += bob_offset(data["correct_index"], times["think_end"])
        progress = ease_in_out((local - times["move_start"]) / (times["snap"] - times["move_start"]))
        lift = math.sin(progress * math.pi) * 40
        x = cx + (hole_center[0] - cx) * progress
        y = cy + (hole_center[1] - cy) * progress - lift
        glow = piece_glow(round_spec, data["hole_slot"], data["hole_edges"], difficulty, scale, max(4, round(10 * scale)))
        zoom = factor + (1 - factor) * progress
        _paste_scaled(image, glow, (x * scale, y * scale), zoom, 1.0)
        _paste_scaled(image, hole_sprite, (x * scale, y * scale), zoom * (1 + .06 * math.sin(progress * math.pi)))
    elif state == "solved":
        since = local - times["snap"]
        glow = piece_glow(round_spec, data["hole_slot"], data["hole_edges"], difficulty, scale, max(4, round(14 * scale)))
        _paste_scaled(image, glow, (hole_center[0] * scale, hole_center[1] * scale), 1.0, 1 - _clamp(since / .7))
        _paste_scaled(image, hole_sprite, (hole_center[0] * scale, hole_center[1] * scale), 1 + .08 * (1 - ease_out_cubic(_clamp(since / .25))))
        _snap_burst(image, hole_center, geometry["cell"], since, scale)
    header = header_opacity
    _level_header(image, data.get("level", round_spec.index + 1), spec.round_count, header, scale)
    if state in ("choices", "thinking"):
        total = thinking_duration("puzzle_fit", difficulty)
        remaining = total if state == "choices" else times["think_end"] - local
        _timer(image, remaining, total, header * (_clamp(local / .3) if state == "choices" else 1), scale)
    elif state in ("eliminating", "moving"):
        _timer(image, 0.001, 1, 1 - _clamp((local - times["think_end"]) / .25), scale)


def _snap_burst(image: Image.Image, center: tuple[float, float], cell: float, since: float, scale: float) -> None:
    if since > .6:
        return
    progress = ease_out_cubic(_clamp(since / .6))
    draw = ImageDraw.Draw(image, "RGBA")
    cx, cy = center[0] * scale, center[1] * scale
    radius = (cell * .55 + cell * .9 * progress) * scale
    alpha = round(220 * (1 - progress))
    width = max(2, round(8 * (1 - progress) * scale) + 1)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=_rgb(PALETTE["success"]) + (alpha,), width=width)
    for index in range(12):
        angle = index / 12 * 2 * math.pi + .2
        distance = (cell * .45 + cell * 1.1 * progress) * scale
        px, py = cx + math.cos(angle) * distance, cy + math.sin(angle) * distance
        dot = max(1, round((7 - 5 * progress) * scale))
        color = PALETTE["warning"] if index % 3 == 0 else (PALETTE["accent"] if index % 3 == 1 else PALETTE["text_light"])
        draw.ellipse((px - dot, py - dot, px + dot, py + dot), fill=_rgb(color) + (alpha,))


def _round_image(spec: VideoSpec, round_index: int, size: tuple[int, int]) -> Image.Image:
    round_spec = spec.rounds[round_index]
    key = _palette_key(f"{spec.id}:{spec.difficulty}:{round_spec.fingerprint()}")
    _ROUNDS[key] = round_spec
    return _round_layer(key, spec.difficulty, size, active_theme()).copy()


def draw_puzzle_fit_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook: the first level is on screen from frame one under a bold challenge line."""
    scale = size[0] / 1080
    image = _round_image(spec, 0, size)
    round_spec = spec.rounds[0]
    local = t - spec.intro_duration
    _hole_dashes(image, _hole_points(board_geometry(round_spec.data, spec.difficulty), round_spec.data, scale),
                 PALETTE["accent"], max(1, round(HOLE_DASH_WIDTH * scale)), local * 70 * scale)
    _draw_candidates(image, round_spec, local, spec.difficulty, scale, entrance=_clamp(t / .45))
    fade = 1 - _clamp((t - (spec.intro_duration - .22)) / .22)
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .18)))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(900 * scale), round(84 * scale)),
          PALETTE["text_light"], fade * _clamp(t / .08 + .3), slam)
    subtitle = f"{spec.round_count} LEVELS · EACH ONE HARDER"
    _text(image, (540 * scale, 232 * scale), subtitle, font(round(34 * scale)), PALETTE["accent"], fade * _clamp((t - .15) / .2))
    return image


def draw_puzzle_fit_round(spec: VideoSpec, round_index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    image = _round_image(spec, round_index, size)
    entrance = 1.0 if round_index == 0 else _clamp(local / .45)
    _draw_round(image, spec.rounds[round_index], local, spec, scale, _clamp(local / .25), entrance)
    transition_start = spec.round_duration - .2
    if local > transition_start and round_index < spec.round_count - 1:
        alpha = round(200 * ease_in_out((local - transition_start) / .2))
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (alpha,))
        image.paste(overlay, (0, 0), overlay)
    return image


def _spaced_text(image: Image.Image, center: tuple[float, float], text: str, face, fill: str, opacity: float, spacing: float) -> None:
    if opacity <= 0:
        return
    draw = ImageDraw.Draw(image, "RGBA")
    widths = [draw.textlength(char, font=face) for char in text]
    x = center[0] - (sum(widths) + spacing * (len(text) - 1)) / 2
    for char, width in zip(text, widths):
        draw.text((x, center[1]), char, font=face, fill=_rgb(fill) + (round(255 * opacity),), anchor="lm")
        x += width + spacing


@lru_cache(maxsize=8)
def _outro_glow(radius: int, color: str) -> Image.Image:
    side = radius * 4
    sprite = Image.new("RGBA", (side, side), _rgb(color) + (0,))
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).ellipse((radius, radius, side - radius, side - radius), fill=150)
    sprite.putalpha(mask.filter(ImageFilter.GaussianBlur(radius * .45)))
    return sprite


def draw_puzzle_fit_outro(spec: VideoSpec, local: float, size: tuple[int, int], question_text: str | None = None,
                          prompt_text: str | None = None, *, palette: dict | None = None, background: Image.Image | None = None,
                          hero=None, total: int | None = None) -> Image.Image:
    """End card with almost no reading: a glowing score ring (or the winner), one short line, and a tapped Follow button.

    Score games show `?/N` inside a ring that fills up. Pick games pass `hero`, a function returning the winner sprite
    at a given pixel size, and a short question. The brand stays small at the bottom.
    """
    pal = {**PALETTE, **(palette or {})}
    scale = size[0] / 1080
    image = (background if background is not None else _background(size, 800)).copy()
    draw = ImageDraw.Draw(image, "RGBA")
    # Soft particles drifting upward.
    rng = random.Random(7)
    for _ in range(24):
        x, y0, speed, radius = rng.uniform(60, 1020), rng.uniform(300, 1800), rng.uniform(60, 160), rng.uniform(2, 5)
        y = y0 - speed * local
        alpha = round(90 * _clamp(local / .3) * (.4 + .6 * rng.random()))
        draw.ellipse(((x - radius) * scale, (y - radius) * scale, (x + radius) * scale, (y + radius) * scale),
                     fill=_rgb(pal["accent"]) + (alpha,))
    # Hero ring.
    cx, cy, ring = 540 * scale, 760 * scale, 200 * scale
    pop = ease_out_back(_clamp(local / .35))
    glow = _outro_glow(max(4, round(ring * 1.05)), pal["accent"])
    pulse = .85 + .15 * math.sin(local * 6)
    faded = glow.copy()
    faded.putalpha(glow.getchannel("A").point(lambda value: round(value * pulse * _clamp(local / .3))))
    image.paste(faded, (round(cx - faded.width / 2), round(cy - faded.height / 2)), faded)
    draw = ImageDraw.Draw(image, "RGBA")
    radius = ring * max(.3, pop)
    width = max(3, round(18 * scale))
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=_rgb(pal["background"]) + (230,),
                 outline=_rgb(pal["surface_edge"]) + (255,), width=width)
    progress = ease_out_cubic(_clamp((local - .1) / .6))
    if progress > 0:
        draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), -90, -90 + 360 * progress, fill=_rgb(pal["accent"]) + (255,), width=width)
        end = math.radians(-90 + 360 * progress)
        dot = width * .9
        ex, ey = cx + math.cos(end) * (radius - width / 2), cy + math.sin(end) * (radius - width / 2)
        draw.ellipse((ex - dot, ey - dot, ex + dot, ey + dot), fill=(255, 255, 255, 255))
    inner = ease_out_back(_clamp((local - .15) / .35))
    if inner > 0:
        if hero is not None:
            sprite = hero(max(2, round(230 * scale * inner)))
            image.paste(sprite, (round(cx - sprite.width / 2), round(cy - sprite.height / 2)), sprite)
        else:
            count = total or spec.round_count
            big, small = font(round(190 * scale)), font(round(110 * scale))
            suffix = f"/{count}"
            w_big, w_small = draw.textlength("?", font=big), draw.textlength(suffix, font=small)
            start = cx - (w_big + w_small) / 2
            _text(image, (start + w_big / 2, cy - 10 * scale), "?", big, pal["accent"], 1.0, inner)
            _text(image, (start + w_big + w_small / 2, cy + 30 * scale), suffix, small, pal["text_light"], 1.0, inner)
    # One short line.
    line = (question_text or "").upper() if hero is not None else "COMMENT YOUR SCORE"
    line_face = fitted_font(line, round(900 * scale), round(46 * scale))
    _spaced_text(image, (cx, 1045 * scale), line, line_face, pal["text_light"], _clamp((local - .3) / .25), 6 * scale)
    chevron = _clamp((local - .4) / .25)
    if chevron > 0:
        bob = 8 * math.sin(local * 9) * scale
        y = 1110 * scale + bob
        draw = ImageDraw.Draw(image, "RGBA")
        draw.line(((cx - 22 * scale, y - 10 * scale), (cx, y + 10 * scale), (cx + 22 * scale, y - 10 * scale)),
                  fill=_rgb(pal["accent"]) + (round(255 * chevron),), width=max(2, round(7 * scale)), joint="curve")
    # Follow button, pressed by a tapping finger.
    appear = ease_out_cubic(_clamp((local - .45) / .25))
    if appear > 0:
        press = math.sin(math.pi * _clamp((local - 1.0) / .14)) if local >= 1.0 else 0.0
        zoom = 1 - .06 * press
        bw, bh = 620 * scale * zoom, 128 * scale * zoom
        by = (1255 + 60 * (1 - appear)) * scale
        rounded_surface(image, (cx - bw / 2, by - bh / 2 + 10 * scale, cx + bw / 2, by + bh / 2 + 10 * scale), bh / 2,
                        (0, 0, 0, round(120 * appear)))
        fill = _rgb(pal["accent"])
        if local >= 1.0:
            flash = _clamp(1 - (local - 1.0) / .4)
            fill = tuple(round(channel + (255 - channel) * .35 * flash) for channel in fill)
        rounded_surface(image, (cx - bw / 2, by - bh / 2, cx + bw / 2, by + bh / 2), bh / 2, fill + (round(255 * appear),))
        icon_x, icon_r = cx - bw / 2 + 78 * scale * zoom, 34 * scale * zoom
        draw = ImageDraw.Draw(image, "RGBA")
        ink = _rgb(pal["background"]) + (round(255 * appear),)
        draw.ellipse((icon_x - icon_r, by - icon_r, icon_x + icon_r, by + icon_r), outline=ink, width=max(2, round(6 * scale)))
        arm = icon_r * .5
        draw.line(((icon_x - arm, by), (icon_x + arm, by)), fill=ink, width=max(2, round(6 * scale)))
        draw.line(((icon_x, by - arm), (icon_x, by + arm)), fill=ink, width=max(2, round(6 * scale)))
        _text(image, (cx + 40 * scale * zoom, by - 3 * scale), "Follow for more", font(round(54 * scale * zoom)), pal["background"], appear)
        # The finger glides in, taps, and a ripple spreads.
        if local >= .7:
            travel = ease_out_cubic(_clamp((local - .7) / .3))
            tx = icon_x + (180 * scale) * (1 - travel)  # lands on the + icon, never over the label
            ty = by + (225 * scale) * (1 - travel) + 14 * scale
            fade = _clamp(1 - (local - 1.35) / .25)
            finger = (30 - 6 * press) * scale
            draw.ellipse((tx - finger, ty - finger + 8 * scale, tx + finger, ty + finger + 8 * scale), fill=(0, 0, 0, round(90 * fade)))
            draw.ellipse((tx - finger, ty - finger, tx + finger, ty + finger), fill=(255, 255, 255, round(235 * fade)),
                         outline=_rgb(pal["background"]) + (round(200 * fade),), width=max(1, round(3 * scale)))
            if local >= 1.0:
                ripple = ease_out_cubic(_clamp((local - 1.0) / .5))
                r = (30 + 150 * ripple) * scale
                draw.ellipse((tx - r, ty - r, tx + r, ty + r), outline=(255, 255, 255, round(200 * (1 - ripple))),
                             width=max(2, round(6 * (1 - ripple) * scale) + 1))
    # Small brand at the bottom.
    brand = _clamp((local - .6) / .3)
    if brand > 0:
        mark = round(56 * scale)
        name_face = font(round(34 * scale))
        name_w = ImageDraw.Draw(image).textlength(BRAND_NAME, font=name_face)
        start = cx - (mark + 16 * scale + name_w) / 2
        draw_brand_mark(image, (round(start + mark / 2), round(1470 * scale)), mark, pal, symbol=None)
        _text(image, (start + mark + 16 * scale + name_w / 2, 1470 * scale), BRAND_NAME, name_face, pal["text_muted"], brand)
    return image


def draw_puzzle_fit_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        return draw_puzzle_fit_intro(spec, t, size)
    rounds_end = spec.intro_duration + spec.round_count * spec.round_duration
    if t >= rounds_end:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size)
    elapsed = t - spec.intro_duration
    round_index = min(spec.round_count - 1, int(elapsed / spec.round_duration))
    return draw_puzzle_fit_round(spec, round_index, elapsed - round_index * spec.round_duration, size)


COVER_TIME = 0.6
