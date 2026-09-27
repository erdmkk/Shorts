"""Lucky Pick snake chase, Puzzly for You look: a neon arena, seven fleeing targets, and a light-tube snake.

The snake has no face: a glowing tube with a bright head. Every target it swallows travels down its body as a bulge
and stays as a band of that colour near the tail, so the body keeps score.
"""
from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..config import LUCKY_APPEARANCE_DURATION, LUCKY_SELECTION_DURATION, PUZZLE_FIT_PALETTE as PALETTE
from ..models import RoundSpec, VideoSpec
from ..palette import object_color
from ..puzzles.lucky_snake import ARENA_CENTER, ARENA_RADIUS, ENTRY, SNAKE_HEAD_RADIUS, TARGET_SIZE, release_time
from .easing import ease_in_out, ease_out_back
from .memory import token_image
from .puzzle_fit import _background, _text, _timer, active_theme, draw_puzzle_fit_outro
from .text import font

SNAKE_CORE, SNAKE_EDGE, SNAKE_GLOW = "#EAF6FF", "#6E8FB5", "#2EE6C5"
SWALLOW = 0.8  # seconds for a swallowed target to travel down the body as a bulge
GULP = 0.18  # the target shrinks into the head this fast
RING_FADE = 0.3
EMERGE = 0.45  # the snake rises out of its portal
DEN_FADE = 0.4  # ... and the portal then fades away


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _mix(a: tuple, b: tuple, t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


# ---------------------------------------------------------------- arena (static per theme)

@lru_cache(maxsize=6)
def _arena(size: tuple[int, int], theme: str) -> Image.Image:
    """A dark circular floor with a faint grid and a neon rim (violet at the top, cyan at the bottom) with bloom."""
    scale = size[0] / 1080
    base = np.asarray(_background(size, 900, theme), dtype=np.float32)
    height, width = size[1], size[0]
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    cx, cy, radius = ARENA_CENTER[0] * scale, ARENA_CENTER[1] * scale, ARENA_RADIUS * scale
    d = np.hypot(x - cx, y - cy)
    inside = np.clip((radius - d) / (1.5 * scale) + .5, 0, 1)[..., None]
    floor = np.array(_rgb("#0A0D24"), np.float32) * (1 - .45 * np.clip(d / radius, 0, 1) ** 2)[..., None]
    grid = (((x - cx) % (48 * scale)) < 1.6 * scale) | (((y - cy) % (48 * scale)) < 1.6 * scale)
    floor += grid[..., None] * 9.0 * (1 - np.clip(d / radius, 0, 1))[..., None]
    image = base * (1 - inside) + floor * inside
    band = np.clip(1 - np.abs(d - radius) / (5 * scale), 0, 1)
    bloom = np.exp(-((d - radius) / (22 * scale)) ** 2)
    rows = np.clip((y - (cy - radius)) / (2 * radius), 0, 1)[..., None]
    neon = np.array(_rgb(PALETTE["accent"]), np.float32) * rows + np.array(_rgb(PALETTE["primary"]), np.float32) * (1 - rows)
    image += neon * (bloom * .45)[..., None]
    image = image * (1 - band[..., None]) + (neon * .8 + 255 * .2) * band[..., None]
    return Image.fromarray(np.clip(image, 0, 255).astype(np.uint8))


def den_opacity(s: float) -> float:
    """The den marks where the snake will appear; it fades away once the snake is fully out."""
    return 1.0 if s < EMERGE else round(1 - _clamp((s - EMERGE) / DEN_FADE), 6)


def _portal(image: Image.Image, scale: float, strength: float, local: float, opacity: float = 1.0) -> None:
    """The snake's den on the bottom of the rim."""
    if opacity <= 0:
        return
    x, y = ENTRY[0] * scale, (ENTRY[1] + 8) * scale
    _glow(image, (x, y), (40 + 16 * strength) * scale, SNAKE_GLOW, round((90 + 130 * strength) * opacity))
    draw = ImageDraw.Draw(image, "RGBA")
    for index, radius in enumerate((38, 26)):
        r = radius * scale
        start = (local * (110 if index == 0 else -160)) % 360
        for arc in range(3):
            draw.arc((x - r, y - r, x + r, y + r), start + arc * 120, start + arc * 120 + 70,
                     fill=_rgb(SNAKE_GLOW if index == 0 else PALETTE["primary"]) + (round(200 * opacity),), width=max(2, round(4 * scale)))


@lru_cache(maxsize=64)
def _glow_sprite(radius: int, color: str, alpha: int) -> Image.Image:
    side = radius * 4
    sprite = Image.new("RGBA", (side, side), _rgb(color) + (0,))
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).ellipse((radius, radius, side - radius, side - radius), fill=alpha)
    sprite.putalpha(mask.filter(ImageFilter.GaussianBlur(radius * .45)))
    return sprite


