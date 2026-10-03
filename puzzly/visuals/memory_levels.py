"""Memory Challenge V8 in the Puzzly for You look: three levels on glossy 3D cards.

`where` levels (1 and 3): the board is shown, the cards flip face down, and for every question a shape appears under the board
and the viewer finds where it was (the card lights up green and flips). `vanish` level (2): the board stays face up, one card
shrinks away, and the viewer names the shape that vanished (it pops back with a burst). After the last question the board
is shown complete. Cards are big and fill the screen, bob gently while the viewer memorizes, and float on a slab with a soft
shadow, so the board feels alive. `phases` and `schedule` give every moment; durations come from `config.memory_level_round`.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from ..config import (MEMORY_V8_COVER, MEMORY_V8_ENTRANCE, MEMORY_V8_FINALE, MEMORY_V8_VANISH, MEMORY_V8_WHERE_EXTRA,
                      PUZZLE_FIT_PALETTE as PALETTE, memory_level_round, memory_question_length)
from ..models import RoundSpec, VideoSpec
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .memory import token_image
from .puzzle_fit import _background, _level_header, _snap_burst, _text, _timer, active_theme, draw_puzzle_fit_outro
from .text import fitted_font, font

AREA_WIDTH = 880.0
GAP = 32.0
MAX_CARD = 330.0
CENTER_Y = 825.0
PILL_Y = 312.0
TARGET_SIZE = 210.0
HOOK_TEXT = "REMEMBER IT ALL."
COVER_TIME = 0.6
GREEN = (61, 240, 143)
CONCEPT = {2: ("diamond", "#FFD93D"), 6: ("hexagon", "#FF6B6B"), 7: ("ring", "#4FC3F7")}  # the hook's demo faces, never a real board


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _mix(a: tuple, b: tuple, t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


# ---------------------------------------------------------------- geometry

def grid_layout(rows: int, cols: int) -> dict[str, float]:
    """The card size and the board's box: cards are as big as the screen allows (up to 330 logical px)."""
    size = min(MAX_CARD, (AREA_WIDTH - GAP * (cols - 1)) / cols, (AREA_WIDTH - GAP * (rows - 1)) / rows)
    width, height = cols * size + GAP * (cols - 1), rows * size + GAP * (rows - 1)
    return {"size": size, "rows": rows, "cols": cols, "width": width, "height": height, "left": 540 - width / 2,
            "top": CENTER_Y - height / 2}


def card_center(layout: dict[str, float], position: int) -> tuple[float, float]:
    row, column = divmod(position - 1, int(layout["cols"]))
    return (layout["left"] + layout["size"] / 2 + column * (layout["size"] + GAP),
            layout["top"] + layout["size"] / 2 + row * (layout["size"] + GAP))


def target_center(layout: dict[str, float]) -> tuple[float, float]:
    return 540.0, layout["top"] + layout["height"] + 60 + TARGET_SIZE / 2


def layout_of(item: RoundSpec) -> dict[str, float]:
    return grid_layout(item.data["rows"], item.data["cols"])


# ---------------------------------------------------------------- timing

def phases(item: RoundSpec) -> dict[str, float]:
    """A level's moments in seconds from its start."""
    data = item.data
    memorize_end = MEMORY_V8_ENTRANCE + float(data["memorize_seconds"])
    kind = data["kind"]
    first = memorize_end + (MEMORY_V8_COVER if kind == "where" else 0.0)
    length = memory_question_length(data)
    questions_end = first + data["question_count"] * length
    return {"memorize_end": memorize_end, "questions_start": first, "question_length": length, "questions_end": questions_end,
            "end": questions_end + MEMORY_V8_FINALE[kind]}


def question_times(item: RoundSpec) -> list[dict[str, float]]:
    """For every question: when it starts, when thinking starts and ends, and when its answer lands."""
    times = phases(item)
    thinking = float(item.data["thinking_seconds"])
    result = []
    for index in range(item.data["question_count"]):
        start = times["questions_start"] + index * times["question_length"]
        if item.data["kind"] == "where":
            result.append({"start": start, "think_start": start + .25, "think_end": start + .25 + thinking,
                           "answer": start + .5 + thinking})
        else:
            vanish = MEMORY_V8_VANISH[0]
            result.append({"start": start, "think_start": start + vanish, "think_end": start + vanish + thinking,
                           "answer": start + vanish + thinking})
    return result


