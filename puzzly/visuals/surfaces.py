"""Tabletop backgrounds for the calm board games (Matchstick Math and Chess: Mate in 1).

Procedural, local and deterministic (no image assets): a dark wood table for matches and a felt cloth for chess, both
tinted with the video's background tone (`DARK_THEMES`), lit by a warm lamp over the puzzle with a deep vignette, so the
screen feels like a dimly lit table instead of an empty gradient. Cached per size, theme and light centre.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image

from ..config import DARK_THEMES, glow_strength

WOOD_BROWN = np.array((74, 48, 30), np.float32)
LAMP = np.array((255, 222, 176), np.float32)


def _rgb(value: str) -> np.ndarray:
    raw = value.lstrip("#")
    return np.array([int(raw[index:index + 2], 16) for index in (0, 2, 4)], np.float32)


def _noise(width: int, height: int, cells: tuple[int, int], rng: np.random.Generator) -> np.ndarray:
    """Smooth value noise in 0..1: a coarse random grid enlarged with bicubic filtering."""
    grid = (rng.random((cells[1], cells[0])) * 255).astype(np.uint8)
    return np.asarray(Image.fromarray(grid).resize((width, height), Image.Resampling.BICUBIC), np.float32) / 255


def _wood(width: int, height: int, scale: float, rng: np.random.Generator) -> np.ndarray:
    """Luminance of a table of horizontal planks: long uneven grain streaks, a faint wavy figure, and dark seams."""
    y = np.mgrid[0:height, 0:width][0].astype(np.float32)
    plank = 330 * scale
    index = np.floor(y / plank)
    streaks = _noise(width, height, (5, 260), rng)  # long streaks along the planks
    fibres = _noise(width, height, (14, 900), rng)  # fine grain lines
    warp = _noise(width, height, (3, 10), rng) * 22 * scale
    figure = .5 + .5 * np.sin((y + warp) / (5.5 * scale))
    tone = (.80 + .08 * np.sin(index * 2.3) + .24 * (streaks - .5) + .16 * (fibres - .5) + .05 * figure
            + .08 * (_noise(width, height, (4, 8), rng) - .5))
    seam = (np.clip(1 - np.abs(y - (index + 1) * plank) / (3.2 * scale), 0, 1)
            + np.clip(1 - np.abs(y - index * plank) / (1.6 * scale), 0, 1))
    return np.clip(tone - .45 * seam, 0, 1.3)


def _felt(width: int, height: int, scale: float, rng: np.random.Generator) -> np.ndarray:
    """Luminance of a felt cloth: fine fibres over a soft, uneven nap."""
    fibres = rng.random((height, width)).astype(np.float32)
    small = Image.fromarray((fibres * 255).astype(np.uint8)).resize((max(1, width // 2), max(1, height // 2)), Image.Resampling.BOX)
    fibres = np.asarray(small.resize((width, height), Image.Resampling.BILINEAR), np.float32) / 255
    nap = _noise(width, height, (7, 12), rng)
    return .86 + .16 * (fibres - .5) + .14 * (nap - .5)


@lru_cache(maxsize=6)
def table(size: tuple[int, int], theme: str, material: str, light: tuple[float, float]) -> Image.Image:
    """The tabletop at `size`: `material` is 'wood' or 'felt', `light` the lamp centre in logical 1080x1920 pixels."""
    width, height = size
    scale = width / 1080
    rng = np.random.default_rng(7 if material == "wood" else 11)  # the same grain in every video: only the tone changes
    top, bottom, glow = (_rgb(value) for value in DARK_THEMES.get(theme, DARK_THEMES["violet"]))
    if material == "wood":
        weight = glow_strength(theme, .38)  # vivid tones tint the table harder
        base = WOOD_BROWN * (1 - weight) + glow * weight
        pattern = _wood(width, height, scale, rng)
    else:
        weight = min(.95, glow_strength(theme, .55))
        base = glow * weight + bottom * (1 - weight)
        pattern = _felt(width, height, scale, rng)
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    lx, ly = light[0] * scale, light[1] * scale
    distance = np.hypot((x - lx) / (620 * scale), (y - ly) / (760 * scale))
    spot = np.exp(-distance ** 2 * 1.6)
    vignette = np.clip(1 - np.clip(np.hypot(x / width - .5, (y / height - .5) * .85) - .25, 0, 1) * 1.6, 0, 1)
    light_level = (.20 + .95 * spot) * (.35 + .65 * vignette)
    rgb = base[None, None, :] * pattern[..., None] * light_level[..., None]
    rgb += LAMP[None, None, :] * (spot ** 3 * .07)[..., None]  # a warm sheen right under the lamp
    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
