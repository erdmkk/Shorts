"""Cube Count: isometric 5x5 (4x4 on Easy) board with 1-3 cube stacks, flashed briefly, then counted.

Besides the one-cell towers, every level has a big block (`size` 2): one box on a 2x2 footprint, one cube tall, that
counts as ONE cube. It has no inner edges, so a hurried viewer counts it as four.
"""
from __future__ import annotations

from functools import cmp_to_key, lru_cache
from hashlib import sha256
import math
import random

import numpy as np
from PIL import Image, ImageDraw

from ..config import (CUBE_COLORS, CUBE_ROUND_COLORS, THEME_CLASHING_CUBES, dark_theme_for, CUBE_VISIBLE, DEFAULT_ROUNDS, PUZZLE_FIT_INTRO_DURATION,
                      PUZZLE_FIT_OUTRO_DURATION, round_duration)
from ..models import RoundSpec, VideoSpec

GRID = {"easy": 4, "medium": 5, "hard": 5}
MAX_HEIGHT = 4  # only Hard's final level uses 4-cube towers; everything else stays at 3
# Cube totals per level tier (opening, middle, final): every video gets harder as it goes.
COUNT_RANGES = {
    "easy": ((4, 6), (5, 8), (7, 10)),
    "medium": ((6, 9), (8, 11), (10, 13)),
    "hard": ((8, 11), (10, 13), (12, 15)),
}
HEIGHT_WEIGHTS = {"easy": (5, 3, 1), "medium": (3, 4, 3), "hard": (3, 4, 4)}
MIN_CUBES_PER_STACK = 2.5  # at least ceil(total / 2.5) stacks
FINAL_HARD_WEIGHTS = (3, 4, 3, 3)  # Hard final level: towers up to 4 cubes, at least one of them
BOARD_WIDTH = 820  # logical width of the isometric floor diamond
BOARD_CENTER_Y = 860
CUBE_RATIO = 1.15  # cube height / tile height: keeps a stack's top face from aliasing onto a shorter stack behind it
MIN_TOP_VISIBLE = 0.60   # every stack's top face is clearly visible
MIN_SIDE_VISIBLE = 0.35  # every cube shows a clear side face, so each level can be counted
MIN_BASE_VISIBLE = 0.60  # both sides of the bottom cube are mostly visible
MIN_FOOTING_VISIBLE = 0.75  # the bottom edges where the stack meets the floor are visible, so its footing (and so its
# height) is never judged against the floor of a stack in front of it
# Stacks never touch front/back or left/right; only the screen-level diagonal neighbour is allowed, because it sits
# beside the stack on screen instead of in front of or behind it. This stops a stack standing one cell behind another
# from reading as a taller stack in front of it.
BLOCKING_OFFSETS = {(di, dj) for di in (-1, 0, 1) for dj in (-1, 0, 1)} - {(0, 0), (1, -1), (-1, 1)}
CANDIDATES = {"easy": 3, "medium": 6, "hard": 10}
BIG_BLOCKS = {"easy": (1, 1, 1), "medium": (1, 1, 1), "hard": (1, 1, 1)}  # big 2x2 blocks per level tier (two do not fit a 5x5 board)
CUBE_VERSION = 2  # rounds with big blocks
GRID_BIG = {"easy": 5, "medium": 6, "hard": 6}  # one cell larger than GRID: the 2x2 block needs the room
ATTEMPTS = 8000


def size_of(stack: dict) -> int:
    return int(stack.get("size", 1))


def cubes_in(stack: dict) -> int:
    """What a stack counts for: a big block is one cube, a tower is its height."""
    return 1 if size_of(stack) == 2 else stack["height"]


def stack_cells(stack: dict) -> list[tuple[int, int]]:
    i, j = stack["cell"]
    size = size_of(stack)
    return [(i + a, j + b) for a in range(size) for b in range(size)]


def level_tier(index: int, count: int) -> int:
    if count <= 1:
        return 2
    fraction = index / (count - 1)
    return 0 if fraction < 0.34 else (1 if fraction < 0.75 else 2)


