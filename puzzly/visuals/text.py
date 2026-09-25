from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

WINDOWS_FONTS = Path("C:/Windows/Fonts")
DISPLAY_FONT_FILES = ("Inkfree.ttf", "segoeprb.ttf", "comicbd.ttf")


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


@lru_cache(maxsize=64)
def display_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = tuple(WINDOWS_FONTS / name for name in DISPLAY_FONT_FILES) + (
        WINDOWS_FONTS / "seguisb.ttf",
        Path("DejaVuSans-Bold.ttf"),
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


@lru_cache(maxsize=64)
def strong_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Clean heavy UI face for calls to action (Segoe UI Bold, then Arial Bold, then DejaVu)."""
    for candidate in (WINDOWS_FONTS / "segoeuib.ttf", WINDOWS_FONTS / "arialbd.ttf", Path("DejaVuSans-Bold.ttf")):
        try:
            return ImageFont.truetype(str(candidate), size=size)
        except OSError:
            continue
    return font(size)


def draw_cta(
    image: Image.Image, center: tuple[int, int], size: int, fill: str,
    outline: str, opacity: int = 255, text: str = "Follow for more",
) -> None:
    """Draw the end-of-video call to action as a solid pill button: `fill` is the pill, `outline` the label."""
    from .effects import rounded_surface

    opacity = max(0, min(255, opacity))
    if opacity == 0:
        return
    probe = ImageDraw.Draw(image)
    max_text = image.width * 0.62
    size = max(8, size)
    while size > 8 and probe.textlength(text, font=strong_font(size)) > max_text:
        size -= 2
    face = strong_font(size)
    text_width = probe.textlength(text, font=face)
    half_w, half_h = text_width / 2 + size * .95, size * .95
    x, y = center
    rounded_surface(image, (x - half_w, y - half_h, x + half_w, y + half_h), half_h, fill,
                    shadow=True, opacity=opacity)
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((x, y + size * .02), text, font=face, fill=outline, anchor="mm")
    if opacity < 255:
        layer.putalpha(layer.getchannel("A").point(lambda value: value * opacity // 255))
    image.paste(layer, (0, 0), layer)
