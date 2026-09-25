from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Iterable


@dataclass(frozen=True)
class MemoryColor:
    id: str
    value: str
    family: str

    @property
    def oklab(self) -> tuple[float, float, float]:
        return hex_to_oklab(self.value)

    @property
    def lightness(self) -> float:
        return self.oklab[0]

    def to_dict(self) -> dict[str, str | float]:
        result: dict[str, str | float] = asdict(self)
        result["lightness"] = round(self.lightness, 6)
        return result


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def hex_to_oklab(value: str) -> tuple[float, float, float]:
    raw = value.lstrip("#")
    r, g, b = (_linear(int(raw[index:index + 2], 16)) for index in (0, 2, 4))
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = math.copysign(abs(l) ** (1 / 3), l), math.copysign(abs(m) ** (1 / 3), m), math.copysign(abs(s) ** (1 / 3), s)
    return (0.2104542553*l_ + 0.793617785*m_ - 0.0040720468*s_,
            1.9779984951*l_ - 2.428592205*m_ + 0.4505937099*s_,
            0.0259040371*l_ + 0.7827717662*m_ - 0.808675766*s_)


def perceptual_distance(first: MemoryColor | str, second: MemoryColor | str) -> float:
    a = first.oklab if isinstance(first, MemoryColor) else hex_to_oklab(first)
    b = second.oklab if isinstance(second, MemoryColor) else hex_to_oklab(second)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


COLORS = {item.id: item for item in (
    MemoryColor("red", "#D9434E", "red"), MemoryColor("blue", "#2874C6", "blue"),
    MemoryColor("yellow", "#DCA915", "yellow"), MemoryColor("green", "#3A9B55", "green"),
    MemoryColor("purple", "#8655B7", "purple"), MemoryColor("coral", "#E56555", "red"),
    MemoryColor("navy", "#325AA8", "blue"), MemoryColor("gold", "#C8951B", "yellow"),
    MemoryColor("emerald", "#248F70", "green"), MemoryColor("violet", "#9956B5", "purple"),
    MemoryColor("med_blue", "#337FC2", "blue"), MemoryColor("turquoise", "#259D9A", "cyan"),
    MemoryColor("med_red", "#D65355", "red"), MemoryColor("orange", "#DA7A34", "orange"),
    MemoryColor("med_purple", "#8A5AB5", "purple"), MemoryColor("pink", "#D45F91", "pink"),
    MemoryColor("med_green", "#559753", "green"), MemoryColor("med_yellow", "#D2A62A", "yellow"),
    MemoryColor("cool_cyan", "#268DA8", "cool"), MemoryColor("cool_blue", "#397FAF", "cool"),
    MemoryColor("cool_indigo", "#506FAE", "cool"), MemoryColor("cool_violet", "#6A64AD", "cool"),
    MemoryColor("cool_purple", "#825BA7", "cool"), MemoryColor("warm_red", "#C95458", "warm"),
    MemoryColor("warm_coral", "#D25E50", "warm"), MemoryColor("warm_orange", "#D66C42", "warm"),
    MemoryColor("warm_pink", "#C95B77", "warm"), MemoryColor("warm_magenta", "#B9588D", "warm"),
)}

PALETTE_IDS = {
    "easy": (("red", "blue", "yellow", "green", "purple"),
             ("coral", "navy", "gold", "emerald", "violet")),
    "medium": (("med_blue", "turquoise", "med_yellow", "med_red", "med_purple"),
               ("med_red", "orange", "med_blue", "med_green", "pink")),
    "hard": (("cool_cyan", "cool_blue", "cool_indigo", "cool_violet", "cool_purple"),
             ("warm_red", "warm_coral", "warm_orange", "warm_pink", "warm_magenta")),
}


def palette(difficulty: str, variant: int) -> tuple[MemoryColor, ...]:
    groups = PALETTE_IDS[difficulty]
    return tuple(COLORS[color_id] for color_id in groups[variant % len(groups)])


def distance_stats(colors: Iterable[MemoryColor]) -> tuple[float, float]:
    values = list(colors)
    distances = [perceptual_distance(a, b) for index, a in enumerate(values) for b in values[index + 1:]]
    return min(distances), sum(distances) / len(distances)


COLOR_RULES = {
    "easy": {"min_distance": 0.125, "min_average": 0.235},
    "medium": {"min_distance": 0.075, "min_average": 0.19},
    "hard": {"min_distance": 0.032, "min_average": 0.068, "max_average": 0.16},
}