def geometry(grid: int) -> dict[str, float]:
    tile_w = BOARD_WIDTH / grid
    tile_h = tile_w / 3 ** .5
    cube_h = tile_h * CUBE_RATIO
    thickness = tile_h * .38
    top = -MAX_HEIGHT * cube_h
    bottom = grid * tile_h + thickness
    origin_y = BOARD_CENTER_Y - (top + bottom) / 2
    return {"grid": grid, "tile_w": tile_w, "tile_h": tile_h, "cube_h": cube_h, "thickness": thickness,
            "origin_x": 540.0, "origin_y": origin_y}


def project(geo: dict[str, float], i: float, j: float, k: float) -> tuple[float, float]:
    return (geo["origin_x"] + (i - j) * geo["tile_w"] / 2,
            geo["origin_y"] + (i + j) * geo["tile_h"] / 2 - k * geo["cube_h"])


def cube_faces(geo: dict[str, float], i: int, j: int, k: int, size: int = 1) -> dict[str, list[tuple[float, float]]]:
    p = lambda a, b, c: project(geo, a, b, c)
    s = size
    return {
        "top": [p(i, j, k + 1), p(i + s, j, k + 1), p(i + s, j + s, k + 1), p(i, j + s, k + 1)],
        "left": [p(i, j + s, k + 1), p(i + s, j + s, k + 1), p(i + s, j + s, k), p(i, j + s, k)],
        "right": [p(i + s, j, k + 1), p(i + s, j + s, k + 1), p(i + s, j + s, k), p(i + s, j, k)],
    }


def _behind(a: dict, b: dict) -> bool:
    """a lies entirely behind b along one floor axis (the viewer looks from large i + j)."""
    return a["cell"][0] + size_of(a) <= b["cell"][0] or a["cell"][1] + size_of(a) <= b["cell"][1]


def stack_order(stacks: list[dict]) -> list[int]:
    """Stacks back to front. Boxes that could overlap on screen are ordered by the floor axis that separates them;
    the rest by their centre (for one-cell towers this is the classic (i + j, i) order)."""
    def centre(stack: dict) -> tuple[float, float]:
        half = size_of(stack) / 2
        return (stack["cell"][0] + stack["cell"][1] + 2 * half, stack["cell"][0] + half)

    def compare(x: int, y: int) -> int:
        a, b = stacks[x], stacks[y]
        first, second = _behind(a, b), _behind(b, a)
        if first != second:
            return -1 if first else 1
        return (centre(a) > centre(b)) - (centre(a) < centre(b))

    return sorted(range(len(stacks)), key=cmp_to_key(compare))


def draw_order(stacks: list[dict]) -> list[tuple[int, int]]:
    """(stack index, cube level) pairs back to front, bottom to top: a correct painter's order on a heightmap."""
    return [(index, level) for index in stack_order(stacks) for level in range(stacks[index]["height"])]


def _area(points: list[tuple[float, float]]) -> float:
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1]))) / 2


