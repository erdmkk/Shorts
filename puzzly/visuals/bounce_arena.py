"""Bounce Arena, Puzzly for You look: a spinning neon ring, glossy lit balls, impact sparks, and an OUT shelf."""
from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
import math

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFilter

from ..config import BOUNCE_SELECTION_DURATION, PUZZLE_FIT_PALETTE as PALETTE
from ..models import VideoSpec
from ..palette import object_color
from ..puzzles.bounce_arena import GRAVITY, gap_geometry
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .puzzle_fit import _background, _text, _timer, draw_puzzle_fit_outro
from .text import fitted_font, font

HOOK_TEXT = "PICK ONE."
HOOK_SUBTITLE = "LAST BALL IN THE RING WINS."
OUTRO_QUESTION = "Did your ball win?"
OUTRO_PROMPT = "Comment your color ↓"
SHELF_Y = 1500
SHELF_SPACING = 138
SHELF_SCALE = 0.72
EXIT_FLIGHT = 1.15  # seconds from leaving the ring to resting on the OUT shelf
COVER_TIME = 1.0


def _rgb(value: str) -> tuple[int, int, int]:
    return ImageColor.getrgb(value)[:3]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------- timeline

def timeline_positions(data: dict, simulation_time: float) -> dict[int, tuple[float, float]]:
    frames = data["frames"]
    times = _frame_times(id(frames), len(frames), frames)
    index = max(0, min(len(frames) - 1, bisect_right(times, simulation_time) - 1))
    current = {int(item[0]): (float(item[1]), float(item[2])) for item in frames[index]["balls"]}
    if index == len(frames) - 1:
        return current
    following = {int(item[0]): (float(item[1]), float(item[2])) for item in frames[index + 1]["balls"]}
    span = max(1e-9, times[index + 1] - times[index])
    amount = max(0.0, min(1.0, (simulation_time - times[index]) / span))
    return {ball_id: (
        position[0] + (following.get(ball_id, position)[0] - position[0]) * amount,
        position[1] + (following.get(ball_id, position)[1] - position[1]) * amount,
    ) for ball_id, position in current.items()}


_TIMES_CACHE: dict[int, list[float]] = {}


def _frame_times(key: int, length: int, frames: list) -> list[float]:
    cached = _TIMES_CACHE.get(key)
    if cached is None or len(cached) != length:
        cached = [float(frame["time"]) for frame in frames]
        _TIMES_CACHE.clear()
        _TIMES_CACHE[key] = cached
    return cached


def winner_effect_state(celebration_time: float) -> tuple[float, float, float]:
    progress = _clamp(celebration_time / .5)
    settled = min(1.0, ease_out_back(progress))
    pulse = math.sin(max(0.0, celebration_time) * math.tau * 1.8)
    scale = 1.0 + .45 * settled + .03 * pulse * progress
    glow = _clamp(celebration_time / .28)
    return scale, glow, progress


def exit_position(event: dict, age: float, slot: int) -> tuple[tuple[float, float], float]:
    """Where an eliminated ball is `age` seconds after leaving: a real ballistic arc that eases onto the OUT shelf."""
    px, py = event["position"]
    vx, vy = event.get("velocity", (0.0, 0.0))
    t = max(0.0, age)
    ballistic = (min(1010.0, max(70.0, px + vx * t)), min(SHELF_Y + 20.0, py + vy * t + .5 * GRAVITY * t * t))  # lands on the shelf
    target = (540 + (slot - 2) * SHELF_SPACING, SHELF_Y)
    blend = ease_in_out(_clamp((t - .22) / (EXIT_FLIGHT - .22)))
    return ((ballistic[0] + (target[0] - ballistic[0]) * blend, ballistic[1] + (target[1] - ballistic[1]) * blend),
            1 + (SHELF_SCALE - 1) * blend)


# ---------------------------------------------------------------- sprites

def ball_sprite(color: str, diameter: int) -> Image.Image:
    """A ball in the active object palette (see puzzly.palette)."""
    return _ball_sprite(object_color(color), diameter)


