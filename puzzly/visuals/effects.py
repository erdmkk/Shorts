from __future__ import annotations

import math
from functools import lru_cache
from PIL import Image, ImageColor, ImageDraw, ImageFilter


@lru_cache(maxsize=512)
def _surface_patch(
    patch_size: tuple[int, int], shape: tuple[int, int, int, int], radius_px: int,
    rgba_fill: tuple[int, ...], rgba_outline: tuple[int, ...] | None, border_px: int,
    shadow: bool, blur_px: float, offset_px: int, local_scale: int,
) -> Image.Image:
    high = Image.new("RGBA", (patch_size[0] * local_scale, patch_size[1] * local_scale), (0, 0, 0, 0))
    if shadow:
        shadow_layer = Image.new("RGBA", high.size, (0, 0, 0, 0))
        shadow_box = (shape[0], shape[1] + offset_px, shape[2], shape[3] + offset_px)
        ImageDraw.Draw(shadow_layer).rounded_rectangle(shadow_box, radius=radius_px, fill=(26, 55, 68, 42))
        high.alpha_composite(shadow_layer.filter(ImageFilter.GaussianBlur(blur_px)))
    ImageDraw.Draw(high).rounded_rectangle(shape, radius=radius_px, fill=rgba_fill,
                                           outline=rgba_outline, width=border_px)
    return high.resize(patch_size, Image.Resampling.LANCZOS)


def rounded_surface_metrics(bounds: tuple[float, float, float, float], radius: float, width: float, local_scale: int = 2) -> dict[str, int]:
    x1, y1, x2, y2 = bounds
    safe_radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return {"local_scale": local_scale, "radius_px": round(safe_radius * local_scale),
            "border_px": max(0, round(width * local_scale))}


def rounded_surface(
    image: Image.Image, bounds: tuple[float, float, float, float], radius: float,
    fill: str | tuple[int, ...], outline: str | tuple[int, ...] | None = None,
    width: float = 0, *, shadow: bool = False, opacity: int = 255,
    local_scale: int = 2,
) -> None:
    """Rasterize a rounded surface locally at 2x and downsample once with LANCZOS."""
    if local_scale < 1:
        raise ValueError("local_scale must be positive")
    x1, y1, x2, y2 = (float(value) for value in bounds)
    if x2 <= x1 or y2 <= y1:
        raise ValueError("rounded surface bounds must have positive area")
    metrics = rounded_surface_metrics((x1, y1, x2, y2), radius, width, local_scale)
    blur = max(3.0, radius / 8) if shadow else 0.0
    offset = max(2.0, min(12.0, radius / 5)) if shadow else 0.0
    pad = int(round(blur * 3 + offset + 2))
    left, top = math.floor(x1) - pad, math.floor(y1) - pad
    right, bottom = math.ceil(x2) + pad, math.ceil(y2) + pad
    patch_size = (max(1, right - left), max(1, bottom - top))
    shape = tuple(round((value - origin) * local_scale) for value, origin in zip((x1, y1, x2, y2), (left, top, left, top)))
    rgba_fill = ImageColor.getcolor(fill, "RGBA") if isinstance(fill, str) else fill
    rgba_fill = (*rgba_fill[:3], round(rgba_fill[3] * max(0, min(255, opacity)) / 255))
    rgba_outline = ImageColor.getcolor(outline, "RGBA") if isinstance(outline, str) else outline
    patch = _surface_patch(patch_size, shape, metrics["radius_px"], tuple(rgba_fill),
                           tuple(rgba_outline) if rgba_outline else None, metrics["border_px"],
                           shadow, blur * local_scale, round(offset * local_scale), local_scale)
    image.paste(patch, (left, top), patch)


def rounded_card(image: Image.Image, bounds: tuple[int, int, int, int], radius: int, fill: str, outline: str, width: int = 5) -> None:
    rounded_surface(image, bounds, radius, fill, outline, width, shadow=True)


def draw_progress_bar(image: Image.Image, bounds: tuple[int, int, int, int], progress: float, track: str, fill: str) -> None:
    x1, y1, x2, y2 = bounds
    radius = max(2, (y2 - y1) // 2)
    rounded_surface(image, bounds, radius, track)
    width = max(y2 - y1, int((x2 - x1) * max(0, min(1, progress))))
    rounded_surface(image, (x1, y1, x1 + width, y2), radius, fill)


def draw_sparkles(draw: ImageDraw.ImageDraw, size: tuple[int, int], color: str, phase: float = 1.0) -> None:
    w, h = size
    scale = w / 1080
    for index, (x, y) in enumerate(((180, 390), (895, 480), (145, 1050), (920, 1110), (275, 1460), (800, 1510))):
        amount = max(0.2, min(1.0, phase * 1.4 - index * 0.05))
        sx, sy, radius = int(x * scale), int(y * h / 1920), max(2, int(16 * scale * amount))
        draw.line((sx - radius, sy, sx + radius, sy), fill=color, width=max(2, int(6 * scale)))
        draw.line((sx, sy - radius, sx, sy + radius), fill=color, width=max(2, int(6 * scale)))