@lru_cache(maxsize=256)
def _visibility_cached(grid: int, stack_key: tuple[tuple[int, int, int, int], ...]) -> tuple[tuple[float, ...], ...]:
    stacks = [{"cell": [i, j], "height": h, "size": s} for i, j, h, s in stack_key]
    geo = geometry(grid)
    scale = .5
    ids = Image.new("I", (540, 960), 0)
    draw = ImageDraw.Draw(ids)
    faces_meta: dict[int, float] = {}
    face_names = ("top", "left", "right")
    for stack_index, level in draw_order(stacks):
        i, j = stacks[stack_index]["cell"]
        faces = cube_faces(geo, i, j, level, size_of(stacks[stack_index]))
        for face_index, name in enumerate(face_names):
            if name == "top" and level != stacks[stack_index]["height"] - 1:
                continue
            face_id = 1 + (stack_index * MAX_HEIGHT + level) * 3 + face_index
            polygon = [(x * scale, y * scale) for x, y in faces[name]]
            draw.polygon(polygon, fill=face_id)
            faces_meta[face_id] = _area(polygon)
    buffer = np.asarray(ids, dtype=np.int64)
    counts = np.bincount(buffer.ravel(), minlength=max(faces_meta, default=0) + 1)

    def footing(stack_index: int) -> float:
        """Share of sample points along the bottom cube's two floor edges that belong to its own side faces."""
        i, j = stacks[stack_index]["cell"]
        s = size_of(stacks[stack_index])
        base = 1 + stack_index * MAX_HEIGHT * 3
        hits = total = 0
        for start, end, face_id in ((project(geo, i, j + s, 0), project(geo, i + s, j + s, 0), base + 1),
                                    (project(geo, i + s, j + s, 0), project(geo, i + s, j, 0), base + 2)):
            for step in range(1, 12):
                t = step / 12
                x = (start[0] + (end[0] - start[0]) * t) * scale
                y = (start[1] + (end[1] - start[1]) * t) * scale - 2  # just above the edge, inside the face
                row, column = int(round(y)), int(round(x))
                total += 1
                if 0 <= row < buffer.shape[0] and 0 <= column < buffer.shape[1] and buffer[row, column] == face_id:
                    hits += 1
        return hits / max(1, total)

    result = []
    for stack_index, stack in enumerate(stacks):
        per_cube = []
        for level in range(stack["height"]):
            base = 1 + (stack_index * MAX_HEIGHT + level) * 3
            per_cube.append(tuple(round(counts[base + offset] / max(1.0, faces_meta.get(base + offset, 1.0)), 4)
                                  for offset in (1, 2)))
        top_id = 1 + (stack_index * MAX_HEIGHT + stack["height"] - 1) * 3
        result.append((round(counts[top_id] / max(1.0, faces_meta[top_id]), 4), round(footing(stack_index), 4), *per_cube))
    return tuple(result)


def visibility(grid: int, stacks: list[dict]) -> list[tuple[float, ...]]:
    """Per stack: (top fraction, footing-edge fraction, (left, right) side fractions of each cube bottom up)."""
    key = tuple((stack["cell"][0], stack["cell"][1], stack["height"], size_of(stack)) for stack in stacks)
    return list(_visibility_cached(grid, key))


def spaced(cells: list[tuple[int, int]] | list[list[int]]) -> bool:
    occupied = {tuple(cell) for cell in cells}
    return not any((i + di, j + dj) in occupied for i, j in occupied for di, dj in BLOCKING_OFFSETS)


def spaced_stacks(stacks: list[dict]) -> bool:
    """spaced() for boxes of any footprint: no two stacks share a cell or stand in a blocking position."""
    cells = [stack_cells(stack) for stack in stacks]
    for index, first in enumerate(cells):
        for second in cells[index + 1:]:
            if any((b[0] - a[0], b[1] - a[1]) in BLOCKING_OFFSETS | {(0, 0)} for a in first for b in second):
                return False
    return True


def readable(grid: int, stacks: list[dict]) -> bool:
    return all(top >= MIN_TOP_VISIBLE and footing >= MIN_FOOTING_VISIBLE and min(sides[0]) >= MIN_BASE_VISIBLE
               and all(max(side) >= MIN_SIDE_VISIBLE for side in sides)
               for top, footing, *sides in visibility(grid, stacks))


def occlusion_score(grid: int, stacks: list[dict]) -> float:
    """How much of the cube surfaces is hidden: higher means harder to count at a glance."""
    values = visibility(grid, stacks)
    return sum((1 - top) + sum(2 - sum(side) for side in sides) for top, _, *sides in values) / max(1, len(values))


def _spaced_cells(count: int, grid: int, rng: random.Random, placed: list[dict] | None = None) -> list[tuple[int, int]] | None:
    """`count` one-cell positions, spaced from each other and from the already `placed` stacks."""
    placed = list(placed or [])
    order = [(i, j) for i in range(grid) for j in range(grid)]
    rng.shuffle(order)
    chosen: list[tuple[int, int]] = []
    if count == 0:
        return chosen
    for cell in order:
        candidate = {"cell": list(cell), "height": 1}
        if spaced_stacks(placed + [candidate]):
            placed.append(candidate)
            chosen.append(cell)
            if len(chosen) == count:
                return chosen
    return None