@lru_cache(maxsize=24)
def _ball_sprite(color: str, diameter: int) -> Image.Image:
    """Glossy lit sphere with a crisp edge: lambert shading, a specular hotspot, and a thin darker rim."""
    pad = max(2, round(diameter * .22))
    side = diameter + pad * 2
    ss = 2
    n = side * ss
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    radius = diameter * ss / 2
    cx = cy = n / 2
    x, y = (xx - cx) / radius, (yy - cy) / radius
    rr = x * x + y * y
    inside = np.clip((1 - np.sqrt(rr)) * radius, 0, 1)
    z = np.sqrt(np.clip(1 - rr, 0, 1))
    light = np.array([-.45, -.62, .64], np.float32); light /= np.linalg.norm(light)
    lambert = np.clip(x * light[0] + y * light[1] + z * light[2], 0, 1)
    base = np.array(_rgb(color), np.float32)
    rgb = base * (.28 + .82 * lambert[..., None])
    half = np.array([light[0], light[1], light[2] + 1]); half /= np.linalg.norm(half)
    spec = np.clip(x * half[0] + y * half[1] + z * half[2], 0, 1) ** 60
    rgb = rgb + 255 * .95 * spec[..., None]
    edge = np.clip((np.sqrt(rr) - .93) / .07, 0, 1)  # a thin darker rim keeps the silhouette crisp
    rgb = rgb * (1 - .30 * edge[..., None])
    alpha = inside
    color_out = rgb
    image = Image.fromarray(np.dstack([np.clip(color_out, 0, 255), alpha * 255]).astype(np.uint8))
    return image.resize((side, side), Image.Resampling.LANCZOS)


def _paste_ball(image: Image.Image, center: tuple[float, float], diameter: float, color: str,
                squash: float = 0.0, normal: tuple[float, float] = (0.0, 1.0), opacity: float = 1.0) -> None:
    size = max(2, round(diameter))
    sprite = ball_sprite(color, size)
    if squash > .01:
        angle = math.degrees(math.atan2(normal[1], normal[0]))
        stretched = sprite.rotate(angle, resample=Image.Resampling.BICUBIC)
        w, h = stretched.size
        stretched = stretched.resize((max(2, round(w * (1 - squash))), max(2, round(h * (1 + squash * .6)))),
                                     Image.Resampling.BICUBIC)
        sprite = stretched.rotate(-angle, resample=Image.Resampling.BICUBIC, expand=True)
    if opacity < 1:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda value: round(value * opacity)))
    image.paste(sprite, (round(center[0] - sprite.width / 2), round(center[1] - sprite.height / 2)), sprite)


@lru_cache(maxsize=4)
def _ring_sprite(size_px: int, radius_px: float, stroke_px: float, wall_half: float, visible_half: float) -> Image.Image:
    """The ring drawn once with its gap at angle 0; frames rotate it to the live gap angle."""
    n = size_px
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    dx, dy = xx - n / 2, yy - n / 2
    rr = np.hypot(dx, dy)
    angle = np.arctan2(dy, dx)
    in_gap = np.abs(angle) < wall_half
    # Distance to the ring's centre line; inside the gap, to the nearest lip end.
    ends = [(radius_px * math.cos(sign * wall_half), radius_px * math.sin(sign * wall_half)) for sign in (-1, 1)]
    to_end = np.minimum(*[np.hypot(dx - ex, dy - ey) for ex, ey in ends])
    distance = np.where(in_gap, to_end, np.abs(rr - radius_px))
    core = np.clip(stroke_px / 2 - distance + .5, 0, 1)
    bloom = np.exp(-(distance / (stroke_px * 1.3)) ** 2) * .75
    blend = (np.cos(angle - math.pi) + 1) / 2  # cyan opposite the gap, violet near it
    cyan, violet = np.array(_rgb(PALETTE["accent"]), np.float32), np.array(_rgb(PALETTE["primary"]), np.float32)
    neon = cyan * blend[..., None] + violet * (1 - blend[..., None])
    hot = np.exp(-(np.abs(np.abs(angle) - wall_half) * radius_px / (stroke_px * 1.6)) ** 2)  # the lips glow hot pink
    neon = neon * (1 - hot[..., None]) + np.array(_rgb(PALETTE["danger"]), np.float32) * hot[..., None]
    center_line = np.clip(stroke_px * .16 - distance + .5, 0, 1)
    rgb = neon * (1 - center_line[..., None] * .75) + 255 * center_line[..., None] * .75
    alpha = np.maximum(core, bloom)
    # Rotating tick marks along the outside make the spin readable.
    ticks = ((np.abs(((angle + math.pi) / (2 * math.pi) * 60) % 1 - .5) < .07) & (rr > radius_px + stroke_px * .75)
             & (rr < radius_px + stroke_px * 1.6) & ~in_gap)
    alpha = np.maximum(alpha, ticks * .55)
    rgb = np.where(ticks[..., None] & (core[..., None] < .5), cyan * .9, rgb)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), np.clip(alpha, 0, 1) * 255]).astype(np.uint8))


