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
