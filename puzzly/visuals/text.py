from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from PIL import ImageFont

WINDOWS_FONTS = Path("C:/Windows/Fonts")


@lru_cache(maxsize=64)
def font(size: int, weight: str = "bold") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    bold = weight in ("bold", "semibold")
    candidates = (
        WINDOWS_FONTS / ("seguisb.ttf" if bold else "segoeui.ttf"),
        WINDOWS_FONTS / ("arialbd.ttf" if bold else "arial.ttf"),
        Path("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def fitted_font(text: str, max_width: int, start_size: int, minimum: int = 24):
    from PIL import Image, ImageDraw
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(start_size, minimum - 1, -2):
        candidate = font(size)
        if draw.textbbox((0, 0), text, font=candidate)[2] <= max_width:
            return candidate
    return font(minimum)
