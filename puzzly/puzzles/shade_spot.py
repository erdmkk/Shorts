"""Shade Spot: two grids of nearly the same colours, and exactly one tile has a slightly different shade. Find it.

Every level draws a base palette of tile colours around one hue (the top grid). The bottom grid is the same palette with
ONE tile moved away from its original by a fixed distance in the OKLab colour space (`delta`), so the answer is unique by
construction: all other tiles are identical in both grids. Levels get harder by growing the grid (3x3 up to 5x5) and
shrinking `delta` (0.11 down to 0.04, from clearly different to just noticeable). The answer is the tile's spot named like
a chessboard square: a column letter and a row number (`B3`), counted from the top left.
"""
from __future__ import annotations

from hashlib import sha256
import math
import random

from ..config import (READY_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION, DEFAULT_ROUNDS, SHADE_DELTA_TOLERANCE, SHADE_LEVELS,
                      SHADE_TIERS, shade_average_round)
from ..models import RoundSpec, VideoSpec

VERSION = "shade_v1"
MIN_TILE_GAP = 0.022  # base tiles are never (nearly) the same colour
OUTLIER_FACTOR = 1.6  # the odd tile never stands out inside its own grid: a similar tile exists
HUE_SPREAD = 24.0  # degrees of hue the tiles of one level wander around the base hue
DELTA_RANGE = (0.02, 0.2)  # accepted stored differences (about 0.02 is the least an eye notices)
LIGHTNESS = (0.50, 0.78)
CHROMA = (0.085, 0.17)


# ---------------------------------------------------------------- colour maths (sRGB <-> OKLab)

def _to_linear(value: float) -> float:
    value /= 255
    return value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4


def _from_linear(value: float) -> float:
    return 12.92 * value if value <= .0031308 else 1.055 * value ** (1 / 2.4) - .055


def hex_to_lab(value: str) -> tuple[float, float, float]:
    r, g, b = (_to_linear(int(value[index:index + 2], 16)) for index in (1, 3, 5))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def lab_to_hex(lightness: float, a: float, b: float) -> str | None:
    """The sRGB colour of an OKLab colour, or None when it falls outside the screen's gamut."""
    l = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    linear = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
              -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
              -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    if any(channel < -.002 or channel > 1.002 for channel in linear):
        return None
    return "#" + "".join(f"{round(max(0.0, min(1.0, _from_linear(max(0.0, min(1.0, channel))))) * 255):02X}" for channel in linear)


def distance(first: str, second: str) -> float:
    """OKLab distance between two hex colours (about 0.02 is the smallest difference an eye notices side by side)."""
    return math.dist(hex_to_lab(first), hex_to_lab(second))


def label(index: int, grid: int) -> str:
    """The spot of tile `index` (row-major from the top left): column letter and row number, like `B3`."""
    return f"{chr(65 + index % grid)}{index // grid + 1}"


# ---------------------------------------------------------------- generation

def _tile(hue: float, rng: random.Random) -> str | None:
    """A colour near `hue`; too saturated for the screen's gamut means a little less chroma."""
    angle = math.radians(hue + rng.uniform(-HUE_SPREAD, HUE_SPREAD))
    lightness, chroma = rng.uniform(*LIGHTNESS), rng.uniform(*CHROMA)
    for _ in range(10):
        color = lab_to_hex(lightness, chroma * math.cos(angle), chroma * math.sin(angle))
        if color:
            return color
        chroma *= .9
    return None


def _palette(grid: int, rng: random.Random) -> list[str]:
    for _ in range(60):  # a new base hue if one cannot hold every tile
        hue = rng.uniform(0, 360)
        colors: list[str] = []
        for _tile_number in range(grid * grid):
            for _ in range(300):
                color = _tile(hue, rng)
                if color and all(distance(color, other) >= MIN_TILE_GAP for other in colors):
                    colors.append(color)
                    break
            else:
                break
        if len(colors) == grid * grid:
            return colors
    raise RuntimeError("Could not create a shade palette")


def _nearest(color: str, others: list[str]) -> float:
    return min(distance(color, other) for other in others)