def palette_errors(colors: Iterable[MemoryColor], difficulty: str, backgrounds: Iterable[str] = ()) -> list[str]:
    values = list(colors); errors: list[str] = []
    if len(values) != 5 or len({item.id for item in values}) != 5:
        errors.append("memory palette must contain five unique colors")
        return errors
    minimum, average = distance_stats(values); rules = COLOR_RULES[difficulty]
    if minimum < rules["min_distance"] or average < rules["min_average"]:
        errors.append("memory colors do not meet perceptual separation minimums")
    if average > rules.get("max_average", 1.0):
        errors.append("memory colors are too dissimilar for this difficulty")
    for color in values:
        if any(abs(color.lightness - hex_to_oklab(background)[0]) < 0.10 for background in backgrounds):
            errors.append(f"memory color lacks background lightness contrast: {color.id}")
    return errors


# ---------------------------------------------------------------- 3x3 grid board (nine tokens on the dark theme)

GRID_COLORS = {item.id: item for item in (
    # Easy: nine clearly different hues.
    MemoryColor("g_red", "#FF5A5F", "red"), MemoryColor("g_orange", "#FF9F1C", "orange"),
    MemoryColor("g_yellow", "#FFD93D", "yellow"), MemoryColor("g_lime", "#7ED957", "green"),
    MemoryColor("g_teal", "#2EC4B6", "cyan"), MemoryColor("g_sky", "#4FC3F7", "blue"),
    MemoryColor("g_blue", "#3D6BFF", "blue"), MemoryColor("g_purple", "#A66BFF", "purple"),
    MemoryColor("g_pink", "#FF6FB5", "pink"),
    MemoryColor("g2_red", "#F94144", "red"), MemoryColor("g2_orange", "#F8961E", "orange"),
    MemoryColor("g2_yellow", "#F9C74F", "yellow"), MemoryColor("g2_green", "#90BE6D", "green"),
    MemoryColor("g2_teal", "#43AA8B", "cyan"), MemoryColor("g2_sky", "#4D9DE0", "blue"),
    MemoryColor("g2_blue", "#577BFF", "blue"), MemoryColor("g2_purple", "#B56CE0", "purple"),
    MemoryColor("g2_pink", "#F15BB5", "pink"),
    # Medium: three related shades in each of three families.
    MemoryColor("m_coral", "#FF6B6B", "warm"), MemoryColor("m_orange", "#FF9F43", "warm"),
    MemoryColor("m_amber", "#FFC857", "warm"), MemoryColor("m_blue", "#4DA3FF", "cool"),
    MemoryColor("m_indigo", "#6C7BFF", "cool"), MemoryColor("m_lilac", "#A78BFA", "cool"),
    MemoryColor("m_mint", "#34D399", "green"), MemoryColor("m_aqua", "#2DD4BF", "green"),
    MemoryColor("m_lime", "#A3E635", "green"),
    MemoryColor("m2_red", "#F2545B", "warm"), MemoryColor("m2_orange", "#F28C38", "warm"),
    MemoryColor("m2_amber", "#F2B84B", "warm"), MemoryColor("m2_cyan", "#3FA7D6", "cool"),
    MemoryColor("m2_blue", "#5A7BE0", "cool"), MemoryColor("m2_violet", "#9A7BE8", "cool"),
    MemoryColor("m2_green", "#3CC48B", "green"), MemoryColor("m2_teal", "#26B5A8", "green"),
    MemoryColor("m2_lime", "#8FCB3E", "green"),
    # Hard: nine close shades of one family.
    MemoryColor("h_cyan", "#5EC8FF", "cool"), MemoryColor("h_azure", "#45A6FF", "cool"),
    MemoryColor("h_blue", "#3D84FF", "cool"), MemoryColor("h_indigo", "#5F6BFF", "cool"),
    MemoryColor("h_violet", "#7D6BFF", "cool"), MemoryColor("h_lavender", "#9C82FF", "cool"),
    MemoryColor("h_ice", "#6BD6E8", "cool"), MemoryColor("h_steel", "#4DB8D8", "cool"),
    MemoryColor("h_periwinkle", "#8FA8FF", "cool"),
    MemoryColor("h_red", "#FF6B6B", "warm"), MemoryColor("h_coral", "#FF8A5B", "warm"),
    MemoryColor("h_orange", "#FFA94D", "warm"), MemoryColor("h_pink", "#FF7AA2", "warm"),
    MemoryColor("h_rose", "#FF5C8A", "warm"), MemoryColor("h_apricot", "#FFB86B", "warm"),
    MemoryColor("h_brick", "#F2735A", "warm"), MemoryColor("h_salmon", "#FF9E8A", "warm"),
    MemoryColor("h_gold", "#FFC857", "warm"),
    # Hard (current): neighbouring hues of one half of the wheel, varied in lightness, so the board is readable but
    # still easy to mix up. The single-family h_* shades above stay only for re-rendering older manifests.
    MemoryColor("hc_sky", "#4FD1FF", "cool"), MemoryColor("hc_blue", "#3D8BFF", "cool"),
    MemoryColor("hc_indigo", "#5B5BFF", "cool"), MemoryColor("hc_violet", "#9A5BFF", "cool"),
    MemoryColor("hc_orchid", "#D98BFF", "cool"), MemoryColor("hc_mint", "#7FE3D0", "cool"),
    MemoryColor("hc_periwinkle", "#A8B8FF", "cool"), MemoryColor("hc_teal", "#2FB5C8", "cool"),
    MemoryColor("hc_cornflower", "#6FA0FF", "cool"),
    MemoryColor("hc_red", "#FF5A5A", "warm"), MemoryColor("hc_orange", "#FF8A3D", "warm"),
    MemoryColor("hc_amber", "#FFC23D", "warm"), MemoryColor("hc_yellow", "#F2E14B", "warm"),
    MemoryColor("hc_lime", "#A6E05A", "warm"), MemoryColor("hc_pink", "#FF7AA8", "warm"),
    MemoryColor("hc_peach", "#FFB08A", "warm"), MemoryColor("hc_brick", "#D9503E", "warm"),
    MemoryColor("hc_cream", "#FFDDA0", "warm"),
)}

