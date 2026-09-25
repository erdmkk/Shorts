"""Lucky Pick, Puzzly for You look: a seeded neon maze, a lit creature with a real eating animation, and a survivor."""
from __future__ import annotations

from functools import lru_cache
import math

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFilter

from ..config import LUCKY_APPEARANCE_DURATION, LUCKY_SELECTION_DURATION, LUCKY_WINNER_HOLD, PUZZLE_FIT_PALETTE as PALETTE
from ..models import RoundSpec, VideoSpec
from ..puzzles.lucky_pick import (CHOMP_AT, CORRIDOR_WIDTH, EAT_ANTICIPATION, EAT_BITE, POCKET_RADIUS, POST_EAT,
                                  STOP_GAP, TARGET_SIZE, path_length, point_on_path, travel_distance)
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .memory import token_image
from .puzzle_fit import _background, _text, _timer, active_theme, draw_puzzle_fit_outro
from .text import fitted_font, font

HOOK_TEXT = "PICK ONE."
HOOK_SUBTITLE = "ONLY ONE SURVIVES."
OUTRO_QUESTION = "Did yours survive?"
OUTRO_PROMPT = "Comment your pick ↓"
CHARACTER_RADIUS = 64  # logical px; the body is 128 px wide inside 118 px corridors
RIM = 7  # neon wall rim thickness
BODY_TOP, BODY_BOTTOM = "#43369E", "#1D1754"
BODY_RIM = "#2EE6C5"
FACE_LINE = "#D8FFF8"
MOUTH_INSIDE, THROAT, TONGUE = "#15041F", "#FF3D7F", "#FF7AB8"
TRAIL_SECONDS = 0.42
BURST_SECONDS = 0.5
COVER_TIME = 0.6


def _rgb(value: str) -> tuple[int, int, int]:
    return ImageColor.getrgb(value)[:3]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------- maze board (static per video)

def _maze_masks(size: tuple[int, int], corridors: tuple, pockets: tuple, entrance: tuple, grow: float) -> Image.Image:
    scale = size[0] / 1080
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    half = (CORRIDOR_WIDTH / 2 + grow) * scale
    for (ax, ay), (bx, by) in corridors:
        x1, x2 = sorted((ax * scale, bx * scale)); y1, y2 = sorted((ay * scale, by * scale))
        draw.rectangle((x1 - half, y1 - half, x2 + half, y2 + half), fill=255)
    pocket = (POCKET_RADIUS + grow) * scale
    for x, y in pockets:
        draw.ellipse((x * scale - pocket, y * scale - pocket, x * scale + pocket, y * scale + pocket), fill=255)
    portal = (70 + grow) * scale
    ex, ey = entrance[0] * scale, entrance[1] * scale
    draw.ellipse((ex - portal, ey - portal, ex + portal, ey + portal), fill=255)
    return mask