def _glow(image: Image.Image, center: tuple[float, float], radius: float, color: str, alpha: int) -> None:
    sprite = _glow_sprite(max(2, round(radius)), color, max(0, min(255, alpha)))
    image.paste(sprite, (round(center[0] - sprite.width / 2), round(center[1] - sprite.height / 2)), sprite)


# ---------------------------------------------------------------- the recorded chase

class Chase:
    """Interpolates the recorded simulation: head path (with cumulative distance for the body) and target positions."""

    def __init__(self, data: dict) -> None:
        self.frames = data["frames"]
        self.times = [frame[0] for frame in self.frames]
        head = np.array([[frame[1], frame[2]] for frame in self.frames], dtype=np.float64)
        steps = np.hypot(*np.diff(head, axis=0).T) if len(head) > 1 else np.zeros(0)
        self.head = head
        self.distance = np.concatenate([[0.0], np.cumsum(steps)])
        self.catches = {event["target_index"]: event for event in data["catches"]}
        self.duration = float(data["simulation_duration"])

    def _index(self, s: float) -> tuple[int, float]:
        s = max(0.0, min(self.duration, s))
        index = max(0, min(len(self.times) - 2, bisect_right(self.times, s) - 1))
        span = self.times[index + 1] - self.times[index] if len(self.times) > 1 else 1
        return index, _clamp((s - self.times[index]) / span) if span > 0 else 0.0

    def head_at(self, s: float) -> tuple[float, float, float, float]:
        """Head x, y, heading, and distance travelled so far."""
        if len(self.frames) == 1:
            frame = self.frames[0]
            return frame[1], frame[2], frame[3], 0.0
        index, u = self._index(s)
        a, b = self.frames[index], self.frames[index + 1]
        turn = (b[3] - a[3] + math.pi) % (2 * math.pi) - math.pi
        return (a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u, a[3] + turn * u,
                float(self.distance[index] + (self.distance[index + 1] - self.distance[index]) * u))

    def length_at(self, s: float) -> float:
        index, _ = self._index(s)
        return float(self.frames[index][4])

    def body(self, s: float, spacing: float = 5.0) -> list[tuple[float, float]]:
        """Points from the head back along its path, `spacing` px apart, as long as the snake (it grows as it emerges)."""
        x, y, _, travelled = self.head_at(s)
        length = min(self.length_at(s), travelled)
        points = [(x, y)]
        for k in range(1, int(length / spacing) + 1):
            back = travelled - k * spacing
            index = max(0, min(len(self.distance) - 2, int(np.searchsorted(self.distance, back)) - 1))
            span = self.distance[index + 1] - self.distance[index]
            u = _clamp((back - self.distance[index]) / span) if span > 0 else 0.0
            points.append(tuple(self.head[index] + (self.head[index + 1] - self.head[index]) * u))
        return points

    def targets_at(self, s: float) -> dict[int, tuple[float, float]]:
        index, u = self._index(s)
        a = {record[0]: (record[1], record[2]) for record in self.frames[index][5]}
        b = {record[0]: (record[1], record[2]) for record in self.frames[min(len(self.frames) - 1, index + 1)][5]}
        return {key: (value[0] + (b[key][0] - value[0]) * u, value[1] + (b[key][1] - value[1]) * u) if key in b else value
                for key, value in a.items()}


_CHASES: dict[str, Chase] = {}


def chase_for(spec: VideoSpec) -> Chase:
    key = f"{spec.id}:{spec.rounds[0].fingerprint()}"
    if key not in _CHASES:
        _CHASES.clear()
        _CHASES[key] = Chase(spec.rounds[0].data)
    return _CHASES[key]


# ---------------------------------------------------------------- snake