# Colour similarity levels, chosen in the UI: the higher the level, the closer the nine colours.
GRID_PALETTE_IDS = {
    1: (("g_red", "g_orange", "g_yellow", "g_lime", "g_teal", "g_sky", "g_blue", "g_purple", "g_pink"),
             ("g2_red", "g2_orange", "g2_yellow", "g2_green", "g2_teal", "g2_sky", "g2_blue", "g2_purple", "g2_pink")),
    2: (("m_coral", "m_orange", "m_amber", "m_blue", "m_indigo", "m_lilac", "m_mint", "m_aqua", "m_lime"),
               ("m2_red", "m2_orange", "m2_amber", "m2_cyan", "m2_blue", "m2_violet", "m2_green", "m2_teal", "m2_lime")),
    3: (("hc_sky", "hc_blue", "hc_indigo", "hc_violet", "hc_orchid", "hc_mint", "hc_periwinkle", "hc_teal",
              "hc_cornflower"),
             ("hc_red", "hc_orange", "hc_amber", "hc_yellow", "hc_lime", "hc_pink", "hc_peach", "hc_brick", "hc_cream")),
    4: (("h_cyan", "h_azure", "h_blue", "h_indigo", "h_violet", "h_lavender", "h_ice", "h_steel", "h_periwinkle"),
        ("h_red", "h_coral", "h_orange", "h_pink", "h_rose", "h_apricot", "h_brick", "h_salmon", "h_gold")),
}
GRID_COLOR_RULES = {
    1: {"min_distance": 0.10, "min_average": 0.24},  # nine distinct hues (yellow, orange, blue, green, pink...)
    2: {"min_distance": 0.05, "min_average": 0.20},  # three shades in each of three families
    3: {"min_distance": 0.07, "min_average": 0.16, "max_average": 0.20},  # neighbouring hues of half the wheel
    4: {"min_distance": 0.035, "min_average": 0.10, "max_average": 0.15},  # close shades of one family
}
GRID_COLOR_LEVELS = tuple(GRID_PALETTE_IDS)
DEFAULT_GRID_COLOR_LEVEL = 1
COLOR_LEVEL_THEMES = {f"colors_{level}": level for level in GRID_COLOR_LEVELS}  # UI choice travels as the theme


def infer_color_level(color_ids: Iterable[str]) -> int | None:
    """Level whose palette holds these colours (older manifests stored no level)."""
    ids = set(color_ids)
    return next((level for level, groups in GRID_PALETTE_IDS.items() if any(ids == set(group) for group in groups)), None)
GRID_MIN_LIGHTNESS = 0.55  # every token stays bright on the dark Puzzly for You cards


def grid_palette(level: int, variant: int) -> tuple[MemoryColor, ...]:
    groups = GRID_PALETTE_IDS[level]
    return tuple(GRID_COLORS[color_id] for color_id in groups[variant % len(groups)])


def grid_palette_errors(colors: Iterable[MemoryColor], level: int) -> list[str]:
    values = list(colors)
    if len(values) != 9 or len({item.id for item in values}) != 9:
        return ["memory grid palette must contain nine unique colors"]
    errors: list[str] = []
    minimum, average = distance_stats(values)
    rules = GRID_COLOR_RULES[level]
    if minimum < rules["min_distance"] or average < rules["min_average"]:
        errors.append("memory colors do not meet perceptual separation minimums")
    if average > rules.get("max_average", 1.0):
        errors.append("memory colors are too dissimilar for this difficulty")
    if any(color.lightness < GRID_MIN_LIGHTNESS for color in values):
        errors.append("memory colors must stay bright on the dark board")
    return errors