@lru_cache(maxsize=4)
def _floor_sprite(size_px: int, radius_px: float) -> Image.Image:
    n = size_px
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    rr = np.hypot(xx - n / 2, yy - n / 2) / radius_px
    inside = np.clip((1 - rr) * radius_px, 0, 1)
    top, edge = np.array(_rgb("#141B45"), np.float32), np.array(_rgb("#070A1C"), np.float32)
    rgb = top * (1 - rr[..., None] ** 1.6) + edge * rr[..., None] ** 1.6
    rings = (np.abs((rr * 6) % 1 - .5) > .485) * .06
    rgb = rgb + 255 * rings[..., None]
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), inside * 245]).astype(np.uint8))


@lru_cache(maxsize=512)
def _glow_sprite(radius: int, color: str, alpha: int) -> Image.Image:
    size = radius * 4
    sprite = Image.new("RGBA", (size, size), _rgb(color) + (0,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((radius, radius, size - radius, size - radius), fill=alpha)
    sprite.putalpha(mask.filter(ImageFilter.GaussianBlur(radius * .45)))
    return sprite


def _glow(image: Image.Image, center: tuple[float, float], radius: float, color: str, alpha: int) -> None:
    # Radius and alpha are quantized so the blurred sprites are reused across frames.
    sprite = _glow_sprite(max(2, 2 * round(radius / 2)), color, max(0, min(255, 8 * round(alpha / 8))))
    image.paste(sprite, (round(center[0] - sprite.width / 2), round(center[1] - sprite.height / 2)), sprite)


# ---------------------------------------------------------------- scene pieces

def _draw_ring(image: Image.Image, data: dict, simulation_time: float, scale: float) -> None:
    arena = data["arena"]
    geometry = gap_geometry(arena, simulation_time)
    radius = float(arena["radius"]) * scale
    stroke = float(arena["wall_stroke_width"]) * scale
    size = int(math.ceil((radius + stroke * 3) * 2))
    sprite = _ring_sprite(size, radius, stroke, geometry["wall_half_angle"], geometry["visible_open_half_angle"])
    rotated = sprite.rotate(-math.degrees(geometry["angle"]), resample=Image.Resampling.BILINEAR)
    cx, cy = arena["center"][0] * scale, arena["center"][1] * scale
    image.paste(rotated, (round(cx - size / 2), round(cy - size / 2)), rotated)


def _draw_shelf(image: Image.Image, scale: float, opacity: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    x1, x2 = (540 - 2.5 * SHELF_SPACING) * scale, (540 + 2.5 * SHELF_SPACING) * scale
    y1, y2 = (SHELF_Y - 62) * scale, (SHELF_Y + 62) * scale
    draw.rounded_rectangle((x1, y1, x2, y2), radius=round(40 * scale), fill=_rgb(PALETTE["surface"]) + (round(200 * opacity),),
                           outline=_rgb(PALETTE["surface_edge"]) + (round(255 * opacity),), width=max(1, round(3 * scale)))
    for slot in range(5):
        x = (540 + (slot - 2) * SHELF_SPACING) * scale
        r = 30 * scale
        draw.ellipse((x - r, SHELF_Y * scale - r, x + r, SHELF_Y * scale + r), outline=_rgb(PALETTE["surface_edge"]) + (round(200 * opacity),),
                     width=max(1, round(3 * scale)))
    _text(image, (540 * scale, (SHELF_Y + 96) * scale), "OUT", font(round(30 * scale)), PALETTE["text_muted"], opacity)


def _draw_crown(image: Image.Image, center: tuple[float, float], radius: float, progress: float) -> None:
    if progress <= .15:
        return
    lift = ease_out_back(_clamp((progress - .15) / .6))
    x, y = center
    y -= radius * (1.25 + .35 * lift)
    w, h = radius * .9, radius * .62
    points = ((x - w, y + h * .5), (x - w, y - h * .45), (x - w * .45, y + h * .02), (x, y - h * .7),
              (x + w * .45, y + h * .02), (x + w, y - h * .45), (x + w, y + h * .5))
    _glow(image, (x, y), w * 1.2, PALETTE["warning"], round(150 * lift))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.polygon(points, fill=_rgb(PALETTE["warning"]) + (round(255 * min(1, lift)),))
    for px, py in (points[1], points[3], points[5]):
        r = radius * .1
        draw.ellipse((px - r, py - r, px + r, py + r), fill=(255, 255, 255, round(255 * min(1, lift))))


def _burst(image: Image.Image, center: tuple[float, float], color: str, age: float, scale: float, reach: float = 180) -> None:
    if age < 0 or age > .6:
        return
    progress = ease_out_cubic(age / .6)
    alpha = round(255 * (1 - progress))
    draw = ImageDraw.Draw(image, "RGBA")
    ring = (40 + reach * progress) * scale
    draw.ellipse((center[0] - ring, center[1] - ring, center[0] + ring, center[1] + ring),
                 outline=_rgb(color) + (alpha,), width=max(2, round(8 * (1 - progress) * scale) + 1))
    for index in range(16):
        angle = index / 16 * math.tau + .3
        distance = (30 + reach * 1.15 * progress) * scale
        px, py = center[0] + math.cos(angle) * distance, center[1] + math.sin(angle) * distance
        size = (10 - 7 * progress) * scale
        fill = (255, 255, 255) if index % 3 == 0 else _rgb(color)
        draw.polygon(((px, py - size), (px + size * .7, py), (px, py + size), (px - size * .7, py)), fill=fill + (alpha,))


# ---------------------------------------------------------------- frames

def _base(size: tuple[int, int]) -> Image.Image:
    return _background(size, 930)


def _scene(data: dict, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    image = _base(size).copy()
    arena = data["arena"]
    colors = data["colors"]
    diameter = float(data["ball_radius"]) * 2 * scale
    selecting = local < BOUNCE_SELECTION_DURATION
    simulation_time = 0.0 if selecting else min(float(data["simulation_duration"]), local - BOUNCE_SELECTION_DURATION)
    celebration = local - BOUNCE_SELECTION_DURATION - float(data["simulation_duration"])
    _draw_shelf(image, scale, 1.0)
    # Balls that already left fly behind the arena and drop onto the OUT shelf.
    for slot, event in enumerate(data["eliminations"]):
        age = simulation_time - float(event["time"]) + (celebration if celebration > 0 else 0)
        if age < 0:
            continue
        position, zoom = exit_position(event, age, slot)
        _paste_ball(image, (position[0] * scale, position[1] * scale), diameter * zoom, colors[event["ball_id"]])
    radius_px = float(arena["radius"]) * scale
    floor_size = int(math.ceil(radius_px * 2 + 4))
    floor = _floor_sprite(floor_size, radius_px)
    cx, cy = arena["center"][0] * scale, arena["center"][1] * scale
    image.paste(floor, (round(cx - floor_size / 2), round(cy - floor_size / 2)), floor)
    _draw_ring(image, data, simulation_time, scale)
    if selecting:
        positions = {int(item[0]): (float(item[1]), float(item[2])) for item in data["frames"][0]["balls"]}
        pop = ease_out_back(_clamp(local / .35))
        for ball_id, (x, y) in positions.items():
            bob = 6 * math.sin(local * 2.6 + ball_id * 1.1)
            _paste_ball(image, (x * scale, (y + bob) * scale), diameter * max(.05, pop), colors[ball_id])
        return image
    positions = timeline_positions(data, simulation_time)
    winner = int(data["winner"])
    for ball_id, (x, y) in positions.items():
        if celebration >= 0 and ball_id == winner:
            continue
        _paste_ball(image, (x * scale, y * scale), diameter, colors[ball_id])  # no hit effects: sound only
    if celebration >= 0 and winner in positions:
        zoom, glow, progress = winner_effect_state(celebration)
        start = positions[winner]
        glide = ease_in_out(_clamp(celebration / .55))
        x = (start[0] + (arena["center"][0] - start[0]) * glide) * scale
        y = (start[1] + (arena["center"][1] - start[1]) * glide) * scale
        _glow(image, (x, y), diameter * (1.1 + .15 * math.sin(celebration * 7)), PALETTE["warning"], round(170 * glow))
        _burst(image, (x, y), PALETTE["warning"], celebration - .35, scale, 260)
        _burst(image, (x, y), colors[winner], celebration - .6, scale, 200)
        _paste_ball(image, (x, y), diameter * zoom, colors[winner])
        _draw_crown(image, (x, y), diameter * zoom / 2, progress)
    return image


def draw_bounce_round(spec: VideoSpec, local: float, size: tuple[int, int]) -> Image.Image:
    data = spec.rounds[0].data
    scale = size[0] / 1080
    image = _scene(data, local, size)
    if local < BOUNCE_SELECTION_DURATION:
        pop = ease_out_back(_clamp(local / .3))
        _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(900 * scale), round(80 * scale)),
              PALETTE["text_light"], _clamp(local / .15), max(.5, pop))
        _timer(image, BOUNCE_SELECTION_DURATION - local, BOUNCE_SELECTION_DURATION, _clamp(local / .2), scale)
        _text(image, (540 * scale, 292 * scale), HOOK_SUBTITLE, font(round(34 * scale)), PALETTE["accent"], _clamp((local - .15) / .25))
        return image
    simulation_time = local - BOUNCE_SELECTION_DURATION
    celebration = simulation_time - float(data["simulation_duration"])
    if celebration >= 0:
        winner = int(data["winner"])
        _text(image, (540 * scale, 150 * scale), "WINNER!", fitted_font("WINNER!", round(900 * scale), round(84 * scale)),
              PALETTE["warning"], 1.0, max(.6, ease_out_back(_clamp(celebration / .35))))
        _text(image, (540 * scale, 240 * scale), f"{data.get('color_names', ['RED', 'BLUE', 'YELLOW', 'GREEN', 'PURPLE', 'ORANGE'])[winner].upper()} SURVIVES",
              font(round(40 * scale)), object_color(data["colors"][winner]), _clamp((celebration - .2) / .25))
        return image
    left = len(data["colors"]) - sum(1 for event in data["eliminations"] if float(event["time"]) <= simulation_time)
    color = PALETTE["danger"] if left <= 2 else PALETTE["text_light"]
    _text(image, (540 * scale, 150 * scale), f"{left} LEFT", fitted_font(f"{left} LEFT", round(900 * scale), round(80 * scale)), color)
    return image


def draw_bounce_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t >= spec.round_duration:
        data = spec.rounds[0].data
        return draw_puzzle_fit_outro(spec, t - spec.round_duration, size, OUTRO_QUESTION, OUTRO_PROMPT,
                                     hero=lambda pixels: ball_sprite(data["colors"][int(data["winner"])], pixels))
    return draw_bounce_round(spec, t, size)
