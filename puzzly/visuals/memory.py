from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..config import (MEMORY_ANSWER_FLIP, MEMORY_ANSWER_HIGHLIGHT, MEMORY_BOARD_ENTRANCE,
                      MEMORY_COMPLETED_HOLD, MEMORY_FINAL_DELAY, MEMORY_FINAL_FLIP, MEMORY_GRID_COVER,
                      MEMORY_QUESTION_DURATION, MEMORY_TARGET_ENTRANCE, MEMORY_THINKING_DURATION)
from ..models import RoundSpec, VideoSpec
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .layout import scale_point
from .puzzle_fit import PALETTE, _background, _snap_burst, _text, _timer, draw_puzzle_fit_outro
from .text import fitted_font, font

POSITIONS = ((250, 930), (540, 930), (830, 930), (395, 1290), (685, 1290))
SHAPE_SAFE_BOUNDS = (0.09, 0.09, 0.91, 0.91)
SHAPE_LAYOUT = {
    "circle": (0.94, 0.000, 0.000), "square": (0.91, 0.000, 0.000),
    "triangle": (0.96, 0.000, 0.028), "star": (0.96, 0.000, 0.012),
    "hexagon": (0.94, 0.000, 0.000), "heart": (0.95, 0.000, 0.018),
    "diamond": (0.93, 0.000, 0.000), "pentagon": (0.95, 0.000, 0.012),
    "cross": (0.90, 0.000, 0.000), "moon": (0.94, 0.020, 0.000),
}


def _scaled(value: float, size: tuple[int, int]) -> int:
    return max(1, round(value * size[0] / 1080))