def _big_blocks(count: int, grid: int, rng: random.Random) -> list[dict] | None:
    order = [(i, j) for i in range(grid - 1) for j in range(grid - 1)]
    rng.shuffle(order)
    blocks: list[dict] = []
    for i, j in order:
        if len(blocks) == count:
            break
        candidate = {"cell": [i, j], "height": 1, "size": 2}
        if spaced_stacks(blocks + [candidate]):
            blocks.append(candidate)
    return blocks if len(blocks) == count else None


def max_height(difficulty: str, tier: int) -> int:
    return 4 if difficulty == "hard" and tier == 2 else 3


def varied_heights(heights: list[int]) -> bool:
    """Cubes spread over mixed stacks, so they cannot be counted as 3 + 3 + 3 at a glance.

    No height may repeat on more than half of the stacks, boards with more than four stacks use at least three
    different heights, and there is at least one stack per 2.5 cubes (9 cubes -> 4+ stacks, e.g. 2-2-4-1).
    """
    stacks = len(heights)
    if stacks < 2:
        return False
    counts: dict[int, int] = {}
    for height in heights:
        counts[height] = counts.get(height, 0) + 1
    return (max(counts.values()) <= (stacks + 1) // 2 and len(counts) >= (3 if stacks > 4 else 2)
            and stacks >= math.ceil(sum(heights) / MIN_CUBES_PER_STACK))


def _heights_for(total: int, difficulty: str, tier: int, rng: random.Random) -> list[int] | None:
    tallest = max_height(difficulty, tier)
    weights = FINAL_HARD_WEIGHTS if tallest == 4 else HEIGHT_WEIGHTS[difficulty]
    heights: list[int] = []
    while sum(heights) < total:
        remaining = total - sum(heights)
        options = [height for height in range(1, tallest + 1) if height <= remaining]
        heights.append(rng.choices(options, weights=[weights[height - 1] for height in options])[0])
    if tallest == 4 and 4 not in heights:
        return None
    return heights if varied_heights(heights) else None


def _make_round(index: int, difficulty: str, tier: int, previous_total: int | None, color_id: str,
                rng: random.Random) -> RoundSpec:
    grid = GRID_BIG[difficulty]
    low, high = COUNT_RANGES[difficulty][tier]
    bigs = BIG_BLOCKS[difficulty][tier]
    totals = [value for value in range(low, high + 1) if value != previous_total]
    candidates = []
    for _ in range(ATTEMPTS):
        total = rng.choice(totals)
        heights = _heights_for(total - bigs, difficulty, tier, rng)  # every big block counts as one cube
        if heights is None:
            continue
        blocks = _big_blocks(bigs, grid, rng)
        if blocks is None:
            continue
        cells = _spaced_cells(len(heights), grid, rng, blocks)
        if cells is None:
            continue
        stacks = blocks + [{"cell": [i, j], "height": height} for (i, j), height in zip(cells, heights)]
        stacks = [stacks[index] for index in stack_order(stacks)]
        if readable(grid, stacks):
            candidates.append(stacks)
            if len(candidates) == CANDIDATES[difficulty]:
                break
    if not candidates:
        raise RuntimeError("Could not create a readable cube layout")
    # The final levels keep the most occluded readable layout; the opening level stays approachable.
    stacks = max(candidates, key=lambda item: occlusion_score(grid, item)) if tier else candidates[0]
    total = sum(cubes_in(stack) for stack in stacks)
    return RoundSpec(index, "cube_count", {
        "version": CUBE_VERSION, "grid": grid, "stacks": stacks, "total": total, "level": index + 1, "tier": tier,
        "count_range": [low, high], "visible_seconds": CUBE_VISIBLE[difficulty], "color_id": color_id,
    }, total)


