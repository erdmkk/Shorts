"""Creator-chosen colours for the Puzzly for You (dark-theme) games.

Two choices travel in `VideoSpec.metadata` (outside the fingerprint, like music, and kept in the saved spec so a Final
re-render matches): `background` (one of the DARK_THEMES tones, or absent for the per-video random tone) and
`palette` (an object palette). A palette keeps every colour's hue and only changes its saturation and brightness, so
a red target stays red (colour names such as "BLUE SURVIVES" stay true) and colours stay as distinct as before.
Memory Challenge keeps its own colours (its colour-similarity levels are part of the game), and the light-theme games
are not affected.
"""
from __future__ import annotations

import colorsys
from functools import lru_cache

from .config import DARK_THEMES, dark_theme_for
from .models import VideoSpec

BACKGROUND_LABELS = {"random": "Rastgele", "violet": "Mor", "ocean": "Okyanus mavisi", "teal": "Turkuaz",
                     "crimson": "Kızıl", "emerald": "Zümrüt yeşili", "ember": "Kor turuncu", "plum": "Erik moru"}
PALETTE_LABELS = {"classic": "Klasik", "neon": "Neon", "pastel": "Pastel", "jewel": "Mücevher tonları"}
# (saturation multiplier, saturation floor, brightness multiplier, brightness floor, brightness cap)
PALETTES = {
    "classic": None,
    "neon": (1.25, .85, 1.0, 1.0, 1.0),  # fully saturated and bright
    "pastel": (.55, 0.0, 1.0, .93, 1.0),  # soft and light, but still clearly different hues
    "jewel": (1.1, .7, .74, 0.0, .78),  # deep, rich tones
}
NO_PALETTE_GAMES = ("memory_challenge",)
_ACTIVE = {"palette": None}


def background_for(spec: VideoSpec) -> str:
    """The video's background tone: the creator's choice, or the per-video random tone."""
    chosen = spec.metadata.get("background")
    return chosen if chosen in DARK_THEMES else dark_theme_for(spec.puzzle_type, spec.seed)


def palette_for(spec: VideoSpec) -> str | None:
    chosen = spec.metadata.get("palette")
    return chosen if PALETTES.get(chosen) and spec.puzzle_type not in NO_PALETTE_GAMES else None


def use(spec: VideoSpec) -> None:
    """Make this video's object palette active for everything drawn next (frames and cover)."""
    _ACTIVE["palette"] = palette_for(spec)


def active() -> str | None:
    return _ACTIVE["palette"]


@lru_cache(maxsize=512)
def recolor(value: str, palette: str | None) -> str:
    """The colour in this palette: same hue, the palette's saturation and brightness."""
    rule = PALETTES.get(palette) if palette else None
    if not rule or not value.startswith("#") or len(value) != 7:
        return value
    red, green, blue = (int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))
    hue, saturation, brightness = colorsys.rgb_to_hsv(red, green, blue)
    sat_mult, sat_floor, val_mult, val_floor, val_cap = rule
    saturation = min(1.0, max(sat_floor, saturation * sat_mult)) if saturation > .05 else saturation
    brightness = min(val_cap, max(val_floor, brightness * val_mult))
    return "#%02X%02X%02X" % tuple(round(channel * 255) for channel in colorsys.hsv_to_rgb(hue, saturation, brightness))


def object_color(value: str) -> str:
    """An object's colour under the active palette (unchanged when no palette is active)."""
    return recolor(value, _ACTIVE["palette"])
