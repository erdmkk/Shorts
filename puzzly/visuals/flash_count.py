from __future__ import annotations

from PIL import Image, ImageDraw

from ..config import (FLASH_APPEARANCE_DURATION, FLASH_HIDE_DURATION, FLASH_REVEAL_DURATION,
                      FLASH_THINKING_DURATION)
from ..models import RoundSpec, VideoSpec
from .easing import ease_in_out, ease_out_back
from .effects import draw_progress_bar, draw_sparkles, rounded_surface
from .layout import scale_point
from .memory import token_image
from .text import display_font, font

INTRO_POSITIONS = ((315, 500), (575, 470), (785, 590), (265, 780), (515, 735), (755, 850))
COVER_BOUNDS = (115, 280, 965, 1380)


def _scaled(value: float, size: tuple[int, int]) -> int:
    return max(1, round(value * size[0] / 1080))


def _bounds(values: tuple[float, float, float, float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    first = scale_point((values[0], values[1]), size)
    second = scale_point((values[2], values[3]), size)
    return first[0], first[1], second[0], second[1]


def _paste(image: Image.Image, shape: str, color: str, center: tuple[int, int], logical_size: int,
           amount: float = 1.0) -> None:
    size = _scaled(logical_size * max(.06, amount), image.size)
    asset = token_image(shape, color, size)
    x, y = scale_point(center, image.size)
    image.paste(asset, (x - size // 2, y - size // 2), asset)


def flash_state(local: float, visible_seconds: float = 1.20) -> str:
    visible_end = FLASH_APPEARANCE_DURATION + visible_seconds
    hidden_at = visible_end + FLASH_HIDE_DURATION
    thinking_end = hidden_at + FLASH_THINKING_DURATION
    revealed_at = thinking_end + FLASH_REVEAL_DURATION
    if local < FLASH_APPEARANCE_DURATION:
        return "appearance"
    if local < visible_end:
        return "visible"
    if local < hidden_at:
        return "hiding"
    if local < thinking_end:
        return "thinking"
    if local < revealed_at:
        return "revealing"
    return "solved"


def draw_flash_intro(image: Image.Image, spec: VideoSpec, t: float, palette: dict[str, str]) -> None:
    identity = spec.rounds[0].data
    amount = ease_out_back(t / FLASH_APPEARANCE_DURATION)
    draw = ImageDraw.Draw(image)
    draw.text(scale_point((540, 250), image.size), "How many?", font=display_font(_scaled(70, image.size)),
              fill=palette["text_dark"], anchor="mm")
    for center in INTRO_POSITIONS:
        _paste(image, identity["shape_id"], identity["color_value"], center, 176, amount)


def draw_flash_round(image: Image.Image, item: RoundSpec, local: float, palette: dict[str, str]) -> None:
    data = item.data
    visible_seconds = float(data["visible_seconds"])
    state = flash_state(local, visible_seconds)
    if state == "appearance":
        amount = ease_out_back(local / FLASH_APPEARANCE_DURATION)
    else:
        amount = 1.0
    for position in data["positions"]:
        _paste(image, data["shape_id"], data["color_value"], tuple(position), data["token_size"], amount)

    visible_end = FLASH_APPEARANCE_DURATION + visible_seconds
    hidden_at = visible_end + FLASH_HIDE_DURATION
    thinking_end = hidden_at + FLASH_THINKING_DURATION
    revealed_at = thinking_end + FLASH_REVEAL_DURATION
    cover_scale = 0.0
    if state == "hiding":
        cover_scale = ease_in_out((local - visible_end) / FLASH_HIDE_DURATION)
    elif state == "thinking":
        cover_scale = 1.0
    elif state == "revealing":
        cover_scale = 1.0 - ease_in_out((local - thinking_end) / FLASH_REVEAL_DURATION)
    if cover_scale > .01:
        x1, y1, x2, y2 = COVER_BOUNDS
        cy = (y1 + y2) / 2
        half_height = (y2 - y1) * cover_scale / 2
        rounded_surface(image, _bounds((x1, cy - half_height, x2, cy + half_height), image.size),
                        _scaled(58 * min(1, cover_scale * 2), image.size), palette["surface"],
                        palette["outline"], _scaled(6, image.size), shadow=True)
        if cover_scale > .72:
            ImageDraw.Draw(image).text(scale_point((540, 830), image.size), "?",
                                       font=font(_scaled(190, image.size)), fill=palette["primary"], anchor="mm")
    if state == "thinking":
        progress = 1 - (local - hidden_at) / FLASH_THINKING_DURATION
        draw_progress_bar(image, _bounds((245, 1510, 835, 1532), image.size), progress,
                          palette["background_2"], palette["primary"])
    if state == "solved":
        reveal_age = local - revealed_at
        bounce = ease_out_back(reveal_age / .28)
        ImageDraw.Draw(image).text(scale_point((540, 1510), image.size), str(item.answer),
                                   font=font(_scaled(132 * max(.1, bounce), image.size)),
                                   fill=palette["primary"], anchor="mm")
        draw_sparkles(ImageDraw.Draw(image), image.size, palette["accent"], reveal_age / .65)