def draw_snake(image: Image.Image, points: list[tuple[float, float]], scale: float, bands: list[tuple[float, str]],
               bulges: list[float], head_pulse: float = 0.0, glow: float = 1.0) -> None:
    """A lit light-tube: bloom, a dark edge, a bright core, and a highlight; tapered from head to tail.

    bands: (distance from the head in px, colour) of swallowed targets; bulges: distances of bulges moving down.
    """
    if len(points) < 2:
        return
    count = len(points)
    head_radius = SNAKE_HEAD_RADIUS * 1.12 * (1 + .22 * head_pulse)

    def radius(index: int) -> float:
        taper = 1 - .55 * (index / max(1, count - 1)) ** 1.3
        swell = sum(.45 * math.exp(-((index * 5 - bulge) / 22) ** 2) for bulge in bulges)
        return (SNAKE_HEAD_RADIUS * .92 * taper) * (1 + swell)

    scaled = [(x * scale, y * scale) for x, y in points]
    # Bloom at quarter resolution.
    xs, ys = [p[0] for p in scaled], [p[1] for p in scaled]
    pad = 150 * scale  # wider than the bloom's reach, so it never ends in a hard box edge
    left, top = int(min(xs) - pad), int(min(ys) - pad)
    box = (max(1, int(max(xs) + pad) - left), max(1, int(max(ys) + pad) - top))
    quarter = (max(1, box[0] // 4), max(1, box[1] // 4))
    bloom = Image.new("L", quarter, 0)
    bloom_draw = ImageDraw.Draw(bloom)
    for index in range(count - 1, -1, -1):
        r = radius(index) * scale * 1.5 / 4
        px, py = (scaled[index][0] - left) / 4, (scaled[index][1] - top) / 4
        bloom_draw.ellipse((px - r, py - r, px + r, py + r), fill=255)
    bloom = bloom.filter(ImageFilter.GaussianBlur(max(1.0, 7 * scale))).resize(box, Image.Resampling.BILINEAR)
    image.paste(Image.new("RGB", box, SNAKE_GLOW), (left, top), bloom.point(lambda v: round(v * .55 * glow)))
    draw = ImageDraw.Draw(image, "RGBA")
    band_color = {}
    for distance, color in bands:
        for index in range(max(0, int((distance - 9) / 5)), min(count, int((distance + 9) / 5) + 1)):
            band_color[index] = _rgb(color)
    edge, core = _rgb(SNAKE_EDGE), _rgb(SNAKE_CORE)
    for layer in range(3):  # edge, core, highlight: tail first so the head sits on top
        for index in range(count - 1, 0, -1):
            x, y = scaled[index]
            r = radius(index) * scale
            if layer == 0:
                fill = _mix(band_color[index], (0, 0, 0), .45) if index in band_color else edge
                draw.ellipse((x - r, y - r, x + r, y + r), fill=fill + (255,))
            elif layer == 1:
                fill = band_color.get(index, core)
                rr = r * .78
                draw.ellipse((x - rr, y - rr, x + rr, y + rr), fill=fill + (255,))
            else:
                rr = r * .28
                draw.ellipse((x - r * .28 - rr, y - r * .32 - rr, x - r * .28 + rr, y - r * .32 + rr), fill=(255, 255, 255, 150))
    # Head: a slightly larger lit bead with a bright tip in its direction of travel.
    hx, hy = scaled[0]
    nx, ny = points[0][0] - points[1][0], points[0][1] - points[1][1]
    length = math.hypot(nx, ny) or 1
    nx, ny = nx / length, ny / length
    r = head_radius * scale
    draw.ellipse((hx - r, hy - r, hx + r, hy + r), fill=edge + (255,))
    draw.ellipse((hx - r * .8, hy - r * .8, hx + r * .8, hy + r * .8), fill=core + (255,))
    tx, ty = hx + nx * r * .45, hy + ny * r * .45
    _glow(image, (tx, ty), r * .9, "#FFFFFF", round(160 + 90 * head_pulse))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((hx - r * .5, hy - r * .55, hx - r * .1, hy - r * .2), fill=(255, 255, 255, 170))


# ---------------------------------------------------------------- frame

def _target(image: Image.Image, target: dict, center: tuple[float, float], scale: float, zoom: float = 1.0,
            glow: float = .55, rotation: float = 0.0) -> None:
    size = max(2, round(TARGET_SIZE * scale * zoom))
    if glow > 0:
        _glow(image, center, size * .62, object_color(target["color_value"]), round(150 * glow))
    sprite = token_image(target["shape_id"], target["color_value"], size)
    if rotation:
        sprite = sprite.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)
    image.paste(sprite, (round(center[0] - sprite.width / 2), round(center[1] - sprite.height / 2)), sprite)


def _burst(image: Image.Image, center: tuple[float, float], color: str, age: float, scale: float, count: int = 14,
           reach: float = 120) -> None:
    from .lucky_pick import _burst as burst
    burst(image, center, color, age, scale, count, reach)


def pick_ring_alpha(s: float) -> float:
    """Pick rings show only while the viewer chooses (s < 0), then fade out as the chase starts."""
    return 1.0 if s < 0 else round(1 - _clamp(s / RING_FADE), 6)


def draw_scene(image: Image.Image, item: RoundSpec, chase: Chase, local: float, scale: float, intro_pop: float = 1.0) -> dict:
    """Arena contents at round-local time `local`. Returns which targets are gone (for the header)."""
    data = item.data
    targets = data["targets"]
    start = release_time()
    s = local - start
    chasing = s >= 0
    winner = data["winner_index"]
    eaten = {index for index, event in chase.catches.items() if chasing and s >= event["time"]}
    _portal(image, scale, (1 - _clamp(s / EMERGE)) if chasing else .35 + .35 * math.sin(local * 5), local, den_opacity(s))
    ring_alpha = pick_ring_alpha(s)
    positions = chase.targets_at(s) if chasing else {target["index"]: tuple(target["position"]) for target in targets}
    head = chase.head_at(s)[:2] if chasing else None
    if ring_alpha > 0:
        draw = ImageDraw.Draw(image, "RGBA")
        for target in targets:
            if target["index"] in positions:
                x, y = positions[target["index"]][0] * scale, positions[target["index"]][1] * scale
                ring = 58 * scale
                pulse = .5 + .5 * math.sin(local * 3.2 + target["index"])
                draw.ellipse((x - ring, y - ring, x + ring, y + ring), outline=_rgb(object_color(target["color_value"])) + (round((120 + 70 * pulse) * ring_alpha),),
                             width=max(2, round(4 * scale)))
    # Targets: a panicked shiver and brighter glow when the head is close.
    gulping = []
    for target in targets:
        index = target["index"]
        event = chase.catches.get(index)
        if event is not None and chasing and s >= event["time"]:
            age = s - event["time"]
            if age < GULP:
                gulping.append((target, event, age))
            continue
        if index not in positions:
            continue
        x, y = positions[index]
        zoom, glow = (ease_out_back(intro_pop) if intro_pop < 1 else 1.0), .55
        if not chasing:
            y += 5 * math.sin(local * 2.4 + index * .9)  # idle bob while the viewer picks
        elif head is not None:
            danger = _clamp(1 - math.dist((x, y), head) / 220)
            x += math.sin(local * 55 + index) * 3 * danger
            glow = .55 + .6 * danger
            # Fleeing fast: fading afterimages behind it.
            for step in (3, 2, 1):
                earlier = chase.targets_at(s - .045 * step).get(index)
                if earlier and math.dist(earlier, (x, y)) > 14:
                    ghost = token_image(target["shape_id"], target["color_value"], max(2, round(TARGET_SIZE * scale * (1 - .08 * step))))
                    ghost.putalpha(ghost.getchannel("A").point(lambda v, k=step: v * (4 - k) // 9))
                    image.paste(ghost, (round(earlier[0] * scale - ghost.width / 2), round(earlier[1] * scale - ghost.height / 2)), ghost)
        if index == winner and chasing and s >= chase.duration:
            age = s - chase.duration
            zoom = 1 + .45 * ease_out_back(_clamp(age / .45))
            glow = 1.0 + .3 * math.sin(age * 8)
            _glow(image, (x * scale, y * scale), 120 * scale, PALETTE["warning"], round(120 * _clamp(age / .3)))
        _target(image, target, (x * scale, y * scale), scale, zoom, glow)
    # The snake.
    if chasing:
        points = chase.body(s)
        emerge = _clamp(s / EMERGE)
        swallowed = sorted((event["time"], object_color(data["targets"][index]["color_value"])) for index, event in chase.catches.items()
                           if s >= event["time"])
        length = len(points) * 5
        bands, bulges = [], []
        for number, (time_value, color) in enumerate(swallowed):
            final = max(20.0, length - 34 - 24 * number)  # bands stack up from the tail
            travel = _clamp((s - time_value) / SWALLOW)
            position = final * ease_in_out(travel)
            if travel < 1:
                bulges.append(position)
            bands.append((position, color))
        pulse = max([1 - (s - event["time"]) / .25 for event in chase.catches.values() if 0 <= s - event["time"] < .25] or [0.0])
        draw_snake(image, points, scale, bands, bulges, pulse, emerge)
    # A swallowed target shrinks and spins into the head, over a burst in its colour.
    for target, event, age in gulping:
        u = ease_in_out(age / GULP)
        ex, ey = event["position"]
        hx, hy = chase.head_at(event["time"] + age)[:2]
        _target(image, target, ((ex + (hx - ex) * u) * scale, (ey + (hy - ey) * u) * scale), scale, 1 - .85 * u, .55 * (1 - u), 200 * u)
    for index, event in chase.catches.items():
        if chasing and 0 <= s - event["time"] < .5:
            _burst(image, (event["position"][0] * scale, event["position"][1] * scale), object_color(data["targets"][index]["color_value"]),
                   s - event["time"], scale)
    if chasing and s >= chase.duration:
        target = data["targets"][winner]
        center = positions.get(winner, tuple(target["position"]))
        _burst(image, (center[0] * scale, center[1] * scale), PALETTE["warning"], s - chase.duration - .1, scale, 18, 190)
        _burst(image, (center[0] * scale, center[1] * scale), PALETTE["success"], s - chase.duration - .45, scale, 12, 150)
    return {"eaten": eaten}


def draw_snake_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook: the real targets in the empty arena under PICK ONE. The snake stays hidden in its den."""
    from .lucky_pick import HOOK_SUBTITLE, HOOK_TEXT, _header
    scale = size[0] / 1080
    item = spec.rounds[0]
    image = _arena(size, active_theme()).copy()
    draw_scene(image, item, chase_for(spec), t, scale, intro_pop=_clamp(t / .35))  # the intro ends long before the release
    pop = ease_out_back(_clamp(t / .3))
    _header(image, HOOK_TEXT, PALETTE["text_light"], scale, _clamp(t / .15), max(.5, pop))
    _text(image, (540 * scale, 250 * scale), HOOK_SUBTITLE, font(round(42 * scale)), PALETTE["accent"], _clamp((t - .2) / .25))
    return image


def draw_snake_round(spec: VideoSpec, local: float, size: tuple[int, int]) -> Image.Image:
    from .lucky_pick import HOOK_SUBTITLE, HOOK_TEXT, _header, _progress_dots
    scale = size[0] / 1080
    item = spec.rounds[0]
    chase = chase_for(spec)
    image = _arena(size, active_theme()).copy()
    state = draw_scene(image, item, chase, local, scale, intro_pop=_clamp(local / LUCKY_APPEARANCE_DURATION) if local < LUCKY_APPEARANCE_DURATION else 1.0)
    s = local - release_time()
    eaten = state["eaten"]
    if s < 0:
        _header(image, HOOK_TEXT, PALETTE["text_light"], scale)
        _timer(image, release_time() - local, LUCKY_SELECTION_DURATION, 1.0, scale)
        _text(image, (540 * scale, 290 * scale), HOOK_SUBTITLE, font(round(32 * scale)), PALETTE["text_muted"])
    elif s >= chase.duration:
        age = s - chase.duration
        _header(image, "SURVIVOR!", PALETTE["warning"], scale, 1.0, max(.6, ease_out_back(_clamp(age / .35))))
        _progress_dots(image, item, eaten, _clamp(age / .4), scale)
    else:
        left = len(item.data["targets"]) - len(eaten)
        _header(image, f"{left} LEFT", PALETTE["danger"] if left <= 3 else PALETTE["text_light"], scale)
        _progress_dots(image, item, eaten, 0.0, scale)
    return image


def draw_snake_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    from .lucky_pick import OUTRO_PROMPT, OUTRO_QUESTION
    if t < spec.intro_duration:
        return draw_snake_intro(spec, t, size)
    end = spec.intro_duration + spec.round_duration
    if t >= end:
        winner = spec.rounds[0].data["targets"][spec.rounds[0].data["winner_index"]]
        return draw_puzzle_fit_outro(spec, t - end, size, OUTRO_QUESTION, OUTRO_PROMPT,
                                     hero=lambda pixels: token_image(winner["shape_id"], winner["color_value"], pixels))
    return draw_snake_round(spec, t - spec.intro_duration, size)