def _odd_color(base: list[str], index: int, delta: float, rng: random.Random) -> str | None:
    """The odd tile's new colour: `delta` away from the original in a random direction, still inside the palette's range."""
    lab = hex_to_lab(base[index])
    for _ in range(200):
        direction = [rng.gauss(0, 1) for _ in range(3)]
        direction[0] *= .5  # mostly a change of hue and saturation, less of brightness
        norm = math.sqrt(sum(value * value for value in direction)) or 1
        color = lab_to_hex(*(lab[axis] + delta * direction[axis] / norm for axis in range(3)))
        if not color or abs(distance(base[index], color) - delta) > delta * SHADE_DELTA_TOLERANCE:
            continue
        others = base[:index] + base[index + 1:]
        spacing = sorted(_nearest(tile, [other for other in others if other != tile]) for tile in others)[len(others) // 2]
        if _nearest(color, others) <= max(0.06, spacing * OUTLIER_FACTOR):
            return color
    return None


def make_round(index: int, tier: int, previous_answer: str | None, rng: random.Random) -> RoundSpec:
    level = SHADE_LEVELS[tier]
    grid, delta = level["grid"], level["delta"]
    for _ in range(400):
        base = _palette(grid, rng)
        odd = rng.randrange(grid * grid)
        if label(odd, grid) == previous_answer:
            continue
        color = _odd_color(base, odd, delta, rng)
        if color is None:
            continue
        answer = label(odd, grid)
        return RoundSpec(index, "shade_spot", {
            "version": VERSION, "grid": grid, "tier": tier, "tiles": base, "odd": odd, "odd_color": color,
            "delta": delta, "measured": round(distance(base[odd], color), 4), "thinking_seconds": level["thinking"],
            "level": index + 1}, answer)
    raise RuntimeError("Could not create a shade level")


def generate(seed: int, difficulty: str = "hard", theme: str = "shades", round_count: int | None = None) -> VideoSpec:
    """Always Hard (every level escalates inside one video); `difficulty` is accepted for the common interface."""
    count = round_count or DEFAULT_ROUNDS["shade_spot"]
    tiers = SHADE_TIERS.get(count, SHADE_TIERS[DEFAULT_ROUNDS["shade_spot"]])
    rng = random.Random(f"shade_spot_v1:{seed}:{count}")
    rounds: list[RoundSpec] = []
    previous = None
    for index, tier in enumerate(tiers):
        item = make_round(index, tier, previous, rng)
        rounds.append(item)
        previous = item.answer
    stable_id = sha256(f"shade_spot_v1:{seed}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "shade_spot", seed, "hard", "shades", tuple(rounds), READY_INTRO_DURATION,
                     shade_average_round([item.data for item in rounds]), PUZZLE_FIT_OUTRO_DURATION)


# ---------------------------------------------------------------- validation

def errors(data: dict, answer: str, difficulty: str | None) -> list[str]:
    tier = data.get("tier")
    if data.get("version") != VERSION or tier not in range(len(SHADE_LEVELS)):
        return ["shade level metadata is invalid"]
    grid = data.get("grid")
    tiles = data.get("tiles", [])
    delta = data.get("delta")
    if grid not in (3, 4, 5) or len(tiles) != grid * grid:
        return ["shade grid must be 3x3, 4x4 or 5x5 with a colour for every tile"]
    if not isinstance(delta, (int, float)) or not DELTA_RANGE[0] <= delta <= DELTA_RANGE[1]:
        return ["the odd tile's colour difference is out of range"]
    if any(not isinstance(color, str) or len(color) != 7 or not color.startswith("#") for color in [*tiles, data.get("odd_color", "")]):
        return ["shade colours must be hex colours"]
    odd = data.get("odd")
    if not isinstance(odd, int) or not 0 <= odd < len(tiles) or answer != label(odd, grid):
        return ["the answer must name the odd tile"]
    if any(distance(a, b) < MIN_TILE_GAP for index, a in enumerate(tiles) for b in tiles[index + 1:]):
        return ["shade tiles must all be different colours"]
    measured = distance(tiles[odd], data["odd_color"])
    if abs(measured - delta) > delta * (SHADE_DELTA_TOLERANCE + .05):
        return ["the odd tile's colour difference does not match its level"]
    if data["odd_color"] == tiles[odd]:
        return ["the odd tile must differ"]
    others = tiles[:odd] + tiles[odd + 1:]
    if _nearest(data["odd_color"], others) > 0.12:
        return ["the odd tile must stay inside its palette's range"]
    if not 3.0 <= float(data.get("thinking_seconds", 0)) <= 15.0:
        return ["shade thinking time is out of range"]
    return []
