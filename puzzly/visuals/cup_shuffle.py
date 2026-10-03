"""Cup Shuffle frames (Puzzly for You look): glossy 3D-shaded cups on a lamp-lit wood table, a gold ball, and swaps in which
one cup arcs in front while the other passes behind.

Level timeline (`phases`): the cups drop in, the ball's cup lifts to show the ball, stays up, comes down, the cups swap
(speed from the level's own data), a numeric timer runs while the viewer decides, then the right cup lifts, the ball
shows, a green burst and a hold. Numbered badges under the five positions let viewers comment a cup number.
"""
from __future__ import annotations

from functools import lru_cache
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..config import (CUP_ANSWER, CUP_ENTRANCE, CUP_HOLD, CUP_LIFT, CUP_LOWER, CUP_REVEAL, CUP_SHOW, PUZZLE_FIT_PALETTE as PALETTE,
                      cup_round)
from ..models import RoundSpec, VideoSpec
from ..puzzles.cup_shuffle import states
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .puzzle_fit import _level_header, _snap_burst, _text, _timer, active_theme, draw_puzzle_fit_outro
from .surfaces import table
from .text import fitted_font, font

PROMPT_WATCH = "WATCH THE BALL."
PROMPT_GUESS = "WHERE IS THE BALL?"
COMMENT = "Comment the cup number ↓"
HOOK_TEXT = "FOLLOW THE BALL."
BASE_Y = 1040.0  # where the cups stand on the table (logical 1080x1920)
BADGE_Y = BASE_Y + 158
PROMPT_Y = 520.0
COMMENT_Y = 1400.0
MAT = (50, 590, 1030, 1310)  # the felt mat the cups stand on
LIFT_HEIGHTS = .62  # a lifted cup rises this many cup heights: just enough to show the ball
COVER_TIME = 0.6
CUP_HEX = {"coral": "#FF5F6D", "violet": "#7C5CFF", "teal": "#1FC8B0", "blue": "#3DA9FF"}
BALL_HEX = "#FFD23F"
OUTLINE = (11, 16, 32)


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------- timing

def phases(item: RoundSpec) -> dict[str, float]:
    data = item.data
    lift_end = CUP_ENTRANCE + CUP_LIFT
    show_end = lift_end + CUP_SHOW
    shuffle_start = show_end + CUP_LOWER
    shuffle_end = shuffle_start + len(data["swaps"]) * float(data["swap_seconds"])
    think_end = shuffle_end + float(data["thinking_seconds"])
    reveal_end = think_end + CUP_REVEAL
    return {"lift_end": lift_end, "show_end": show_end, "shuffle_start": shuffle_start, "shuffle_end": shuffle_end,
            "think_end": think_end, "reveal_end": reveal_end, "answer_end": reveal_end + CUP_ANSWER,
            "hold_end": reveal_end + CUP_ANSWER + CUP_HOLD}


def schedule(spec: VideoSpec) -> list[tuple[float, float]]:
    """(start, duration) of every level; later levels shuffle more and faster."""
    result, start = [], spec.intro_duration
    for item in spec.rounds:
        duration = cup_round(item.data)
        result.append((start, duration))
        start += duration
    return result


def layout(cups: int) -> tuple[list[float], float]:
    """x of every position and the cup width (logical px); five cups still fit inside x 110-970."""
    spacing = min(330.0, 960.0 / cups)
    return [540 + (index - (cups - 1) / 2) * spacing for index in range(cups)], min(260.0, spacing * .78)


# ---------------------------------------------------------------- sprites

SPRITE = 2  # the sprites are painted at 2x and shrunk once
R_BOTTOM, R_TOP, HEIGHT, RY_BOTTOM, RY_TOP, PAD = 400, 272, 760, 96, 68, 40  # cup geometry at 2x, bottom width 800


