from __future__ import annotations

from functools import lru_cache
from PIL import Image, ImageDraw


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


@lru_cache(maxsize=32)
def _cached_background(size: tuple[int, int], colors: tuple[str, ...], variant: int) -> Image.Image:
    w, h = size
    background, background_2, primary, lavender, accent, secondary, outline = colors
    top, bottom = _rgb(background), _rgb(background_2)
    line = Image.new("RGB", (1, h))
    line.putdata([tuple(round(top[channel] + (bottom[channel] - top[channel]) * row / max(1, h - 1)) for channel in range(3)) for row in range(h)])
    image = line.resize((w, h))
    draw = ImageDraw.Draw(image, "RGBA")
    s = w / 1080
    decorations = (
        ((-170, 180, 300, 650), primary),
        ((820, 1320, 1210, 1800), lavender),
    ) if variant % 2 == 0 else (
        ((800, 110, 1210, 520), accent),
        ((-180, 1360, 260, 1840), secondary),
    )
    for bounds, color in decorations:
        draw.ellipse(tuple(int(value * s) for value in bounds), fill=color + "24")
    for x, y in ((80, 340), (980, 690), (90, 1080), (965, 1160), (160, 1660), (900, 1770)):
        px, py, radius = int(x * s), int(y * h / 1920), max(2, int(7 * s))
        draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=outline + "22")
    return image


def create_background(size: tuple[int, int], palette: dict[str, str], variant: int = 0) -> Image.Image:
    colors = (palette["background"], palette["background_2"],
              palette.get("background_accent", palette["primary"]),
              palette.get("background_accent_2", palette["lavender"]),
              palette["accent"], palette["secondary"], palette["outline"])
    return _cached_background(size, colors, variant).copy()