def _bounds(values: tuple[float, float, float, float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    a = scale_point((values[0], values[1]), size); b = scale_point((values[2], values[3]), size)
    return a[0], a[1], b[0], b[1]


def _regular_polygon(sides: int, center: float, radius: float, rotation: float = -math.pi / 2) -> list[tuple[float, float]]:
    return [(center + radius * math.cos(rotation + i * 2 * math.pi / sides),
             center + radius * math.sin(rotation + i * 2 * math.pi / sides)) for i in range(sides)]


def token_layout(shape: str, size: int) -> dict[str, object]:
    scale, offset_x, offset_y = SHAPE_LAYOUT[shape]
    safe = size * .70 * scale
    center = (size * (.5 + offset_x), size * (.475 + offset_y))
    return {"content_size": safe, "optical_center": center, "scale": scale,
            "offset": (offset_x, offset_y)}


def _raw_shape_mask(shape: str, size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0); draw = ImageDraw.Draw(mask)
    p, q, c, r = size * .08, size * .92, size / 2, size * .41
    if shape == "circle": draw.ellipse((p, p, q, q), fill=255)
    elif shape == "square": draw.rounded_rectangle((p, p, q, q), radius=round(size * .055), fill=255)
    elif shape == "triangle": draw.polygon(_regular_polygon(3, c, r, -math.pi / 2), fill=255)
    elif shape == "diamond": draw.polygon(_regular_polygon(4, c, r, 0), fill=255)
    elif shape == "pentagon": draw.polygon(_regular_polygon(5, c, r), fill=255)
    elif shape == "hexagon": draw.polygon(_regular_polygon(6, c, r), fill=255)
    elif shape == "star":
        points = [(c + (r if i % 2 == 0 else r * .43) * math.cos(-math.pi/2 + i*math.pi/5),
                   c + (r if i % 2 == 0 else r * .43) * math.sin(-math.pi/2 + i*math.pi/5)) for i in range(10)]
        draw.polygon(points, fill=255)
    elif shape == "heart":
        points = []
        for i in range(181):
            t = 2 * math.pi * i / 180
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t)
            points.append((c + x * size / 43, c - y * size / 43 + size * .04))
        draw.polygon(points, fill=255)
    elif shape == "cross":
        arm = size * .15
        draw.rounded_rectangle((c - arm, p, c + arm, q), radius=round(size * .05), fill=255)
        draw.rounded_rectangle((p, c - arm, q, c + arm), radius=round(size * .05), fill=255)
    elif shape == "moon":
        draw.ellipse((p, p, q, q), fill=255)
        draw.ellipse((p + size * .30, p - size * .06, q + size * .22, q - size * .20), fill=0)
    else: raise ValueError(f"unsupported memory shape: {shape}")
    return mask


def shape_mask(shape: str, size: int) -> Image.Image:
    raw = _raw_shape_mask(shape, size); box = raw.getbbox()
    if box is None: raise ValueError(f"empty memory shape: {shape}")
    content = raw.crop(box); layout = token_layout(shape, size); target = float(layout["content_size"])
    factor = min(target/content.width, target/content.height)
    resized = content.resize((round(content.width*factor), round(content.height*factor)), Image.Resampling.LANCZOS)
    center_x, center_y = layout["optical_center"]
    left, top = round(center_x-resized.width/2), round(center_y-resized.height/2)
    result = Image.new("L", (size,size), 0); result.paste(resized,(left,top)); return result


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#"); return tuple(int(raw[i:i+2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=128)
def token_image(shape: str, color_value: str, size: int) -> Image.Image:
    high_size = size * 2; mask = shape_mask(shape, high_size)
    base = _rgb(color_value)
    top = tuple(min(255, round(channel * .82 + 255 * .18)) for channel in base)
    bottom = tuple(max(0, round(channel * .82)) for channel in base)
    strip = Image.new("RGBA", (1, high_size))
    strip.putdata([tuple(round(top[c] + (bottom[c] - top[c]) * y / (high_size - 1)) for c in range(3)) + (255,) for y in range(high_size)])
    gradient = strip.resize((high_size, high_size))
    result = Image.new("RGBA", (high_size, high_size), (0,0,0,0))
    shadow = Image.new("RGBA", result.size, (0,0,0,0)); shadow_mask = Image.new("L", result.size, 0)
    shadow_mask.paste(mask, (0, round(high_size*.025))); shadow.putalpha(shadow_mask.filter(ImageFilter.GaussianBlur(high_size*.020)))
    shadow_color = Image.new("RGBA", result.size, (24,51,61,75)); shadow_color.putalpha(shadow.getchannel("A")); result.alpha_composite(shadow_color)
    outline_size = max(3, round(high_size * .045)) | 1
    outline_mask = mask.filter(ImageFilter.MaxFilter(outline_size))
    outline_layer = Image.new("RGBA", result.size, (36,70,83,255)); outline_layer.putalpha(outline_mask); result.alpha_composite(outline_layer)
    result.paste(gradient, (0,0), mask)
    shine = Image.new("L", result.size, 0); ImageDraw.Draw(shine).ellipse((high_size*.20, high_size*.14, high_size*.72, high_size*.45), fill=80)
    shine = ImageChops.multiply(shine, mask); gloss = Image.new("RGBA", result.size, (255,255,255,0)); gloss.putalpha(shine.filter(ImageFilter.GaussianBlur(high_size*.018))); result.alpha_composite(gloss)
    return result.resize((size, size), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------- 3x3 grid board (Puzzly for You look)

GRID_CARD = 250
GRID_STEP = 285
GRID_TOP = 470
GRID_TOKEN = 176
TARGET_Y = 1400
_DARK_CARD = "#1A2246"
_DARK_EDGE = "#34407A"
_COVER_TOP = "#7C5CFF"
_COVER_BOTTOM = "#4A33C8"


def grid_center(position: int) -> tuple[float, float]:
    row, column = divmod(position - 1, 3)
    return 540 + (column - 1) * GRID_STEP, GRID_TOP + row * GRID_STEP


def grid_phases(item: RoundSpec) -> dict[str, float]:
    memorize = float(item.data["memorization_seconds"])
    cover = MEMORY_BOARD_ENTRANCE + memorize
    questions = cover + MEMORY_GRID_COVER
    final = questions + len(item.data["question_order"]) * MEMORY_QUESTION_DURATION
    return {"memorize_start": MEMORY_BOARD_ENTRANCE, "cover": cover, "questions": questions, "final": final,
            "final_flip": final + MEMORY_FINAL_DELAY, "completed": final + MEMORY_FINAL_DELAY + MEMORY_FINAL_FLIP}


def memory_state(local: float, item: RoundSpec) -> dict[str, object]:
    times = grid_phases(item)
    order = item.data["question_order"]
    everything = tuple(range(1, len(item.data["tokens"]) + 1))
    if local < times["memorize_start"]:
        return {"phase": "entrance", "open_positions": everything, "timer_active": False}
    if local < times["cover"]:
        return {"phase": "memorize", "open_positions": everything, "timer_active": True}
    if local < times["questions"]:
        return {"phase": "cover", "open_positions": (), "timer_active": False}
    if local < times["final"]:
        index = int((local - times["questions"]) / MEMORY_QUESTION_DURATION)
        relative = local - times["questions"] - index * MEMORY_QUESTION_DURATION
        reveal = MEMORY_TARGET_ENTRANCE + MEMORY_THINKING_DURATION
        flip = reveal + MEMORY_ANSWER_HIGHLIGHT
        phase = "question" if relative < reveal else ("highlight" if relative < flip else "answer_reveal")
        opened = list(order[:index]) + ([order[index]] if relative >= flip + MEMORY_ANSWER_FLIP / 2 else [])
        return {"phase": phase, "question_index": index, "target_position": order[index], "relative": relative,
                "open_positions": tuple(opened), "timer_active": MEMORY_TARGET_ENTRANCE <= relative < reveal}
    relative = local - times["final"]
    opened = list(order)
    if relative < MEMORY_FINAL_DELAY:
        phase = "final_wait"
    elif relative < MEMORY_FINAL_DELAY + MEMORY_FINAL_FLIP:
        phase = "final_reveal"
        if relative >= MEMORY_FINAL_DELAY + MEMORY_FINAL_FLIP / 2:
            opened.append(item.data["final_position"])
    else:
        phase = "completed"
        opened.append(item.data["final_position"])
    return {"phase": phase, "open_positions": tuple(opened), "timer_active": False, "relative": relative}


@lru_cache(maxsize=64)
def _face_card(shape: str, color_value: str, size: int, scale: float) -> Image.Image:
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rounded_surface(card, (0, 0, size, size), 44 * scale, _DARK_CARD, _DARK_EDGE, 3 * scale)
    token = token_image(shape, color_value, round(GRID_TOKEN * scale))
    card.alpha_composite(token, ((size - token.width) // 2, (size - token.height) // 2))
    return card


@lru_cache(maxsize=32)
def _cover_card(number: int, size: int, scale: float, glow: bool) -> Image.Image:
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=round(44 * scale), fill=255)
    top, bottom = ((61, 240, 143), (22, 170, 100)) if glow else (_rgb(_COVER_TOP), _rgb(_COVER_BOTTOM))
    strip = Image.new("RGBA", (1, size))
    strip.putdata([tuple(round(top[c] + (bottom[c] - top[c]) * y / max(1, size - 1)) for c in range(3)) + (255,)
                   for y in range(size)])
    card.paste(strip.resize((size, size)), (0, 0), mask)
    rim = ImageChops.subtract(mask, ImageChops.offset(mask, 0, round(4 * scale)))
    card.paste((255, 255, 255, 255), (0, 0), rim.point(lambda value: value * 70 // 255))
    ImageDraw.Draw(card).text((size / 2, size / 2), str(number), font=font(round(112 * scale)), fill=(255, 255, 255), anchor="mm")
    return card


def _place(image: Image.Image, sprite: Image.Image, center: tuple[float, float], scale: float,
           width_factor: float = 1.0, zoom: float = 1.0) -> None:
    width = max(1, round(sprite.width * width_factor * zoom))
    height = max(1, round(sprite.height * zoom))
    if (width, height) != sprite.size:
        sprite = sprite.resize((width, height), Image.Resampling.LANCZOS)
    x, y = center[0] * scale, center[1] * scale
    image.paste(sprite, (round(x - width / 2), round(y - height / 2)), sprite)


def _glow(image: Image.Image, center: tuple[float, float], scale: float, strength: float, color: tuple[int, int, int]) -> None:
    if strength <= 0:
        return
    pad = round(40 * scale)
    size = round(GRID_CARD * scale) + 2 * pad
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad, size - pad, size - pad), radius=round(48 * scale), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(18 * scale)).point(lambda value: round(value * min(1.0, strength)))
    image.paste(Image.new("RGB", (size, size), color), (round(center[0] * scale - size / 2), round(center[1] * scale - size / 2)), mask)


def _flip(image, open_sprite, closed_sprite, center, scale, progress: float) -> None:
    """Card flip: shrink the closed face to zero width, then grow the open face."""
    if progress < .5:
        _place(image, closed_sprite, center, scale, max(.02, 1 - progress * 2))
    else:
        _place(image, open_sprite, center, scale, max(.02, (progress - .5) * 2))


def draw_memory_board(image: Image.Image, item: RoundSpec, local: float) -> None:
    """Draw the 3x3 board, covers, and flips for one moment of the single Memory round."""
    scale = image.width / 1080
    size = round(GRID_CARD * scale)
    tokens = item.data["tokens"]
    times = grid_phases(item)
    state = memory_state(local, item)
    phase = state["phase"]
    opened = set(state["open_positions"])
    target = state.get("target_position")
    for token in tokens:
        position = token["position"]
        center = grid_center(position)
        face = _face_card(token["shape"], token["color_value"], size, round(scale, 4))
        cover = _cover_card(position, size, round(scale, 4), False)
        if phase == "entrance":
            _place(image, face, center, scale, zoom=max(.05, ease_out_back((local - (position - 1) * .02) / .28)))
        elif phase == "memorize":
            _place(image, face, center, scale)
        elif phase == "cover":
            progress = _clamp01((local - times["cover"] - (position - 1) * .035) / .3)
            _flip(image, cover, face, center, scale, progress)
        elif position == target and phase in ("highlight", "answer_reveal"):
            relative = float(state["relative"]) - MEMORY_TARGET_ENTRANCE - MEMORY_THINKING_DURATION
            _glow(image, center, scale, ease_in_out(relative / MEMORY_ANSWER_HIGHLIGHT), (61, 240, 143))
            lit = _cover_card(position, size, round(scale, 4), True)
            if phase == "highlight":
                _place(image, lit, center, scale, zoom=1 + .05 * ease_in_out(relative / MEMORY_ANSWER_HIGHLIGHT))
            else:
                _flip(image, face, lit, center, scale, _clamp01((relative - MEMORY_ANSWER_HIGHLIGHT) / MEMORY_ANSWER_FLIP))
        elif phase == "final_reveal" and position == item.data["final_position"]:
            progress = _clamp01((float(state["relative"]) - MEMORY_FINAL_DELAY) / MEMORY_FINAL_FLIP)
            _glow(image, center, scale, 1 - progress, (124, 92, 255))
            _flip(image, face, cover, center, scale, progress)
        elif position in opened:
            _place(image, face, center, scale)
        else:
            _place(image, cover, center, scale)
    if phase == "completed":
        strength = 1 - _clamp01(float(state["relative"]) / MEMORY_COMPLETED_HOLD)
        for position in range(1, len(tokens) + 1):
            _glow(image, grid_center(position), scale, .35 * strength, (61, 240, 143))


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------- full frames

_DEMO_FACES = {2: ("star", "#FFD93D"), 6: ("heart", "#FF5A5F"), 7: ("moon", "#4FC3F7")}
COVER_TIME = 0.6


def _header(image: Image.Image, label: str, suffix: str, opacity: float, scale: float) -> None:
    if opacity <= 0:
        return
    big, small = font(round(60 * scale)), font(round(38 * scale))
    draw = ImageDraw.Draw(image)
    gap = 14 * scale
    width_big = draw.textlength(label, font=big)
    width_small = draw.textlength(suffix, font=small) if suffix else 0
    start = image.width / 2 - (width_big + (gap + width_small if suffix else 0)) / 2
    y = 150 * scale
    _text(image, (start + width_big / 2, y), label, big, PALETTE["text_light"], opacity)
    if suffix:
        _text(image, (start + width_big + gap + width_small / 2, y + 8 * scale), suffix, small, PALETTE["text_muted"], opacity)


def _target(image: Image.Image, token: dict, relative: float, scale: float) -> None:
    amount = ease_out_back(_clamp01(relative / MEMORY_TARGET_ENTRANCE))
    if amount <= 0:
        return
    size = round(250 * scale)
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rounded_surface(card, (0, 0, size, size), 50 * scale, "#20295A", PALETTE["accent"], 4 * scale)
    token_sprite = token_image(token["shape"], token["color_value"], round(190 * scale))
    card.alpha_composite(token_sprite, ((size - token_sprite.width) // 2, (size - token_sprite.height) // 2))
    halo = Image.new("L", (size + round(80 * scale),) * 2, 0)
    pad = round(40 * scale)
    ImageDraw.Draw(halo).rounded_rectangle((pad, pad, pad + size, pad + size), radius=round(54 * scale), fill=150)
    halo = halo.filter(ImageFilter.GaussianBlur(20 * scale))
    image.paste(Image.new("RGB", halo.size, PALETTE["accent"]),
                (round(540 * scale - halo.width / 2), round(TARGET_Y * scale - halo.height / 2)), halo.point(lambda v: round(v * amount)))
    _place(image, card, (540, TARGET_Y), scale, zoom=max(.05, amount))
    _text(image, (540 * scale, (TARGET_Y - 175) * scale), "WHERE WAS IT?", font(round(40 * scale)), PALETTE["accent"], amount)


def draw_memory_round(spec: VideoSpec, local: float, size: tuple[int, int]) -> Image.Image:
    item = spec.rounds[0]
    scale = size[0] / 1080
    image = _background(size, 800).copy()
    draw_memory_board(image, item, local)
    state = memory_state(local, item)
    phase = state["phase"]
    times = grid_phases(item)
    total = len(item.data["question_order"])
    if phase in ("entrance", "memorize"):
        memorize = float(item.data["memorization_seconds"])
        _header(image, "MEMORIZE", "", _clamp01(local / .25), scale)
        remaining = memorize if phase == "entrance" else times["cover"] - local
        _timer(image, remaining, memorize, _clamp01(local / .3), scale, show_seconds=False)  # bar only while memorizing
    elif phase == "cover":
        _header(image, "MEMORIZE", "", 1 - _clamp01((local - times["cover"]) / .3), scale)
    elif "question_index" in state:
        index = int(state["question_index"])
        relative = float(state["relative"])
        _header(image, f"QUESTION {index + 1}", f"/{total}", 1.0, scale)
        _target(image, item.data["tokens"][int(state["target_position"]) - 1], relative, scale)
        if state["timer_active"]:
            _timer(image, MEMORY_TARGET_ENTRANCE + MEMORY_THINKING_DURATION - relative, MEMORY_THINKING_DURATION, 1.0, scale)
    elif phase in ("final_wait", "final_reveal"):
        _header(image, "LAST ONE", "", 1.0, scale)
    else:
        _header(image, "ALL 9", "", _clamp01(float(state["relative"]) / .25), scale)
        _snap_burst(image, (540, TARGET_Y - 60), 170, float(state["relative"]), scale)
    return image


def draw_memory_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook with a fixed concept board (never the real board): numbered covers and three demo tokens."""
    scale = size[0] / 1080
    image = _background(size, 800).copy()
    card_size = round(GRID_CARD * scale)
    for position in range(1, 10):
        center = grid_center(position)
        zoom = max(.05, ease_out_back((t - (position - 1) * .03) / .3))
        if position in _DEMO_FACES:
            shape, color = _DEMO_FACES[position]
            _place(image, _face_card(shape, color, card_size, round(scale, 4)), center, scale, zoom=zoom)
        else:
            _place(image, _cover_card(position, card_size, round(scale, 4), False), center, scale, zoom=zoom)
    fade = 1 - _clamp01((t - (spec.intro_duration - .22)) / .22)
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp01(t / .18)))
    hook = "REMEMBER ALL 9."
    _text(image, (540 * scale, 150 * scale), hook, fitted_font(hook, round(940 * scale), round(84 * scale)),
          PALETTE["text_light"], fade * _clamp01(t / .08 + .3), slam)
    seconds = float(spec.rounds[0].data["memorization_seconds"])
    subtitle = f"{len(spec.rounds[0].data['question_order'])} QUESTIONS \u00b7 {seconds:g} SECONDS TO MEMORIZE"
    _text(image, (540 * scale, 232 * scale), subtitle, font(round(34 * scale)), PALETTE["accent"], fade * _clamp01((t - .15) / .2))
    return image


def draw_memory_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        return draw_memory_intro(spec, t, size)
    end = spec.intro_duration + spec.round_duration
    if t >= end:
        return draw_puzzle_fit_outro(spec, t - end, size, total=len(spec.rounds[0].data["question_order"]))
    return draw_memory_round(spec, t - spec.intro_duration, size)