@lru_cache(maxsize=16)
def _cup(color: str, palette: str | None) -> tuple[Image.Image, tuple[float, float]]:
    """An upside-down cup: cylindrical shading lit from the left, a highlight stripe, a light band and a lip.

    Returns the RGBA sprite (bottom ellipse centre at the returned anchor) at 1x (bottom width 400 px)."""
    from ..palette import recolor
    base = np.array(_rgb(recolor(CUP_HEX[color], palette)), np.float32)
    width, height = 2 * (R_BOTTOM + PAD), HEIGHT + RY_TOP + RY_BOTTOM + 2 * PAD
    cx, cy_b = width / 2, height - PAD - RY_BOTTOM
    cy_t = cy_b - HEIGHT
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    t = np.clip((y - cy_t) / HEIGHT, 0, 1)  # 0 at the top ellipse centre, 1 at the bottom one
    radius = R_TOP + (R_BOTTOM - R_TOP) * t
    u = np.clip((x - cx) / radius, -1, 1)
    normal_z = np.sqrt(1 - u * u)
    diffuse = np.clip(-.55 * u + .83 * normal_z, 0, 1)
    light = .40 + .78 * diffuse - .18 * t ** 3  # darker toward the lip
    spec = np.exp(-((u + .46) / .075) ** 2) * (.62 - .25 * t) + np.exp(-((u + .30) / .22) ** 2) * .10
    rgb = base[None, None, :] * light[..., None] + 255 * spec[..., None]
    # A light band around the cup and a slightly darker lip at the bottom.
    groove = np.exp(-((t - .585) / .013) ** 2)  # an embossed rib: a dark groove with a light edge below it
    edge = np.exp(-((t - .615) / .011) ** 2)
    rgb = rgb * (1 - .30 * groove[..., None]) + 255 * .16 * edge[..., None] * light[..., None]
    lip = np.clip((t - .90) / .10, 0, 1)
    rgb = rgb * (1 - .26 * lip[..., None])
    body = np.zeros((height, width), np.uint8)
    mask = Image.fromarray(body)
    draw = ImageDraw.Draw(mask)
    draw.polygon(((cx - R_TOP, cy_t), (cx + R_TOP, cy_t), (cx + R_BOTTOM, cy_b), (cx - R_BOTTOM, cy_b)), fill=255)
    draw.ellipse((cx - R_BOTTOM, cy_b - RY_BOTTOM, cx + R_BOTTOM, cy_b + RY_BOTTOM), fill=255)
    draw.ellipse((cx - R_TOP, cy_t - RY_TOP, cx + R_TOP, cy_t + RY_TOP), fill=255)
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).convert("RGBA")
    image.putalpha(mask)
    d = ImageDraw.Draw(image)
    # The flat top: a lighter disc with a soft inner ring.
    top = tuple(np.clip(base * 1.16 + 34, 0, 255).astype(int))
    d.ellipse((cx - R_TOP, cy_t - RY_TOP, cx + R_TOP, cy_t + RY_TOP), fill=top + (255,))
    ring = tuple(np.clip(base * .78, 0, 255).astype(int))
    d.ellipse((cx - R_TOP * .84, cy_t - RY_TOP * .82, cx + R_TOP * .84, cy_t + RY_TOP * .82), outline=ring + (255,), width=6)
    # A bright arc along the lip and a dark edge around the whole silhouette.
    d.arc((cx - R_BOTTOM + 4, cy_b - RY_BOTTOM + 4, cx + R_BOTTOM - 4, cy_b + RY_BOTTOM - 4), 8, 172, fill=(255, 255, 255, 120), width=7)
    edge = mask.filter(ImageFilter.MaxFilter(7))
    outline = Image.new("RGBA", image.size, OUTLINE + (0,))
    outline.putalpha(Image.fromarray(np.clip(np.asarray(edge, np.int16) - np.asarray(mask, np.int16), 0, 255).astype(np.uint8)))
    outline.alpha_composite(image)
    small = outline.resize((width // SPRITE, height // SPRITE), Image.Resampling.LANCZOS)
    return small, (cx / SPRITE, cy_b / SPRITE)


def cup_sprite(color: str, px: int) -> Image.Image:
    """The cup at `px` pixels of bottom width (cover floaters and previews)."""
    from ..palette import active
    sprite, _ = _cup(color, active())
    factor = px / (2 * R_BOTTOM / SPRITE)
    return sprite.resize((max(2, round(sprite.width * factor)), max(2, round(sprite.height * factor))), Image.Resampling.LANCZOS)


@lru_cache(maxsize=4)
def _ball() -> Image.Image:
    """A glossy gold ball (200 px), lit from the upper left."""
    size = 400
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    nx, ny = (x - size / 2) / (size / 2), (y - size / 2) / (size / 2)
    inside = nx * nx + ny * ny <= 1
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
    diffuse = np.clip(-.45 * nx - .55 * ny + .70 * nz, 0, 1)
    spec = np.exp(-(((nx + .38) ** 2 + (ny + .42) ** 2) / .012))
    base = np.array(_rgb(BALL_HEX), np.float32)
    rgb = base[None, None, :] * (.38 + .82 * diffuse[..., None]) + 255 * spec[..., None] * .95
    rim = np.clip((np.hypot(nx, ny) - .86) / .14, 0, 1)
    rgb = rgb * (1 - .45 * rim[..., None])
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).convert("RGBA")
    image.putalpha(Image.fromarray((inside * 255).astype(np.uint8)))
    return image.resize((size // 2, size // 2), Image.Resampling.LANCZOS)


def ball_sprite(px: int) -> Image.Image:
    sprite = _ball()
    return sprite.resize((max(2, px), max(2, px)), Image.Resampling.LANCZOS)


@lru_cache(maxsize=2)
def _shadow() -> Image.Image:
    """A soft contact shadow (its ellipse is 420 px wide), drawn once and scaled per cup."""
    width, height = 600, 220
    layer = Image.new("L", (width, height), 0)
    ImageDraw.Draw(layer).ellipse((90, 60, width - 90, height - 60), fill=190)
    layer = layer.filter(ImageFilter.GaussianBlur(26))
    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    shadow.putalpha(layer)
    return shadow


def _paste(image: Image.Image, sprite: Image.Image, anchor: tuple[float, float], point: tuple[float, float], factor: float,
           opacity: float = 1.0) -> None:
    """Paste `sprite` scaled by `factor` so that its `anchor` lands on `point`."""
    if factor <= 0 or opacity <= 0:
        return
    size = (max(1, round(sprite.width * factor)), max(1, round(sprite.height * factor)))
    scaled = sprite.resize(size, Image.Resampling.LANCZOS) if size != sprite.size else sprite
    if opacity < 1:
        scaled = scaled.copy()
        scaled.putalpha(scaled.getchannel("A").point(lambda value: round(value * opacity)))
    image.alpha_composite(scaled, (round(point[0] - anchor[0] * factor), round(point[1] - anchor[1] * factor)))


# ---------------------------------------------------------------- the table

@lru_cache(maxsize=4)
def _table(size: tuple[int, int], theme: str) -> Image.Image:
    """Wood table under a lamp, with a felt mat the cups stand on (both take the video's background tone)."""
    image = table(size, theme, "wood", (540, BASE_Y - 60)).convert("RGBA")
    scale = size[0] / 1080
    box = tuple(value * scale for value in MAT)
    radius = 70 * scale
    shadow = Image.new("L", size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((box[0], box[1] + 14 * scale, box[2], box[3] + 28 * scale), radius=radius, fill=190)
    image.paste((0, 0, 0), (0, 0), shadow.filter(ImageFilter.GaussianBlur(max(1, 24 * scale))))
    felt = table(size, theme, "felt", (540, BASE_Y - 40)).convert("RGBA")
    boost = felt.point(lambda value: min(255, round(value * 1.12)))  # a touch brighter than the dark table around it
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
    image.paste(boost, (0, 0), mask)
    draw = ImageDraw.Draw(image, "RGBA")
    inset = 22 * scale
    draw.rounded_rectangle((box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset), radius=radius - inset,
                           outline=_rgb(PALETTE["warning"]) + (150,), width=max(1, round(3 * scale)))
    draw.rounded_rectangle(box, radius=radius, outline=_rgb(PALETTE["surface_edge"]) + (255,), width=max(2, round(5 * scale)))
    return image


# ---------------------------------------------------------------- motion

def cup_poses(data: dict, local: float) -> list[dict]:
    """Where every cup is at `local`: x, table y, scale, lift (0..1, in cup heights), and the position it stands at."""
    cups = data["cups"]
    xs, _ = layout(cups)
    order = states(cups, data["swaps"])
    seconds = float(data["swap_seconds"])
    times = phases(RoundSpec(0, "cup_shuffle", data, 0))
    poses = []
    step = None
    if times["shuffle_start"] <= local < times["shuffle_end"]:
        step = min(len(data["swaps"]) - 1, int((local - times["shuffle_start"]) / seconds))
        progress = _clamp((local - times["shuffle_start"] - step * seconds) / seconds)
    settled = order[0] if local < times["shuffle_start"] else (order[-1] if step is None else order[step])
    for cup in range(cups):
        position = settled.index(cup)
        pose = {"cup": cup, "x": xs[position], "y": BASE_Y, "scale": 1.0, "lift": 0.0, "position": position}
        if step is not None:
            first, second, front = data["swaps"][step]
            if cup in (order[step][first], order[step][second]):
                here = position
                there = second if here == first else first
                e = ease_in_out(progress)
                pose["x"] = xs[here] + (xs[there] - xs[here]) * e
                gap = abs(there - here)
                arc = math.sin(math.pi * e) * min(1.6, .75 + .25 * gap)
                if here == front:  # this cup travels in front: lower on screen, a little bigger
                    pose["y"] = BASE_Y + 84 * arc
                    pose["scale"] = 1 + .14 * arc
                else:  # the other passes behind: higher, a little smaller
                    pose["y"] = BASE_Y - 68 * arc
                    pose["scale"] = 1 - .11 * arc
        poses.append(pose)
    return poses


def ball_cup(data: dict) -> int:
    return data["start"]


# ---------------------------------------------------------------- frame

def _badges(image: Image.Image, data: dict, scale: float, state: str, answer_position: int, opacity: float,
            solved: float) -> None:
    xs, _ = layout(data["cups"])
    draw = ImageDraw.Draw(image, "RGBA")
    for position, x in enumerate(xs):
        right = state == "answer" and position == answer_position
        fill = PALETTE["success"] if right else PALETTE["accent"]
        alpha = round(255 * opacity * (1.0 if (state != "answer" or right) else .35))
        r = (38 + 6 * (solved if right else 0)) * scale
        cx, cy = x * scale, BADGE_Y * scale
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=_rgb(fill) + (alpha,), outline=OUTLINE + (alpha,), width=max(1, round(4 * scale)))
        _text(image, (cx, cy - 2 * scale), str(position + 1), font(round(46 * scale)), PALETTE["background"], alpha / 255)


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


def _draw_scene(image: Image.Image, item: RoundSpec, local: float, scale: float, hook: bool = False) -> dict:
    """Shadows, the ball, and the cups. Returns the reveal facts the caller needs."""
    data = item.data
    times = phases(item)
    xs, width = layout(data["cups"])
    poses = cup_poses(data, local)
    answer_cup = states(data["cups"], data["swaps"])[-1][item.answer - 1]
    from ..palette import active
    sprite, anchor = _cup(data["color"], active())
    factor = width / (2 * R_BOTTOM / SPRITE)
    cup_height = (HEIGHT + RY_TOP) / SPRITE * factor  # logical height of one cup
    ball_px = round(width * .42 * scale)
    # Lift (in cup heights) of the ball's cup while it shows the ball, and of the answer cup at the reveal.
    lifts = {cup: 0.0 for cup in range(data["cups"])}
    show = 0.0
    if not hook:
        if CUP_ENTRANCE <= local < times["lift_end"]:
            show = ease_out_cubic((local - CUP_ENTRANCE) / CUP_LIFT)
        elif times["lift_end"] <= local < times["show_end"]:
            show = 1.0
        elif times["show_end"] <= local < times["shuffle_start"]:
            show = 1 - ease_in_out((local - times["show_end"]) / CUP_LOWER)
    else:
        show = 1.0
    reveal = _clamp((local - times["think_end"]) / CUP_REVEAL) if not hook else 0.0
    lifts[ball_cup(data)] = show
    if reveal:
        lifts[answer_cup] = max(lifts[answer_cup], ease_out_back(reveal) if reveal < 1 else 1.0)
    dropped = 1.0
    ball_at = None
    for pose in poses:
        pose["lift"] = lifts[pose["cup"]]
    if not hook and local < CUP_ENTRANCE:
        dropped = local / CUP_ENTRANCE
    # Contact shadows first.
    shadow = _shadow()
    for pose in sorted(poses, key=lambda p: p["y"]):
        point = (pose["x"] * scale, (pose["y"] + 6) * scale)
        strength = (1 - .45 * min(1.0, pose["lift"])) * _clamp(dropped * 2.2)
        _paste(image, shadow, (shadow.width / 2, shadow.height / 2), point, width * pose["scale"] * 1.18 * scale / 420, .85 * strength)
    # The ball rests on the table under its cup (drawn before the cups, so a cup on top hides it).
    if reveal or show or hook:
        target = answer_cup if reveal else ball_cup(data)
        pose = next(p for p in poses if p["cup"] == target)
        ball = ball_sprite(ball_px)
        r = ball_px / 2
        _paste(image, ball, (r, r), (pose["x"] * scale, (pose["y"] - width * .13) * scale), 1.0)
        ball_at = (pose["x"], pose["y"] - width * .13)
    for pose in sorted(poses, key=lambda p: p["y"]):
        drop = (1 - ease_out_back(_clamp(dropped * 1.15 - pose["cup"] * .06))) * 420 if dropped < 1 else 0.0
        lift = pose["lift"] * cup_height * LIFT_HEIGHTS
        point = (pose["x"] * scale, (pose["y"] - lift - drop) * scale)
        dim = 1.0
        if reveal and pose["cup"] != answer_cup:
            dim = 1 - .28 * _clamp(reveal * 1.5)
        _paste(image, sprite, anchor, point, factor * pose["scale"] * scale, dim if dim < 1 else 1.0)
    return {"answer_cup": answer_cup, "ball_at": ball_at, "reveal": reveal, "position": states(data["cups"], data["swaps"])[-1].index(answer_cup)}


def draw_cup_round(spec: VideoSpec, index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[index]
    data = item.data
    times = phases(item)
    image = _table(size, active_theme()).copy()
    _level_header(image, index + 1, spec.round_count, 1.0, scale)
    _text(image, (540 * scale, 330 * scale), f"{data['cups']} CUPS", font(round(48 * scale)), PALETTE["accent"], _clamp(local / .3))
    facts = _draw_scene(image, item, local, scale)
    thinking = float(data["thinking_seconds"])
    guessing = times["shuffle_end"] <= local < times["think_end"]
    if guessing:
        remaining = times["think_end"] - local
        _timer(image, min(thinking, remaining), thinking, _clamp((local - times["shuffle_end"]) / .25), scale)
        _prompt(image, PROMPT_GUESS, scale, _clamp((local - times["shuffle_end"]) / .2),
                abs(math.sin(local * math.pi)) * (1 if remaining < 3 else 0))
        _text(image, (540 * scale, COMMENT_Y * scale), COMMENT, font(round(54 * scale)), PALETTE["text_light"],
              _clamp((local - times["shuffle_end"]) / .3))
    elif local >= times["think_end"]:
        _prompt(image, f"IT WAS CUP {item.answer}!", scale, 1.0, 0.0, PALETTE["success"])
    else:
        _prompt(image, PROMPT_WATCH, scale, _clamp(local / .3))
    solved = _clamp((local - times["reveal_end"]) / CUP_ANSWER)
    _badges(image, data, scale, "answer" if local >= times["think_end"] else "play", facts["position"],
            _clamp(local / .4), solved)
    if facts["reveal"] >= 1 and facts["ball_at"] is not None:
        _snap_burst(image, facts["ball_at"], layout(data["cups"])[1] * .8, local - times["reveal_end"], scale)
    if local < .2 and index > 0:
        image.alpha_composite(Image.new("RGBA", size, _rgb(PALETTE["background"]) + (round(200 * (1 - _clamp(local / .2))),)))
    return image


def draw_cup_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook: level 1's real cups with the ball showing under one of them, under `FOLLOW THE BALL.`."""
    scale = size[0] / 1080
    item = spec.rounds[0]
    image = _table(size, active_theme()).copy()
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .18)))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(960 * scale), round(84 * scale)),
          PALETTE["text_light"], _clamp(t / .08 + .3), slam)
    _text(image, (540 * scale, 232 * scale), f"{spec.round_count} LEVELS · EACH ONE FASTER", font(round(38 * scale)),
          PALETTE["accent"], _clamp((t - .15) / .2))
    _draw_scene(image, item, 0.0, scale, hook=True)
    _prompt(image, PROMPT_WATCH, scale, _clamp((t - .1) / .2))
    _badges(image, item.data, scale, "play", 0, 1.0, 0.0)
    return image


def draw_cup_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        from .ready import HOOK_SECONDS, draw_ready_screen, has_ready
        if has_ready(spec) and t >= HOOK_SECONDS:
            return draw_ready_screen(spec, t - HOOK_SECONDS, size, _table(size, active_theme()))  # the same table
        return draw_cup_intro(spec, t, size).convert("RGB")
    levels = schedule(spec)
    rounds_end = levels[-1][0] + levels[-1][1]
    if t >= rounds_end:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size, total=spec.round_count)
    index = max(position for position, (start, _) in enumerate(levels) if t >= start)
    return draw_cup_round(spec, index, t - levels[index][0], size).convert("RGB")