def generate(seed: int, difficulty: str = "easy", theme: str = "isometric_cubes", round_count: int | None = None,
             background: str | None = None) -> VideoSpec:
    """`background` is the creator's chosen background tone, if any; the cube colours avoid it."""
    difficulty = difficulty if difficulty in GRID else "easy"
    count = round_count or DEFAULT_ROUNDS["cube_count"]
    rng = random.Random(f"cube_count_v1:{seed}:{difficulty}:{count}")
    # Every round gets its own cube colour (never the same twice in a video), so each level feels like a new challenge.
    tone = background if background in THEME_CLASHING_CUBES else dark_theme_for("cube_count", seed)
    clashing = THEME_CLASHING_CUBES[tone]  # keep the cubes readable on this video's background
    pool = [color for color in CUBE_ROUND_COLORS if color not in clashing]
    colors = random.Random(f"cube_colors_v1:{seed}:{difficulty}:{count}").sample(pool, min(count, len(pool)))
    rounds: list[RoundSpec] = []
    previous = None
    for index in range(count):
        item = _make_round(index, difficulty, level_tier(index, count), previous, colors[index % len(colors)], rng)
        rounds.append(item)
        previous = item.answer
    stable_id = sha256(f"cube_count_v1:{seed}:{difficulty}:{count}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "cube_count", seed, difficulty, "isometric_cubes", tuple(rounds),
                     PUZZLE_FIT_INTRO_DURATION, round_duration("cube_count", difficulty), PUZZLE_FIT_OUTRO_DURATION)


def errors(data: dict, answer: int, difficulty: str | None) -> list[str]:
    difficulty = difficulty or "easy"
    grid = data.get("grid")
    expected = GRID_BIG if data.get("version") == CUBE_VERSION else GRID
    if difficulty not in GRID or grid != expected[difficulty]:
        return ["cube board size does not match difficulty"]
    stacks = data.get("stacks", [])
    if not stacks or any(len(stack.get("cell", ())) != 2 or stack.get("size", 1) not in (1, 2) for stack in stacks):
        return ["cube stacks must sit on distinct board cells"]
    cells = [cell for stack in stacks for cell in stack_cells(stack)]
    if len(set(cells)) != len(cells) or any(not all(0 <= value < grid for value in cell) for cell in cells):
        return ["cube stacks must sit on distinct board cells"]
    tier = data.get("tier")
    blocks = [stack for stack in stacks if size_of(stack) == 2]
    towers = [stack for stack in stacks if size_of(stack) == 1]
    if any(stack.get("height") != 1 for stack in blocks):
        return ["a big block is exactly one cube tall"]
    if data.get("version") == CUBE_VERSION and len(blocks) != BIG_BLOCKS[difficulty][tier if tier in (0, 1, 2) else 0]:
        return ["the level has the wrong number of big blocks"]
    tallest = max_height(difficulty, tier if tier in (0, 1, 2) else 0)
    if any(stack.get("height") not in range(1, tallest + 1) for stack in towers):
        return [f"cube stacks must be 1-{tallest} cubes tall"]
    if tallest == 4 and not any(stack["height"] == 4 for stack in towers):
        return ["the final Hard level must include a 4-cube tower"]
    if not varied_heights([stack["height"] for stack in towers]):
        return ["cubes must be spread over mixed stack heights"]
    total = sum(cubes_in(stack) for stack in stacks)
    if data.get("total") != total or answer != total:
        return ["cube answer must equal the number of cubes"]
    tier = data.get("tier")
    if tier not in (0, 1, 2) or data.get("count_range") != list(COUNT_RANGES[difficulty][tier]):
        return ["cube level metadata is invalid"]
    low, high = COUNT_RANGES[difficulty][tier]
    if not low <= total <= high:
        return ["cube total is outside its level range"]
    if data.get("visible_seconds") != CUBE_VISIBLE[difficulty]:
        return ["cube flash duration does not match difficulty"]
    if data.get("color_id") not in CUBE_COLORS:
        return ["cube color is invalid"]
    if not spaced_stacks(stacks):
        return ["cube stacks must not stand directly beside, in front of, or behind each other"]
    if not readable(grid, stacks):
        return ["every stack must show its top, its footing, and a side of every cube"]
    return []
