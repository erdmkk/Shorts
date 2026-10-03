"""Puzzle Fit V12 frames: one big picture with three lettered holes, six tilted numbered options below.

Screen (logical 1080x1920): `3 MISSING PIECES` and the numeric timer at the top; the picture (4x3 pieces, 820x615 px)
with holes marked A, B, C; a large `FIND THE MISSING PIECES` pill; six option cards (3x2), each piece tilted and
numbered; `Comment like A4 B1 C6`. Reveal: the traps dim, then A, B and C fly in one after another, straighten and click
into place, the finished picture shines, and the answer (`A4 · B1 · C6`) appears in green.
"""
from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..config import FIT_CLEAR, FIT_ENTRANCE, FIT_PLACE, FIT_SHINE, PUZZLE_FIT_PALETTE as PALETTE
from ..models import RoundSpec, VideoSpec
from ..puzzles.puzzle_fit_v12 import LETTERS
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .jigsaw import piece_points
from .puzzle_fit import _background, _hole_dashes, _snap_burst, _text, _timer, active_theme, draw_puzzle_fit_outro
from .scenes import scene
from .text import fitted_font, font

HEADER = "3 MISSING PIECES"
PROMPT = "FIND THE MISSING PIECES"
HOOK_TEXT = "FIND THE MISSING PIECES."
OUTLINE = (11, 16, 32)
CELL, LEFT, TOP = 205.0, 130.0, 300.0
TAB = CELL / 4.3
MARGIN = TAB + 10
OPTION_FACTOR = .66  # options are drawn smaller than the picture, so six fit under it
OPTION_CENTERS = [(x, y) for y in (1250, 1550) for x in (215, 540, 865)]
PROMPT_Y = 1035
COMMENT_Y = 1770
COVER_TIME = 0.6


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def phases(item: RoundSpec) -> dict[str, float]:
    think_end = FIT_ENTRANCE + float(item.data["thinking_seconds"])
    place = think_end + FIT_CLEAR
    shine = place + 3 * FIT_PLACE
    return {"think_end": think_end, "place": place, "shine": shine, "shine_end": shine + FIT_SHINE}


def slot_center(slot: int) -> tuple[float, float]:
    row, column = divmod(slot, 4)
    return LEFT + (column + .5) * CELL, TOP + (row + .5) * CELL


def order(data: dict) -> list[int]:
    """Option indexes of the missing pieces A, B, C."""
    return [next(index for index, option in enumerate(data["options"]) if option["hole"] == letter) for letter in LETTERS]


# ---------------------------------------------------------------- sprites

def _art(data: dict, scale: float) -> Image.Image:
    width = round((4 * CELL + 2 * MARGIN) * scale)
    height = round((3 * CELL + 2 * MARGIN) * scale)
    return scene(data["scene"], int(data["scene_seed"]), width, height)


@lru_cache(maxsize=64)
def _mask(cell_px: float, margin_px: float, tab_px: float, edges: tuple[int, ...]) -> Image.Image:
    side = round(cell_px + 2 * margin_px)
    high = Image.new("L", (side * 2, side * 2), 0)
    bounds = (margin_px * 2, margin_px * 2, (margin_px + cell_px) * 2, (margin_px + cell_px) * 2)
    ImageDraw.Draw(high).polygon(piece_points(bounds, list(edges), tab_px * 2), fill=255)
    return high.resize((side, side), Image.Resampling.LANCZOS)