def schedule(spec: VideoSpec) -> list[tuple[float, float]]:
    """(start, duration) of every level; bigger boards last longer."""
    result, start = [], spec.intro_duration
    for item in spec.rounds:
        duration = memory_level_round(item.data)
        result.append((start, duration))
        start += duration
    return result


def total_questions(spec: VideoSpec) -> int:
    return sum(item.data["question_count"] for item in spec.rounds)


# ---------------------------------------------------------------- sprites

def _mask(px: int, radius: int) -> Image.Image:
    big = 3
    mask = Image.new("L", (px * big, px * big), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, px * big - 1, px * big - 1), radius=radius * big, fill=255)
    return mask.resize((px, px), Image.Resampling.LANCZOS)


def _gradient(px: int, top: tuple, bottom: tuple) -> Image.Image:
    ramp = np.linspace(0, 1, px, dtype=np.float32)[:, None, None]
    colors = np.array(top, np.float32) * (1 - ramp) + np.array(bottom, np.float32) * ramp
    return Image.fromarray(np.repeat(colors, px, axis=1).astype(np.uint8)).convert("RGBA")


def _card(px: int, face: Image.Image) -> tuple[Image.Image, tuple[float, float]]:
    """A card standing on a slab, with a soft shadow under it. Returns the sprite and where the face's middle is in it."""
    margin, depth = round(px * .09), max(4, round(px * .05))
    out = Image.new("RGBA", (px + 2 * margin, px + 2 * margin + depth), (0, 0, 0, 0))
    mask = _mask(px, round(px * .16))
    shadow = Image.new("L", out.size, 0)
    shadow.paste(mask, (margin, margin + depth + round(px * .03)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(px * .035)).point(lambda value: value * 150 // 255)
    out.paste((0, 0, 0, 255), (0, 0), shadow)
    out.paste(Image.new("RGBA", (px, px), (9, 12, 36, 255)), (margin, margin + depth), mask)
    out.paste(face, (margin, margin), mask)
    return out, (margin + px / 2, margin + px / 2)


def _gloss(face: Image.Image, strength: int = 34) -> None:
    px = face.width
    shine = Image.new("L", face.size, 0)
    ImageDraw.Draw(shine).ellipse((-px * .15, -px * .6, px * 1.15, px * .4), fill=strength)
    face.paste(Image.new("RGBA", face.size, (255, 255, 255, 255)), (0, 0), shine)


@lru_cache(maxsize=96)
def _face_sprite(shape: str, color: str, px: int) -> tuple[Image.Image, tuple[float, float]]:
    base = _rgb(color)
    face = _gradient(px, _mix((43, 54, 128), base, .10), _mix((22, 28, 70), base, .10))
    halo = Image.new("L", face.size, 0)
    ImageDraw.Draw(halo).ellipse((px * .14, px * .14, px * .86, px * .86), fill=95)
    face.paste(Image.new("RGBA", face.size, base + (255,)), (0, 0), halo.filter(ImageFilter.GaussianBlur(px * .12)))
    token = token_image(shape, color, round(px * .72))
    face.alpha_composite(token, ((px - token.width) // 2, (px - token.height) // 2))
    _gloss(face)
    ImageDraw.Draw(face).rounded_rectangle((1, 1, px - 2, px - 2), radius=round(px * .16), outline=_mix(base, (90, 105, 190), .5) + (190,),
                                           width=max(2, round(px * .012)))
    return _card(px, face)


@lru_cache(maxsize=64)
def _cover_sprite(number: int, px: int, lit: bool) -> tuple[Image.Image, tuple[float, float]]:
    top, bottom = ((77, 240, 154), (22, 160, 100)) if lit else ((143, 114, 255), (74, 51, 200))
    face = _gradient(px, top, bottom)
    ImageDraw.Draw(face).text((px / 2, px / 2 + px * .02), str(number), font=font(round(px * .46)), fill=(255, 255, 255), anchor="mm")
    _gloss(face, 46)
    ImageDraw.Draw(face).rounded_rectangle((1, 1, px - 2, px - 2), radius=round(px * .16), outline=(255, 255, 255, 70),
                                           width=max(2, round(px * .012)))
    return _card(px, face)


@lru_cache(maxsize=32)
def _socket_sprite(number: int, px: int) -> tuple[Image.Image, tuple[float, float]]:
    face = _gradient(px, (12, 16, 44), (8, 11, 32))
    draw = ImageDraw.Draw(face)
    accent = _rgb(PALETTE["accent"])
    draw.rounded_rectangle((px * .05, px * .05, px * .95, px * .95), radius=round(px * .13), outline=accent + (210,),
                           width=max(3, round(px * .02)))
    draw.text((px / 2, px / 2 + px * .02), "?", font=font(round(px * .55)), fill=accent, anchor="mm")
    draw.text((px * .17, px * .14), str(number), font=font(round(px * .13)), fill=(150, 160, 205), anchor="mm")
    return _card(px, face)


def _place(image: Image.Image, sprite: tuple[Image.Image, tuple[float, float]], center: tuple[float, float], scale: float,
           width_factor: float = 1.0, zoom: float = 1.0, opacity: float = 1.0) -> None:
    picture, (ax, ay) = sprite
    width, height = max(1, round(picture.width * width_factor * zoom)), max(1, round(picture.height * zoom))
    if (width, height) != picture.size:
        picture = picture.resize((width, height), Image.Resampling.LANCZOS)
    if opacity < 1:
        picture = picture.copy()
        picture.putalpha(picture.getchannel("A").point(lambda value: round(value * opacity)))
    x = center[0] * scale - ax * width_factor * zoom
    y = center[1] * scale - ay * zoom
    image.paste(picture, (round(x), round(y)), picture)


def _flip(image: Image.Image, before, after, center: tuple[float, float], scale: float, progress: float) -> None:
    """Card flip: the first face narrows to nothing, then the second widens."""
    if progress < .5:
        _place(image, before, center, scale, max(.02, 1 - progress * 2))
    else:
        _place(image, after, center, scale, max(.02, (progress - .5) * 2))


def _glow(image: Image.Image, center: tuple[float, float], size: float, scale: float, strength: float, color: tuple[int, int, int]) -> None:
    if strength <= 0:
        return
    pad = round(46 * scale)
    side = round(size * scale) + 2 * pad
    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).rounded_rectangle((pad, pad, side - pad, side - pad), radius=round(size * .2 * scale), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(20 * scale)).point(lambda value: round(value * min(1.0, strength)))
    image.paste(Image.new("RGB", (side, side), color), (round(center[0] * scale - side / 2), round(center[1] * scale - side / 2)), mask)


# ---------------------------------------------------------------- the board

def _bob(position: int, local: float, amount: float = 4.0) -> float:
    return amount * math.sin(local * 2.4 + position * .9)


def _board(image: Image.Image, item: RoundSpec, local: float, scale: float) -> dict:
    """Draw the cards for this moment. Returns facts for the overlays: phase, question index, and so on."""
    data = item.data
    layout = layout_of(item)
    px = round(layout["size"] * scale)
    times = phases(item)
    questions = question_times(item)
    count = len(data["tokens"])
    faces = {token["position"]: _face_sprite(token["shape"], token["color_value"], px) for token in data["tokens"]}
    covers = {position: _cover_sprite(position, px, False) for position in range(1, count + 1)}
    centers = {position: card_center(layout, position) for position in range(1, count + 1)}
    info: dict = {"phase": "memorize", "layout": layout}
    if data["kind"] == "where":
        order = list(data["questions"])
        opened: set[int] = set()
        target = None
        if local < MEMORY_V8_ENTRANCE:
            info["phase"] = "entrance"
            for position in range(1, count + 1):
                _place(image, faces[position], centers[position], scale, zoom=max(.05, ease_out_back((local - (position - 1) * .04) / .28)))
        elif local < times["memorize_end"]:
            for position in range(1, count + 1):
                x, y = centers[position]
                _place(image, faces[position], (x, y + _bob(position, local)), scale)
        elif local < times["questions_start"]:
            info["phase"] = "cover"
            for position in range(1, count + 1):
                progress = _clamp((local - times["memorize_end"] - (position - 1) * .04) / .3)
                _flip(image, faces[position], covers[position], centers[position], scale, progress)
        elif local < times["questions_end"]:
            relative = local - times["questions_start"]
            index = min(len(order) - 1, int(relative / times["question_length"]))
            rel = relative - index * times["question_length"]
            reveal = .25 + float(data["thinking_seconds"])
            flipping = reveal + .25
            info.update(phase="question", question=index, relative=rel, target=order[index])
            if rel >= reveal:
                info["phase"] = "highlight" if rel < flipping else "answer"
            opened = set(order[:index]) | ({order[index]} if rel >= flipping + .225 else set())
            for position in range(1, count + 1):
                center = centers[position]
                if position == order[index] and rel >= reveal:
                    since = rel - reveal
                    _glow(image, center, layout["size"], scale, ease_in_out(since / .25), GREEN)
                    lit = _cover_sprite(position, px, True)
                    if rel < flipping:
                        _place(image, lit, center, scale, zoom=1 + .05 * ease_in_out(since / .25))
                    else:
                        _flip(image, lit, faces[position], center, scale, _clamp((rel - flipping) / .45))
                        if rel >= flipping + .45:
                            _snap_burst(image, center, layout["size"] * .9, rel - flipping - .45, scale)
                elif position in opened:
                    _place(image, faces[position], center, scale)
                else:
                    _place(image, covers[position], center, scale)
        else:
            relative = local - times["questions_end"]
            info.update(phase="finale", relative=relative)
            rest = [position for position in range(1, count + 1) if position not in order]
            for position in range(1, count + 1):
                if position in order:
                    _place(image, faces[position], centers[position], scale)
                else:
                    slot = rest.index(position)
                    progress = _clamp((relative - slot * .08) / .35)
                    _glow(image, centers[position], layout["size"], scale, (1 - progress) * .8, (124, 92, 255))
                    _flip(image, covers[position], faces[position], centers[position], scale, progress)
            if relative > .6:
                for position in range(1, count + 1):
                    _glow(image, centers[position], layout["size"], scale, .3 * (1 - _clamp((relative - .6) / .7)), GREEN)
                if relative < 1.2:
                    _snap_burst(image, (540, layout["top"] + layout["height"] / 2), layout["size"] * .8, relative - .6, scale)
        return info
    # ---- vanish: the board stays face up
    order = list(data["questions"])
    if local < MEMORY_V8_ENTRANCE:
        info["phase"] = "entrance"
        for position in range(1, count + 1):
            _place(image, faces[position], centers[position], scale, zoom=max(.05, ease_out_back((local - (position - 1) * .04) / .28)))
        return info
    vanish, reveal, hold = MEMORY_V8_VANISH
    if local < times["memorize_end"]:
        for position in range(1, count + 1):
            x, y = centers[position]
            _place(image, faces[position], (x, y + _bob(position, local)), scale)
        return info
    if local >= times["questions_end"]:
        relative = local - times["questions_end"]
        info.update(phase="finale", relative=relative)
        for position in range(1, count + 1):
            x, y = centers[position]
            _place(image, faces[position], (x, y + _bob(position, local, 3.0)), scale)
            _glow(image, centers[position], layout["size"], scale, .3 * (1 - _clamp(relative / MEMORY_V8_FINALE["vanish"])), GREEN)
        if relative < .6:
            _snap_burst(image, (540, layout["top"] + layout["height"] / 2), layout["size"] * .8, relative, scale)
        return info
    relative = local - times["questions_start"]
    index = min(len(order) - 1, int(relative / times["question_length"]))
    rel = relative - index * times["question_length"]
    target = order[index]
    thinking = float(data["thinking_seconds"])
    info.update(question=index, relative=rel, target=target)
    if rel < vanish:
        info["phase"] = "vanish"
    elif rel < vanish + thinking:
        info["phase"] = "think"
    else:
        info["phase"] = "reveal" if rel < vanish + thinking + reveal else "hold"
    for position in range(1, count + 1):
        x, y = centers[position]
        bobbed = (x, y + _bob(position, local, 3.0))
        if position != target:
            _place(image, faces[position], bobbed, scale)
            continue
        socket = _socket_sprite(position, px)
        if rel < vanish:  # the card shrinks and fades away over its socket
            progress = ease_in_out(rel / vanish)
            _place(image, socket, centers[position], scale, opacity=progress)
            _place(image, faces[position], bobbed, scale, zoom=max(.05, 1 - progress), opacity=1 - progress * .6)
        elif rel < vanish + thinking:
            pulse = .5 + .5 * math.sin(rel * 6)
            _glow(image, centers[position], layout["size"], scale, .22 + .18 * pulse, _rgb(PALETTE["accent"]))
            _place(image, socket, centers[position], scale)
        else:
            since = rel - vanish - thinking
            _place(image, socket, centers[position], scale, opacity=1 - _clamp(since / .2))
            _glow(image, centers[position], layout["size"], scale, ease_out_cubic(1 - _clamp(since / reveal)), GREEN)
            _place(image, faces[position], centers[position], scale, zoom=max(.05, ease_out_back(_clamp(since / .4))))
            if since > .3:
                _snap_burst(image, centers[position], layout["size"] * .9, since - .3, scale)
    return info


# ---------------------------------------------------------------- the rest of the frame

def _pill(image: Image.Image, text: str, scale: float, opacity: float = 1.0, color: str | None = None) -> None:
    if opacity <= 0:
        return
    face = fitted_font(text, round(860 * scale), round(56 * scale))
    width = ImageDraw.Draw(image).textlength(text, font=face) + 96 * scale
    height = 92 * scale
    y = PILL_Y * scale
    rounded_surface(image, (540 * scale - width / 2, y - height / 2, 540 * scale + width / 2, y + height / 2), height / 2,
                    _rgb(color or PALETTE["accent"]) + (round(255 * opacity),))
    _text(image, (540 * scale, y - 2 * scale), text, face, PALETTE["background"], opacity)


def _target(image: Image.Image, token: dict, layout: dict, relative: float, scale: float) -> None:
    """The shape to find, in a glowing card under the board."""
    amount = ease_out_back(_clamp(relative / .25))
    if amount <= 0:
        return
    cx, cy = target_center(layout)
    size = round(TARGET_SIZE * scale)
    card = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rounded_surface(card, (0, 0, size, size), 44 * scale, "#20295A", PALETTE["accent"], 4 * scale)
    sprite = token_image(token["shape"], token["color_value"], round(size * .8))
    card.alpha_composite(sprite, ((size - sprite.width) // 2, (size - sprite.height) // 2))
    halo = Image.new("L", (size + round(80 * scale),) * 2, 0)
    pad = round(40 * scale)
    ImageDraw.Draw(halo).rounded_rectangle((pad, pad, pad + size, pad + size), radius=round(52 * scale), fill=150)
    halo = halo.filter(ImageFilter.GaussianBlur(20 * scale))
    image.paste(Image.new("RGB", halo.size, PALETTE["accent"]),
                (round(cx * scale - halo.width / 2), round(cy * scale - halo.height / 2)), halo.point(lambda v: round(v * _clamp(amount))))
    width = max(1, round(size * max(.05, amount)))
    resized = card.resize((width, width), Image.Resampling.LANCZOS)
    image.paste(resized, (round(cx * scale - width / 2), round(cy * scale - width / 2)), resized)


def _dots(image: Image.Image, total: int, done: int, y: float, scale: float) -> None:
    """One dot per question: filled when answered, a ring for the current one."""
    draw = ImageDraw.Draw(image, "RGBA")
    radius, gap = 11 * scale, 34 * scale
    start = 540 * scale - (total - 1) * gap / 2
    for index in range(total):
        x = start + index * gap
        if index < done:
            draw.ellipse((x - radius, y * scale - radius, x + radius, y * scale + radius), fill=_rgb(PALETTE["success"]) + (255,))
        elif index == done:
            draw.ellipse((x - radius, y * scale - radius, x + radius, y * scale + radius), outline=_rgb(PALETTE["accent"]) + (255,),
                         width=max(2, round(3 * scale)))
        else:
            draw.ellipse((x - radius * .7, y * scale - radius * .7, x + radius * .7, y * scale + radius * .7),
                         fill=_rgb(PALETTE["surface_edge"]) + (255,))


def draw_level(spec: VideoSpec, index: int, local: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[index]
    data = item.data
    times = phases(item)
    image = _background(size, CENTER_Y, active_theme()).copy()
    info = _board(image, item, local, scale)
    layout = info["layout"]
    phase = info["phase"]
    kind = data["kind"]
    thinking = float(data["thinking_seconds"])
    memorize = float(data["memorize_seconds"])
    questions = question_times(item)
    _level_header(image, data["level"], spec.round_count, _clamp(local / .25), scale)
    n = len(data["tokens"])
    if phase in ("entrance", "memorize"):
        remaining = memorize if phase == "entrance" else times["memorize_end"] - local
        _timer(image, remaining, memorize, _clamp(local / .3), scale, show_seconds=False)  # a bar only while memorizing
        _pill(image, "MEMORIZE", scale, _clamp(local / .25))
    elif phase == "cover":
        _pill(image, "MEMORIZE", scale, 1 - _clamp((local - times["memorize_end"]) / .3))
    elif phase == "finale":
        text = f"ALL {n}." if kind == "where" else "SHARP EYES."
        _pill(image, text, scale, _clamp(info["relative"] / .25), PALETTE["success"])
    else:
        question = info["question"]
        window = questions[question]
        relative = info["relative"]
        total = data["question_count"]
        if kind == "where":
            _pill(image, "WHERE WAS IT?", scale)
            _target(image, data["tokens"][info["target"] - 1], layout, relative, scale)
            dots_y = target_center(layout)[1] + TARGET_SIZE / 2 + 52
            if phase == "question":
                _timer(image, window["think_end"] - times["questions_start"] - question * times["question_length"] - relative, thinking, 1.0, scale)
        else:
            if phase in ("reveal", "hold"):
                _pill(image, "THERE IT IS.", scale, 1.0, PALETTE["success"])
            else:
                _pill(image, "WHAT VANISHED?", scale)
            dots_y = layout["top"] + layout["height"] + 70
            if phase == "think":
                _timer(image, MEMORY_V8_VANISH[0] + thinking - relative, thinking, 1.0, scale)
        _dots(image, total, question + (1 if phase in ("answer", "reveal", "hold") else 0), dots_y, scale)
    if local < .2 and index > 0:
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (round(200 * (1 - _clamp(local / .2))),))
        image.paste(overlay, (0, 0), overlay)
    if local > times["end"] - .2 and index < spec.round_count - 1:
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (round(200 * ease_in_out((local - (times["end"] - .2)) / .2)),))
        image.paste(overlay, (0, 0), overlay)
    return image


def draw_levels_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook: a fixed concept board (never a real level): face-down cards and three demo shapes."""
    scale = size[0] / 1080
    image = _background(size, CENTER_Y, active_theme()).copy()
    layout = grid_layout(3, 3)
    px = round(layout["size"] * scale)
    for position in range(1, 10):
        zoom = max(.05, ease_out_back((t - (position - 1) * .03) / .3))
        if position in CONCEPT:
            shape, color = CONCEPT[position]
            sprite = _face_sprite(shape, color, px)
        else:
            sprite = _cover_sprite(position, px, False)
        _place(image, sprite, card_center(layout, position), scale, zoom=zoom)
    from .ready import hook_end
    fade = 1 - _clamp((t - (hook_end(spec) - .22)) / .22)
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .18)))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(940 * scale), round(84 * scale)),
          PALETTE["text_light"], fade * _clamp(t / .08 + .3), slam)
    _text(image, (540 * scale, 232 * scale), f"{spec.round_count} LEVELS · EACH ONE BIGGER", font(round(36 * scale)),
          PALETTE["accent"], fade * _clamp((t - .15) / .2))
    return image


def draw_levels_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        from .ready import HOOK_SECONDS, draw_ready_screen, has_ready
        if has_ready(spec) and t >= HOOK_SECONDS:
            return draw_ready_screen(spec, t - HOOK_SECONDS, size).convert("RGB")
        return draw_levels_intro(spec, t, size).convert("RGB")
    levels = schedule(spec)
    rounds_end = levels[-1][0] + levels[-1][1]
    if t >= rounds_end - 1e-9:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size, total=total_questions(spec)).convert("RGB")
    index = max(position for position, (start, _) in enumerate(levels) if t >= start - 1e-9)
    return draw_level(spec, index, t - levels[index][0], size).convert("RGB")