@lru_cache(maxsize=6)
def _board(size: tuple[int, int], corridors: tuple, pockets: tuple, entrance: tuple, theme: str = "violet") -> Image.Image:
    """Recessed dark corridors carved into lit wall blocks, with a neon rim and bloom along every wall edge."""
    scale = size[0] / 1080
    base = np.asarray(_background(size, 900, theme), dtype=np.float32)
    height, width = size[1], size[0]
    panel = Image.new("L", size, 0)
    ImageDraw.Draw(panel).rounded_rectangle((52 * scale, 322 * scale, 1028 * scale, 1612 * scale), radius=round(46 * scale), fill=255)
    panel_a = np.asarray(panel, dtype=np.float32)[..., None] / 255
    rows = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    wall = np.array(_rgb("#232B63"), np.float32) * (1 - rows) + np.array(_rgb("#161C45"), np.float32) * rows
    # Faint diagonal texture on the wall blocks.
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    stripes = ((xx + yy) / (22 * scale)) % 2 < 1
    wall = wall + stripes[..., None] * 4.0
    image = base * (1 - panel_a) + wall * panel_a
    floor = np.asarray(_maze_masks(size, corridors, pockets, entrance, 0), dtype=np.float32) / 255
    outer = np.asarray(_maze_masks(size, corridors, pockets, entrance, RIM), dtype=np.float32) / 255
    # Recessed floor with an inner shadow near the walls.
    shadow = Image.fromarray(np.uint8((1 - floor) * 255)).filter(ImageFilter.GaussianBlur(18 * scale))
    shade = np.asarray(shadow, dtype=np.float32) / 255
    floor_rgb = np.array(_rgb("#0A0D24"), np.float32) * (1 - .55 * shade[..., None])
    dots = ((xx % (47 * scale)) < 2.2 * scale) & ((yy % (47 * scale)) < 2.2 * scale)
    floor_rgb = floor_rgb + dots[..., None] * 10.0
    image = image * (1 - floor[..., None]) + floor_rgb * floor[..., None]
    # Neon rim: cyan at the bottom fading to violet at the top, plus a soft bloom.
    rim = np.clip(outer - floor, 0, 1)
    neon = (np.array(_rgb(PALETTE["accent"]), np.float32) * rows + np.array(_rgb(PALETTE["primary"]), np.float32) * (1 - rows))
    bloom = np.asarray(Image.fromarray(np.uint8(rim * 255)).filter(ImageFilter.GaussianBlur(14 * scale)), dtype=np.float32) / 255
    image = image + neon * (bloom * .55)[..., None]
    image = image * (1 - rim[..., None]) + (neon * .85 + 255 * .15) * rim[..., None]
    return Image.fromarray(np.clip(image, 0, 255).astype(np.uint8))


def _board_for(item: RoundSpec, size: tuple[int, int]) -> Image.Image:
    data = item.data
    corridors = tuple((tuple(a), tuple(b)) for a, b in data["corridors"])
    pockets = tuple(tuple(point) for point in data["valid_target_positions"])
    return _board(size, corridors, pockets, tuple(data["entrance"]), active_theme()).copy()


def _glow(image: Image.Image, center: tuple[float, float], radius: float, color: str, alpha: int) -> None:
    sprite = _glow_sprite(max(2, round(radius)), color, alpha)
    image.paste(sprite, (round(center[0] - sprite.width / 2), round(center[1] - sprite.height / 2)), sprite)