@lru_cache(maxsize=64)
def _sprite(scene_key: tuple, slot: int, edges: tuple[int, ...], scale: float) -> Image.Image:
    """The picture at `slot`, cut with `edges`, with a soft bevel and a thin dark outline."""
    art = scene(scene_key[0], scene_key[1], round((4 * CELL + 2 * MARGIN) * scale), round((3 * CELL + 2 * MARGIN) * scale))
    row, column = divmod(slot, 4)
    mask = _mask(CELL * scale, MARGIN * scale, TAB * scale, edges)
    x, y = round(column * CELL * scale), round(row * CELL * scale)
    crop = art.crop((x, y, x + mask.width, y + mask.height)).convert("RGBA")
    bevel = max(1, round(3 * scale))
    light = ImageChops.subtract(mask, ImageChops.offset(mask, bevel, bevel))
    dark = ImageChops.subtract(mask, ImageChops.offset(mask, -bevel, -bevel))
    crop.paste((255, 255, 255, 255), (0, 0), light.point(lambda value: value * 70 // 255))
    crop.paste((0, 0, 0, 255), (0, 0), dark.point(lambda value: value * 80 // 255))
    ring = ImageChops.subtract(mask, mask.filter(ImageFilter.MinFilter(2 * max(1, round(2.5 * scale)) + 1)))
    crop.paste(OUTLINE + (255,), (0, 0), ring)
    crop.putalpha(mask)
    return crop


def _halo(sprite: Image.Image, scale: float) -> Image.Image:
    pad = max(2, round(12 * scale))
    out = Image.new("RGBA", (sprite.width + 2 * pad, sprite.height + 2 * pad), (0, 0, 0, 0))
    alpha = Image.new("L", out.size, 0)
    alpha.paste(sprite.getchannel("A"), (pad, pad))
    glow = alpha.filter(ImageFilter.MaxFilter(2 * max(1, round(3 * scale)) + 1)).filter(ImageFilter.GaussianBlur(max(1, 5 * scale)))
    out.paste((226, 232, 255, 255), (0, 0), glow.point(lambda value: value * 110 // 255))
    out.alpha_composite(sprite, (pad, pad))
    return out


def option_sprite(data: dict, option: dict, scale: float) -> Image.Image:
    """An option in board orientation (its base edges), with a light halo; turning and tilting happen on paste."""
    return _halo(_sprite((data["scene"], int(data["scene_seed"])), option["art_slot"], tuple(option["base"]), round(scale, 4)), scale)


def option_angle(option: dict) -> float:
    """On-screen clockwise angle of an option: its quarter turns plus its tilt."""
    return 90.0 * option["turns"] + float(option["tilt"])


def _paste(image: Image.Image, sprite: Image.Image, center: tuple[float, float], factor: float = 1.0,
           opacity: float = 1.0, clockwise: float = 0.0) -> None:
    if factor <= 0 or opacity <= 0:
        return
    if factor != 1:
        sprite = sprite.resize((max(1, round(sprite.width * factor)), max(1, round(sprite.height * factor))), Image.Resampling.LANCZOS)
    if clockwise % 360:
        sprite = sprite.rotate(-clockwise, resample=Image.Resampling.BICUBIC, expand=True)
    if opacity < 1:
        sprite = sprite.copy()
        sprite.putalpha(sprite.getchannel("A").point(lambda value: round(value * opacity)))
    image.alpha_composite(sprite, (round(center[0] - sprite.width / 2), round(center[1] - sprite.height / 2)))


# ---------------------------------------------------------------- board

def _hole_points(data: dict, slot: int, scale: float) -> list[tuple[float, float]]:
    row, column = divmod(slot, 4)
    x1, y1 = (LEFT + column * CELL) * scale, (TOP + row * CELL) * scale
    return piece_points((x1, y1, x1 + CELL * scale, y1 + CELL * scale), data["piece_edges"][slot], TAB * scale)


_ROUNDS: dict[str, RoundSpec] = {}


@lru_cache(maxsize=4)
def _board_layer(key: str, size: tuple[int, int], theme: str) -> Image.Image:
    """Background and the picture with its three dark holes: static for the whole video."""
    data = _ROUNDS[key].data
    scale = size[0] / 1080
    image = _background(size, 610, theme).convert("RGBA")
    card = (LEFT - 45, TOP - 45, LEFT + 4 * CELL + 45, TOP + 3 * CELL + 45)
    rounded_surface(image, tuple(value * scale for value in card), 48 * scale, PALETTE["surface"], PALETTE["surface_edge"],
                    3 * scale, shadow=True)
    for slot, edges in enumerate(data["piece_edges"]):
        if slot in data["holes"]:
            continue
        sprite = _sprite((data["scene"], int(data["scene_seed"])), slot, tuple(edges), round(scale, 4))
        x, y = slot_center(slot)
        _paste(image, sprite, (x * scale, y * scale))
    for slot in data["holes"]:
        ImageDraw.Draw(image).polygon(_hole_points(data, slot, scale), fill=_rgb(PALETTE["hole"]))
    return image


def _register(spec: VideoSpec) -> str:
    from .puzzle_fit import _palette_key
    key = _palette_key(f"{spec.id}:{spec.rounds[0].fingerprint()}")
    _ROUNDS[key] = spec.rounds[0]
    return key


def _letter(image: Image.Image, slot: int, letter: str, scale: float, solved: bool = False, opacity: float = 1.0) -> None:
    x, y = slot_center(slot)
    r = 46 * scale
    fill = PALETTE["success"] if solved else PALETTE["accent"]
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((x * scale - r, y * scale - r, x * scale + r, y * scale + r), fill=_rgb(fill) + (round(255 * opacity),),
                 outline=OUTLINE + (round(255 * opacity),), width=max(1, round(4 * scale)))
    _text(image, (x * scale, (y - 2) * scale), letter, font(round(56 * scale)), PALETTE["background"], opacity)


def _option_card(image: Image.Image, center: tuple[float, float], number: int, scale: float, state: str = "idle",
                 opacity: float = 1.0, letter: str | None = None) -> None:
    x, y = center
    edge = PALETTE["success"] if state == "right" else PALETTE["surface_edge"]
    rounded_surface(image, ((x - 148) * scale, (y - 138) * scale, (x + 148) * scale, (y + 138) * scale), 34 * scale,
                    _rgb(PALETTE["surface"]) + (round(190 * opacity),), outline=_rgb(edge) + (round(255 * opacity),),
                    width=max(1, round((5 if state == "right" else 3) * scale)))
    by, r = (y + 138) * scale, 36 * scale
    badge = PALETTE["success"] if state == "right" else PALETTE["accent"]
    draw = ImageDraw.Draw(image, "RGBA")
    draw.ellipse((x * scale - r, by - r, x * scale + r, by + r), fill=_rgb(badge) + (round(255 * opacity),),
                 outline=OUTLINE + (round(255 * opacity),), width=max(1, round(4 * scale)))
    label = f"{number}" if not letter else f"{number}={letter}"
    face = font(round((44 if not letter else 34) * scale))
    if letter:
        width = ImageDraw.Draw(image).textlength(label, font=face) + 34 * scale
        rounded_surface(image, (x * scale - width / 2, by - r, x * scale + width / 2, by + r), r, _rgb(badge) + (255,),
                        outline=OUTLINE + (255,), width=max(1, round(4 * scale)))
    _text(image, (x * scale, by - 2 * scale), label, face, PALETTE["background"], opacity)


def _prompt(image: Image.Image, scale: float, opacity: float = 1.0, pulse: float = 0.0) -> None:
    if opacity <= 0:
        return
    face = fitted_font(PROMPT, round(860 * scale), round((56 + 4 * pulse) * scale))
    width = ImageDraw.Draw(image).textlength(PROMPT, font=face) + 90 * scale
    height = 96 * scale
    y = PROMPT_Y * scale
    rounded_surface(image, (540 * scale - width / 2, y - height / 2, 540 * scale + width / 2, y + height / 2), height / 2,
                    _rgb(PALETTE["accent"]) + (round(255 * opacity),))
    _text(image, (540 * scale, y - 2 * scale), PROMPT, face, PALETTE["background"], opacity)


def _shine(image: Image.Image, progress: float, scale: float) -> None:
    if not 0 < progress < 1:
        return
    box = tuple(round(value * scale) for value in (LEFT - MARGIN, TOP - MARGIN, LEFT + 4 * CELL + MARGIN, TOP + 3 * CELL + MARGIN))
    width, height = box[2] - box[0], box[3] - box[1]
    band = Image.new("L", (width, height), 0)
    x = -width * .4 + width * 1.8 * progress
    ImageDraw.Draw(band).polygon(((x, 0), (x + width * .16, 0), (x - width * .04, height), (x - width * .2, height)),
                                 fill=round(110 * math.sin(progress * math.pi)))
    band = band.filter(ImageFilter.GaussianBlur(max(1, 16 * scale)))
    region = image.crop(box)
    region.alpha_composite(Image.merge("RGBA", (Image.new("L", band.size, 255),) * 3 + (band,)))
    image.paste(region, box[:2])


def _frame(spec: VideoSpec, local: float, size: tuple[int, int], hook: bool = False) -> Image.Image:
    scale = size[0] / 1080
    item = spec.rounds[0]
    data = item.data
    image = _board_layer(_register(spec), size, active_theme()).copy()
    times = phases(item)
    answers = order(data)
    thinking = float(data["thinking_seconds"])
    placing = local >= times["place"] and not hook
    placed = [position for position, _ in enumerate(answers) if not hook and local >= times["place"] + (position + 1) * FIT_PLACE]
    if hook or local < times["think_end"]:
        for slot in data["holes"]:
            _hole_dashes(image, _hole_points(data, slot, scale), PALETTE["accent"], max(1, round(4 * scale)), local * 70 * scale)
    for position, (letter, slot) in enumerate(zip(LETTERS, data["holes"])):
        if position not in placed:
            _letter(image, slot, letter, scale)
    # Options.
    for index, (cx, cy) in enumerate(OPTION_CENTERS):
        option = data["options"][index]
        pop = 1.0 if hook else ease_out_back(_clamp((local - .1 - index * .06) / .35))
        opacity, state, letter = 1.0, "idle", None
        if not hook and local >= times["think_end"]:
            if option["hole"] is None:
                opacity = 1 - .7 * _clamp((local - times["think_end"]) / FIT_CLEAR)
            elif answers.index(index) in placed:
                state, letter = "right", option["hole"]
        _option_card(image, (cx, cy), index + 1, scale, state, opacity, letter)
        flying_or_placed = placing and index in answers and local >= times["place"] + answers.index(index) * FIT_PLACE
        if not flying_or_placed:
            _paste(image, option_sprite(data, option, scale), (cx * scale, (cy - 12) * scale), OPTION_FACTOR * max(.01, pop),
                   opacity, option_angle(option))
    # Missing pieces fly in one after another, straighten, and click.
    if placing:
        for position, index in enumerate(answers):
            start = times["place"] + position * FIT_PLACE
            if local < start:
                continue
            option = data["options"][index]
            p = ease_in_out(_clamp((local - start) / (FIT_PLACE * .8)))
            (cx, cy), (hx, hy) = OPTION_CENTERS[index], slot_center(data["holes"][position])
            x, y = cx + (hx - cx) * p, (cy - 12) + (hy - cy + 12) * p - math.sin(p * math.pi) * 60
            # Turn the short way home: the stored base orientation is the fitting one.
            angle = option_angle(option) % 360
            angle = angle - 360 if angle > 180 else angle
            settle = 1.0
            if local >= start + FIT_PLACE * .8:
                settle = 1 + .06 * (1 - ease_out_cubic(_clamp((local - start - FIT_PLACE * .8) / .2)))
            sprite = option_sprite(data, option, scale)
            _paste(image, sprite, (x * scale, y * scale), (OPTION_FACTOR + (1 - OPTION_FACTOR) * p) * settle, 1.0, angle * (1 - p))
            if local >= start + FIT_PLACE * .8:
                _snap_burst(image, (hx, hy), CELL, local - start - FIT_PLACE * .8, scale)
    if not hook and local >= times["shine"]:
        _shine(image, (local - times["shine"]) / FIT_SHINE, scale)
    # Header, timer, prompt, and the comment line.
    if hook:
        slam = 1 + .35 * (1 - ease_out_cubic(_clamp(local / .18)))
        _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(960 * scale), round(76 * scale)),
              PALETTE["text_light"], _clamp(local / .08 + .3), slam)
        _text(image, (540 * scale, 232 * scale), "3 PIECES · 6 CHOICES", font(round(38 * scale)), PALETTE["accent"],
              _clamp((local - .15) / .2))
    else:
        _text(image, (540 * scale, 150 * scale), HEADER, font(round(60 * scale)), PALETTE["text_light"])
        if local < times["think_end"]:
            remaining = times["think_end"] - local
            _timer(image, min(thinking, remaining), thinking, _clamp(local / .25), scale)
    if hook or local < times["think_end"]:
        remaining = times["think_end"] - local
        _prompt(image, scale, 1.0 if hook else _clamp(local / .2), abs(math.sin(local * math.pi)) * (1 if not hook and remaining < 3 else 0))
        _text(image, (540 * scale, COMMENT_Y * scale), "Comment like A4 B1 C6 ↓", font(round(44 * scale)), PALETTE["text_light"])
    else:
        _text(image, (540 * scale, PROMPT_Y * scale), "SOLUTION", font(round(52 * scale)), PALETTE["text_muted"])
        if local >= times["shine"]:
            answer = "  ·  ".join(f"{letter} = {number}" for letter, number in
                                  ((part[0], part[1:]) for part in item.answer.split()))
            _text(image, (540 * scale, COMMENT_Y * scale), answer, font(round(56 * scale)), PALETTE["success"],
                  _clamp((local - times["shine"]) / .3))
    return image


def draw_fit_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        return _frame(spec, t, size, hook=True).convert("RGB")
    end = spec.intro_duration + spec.round_duration
    if t >= end:
        return draw_puzzle_fit_outro(spec, t - end, size, total=3)
    return _frame(spec, t - spec.intro_duration, size).convert("RGB")


def fit_cover_card(spec: VideoSpec, scale: float) -> Image.Image:
    """Cover card at `scale`: the picture with its lettered holes, and four of the tilted numbered options under it."""
    data = spec.rounds[0].data
    size = (round(1080 * scale), round(1920 * scale))
    frame = _frame(spec, 0.0, size, hook=True)
    top = frame.crop(tuple(round(value * scale) for value in (LEFT - 45, TOP - 45, LEFT + 4 * CELL + 45, TOP + 3 * CELL + 45)))
    card = Image.new("RGBA", (round(920 * scale), round(1000 * scale)), _rgb(PALETTE["background"]) + (255,))
    top = top.resize((round(880 * scale), round(880 * scale * top.height / top.width)), Image.Resampling.LANCZOS)
    card.alpha_composite(top, (round(20 * scale), round(20 * scale)))
    y = 20 * scale + top.height + 150 * scale
    for position in range(4):
        option = data["options"][position]
        x = (130 + position * 220) * scale
        _paste(card, option_sprite(data, option, scale), (x, y), .56, 1.0, option_angle(option))
        r = 32 * scale
        draw = ImageDraw.Draw(card)
        draw.ellipse((x - r, y + 110 * scale - r, x + r, y + 110 * scale + r), fill=_rgb(PALETTE["accent"]), outline=OUTLINE,
                     width=max(1, round(4 * scale)))
        _text(card, (x, y + 108 * scale), str(position + 1), font(round(40 * scale)), PALETTE["background"])
    return card.crop((0, 0, card.width, round(y + 160 * scale)))