@lru_cache(maxsize=64)
def _glow_sprite(radius: int, color: str, alpha: int) -> Image.Image:
    size = radius * 4
    sprite = Image.new("RGBA", (size, size), _rgb(color) + (0,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((radius, radius, size - radius, size - radius), fill=alpha)
    sprite.putalpha(mask.filter(ImageFilter.GaussianBlur(radius * .45)))
    return sprite


def _pockets(image: Image.Image, item: RoundSpec, eaten: set[int], local: float, scale: float) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    occupied = {tuple(target["position"]): target for target in item.data["targets"]}
    ring = 58 * scale
    width = max(2, round(4 * scale))
    for point in item.data["valid_target_positions"]:
        x, y = point[0] * scale, point[1] * scale
        target = occupied.get(tuple(point))
        if target is None or target["index"] in eaten:
            draw.ellipse((x - ring, y - ring, x + ring, y + ring), outline=_rgb(PALETTE["surface_edge"]) + (150,), width=width)
            continue
        pulse = .5 + .5 * math.sin(local * 3.2 + target["index"])
        draw.ellipse((x - ring, y - ring, x + ring, y + ring), outline=_rgb(target["color_value"]) + (round(120 + 70 * pulse),), width=width)


def _portal(image: Image.Image, entrance: list[int], local: float, scale: float, flash: float) -> None:
    x, y = entrance[0] * scale, entrance[1] * scale
    _glow(image, (x, y), (46 + 14 * flash) * scale, PALETTE["accent"], round(120 + 120 * flash))
    draw = ImageDraw.Draw(image, "RGBA")
    for index, radius in enumerate((52, 38)):
        r = radius * scale
        start = (local * (90 if index == 0 else -140)) % 360
        for arc in range(3):
            draw.arc((x - r, y - r, x + r, y + r), start + arc * 120, start + arc * 120 + 70,
                     fill=_rgb(PALETTE["accent"] if index == 0 else PALETTE["primary"]) + (220,), width=max(2, round(5 * scale)))


# ---------------------------------------------------------------- targets

def _target(image: Image.Image, target: dict, center: tuple[float, float], scale: float, zoom: float = 1.0,
            rotation: float = 0.0, glow: float = .55) -> None:
    size = max(2, round(TARGET_SIZE * scale * zoom))
    if glow > 0:
        _glow(image, center, size * .62, target["color_value"], round(150 * glow))
    sprite = token_image(target["shape_id"], target["color_value"], size)
    if rotation:
        sprite = sprite.rotate(rotation, resample=Image.Resampling.BICUBIC, expand=True)
    image.paste(sprite, (round(center[0] - sprite.width / 2), round(center[1] - sprite.height / 2)), sprite)


def _bob(index: int, local: float) -> float:
    return 5 * math.sin(local * 2.4 + index * 0.9)


# ---------------------------------------------------------------- creature

def creature(radius: float, *, stretch: tuple[float, float] = (1.0, 1.0), tilt: float = 0.0, mouth: float = 0.0,
             look: tuple[float, float] = (0.0, 0.0), blink: float = 0.0, brow: float = 0.0, happy: float = 0.0,
             cheeks: float = 0.0) -> Image.Image:
    """The lit indigo creature. Parameters drive squash/stretch, jaw, eyes, brows, and cheeks."""
    ss = 2
    R = radius * ss
    side = round(R * 3.2)
    c = side / 2
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sx, sy = stretch
    sx += .10 * cheeks
    rx, ry = R * sx, R * sy
    # Halo.
    halo = Image.new("L", (side, side), 0)
    ImageDraw.Draw(halo).ellipse((c - rx * 1.12, c - ry * 1.12, c + rx * 1.12, c + ry * 1.12), fill=120)
    halo_layer = Image.new("RGBA", (side, side), _rgb(BODY_RIM) + (0,))
    halo_layer.putalpha(halo.filter(ImageFilter.GaussianBlur(R * .22)))
    image.alpha_composite(halo_layer)
    # Body with a vertical gradient.
    body_mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(body_mask).ellipse((c - rx, c - ry, c + rx, c + ry), fill=255)
    gradient = np.linspace(0, 1, side, dtype=np.float32)[:, None, None]
    colors = np.array(_rgb(BODY_TOP), np.float32) * (1 - gradient) + np.array(_rgb(BODY_BOTTOM), np.float32) * gradient
    body = Image.fromarray(np.repeat(colors, side, axis=1).astype(np.uint8)).convert("RGBA")
    body.putalpha(body_mask)
    image.alpha_composite(body)
    draw = ImageDraw.Draw(image, "RGBA")
    # Gloss and rim light.
    gloss = Image.new("L", (side, side), 0)
    ImageDraw.Draw(gloss).ellipse((c - rx * .62, c - ry * .86, c - rx * .05, c - ry * .48), fill=70)
    gloss_layer = Image.new("RGBA", (side, side), (255, 255, 255, 0))
    gloss_layer.putalpha(gloss.filter(ImageFilter.GaussianBlur(R * .08)))
    image.alpha_composite(gloss_layer)
    draw.ellipse((c - rx, c - ry, c + rx, c + ry), outline=_rgb(BODY_RIM) + (255,), width=max(2, round(R * .075)))
    if cheeks > 0:
        for side_sign in (-1, 1):
            cx, cy = c + side_sign * rx * .62, c + ry * .22
            r = R * .17
            draw.ellipse((cx - r, cy - r * .7, cx + r, cy + r * .7), fill=_rgb(TONGUE) + (round(200 * cheeks),))
    line = max(2, round(R * .065))
    # Eyes.
    eye_y = c - ry * .22 - R * .10 * mouth
    for side_sign in (-1, 1):
        ex = c + side_sign * rx * .36
        if happy > .5:
            draw.arc((ex - R * .16, eye_y - R * .10, ex + R * .16, eye_y + R * .18), 200, 340, fill=_rgb(FACE_LINE) + (255,), width=line)
            continue
        w, h = R * .17, R * .21 * max(.08, 1 - blink)
        draw.ellipse((ex - w, eye_y - h, ex + w, eye_y + h), fill=(255, 255, 255, 255))
        if h > R * .05:
            px, py = ex + look[0] * R * .07, eye_y + look[1] * R * .08
            pr = R * .095
            draw.ellipse((px - pr, py - pr, px + pr, py + pr), fill=_rgb("#0B0F24") + (255,))
            hr = R * .035
            draw.ellipse((px - pr * .35 - hr, py - pr * .4 - hr, px - pr * .35 + hr, py - pr * .4 + hr), fill=(255, 255, 255, 255))
        if brow > 0:
            inner, outer = ex - side_sign * R * .06, ex + side_sign * R * .22
            draw.line(((outer, eye_y - R * .30), (inner, eye_y - R * .30 + R * .12 * brow)), fill=_rgb(FACE_LINE) + (round(255 * brow),), width=line)
    # Mouth.
    my = c + ry * .34 + R * .06 * mouth
    if mouth < .06:
        width = R * (.24 if happy < .5 else .30)
        draw.arc((c - width, my - R * .22, c + width, my + R * .08), 25, 155, fill=_rgb(FACE_LINE) + (255,), width=line)
    else:
        mw, mh = R * (.22 + .30 * mouth), R * (.06 + .38 * mouth)
        box = (c - mw, my - mh, c + mw, my + mh)
        draw.ellipse(box, fill=_rgb(MOUTH_INSIDE) + (255,))
        throat = Image.new("L", (side, side), 0)
        ImageDraw.Draw(throat).ellipse((c - mw * .6, my, c + mw * .6, my + mh * .9), fill=round(200 * mouth))
        mouth_mask = Image.new("L", (side, side), 0)
        ImageDraw.Draw(mouth_mask).ellipse(box, fill=255)
        glow_alpha = Image.fromarray(np.minimum(np.asarray(throat.filter(ImageFilter.GaussianBlur(R * .08))), np.asarray(mouth_mask)))
        throat_layer = Image.new("RGBA", (side, side), _rgb(THROAT) + (0,))
        throat_layer.putalpha(glow_alpha)
        image.alpha_composite(throat_layer)
        draw = ImageDraw.Draw(image, "RGBA")
        draw.ellipse((c - mw * .5, my + mh * .30, c + mw * .5, my + mh * .95), fill=_rgb(TONGUE) + (255,))
        if mouth > .25:
            tooth = R * .09 * min(1, mouth * 1.5)
            for tx in (c - mw * .42, c + mw * .42 - tooth * 1.1):
                top = my - mh + R * .03
                draw.polygon(((tx, top), (tx + tooth * 1.1, top), (tx + tooth * .55, top + tooth * 1.2)), fill=(255, 255, 255, 255))
        draw.ellipse(box, outline=_rgb(FACE_LINE) + (255,), width=max(2, round(R * .045)))
    if tilt:
        image = image.rotate(tilt, resample=Image.Resampling.BICUBIC)
    return image.resize((side // ss, side // ss), Image.Resampling.LANCZOS)


def _paste_creature(image: Image.Image, center: tuple[float, float], scale: float, zoom: float = 1.0, **params) -> None:
    radius = CHARACTER_RADIUS * scale * zoom
    if radius < 2:
        return
    sprite = creature(radius, **params)
    image.paste(sprite, (round(center[0] - sprite.width / 2), round(center[1] - sprite.height / 2)), sprite)


# ---------------------------------------------------------------- state

def _direction(path: list[list[int]], segment: int) -> tuple[float, float]:
    a, b = path[segment], path[min(len(path) - 1, segment + 1)]
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy) or 1
    return dx / length, dy / length


def _point_at(path: list[list[int]], distance: float) -> tuple[tuple[float, float], tuple[float, float]]:
    total = path_length(path)
    point, segment = point_on_path(path, distance / total if total else 1)
    return point, _direction(path, segment)


def lucky_state(local: float, item: RoundSpec) -> dict:
    data = item.data
    selection_end = LUCKY_APPEARANCE_DURATION + LUCKY_SELECTION_DURATION
    if local < LUCKY_APPEARANCE_DURATION:
        return {"phase": "idle", "eliminated": (), "character": None, "mouth": 0.0}
    if local < selection_end:
        return {"phase": "selection", "eliminated": (), "character": None, "mouth": 0.0}
    eliminated: list[int] = []
    previous_node = None
    for number, step in enumerate(data["movement_steps"]):
        relative = local - float(step["start_time"])
        target = step["target_index"]
        if relative < 0:
            break
        path = step["travel_path"]
        length = path_length(path)
        stop = max(0.0, length - STOP_GAP)
        stop_point, stop_dir = _point_at(path, stop)
        travel = float(step["travel_duration"])
        if relative < travel:
            distance = travel_distance(relative, travel, stop)
            point, direction = _point_at(path, distance)
            trail = [_point_at(path, travel_distance(relative - TRAIL_SECONDS * k / 8, travel, stop))[0] for k in range(9)
                     if relative - TRAIL_SECONDS * k / 8 >= 0]
            return {"phase": "travel", "eliminated": tuple(eliminated), "character": point, "direction": direction,
                    "mouth": 0.0, "target": target, "trail": trail, "moving": True,
                    "emerge": _clamp(relative / .35) if number == 0 else 1.0, "since_start": relative}
        relative -= travel
        node = tuple(path[-1])
        if relative < EAT_ANTICIPATION:
            u = ease_out_cubic(relative / EAT_ANTICIPATION)
            return {"phase": "eat_anticipation", "eliminated": tuple(eliminated), "character": stop_point, "direction": stop_dir,
                    "mouth": .35 * u, "crouch": u, "brow": u, "target": target}
        relative -= EAT_ANTICIPATION
        if relative < EAT_BITE:
            u = relative / EAT_BITE
            lunge = STOP_GAP * .62 * math.sin(math.pi * _clamp(u / .9))
            center = (stop_point[0] + stop_dir[0] * lunge, stop_point[1] + stop_dir[1] * lunge)
            if u < .30:
                mouth = .35 + .65 * ease_out_cubic(u / .30)
            elif u < CHOMP_AT:
                mouth = 1.0
            else:
                mouth = max(0.0, 1 - (u - CHOMP_AT) / .10)
            gone = u >= CHOMP_AT
            return {"phase": "eat", "eliminated": tuple(eliminated + [target]) if gone else tuple(eliminated),
                    "character": center, "direction": stop_dir, "mouth": mouth, "brow": 1 - _clamp((u - CHOMP_AT) / .2),
                    "stretch": .20 * math.sin(math.pi * _clamp(u / .75)), "target": target, "eat_progress": u,
                    "chomp_age": (u - CHOMP_AT) * EAT_BITE if gone else None, "node": node}
        relative -= EAT_BITE
        if relative < POST_EAT:
            v = relative / POST_EAT
            settle = ease_in_out(v)
            center = (stop_point[0] + (node[0] - stop_point[0]) * settle, stop_point[1] + (node[1] - stop_point[1]) * settle)
            return {"phase": "post_eat", "eliminated": tuple(eliminated + [target]), "character": center,
                    "direction": stop_dir, "mouth": 0.0, "cheeks": 1 - v, "happy": 1.0 if v < .75 else 0.0,
                    "wobble": math.sin(v * math.pi * 3) * (1 - v), "target": target,
                    "chomp_age": (1 - CHOMP_AT) * EAT_BITE + relative, "node": node}
        eliminated.append(target)
        previous_node = node
    winner = data["winner_index"]
    winner_position = data["targets"][winner]["position"]
    last = previous_node or tuple(data["movement_steps"][-1]["travel_path"][-1])
    dx, dy = winner_position[0] - last[0], winner_position[1] - last[1]
    length = math.hypot(dx, dy) or 1
    age = max(0.0, local - (float(data["timeline_duration"]) - LUCKY_WINNER_HOLD))
    return {"phase": "winner", "eliminated": tuple(data["elimination_order"]), "character": last,
            "direction": (dx / length, dy / length), "mouth": 0.0, "winner_age": age}


# ---------------------------------------------------------------- frame pieces

def _burst(image: Image.Image, center: tuple[float, float], color: str, age: float, scale: float, count: int = 14,
           reach: float = 120) -> None:
    if age < 0 or age > BURST_SECONDS:
        return
    progress = ease_out_cubic(age / BURST_SECONDS)
    alpha = round(255 * (1 - progress))
    draw = ImageDraw.Draw(image, "RGBA")
    ring = (30 + reach * .8 * progress) * scale
    draw.ellipse((center[0] - ring, center[1] - ring, center[0] + ring, center[1] + ring),
                 outline=_rgb(color) + (round(alpha * .8),), width=max(2, round(6 * (1 - progress) * scale) + 1))
    for index in range(count):
        angle = index / count * 2 * math.pi + (index * 2.399) % .6
        distance = (24 + reach * (.7 + .3 * ((index * 7) % 5) / 4) * progress) * scale
        px, py = center[0] + math.cos(angle) * distance, center[1] + math.sin(angle) * distance
        size = (9 - 6 * progress) * scale * (1.2 if index % 3 == 0 else .8)
        fill = (255, 255, 255) if index % 4 == 0 else _rgb(color)
        draw.polygon(((px, py - size), (px + size * .7, py), (px, py + size), (px - size * .7, py)), fill=fill + (alpha,))


def _progress_dots(image: Image.Image, item: RoundSpec, eaten: set[int], winner_glow: float, scale: float) -> None:
    targets = item.data["targets"]
    gap = 74 * scale
    start = 540 * scale - gap * (len(targets) - 1) / 2
    size = round(44 * scale)
    draw = ImageDraw.Draw(image, "RGBA")
    for slot, target in enumerate(targets):
        x, y = start + gap * slot, 250 * scale
        if target["index"] in eaten:
            r = 17 * scale
            draw.ellipse((x - r, y - r, x + r, y + r), outline=_rgb(PALETTE["surface_edge"]) + (255,), width=max(2, round(3 * scale)))
            draw.line(((x - r * .6, y + r * .6), (x + r * .6, y - r * .6)), fill=_rgb(PALETTE["surface_edge"]) + (255,), width=max(2, round(3 * scale)))
            continue
        zoom = 1 + .3 * winner_glow if target["index"] == item.data["winner_index"] else 1.0
        sprite = token_image(target["shape_id"], target["color_value"], max(2, round(size * zoom)))
        image.paste(sprite, (round(x - sprite.width / 2), round(y - sprite.height / 2)), sprite)


def _header(image: Image.Image, text: str, color: str, scale: float, opacity: float = 1.0, zoom: float = 1.0) -> None:
    face = fitted_font(text, round(900 * scale), round(76 * scale))
    _text(image, (540 * scale, 150 * scale), text, face, color, opacity, zoom)


def _draw_scene(image: Image.Image, item: RoundSpec, local: float, scale: float, state: dict, intro_pop: float = 1.0) -> None:
    data = item.data
    eaten = set(state["eliminated"])
    _pockets(image, item, eaten, local, scale)
    emerge_flash = 0.0
    if state["phase"] == "travel" and state.get("emerge", 1) < 1:
        emerge_flash = 1 - state["emerge"]
    _portal(image, data["entrance"], local, scale, emerge_flash if state["phase"] != "selection" else .35 + .35 * math.sin(local * 5))
    eating = state.get("target") if state["phase"] == "eat" else None
    winner = data["winner_index"]
    swallowed = None
    for target in data["targets"]:
        if target["index"] in eaten:
            continue
        x, y = target["position"][0] * scale, (target["position"][1] + _bob(target["index"], local)) * scale
        zoom, rotation, glow = ease_out_back(intro_pop) if intro_pop < 1 else 1.0, 0.0, .55
        if target["index"] == eating:
            u = float(state["eat_progress"])
            pull = ease_in_out(_clamp((u - .18) / (CHOMP_AT - .18)))
            mouth_x = state["character"][0] + state["direction"][0] * CHARACTER_RADIUS * .2
            mouth_y = state["character"][1] + CHARACTER_RADIUS * .35
            x += (mouth_x * scale - x) * pull
            y += (mouth_y * scale - y) * pull
            zoom *= 1 - .82 * pull
            rotation = 220 * pull
            glow = .55 * (1 - pull)
            if u < .18:  # a nervous shiver before the pull
                x += math.sin(u * 140) * 3 * scale
        if state["phase"] == "winner" and target["index"] == winner:
            age = float(state["winner_age"])
            zoom = 1 + .45 * ease_out_back(_clamp(age / .45))
            glow = 1.0 + .3 * math.sin(age * 8)
            _glow(image, (x, y), 120 * scale, PALETTE["warning"], round(120 * _clamp(age / .3)))
        if target["index"] == eating:
            swallowed = (target, (x, y), zoom, rotation, glow)  # drawn over the open mouth
            continue
        _target(image, target, (x, y), scale, zoom, rotation, glow)
    # Trail behind the moving creature.
    if state["phase"] == "travel" and len(state.get("trail", [])) > 1:
        draw = ImageDraw.Draw(image, "RGBA")
        points = state["trail"]
        for index, (a, b) in enumerate(zip(points, points[1:])):
            fade = 1 - index / len(points)
            draw.line(((a[0] * scale, a[1] * scale), (b[0] * scale, b[1] * scale)), fill=_rgb(BODY_RIM) + (round(150 * fade),),
                      width=max(2, round((26 * fade + 4) * scale)))
    if state["character"] is not None:
        _creature_for_state(image, state, local, scale)
    if swallowed is not None:
        target, center, zoom, rotation, glow = swallowed
        _target(image, target, center, scale, zoom, rotation, glow)
    # Chomp burst at the mouth.
    if state.get("chomp_age") is not None and state.get("target") is not None:
        target = data["targets"][state["target"]]
        center = state["character"]
        _burst(image, (center[0] * scale, (center[1] + CHARACTER_RADIUS * .3) * scale), target["color_value"],
               float(state["chomp_age"]), scale)
    if state["phase"] == "winner":
        target = data["targets"][winner]
        center = (target["position"][0] * scale, target["position"][1] * scale)
        _burst(image, center, PALETTE["warning"], float(state["winner_age"]) - .1, scale, 18, 190)
        _burst(image, center, PALETTE["success"], float(state["winner_age"]) - .45, scale, 12, 150)


def _creature_for_state(image: Image.Image, state: dict, local: float, scale: float) -> None:
    dx, dy = state.get("direction", (0.0, 0.0))
    phase = state["phase"]
    sx = sy = 1.0
    tilt = 0.0
    zoom = 1.0
    blink = 1.0 if (local % 2.7) < .09 else 0.0
    params: dict = {"look": (dx, dy), "mouth": float(state.get("mouth", 0.0)), "blink": blink}
    if phase == "travel":
        waddle = math.sin(float(state["since_start"]) * 16)
        sx, sy = 1 + .05 * waddle, 1 - .05 * waddle
        tilt = -dx * 7 + waddle * 2.5
        zoom = ease_out_back(float(state["emerge"]))
    elif phase == "eat_anticipation":
        crouch = float(state["crouch"])
        sx, sy = 1 + .14 * crouch, 1 - .12 * crouch
        params["brow"] = float(state["brow"])
    elif phase == "eat":
        stretch = float(state["stretch"])
        horizontal = abs(dx) > abs(dy)
        sx, sy = (1 + stretch, 1 - stretch * .6) if horizontal else (1 - stretch * .5, 1 + stretch)
        params["brow"] = float(state["brow"])
        tilt = -dx * 8
    elif phase == "post_eat":
        wobble = float(state["wobble"])
        chew = math.sin(local * 30) * .5 + .5
        sx, sy = 1 + .10 * wobble, 1 - .10 * wobble
        params["cheeks"] = float(state["cheeks"]) * (.7 + .3 * chew)
        params["happy"] = float(state["happy"])
    elif phase == "winner":
        age = float(state["winner_age"])
        params["look"] = (dx, dy)
        params["brow"] = 0.0
        sx, sy = 1 - .04 * math.sin(age * 6), 1 + .04 * math.sin(age * 6)
    params["stretch"] = (sx, sy)
    params["tilt"] = tilt
    center = state["character"]
    _paste_creature(image, (center[0] * scale, center[1] * scale), scale, zoom, **params)


# ---------------------------------------------------------------- frames

def draw_lucky_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook: the real maze and targets under PICK ONE. The creature stays hidden."""
    scale = size[0] / 1080
    item = spec.rounds[0]
    image = _board_for(item, size)
    state = {"phase": "selection", "eliminated": (), "character": None}
    _draw_scene(image, item, t, scale, state, intro_pop=_clamp(t / .35))
    pop = ease_out_back(_clamp(t / .3))
    _header(image, HOOK_TEXT, PALETTE["text_light"], scale, _clamp(t / .15), max(.5, pop))
    _text(image, (540 * scale, 250 * scale), HOOK_SUBTITLE, font(round(42 * scale)), PALETTE["accent"], _clamp((t - .2) / .25))
    return image


def draw_lucky_round(spec: VideoSpec, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[0]
    image = _board_for(item, size)
    state = lucky_state(local, item)
    _draw_scene(image, item, local, scale, state)
    eaten = set(state["eliminated"])
    if state["phase"] in ("idle", "selection"):
        _header(image, HOOK_TEXT, PALETTE["text_light"], scale)
        remaining = LUCKY_APPEARANCE_DURATION + LUCKY_SELECTION_DURATION - local
        _timer(image, remaining, LUCKY_SELECTION_DURATION, 1.0, scale)
        _text(image, (540 * scale, 290 * scale), HOOK_SUBTITLE, font(round(32 * scale)), PALETTE["text_muted"])
    elif state["phase"] == "winner":
        age = float(state["winner_age"])
        _header(image, "SURVIVOR!", PALETTE["warning"], scale, 1.0, max(.6, ease_out_back(_clamp(age / .35))))
        _progress_dots(image, item, eaten, _clamp(age / .4), scale)
    else:
        left = len(item.data["targets"]) - len(eaten)
        _header(image, f"{left} LEFT", PALETTE["danger"] if left <= 3 else PALETTE["text_light"], scale)
        _progress_dots(image, item, eaten, 0.0, scale)
    return image


def draw_lucky_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        return draw_lucky_intro(spec, t, size)
    end = spec.intro_duration + spec.round_duration
    if t >= end:
        winner = spec.rounds[0].data["targets"][spec.rounds[0].data["winner_index"]]
        return draw_puzzle_fit_outro(spec, t - end, size, OUTRO_QUESTION, OUTRO_PROMPT,
                                     hero=lambda pixels: token_image(winner["shape_id"], winner["color_value"], pixels))
    return draw_lucky_round(spec, t - spec.intro_duration, size)
