"""Find the Exit Hard in the "Puzzly for You" look: lit 3D maze, glowing exit portals, and a neon route trace.

Shaped mazes (`cells_v1`, see puzzles/exit_shapes.py: a hexagon, a star, and a diamond) have the start in the middle
and four or five exits around the rim like the circular ones, on the same round plate, with polygon cells.
Rectangular mazes (`deceptive_v2`) have the start below and the exits above. Circular mazes (`polar_v1`, see
puzzles/exit_polar.py) have the start in the middle and four or five exits around the rim; they are drawn on a round plate
with arc walls, and everything after the maze itself (markers, trace, timer, hook) is shared."""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..config import EXIT_HARD_ENTRANCE, EXIT_HARD_TRACE, exit_hard_round
from ..models import RoundSpec, VideoSpec
from ..puzzles import exit_polar, exit_shapes
from .easing import ease_in_out, ease_out_cubic
from .effects import rounded_surface
from .paths import trace_points
from .puzzle_fit import (PALETTE, _background, _clamp, _level_header, _rgb, _snap_burst, _text, _timer,
                         draw_puzzle_fit_outro, active_theme)
from .text import fitted_font, font

HOOK_TEXT = "ONLY ONE EXIT IS OPEN."
EXIT_COLORS = ("#FFC24B", "#B69CFF", "#FF7A45", "#4BE08A", "#4FC3FF")  # star, moon, sun, diamond, hexagon: equal brightness
POLAR_CENTRE = (540.0, 905.0)  # the middle of a circular maze (logical 1080x1920)
POLAR_PLATE = 508.0  # radius of the round plate under it
POLAR_EXIT_RADIUS = exit_polar.OUTER + 40  # where an exit's portal sits
WALL_TOP = "#6F7FE8"
WALL_BOTTOM = "#3A47A8"
WALL_RIM = "#C9D2FF"
FLOOR = "#0F1530"
FLOOR_ALT = "#121A38"
TRAIL = "#2EE6C5"
MAZE_BOX = (100, 400, 980, 1400)  # logical area for the grid itself
COVER_TIME = 0.6


def maze_geometry(data: dict) -> dict[str, float]:
    rows, columns = data["rows"], data["columns"]
    cell = min((MAZE_BOX[2] - MAZE_BOX[0]) / columns, (MAZE_BOX[3] - MAZE_BOX[1]) / rows)
    left = 540 - columns * cell / 2
    top = MAZE_BOX[1]
    return {"cell": cell, "left": left, "top": top, "right": left + columns * cell, "bottom": top + rows * cell,
            "wall": max(10.0, cell * .19)}


def cell_center(geometry: dict[str, float], columns: int, node: int) -> tuple[float, float]:
    row, column = divmod(node, columns)
    return geometry["left"] + (column + .5) * geometry["cell"], geometry["top"] + (row + .5) * geometry["cell"]


def exit_point(geometry: dict[str, float], columns: int, node: int) -> tuple[float, float]:
    return cell_center(geometry, columns, node)[0], geometry["top"] - geometry["cell"] * .62


def start_point(geometry: dict[str, float], columns: int, node: int) -> tuple[float, float]:
    return cell_center(geometry, columns, node)[0], geometry["bottom"] + geometry["cell"] * .55


def wall_segments(data: dict, geometry: dict[str, float]) -> list[tuple[float, float, float, float]]:
    rows, columns = data["rows"], data["columns"]
    edges = {tuple(edge) for edge in data["edges"]}
    cell, left, top = geometry["cell"], geometry["left"], geometry["top"]
    segments = []
    for row in range(rows):
        for column in range(columns):
            node = row * columns + column
            x, y = left + column * cell, top + row * cell
            if row == 0 and node not in data["exits"]:
                segments.append((x, y, x + cell, y))
            if column == 0:
                segments.append((x, y, x, y + cell))
            if column == columns - 1 or (node, node + 1) not in edges:
                segments.append((x + cell, y, x + cell, y + cell))
            if row == rows - 1:
                if node != data["start"]:
                    segments.append((x, y + cell, x + cell, y + cell))
            elif (node, node + columns) not in edges:
                segments.append((x, y + cell, x + cell, y + cell))
    return segments


# ---------------------------------------------------------------- circular mazes

def is_polar(data: dict) -> bool:
    return data.get("layout") == exit_polar.POLAR_LAYOUT


def polar_geometry(data: dict) -> dict:
    sectors = tuple(data["sectors"])
    rings = data["rings"]
    return {"sectors": sectors, "rings": rings, "graph": exit_polar.build_graph(sectors),
            "height": (exit_polar.OUTER - exit_polar.CENTRE) / rings}


def polar_point(radius: float, angle: float) -> tuple[float, float]:
    """A point at `radius` and `angle` (0 at the top, clockwise) around the middle of the maze."""
    return POLAR_CENTRE[0] + radius * math.sin(angle), POLAR_CENTRE[1] - radius * math.cos(angle)


def polar_node_center(geometry: dict, node: int) -> tuple[float, float]:
    graph = geometry["graph"]
    ring = graph["ring"][node]
    if ring == 0:
        return POLAR_CENTRE
    radius = exit_polar.CENTRE + (ring - .5) * geometry["height"]
    return polar_point(radius, exit_polar.angle_of(geometry["sectors"], graph, node))


def polar_exit_point(geometry: dict, node: int) -> tuple[float, float]:
    return polar_point(POLAR_EXIT_RADIUS, exit_polar.angle_of(geometry["sectors"], geometry["graph"], node))


def _arc(radius: float, start: float, end: float) -> list[tuple[float, float]]:
    steps = max(2, math.ceil(radius * abs(end - start) / 7))
    return [polar_point(radius, start + (end - start) * step / steps) for step in range(steps + 1)]


def polar_walls(data: dict, geometry: dict) -> list[list[tuple[float, float]]]:
    """Every wall as a polyline: arcs along the ring boundaries (merged into long runs) and short radial bars."""
    graph, sectors, height = geometry["graph"], geometry["sectors"], geometry["height"]
    edges = {tuple(edge) for edge in data["edges"]}
    exits = set(data["exits"])
    tau = 2 * math.pi
    walls: list[list[tuple[float, float]]] = []
    for boundary in range(geometry["rings"] + 1):  # 0: the middle disc, rings: the outer wall
        radius = exit_polar.CENTRE + boundary * height
        count = sectors[boundary] if boundary < geometry["rings"] else sectors[-1]
        # The outer ring's sectors at this boundary: cells of ring boundary + 1 (or the last ring for the outer wall).
        ring = min(boundary + 1, geometry["rings"])
        blocked = []
        for sector in range(sectors[ring - 1]):
            node = graph["offsets"][ring - 1] + sector
            if boundary == geometry["rings"]:
                blocked.append(node not in exits)
            else:
                blocked.append((exit_polar.inward_of(graph, node), node) not in edges)
        outer = sectors[ring - 1]
        if all(blocked):
            walls.append(_arc(radius, 0.0, tau))
            continue
        first = next(index for index, flag in enumerate(blocked) if not flag)
        run: list[int] = []
        for step in range(1, outer + 1):
            sector = (first + step) % outer
            if blocked[sector]:
                run.append(sector)
            if run and (not blocked[sector] or step == outer):
                start = run[0] * tau / outer
                end = start + len(run) * tau / outer
                walls.append(_arc(radius, start, end))
                run = []
    for ring in range(1, geometry["rings"] + 1):  # radial bars between sectors of a ring
        count = sectors[ring - 1]
        inner, outer_radius = exit_polar.CENTRE + (ring - 1) * height, exit_polar.CENTRE + ring * height
        for sector in range(count):
            node = graph["offsets"][ring - 1] + sector
            neighbour = graph["offsets"][ring - 1] + (sector + 1) % count
            if tuple(sorted((node, neighbour))) not in edges:
                angle = (sector + 1) * tau / count
                walls.append([polar_point(inner, angle), polar_point(outer_radius, angle)])
    return walls


# ---------------------------------------------------------------- static round layer

_ROUNDS: dict[str, RoundSpec] = {}


def _wall_mask(segments, scale: float, size: tuple[int, int], width: float) -> Image.Image:
    high = Image.new("L", (size[0] * 2, size[1] * 2), 0)
    draw = ImageDraw.Draw(high)
    w = max(2, round(width * scale * 2))
    radius = w / 2
    for x1, y1, x2, y2 in segments:
        a, b = (x1 * scale * 2, y1 * scale * 2), (x2 * scale * 2, y2 * scale * 2)
        draw.line((a, b), fill=255, width=w)
        for px, py in (a, b):
            draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=255)
    return high.resize(size, Image.Resampling.LANCZOS)


def _polyline_mask(polylines, scale: float, size: tuple[int, int], width: float) -> Image.Image:
    """Round-capped thick polylines (the circular maze's arc and radial walls), drawn at 2x and shrunk once."""
    high = Image.new("L", (size[0] * 2, size[1] * 2), 0)
    draw = ImageDraw.Draw(high)
    w = max(2, round(width * scale * 2))
    radius = w / 2
    for points in polylines:
        scaled = [(x * scale * 2, y * scale * 2) for x, y in points]
        draw.line(scaled, fill=255, width=w, joint="curve")
        for px, py in (scaled[0], scaled[-1]):
            draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=255)
    return high.resize(size, Image.Resampling.LANCZOS)


def _vertical_gradient(size: tuple[int, int], top: str, bottom: str, y0: float, y1: float) -> Image.Image:
    height = size[1]
    ramp = np.clip((np.arange(height, dtype=np.float32) - y0) / max(1.0, y1 - y0), 0, 1)[:, None]
    colors = np.array(_rgb(top), np.float32) * (1 - ramp) + np.array(_rgb(bottom), np.float32) * ramp
    column = colors.astype(np.uint8)[:, None, :]
    return Image.fromarray(np.repeat(column, size[0], axis=1))


def is_cells(data: dict) -> bool:
    return data.get("layout") == exit_shapes.CELLS_LAYOUT


def cells_layout(data: dict) -> exit_shapes.Layout:
    return exit_shapes.layout_of(data["shape"], data["size"])


def cells_xy(point: tuple[float, float]) -> tuple[float, float]:
    return POLAR_CENTRE[0] + point[0], POLAR_CENTRE[1] + point[1]


def cells_exit_point(layout: exit_shapes.Layout, node: int) -> tuple[float, float]:
    """Where an exit's portal sits: just outside the middle of its cell's opening."""
    middle, normal, _ = layout.gate(node)
    return POLAR_CENTRE[0] + middle[0] + normal[0] * exit_shapes.GATE, POLAR_CENTRE[1] + middle[1] + normal[1] * exit_shapes.GATE


def cells_walls(data: dict, layout: exit_shapes.Layout) -> list[list[tuple[float, float]]]:
    """Every wall as a two-point polyline: the edges between cells that are not joined, and the outer edge except the openings."""
    joined = {tuple(edge) for edge in data["edges"]}
    openings = {layout.gate(node)[2] for node in data["exits"]}
    walls = [[cells_xy(first), cells_xy(second)] for pair, (first, second) in layout.shared.items() if pair not in joined]
    for edges in layout.outer_edges:
        walls += [[cells_xy(first), cells_xy(second)] for first, second in edges if (first, second) not in openings]
    return walls


CELLS_FRAME_GROW = 20.0  # how far the shape's own frame reaches beyond its cells and portals (logical px)
CELLS_PORTAL_REACH = 34.0


def _cells_frame_mask(data: dict, layout: exit_shapes.Layout, size: tuple[int, int], scale: float, grow: float) -> Image.Image:
    """The maze's cells and exit portals grown by `grow` logical px with round corners: a frame in the maze's own shape."""
    small = 4
    mask = Image.new("L", (max(1, size[0] // small), max(1, size[1] // small)), 0)
    draw = ImageDraw.Draw(mask)
    k = scale / small
    for polygon in layout.polygons:
        draw.polygon([(x * k, y * k) for x, y in map(cells_xy, polygon)], fill=255)
    for node in data["exits"]:
        x, y = cells_exit_point(layout, node)
        r = CELLS_PORTAL_REACH * k
        draw.ellipse((x * k - r, y * k - r, x * k + r, y * k + r), fill=255)
    # A blurred step edge crosses 8 % about 1.42 sigma outside the shape: that is the grown outline.
    grown = mask.filter(ImageFilter.GaussianBlur(max(0.5, grow * k / 1.42))).point(lambda value: 255 if value > 20 else 0)
    grown = grown.resize(size, Image.Resampling.BICUBIC).filter(ImageFilter.GaussianBlur(max(0.6, .8 * scale)))
    return grown.point(lambda value: max(0, min(255, round((value - 128) * 3 + 128))))


def _cells_frame(image: Image.Image, data: dict, layout: exit_shapes.Layout, size: tuple[int, int], scale: float) -> None:
    """A dark card shaped like the maze (a hexagon frame for the hexagon, and so on) with an edge line and a soft shadow."""
    outer = _cells_frame_mask(data, layout, size, scale, CELLS_FRAME_GROW)
    inner = _cells_frame_mask(data, layout, size, scale, CELLS_FRAME_GROW - 4)
    shadow = ImageChops.offset(outer, 0, round(14 * scale)).filter(ImageFilter.GaussianBlur(max(1.0, 22 * scale)))
    image.paste(Image.new("RGB", size, (0, 0, 0)), (0, 0), shadow.point(lambda value: value * 150 // 255))
    image.paste(Image.new("RGB", size, _rgb(PALETTE["surface_edge"])), (0, 0), outer)
    image.paste(Image.new("RGB", size, _rgb(PALETTE["surface"])), (0, 0), inner)


def _cells_layer(round_spec: RoundSpec, size: tuple[int, int], theme: str) -> Image.Image:
    data = round_spec.data
    scale = size[0] / 1080
    layout = cells_layout(data)
    image = _background(size, POLAR_CENTRE[1], theme).copy()
    s = lambda values: tuple(value * scale for value in values)
    cx, cy = POLAR_CENTRE
    _cells_frame(image, data, layout, size, scale)
    draw = ImageDraw.Draw(image)
    for node, polygon in enumerate(layout.polygons):  # a faint floor, banded by the distance from the middle
        band = int(layout.depth[node] * 10)
        draw.polygon([(x * scale, y * scale) for x, y in map(cells_xy, polygon)], fill=FLOOR if band % 2 else FLOOR_ALT)
    light = Image.new("L", size, 0)
    light_draw = ImageDraw.Draw(light)
    for node in data["exits"]:
        x, y = cells_exit_point(layout, node)
        radius = layout.unit * 2.4
        light_draw.ellipse(s((x - radius, y - radius, x + radius, y + radius)), fill=100)
    light = light.filter(ImageFilter.GaussianBlur(layout.unit * .9 * scale))
    image.paste(Image.new("RGB", size, "#8C7BFF"), (0, 0), light.point(lambda value: value * 45 // 255))
    wall = max(7.0, min(11.0, layout.unit * .2))
    mask = _polyline_mask(cells_walls(data, layout), scale, size, wall)
    offset = max(2, round(wall * .55 * scale))
    shadow = ImageChops.offset(mask, offset, round(offset * 1.4)).filter(ImageFilter.GaussianBlur(offset * 1.2))
    image.paste(Image.new("RGB", size, (0, 0, 0)), (0, 0), shadow.point(lambda value: value * 170 // 255))
    body = _vertical_gradient(size, WALL_TOP, WALL_BOTTOM, (cy - exit_shapes.OUTER) * scale, (cy + exit_shapes.OUTER) * scale)
    image.paste(body, (0, 0), mask)
    bevel = max(1, round(wall * .22 * scale))
    rim = ImageChops.subtract(mask, ImageChops.offset(mask, bevel, bevel))
    image.paste(Image.new("RGB", size, WALL_RIM), (0, 0), rim.point(lambda value: value * 150 // 255))
    dark = ImageChops.subtract(mask, ImageChops.offset(mask, -bevel, -bevel))
    image.paste(Image.new("RGB", size, "#1E255E"), (0, 0), dark.point(lambda value: value * 160 // 255))
    return image


def _polar_layer(round_spec: RoundSpec, size: tuple[int, int], theme: str) -> Image.Image:
    data = round_spec.data
    scale = size[0] / 1080
    geometry = polar_geometry(data)
    graph, sectors, height = geometry["graph"], geometry["sectors"], geometry["height"]
    image = _background(size, POLAR_CENTRE[1], theme).copy()
    s = lambda values: tuple(value * scale for value in values)
    cx, cy = POLAR_CENTRE
    rounded_surface(image, s((cx - POLAR_PLATE, cy - POLAR_PLATE, cx + POLAR_PLATE, cy + POLAR_PLATE)), POLAR_PLATE * scale,
                    PALETTE["surface"], PALETTE["surface_edge"], 3 * scale, shadow=True)
    # Floor: faint checker cells (annular sectors) lit from the exits around the rim.
    draw = ImageDraw.Draw(image)
    tau = 2 * math.pi
    for ring in range(1, geometry["rings"] + 1):
        inner, outer = exit_polar.CENTRE + (ring - 1) * height, exit_polar.CENTRE + ring * height
        count = sectors[ring - 1]
        for sector in range(count):
            a0, a1 = sector * tau / count, (sector + 1) * tau / count
            points = _arc(outer, a0, a1) + _arc(inner, a1, a0)
            draw.polygon([(x * scale, y * scale) for x, y in points], fill=FLOOR if (ring + sector) % 2 else FLOOR_ALT)
    disc = exit_polar.CENTRE
    draw.ellipse(s((cx - disc, cy - disc, cx + disc, cy + disc)), fill=FLOOR)
    light = Image.new("L", size, 0)
    light_draw = ImageDraw.Draw(light)
    for node in data["exits"]:
        x, y = polar_exit_point(geometry, node)
        radius = height * 2.6
        light_draw.ellipse(s((x - radius, y - radius, x + radius, y + radius)), fill=100)
    light = light.filter(ImageFilter.GaussianBlur(height * .9 * scale))
    image.paste(Image.new("RGB", size, "#8C7BFF"), (0, 0), light.point(lambda value: value * 45 // 255))
    # Walls: blurred drop shadow, gradient body lit from the top, and a bright rim on the lit edges.
    wall = max(8.0, height * .2)
    mask = _polyline_mask(polar_walls(data, geometry), scale, size, wall)
    offset = max(2, round(wall * .55 * scale))
    shadow = ImageChops.offset(mask, offset, round(offset * 1.4)).filter(ImageFilter.GaussianBlur(offset * 1.2))
    image.paste(Image.new("RGB", size, (0, 0, 0)), (0, 0), shadow.point(lambda value: value * 170 // 255))
    body = _vertical_gradient(size, WALL_TOP, WALL_BOTTOM, (cy - exit_polar.OUTER) * scale, (cy + exit_polar.OUTER) * scale)
    image.paste(body, (0, 0), mask)
    bevel = max(1, round(wall * .22 * scale))
    rim = ImageChops.subtract(mask, ImageChops.offset(mask, bevel, bevel))
    image.paste(Image.new("RGB", size, WALL_RIM), (0, 0), rim.point(lambda value: value * 150 // 255))
    dark = ImageChops.subtract(mask, ImageChops.offset(mask, -bevel, -bevel))
    image.paste(Image.new("RGB", size, "#1E255E"), (0, 0), dark.point(lambda value: value * 160 // 255))
    return image


@lru_cache(maxsize=5)
def _round_layer(round_key: str, size: tuple[int, int], theme: str = "violet") -> Image.Image:
    round_spec = _ROUNDS[round_key]
    data = round_spec.data
    if is_polar(data):
        return _polar_layer(round_spec, size, theme)
    if is_cells(data):
        return _cells_layer(round_spec, size, theme)
    scale = size[0] / 1080
    geometry = maze_geometry(data)
    columns = data["columns"]
    image = _background(size, 900, theme).copy()
    s = lambda values: tuple(value * scale for value in values)
    card = (geometry["left"] - 44, geometry["top"] - geometry["cell"] * 1.25, geometry["right"] + 44, geometry["bottom"] + geometry["cell"] * 1.15)
    rounded_surface(image, s(card), 60 * scale, PALETTE["surface"], PALETTE["surface_edge"], 3 * scale, shadow=True)
    # Floor: faint checker tiles lit from the exits above.
    draw = ImageDraw.Draw(image)
    cell = geometry["cell"]
    for row in range(data["rows"]):
        for column in range(columns):
            x, y = geometry["left"] + column * cell, geometry["top"] + row * cell
            draw.rectangle(s((x, y, x + cell, y + cell)), fill=FLOOR if (row + column) % 2 else FLOOR_ALT)
    light = Image.new("L", size, 0)
    light_draw = ImageDraw.Draw(light)
    for node in data["exits"]:
        cx, cy = exit_point(geometry, columns, node)
        radius = cell * 2.4
        light_draw.ellipse(s((cx - radius, geometry["top"] - radius * .5, cx + radius, geometry["top"] + radius * 1.4)), fill=90)
    light = light.filter(ImageFilter.GaussianBlur(cell * .9 * scale))
    image.paste(Image.new("RGB", size, "#8C7BFF"), (0, 0), light.point(lambda value: value * 45 // 255))
    # Walls: blurred drop shadow, gradient body lit from the top, and a bright rim on the lit edges.
    mask = _wall_mask(wall_segments(data, geometry), scale, size, geometry["wall"])
    offset = max(2, round(geometry["wall"] * .55 * scale))
    shadow = ImageChops.offset(mask, offset, round(offset * 1.4)).filter(ImageFilter.GaussianBlur(offset * 1.2))
    image.paste(Image.new("RGB", size, (0, 0, 0)), (0, 0), shadow.point(lambda value: value * 170 // 255))
    body = _vertical_gradient(size, WALL_TOP, WALL_BOTTOM, geometry["top"] * scale, geometry["bottom"] * scale)
    image.paste(body, (0, 0), mask)
    bevel = max(1, round(geometry["wall"] * .22 * scale))
    rim = ImageChops.subtract(mask, ImageChops.offset(mask, bevel, bevel))
    image.paste(Image.new("RGB", size, WALL_RIM), (0, 0), rim.point(lambda value: value * 150 // 255))
    dark = ImageChops.subtract(mask, ImageChops.offset(mask, -bevel, -bevel))
    image.paste(Image.new("RGB", size, "#1E255E"), (0, 0), dark.point(lambda value: value * 160 // 255))
    return image


# ---------------------------------------------------------------- markers

def _glow_disc(image: Image.Image, center: tuple[float, float], radius: float, color: str, strength: float) -> None:
    if strength <= 0:
        return
    pad = int(radius * 2)
    size = (pad * 2, pad * 2)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse((pad - radius, pad - radius, pad + radius, pad + radius), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(radius * .55)).point(lambda value: round(value * min(1.0, strength)))
    image.paste(Image.new("RGB", size, color), (round(center[0] - pad), round(center[1] - pad)), mask)


def _symbol(draw: ImageDraw.ImageDraw, index: int, x: float, y: float, radius: float, color, cutout) -> None:
    if index == 0:
        points = [(x + math.sin(i * math.pi / 5) * radius * (1 if i % 2 == 0 else .46),
                   y - math.cos(i * math.pi / 5) * radius * (1 if i % 2 == 0 else .46)) for i in range(10)]
        draw.polygon(points, fill=color)
    elif index == 1:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
        draw.ellipse((x - radius * .2, y - radius * 1.1, x + radius * 1.15, y + radius * .4), fill=cutout)
    elif index == 3:  # diamond (levels with four exits)
        draw.polygon([(x, y - radius), (x + radius * .78, y), (x, y + radius), (x - radius * .78, y)], fill=color)
    elif index == 4:  # hexagon (levels with five exits)
        draw.polygon([(x + math.cos(math.pi / 3 * i + math.pi / 6) * radius, y + math.sin(math.pi / 3 * i + math.pi / 6) * radius)
                      for i in range(6)], fill=color)
    else:
        draw.ellipse((x - radius * .6, y - radius * .6, x + radius * .6, y + radius * .6), fill=color)
        for i in range(8):
            angle = i * math.pi / 4
            draw.line((x + math.cos(angle) * radius * .78, y + math.sin(angle) * radius * .78,
                       x + math.cos(angle) * radius * 1.12, y + math.sin(angle) * radius * 1.12),
                      fill=color, width=max(2, round(radius * .16)))


def _exit_portal(image: Image.Image, index: int, center: tuple[float, float], radius: float, glow: float, dim: float) -> None:
    from ..palette import object_color
    color = object_color(EXIT_COLORS[index])
    _glow_disc(image, center, radius * 1.7, color, .55 * glow * (1 - dim))
    draw = ImageDraw.Draw(image)
    x, y = center
    ring = radius * 1.18
    fill = tuple(round(channel * (1 - .65 * dim)) for channel in _rgb("#1B2350"))
    draw.ellipse((x - ring, y - ring, x + ring, y + ring), fill=fill,
                 outline=tuple(round(c * (1 - .6 * dim)) for c in _rgb(color)), width=max(2, round(radius * .12)))
    symbol_color = tuple(round(c * (1 - .6 * dim)) for c in _rgb(color))
    _symbol(draw, index, x, y, radius * .72, symbol_color, fill)


def _start_orb(image: Image.Image, center: tuple[float, float], radius: float, local: float, heading: float = 0.0,
               arrow: bool = False) -> None:
    """The start marker: its triangle points up, or `heading` radians clockwise from up. A circular maze (`arrow`) shows a real
    arrow, a shaft with a head, because a plain triangle has three corners and is hard to read as a direction."""
    pulse = .5 + .5 * math.sin(local * 5)
    _glow_disc(image, center, radius * (1.6 + .25 * pulse), TRAIL, .7)
    draw = ImageDraw.Draw(image)
    x, y = center
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=TRAIL, outline=PALETTE["text_light"], width=max(2, round(radius * .12)))
    tip = radius * .5
    cosine, sine = math.cos(heading), math.sin(heading)
    corners = [(-tip, tip * .55), (0.0, -tip * .75), (tip, tip * .55)]
    if arrow:  # shaft from the bottom, a wide head, and a sharp tip toward the opening
        corners = [(-radius * .15, radius * .58), (-radius * .15, -radius * .08), (-radius * .5, -radius * .08), (0.0, -radius * .86),
                   (radius * .5, -radius * .08), (radius * .15, -radius * .08), (radius * .15, radius * .58)]
    draw.polygon([(x + dx * cosine - dy * sine, y + dx * sine + dy * cosine) for dx, dy in corners], fill=PALETTE["background"])


# ---------------------------------------------------------------- trace

def _trail(image: Image.Image, points: list[tuple[float, float]], width: float, scale: float) -> None:
    if len(points) < 2:
        return
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    pad = width * 4
    left, top = int(min(xs) - pad), int(min(ys) - pad)
    right, bottom = int(max(xs) + pad), int(max(ys) + pad)
    size = (max(1, right - left), max(1, bottom - top))
    local = [(x - left, y - top) for x, y in points]
    # Bloom at quarter resolution keeps the glow cheap at Final size.
    quarter = (max(1, size[0] // 4), max(1, size[1] // 4))
    bloom = Image.new("L", quarter, 0)
    ImageDraw.Draw(bloom).line([(x / 4, y / 4) for x, y in local], fill=255, width=max(1, round(width * 1.6 / 4)), joint="curve")
    bloom = bloom.filter(ImageFilter.GaussianBlur(max(1.0, width / 4))).resize(size, Image.Resampling.BILINEAR)
    image.paste(Image.new("RGB", size, TRAIL), (left, top), bloom.point(lambda value: value * 150 // 255))
    core = Image.new("L", size, 0)
    core_draw = ImageDraw.Draw(core)
    core_draw.line(local, fill=255, width=max(2, round(width)), joint="curve")
    for x, y in (local[0], local[-1]):
        r = width / 2
        core_draw.ellipse((x - r, y - r, x + r, y + r), fill=255)
    image.paste(Image.new("RGB", size, TRAIL), (left, top), core)
    highlight = Image.new("L", size, 0)
    ImageDraw.Draw(highlight).line(local, fill=255, width=max(1, round(width * .35)), joint="curve")
    image.paste(Image.new("RGB", size, "#D9FFF7"), (left, top), highlight.point(lambda value: value * 200 // 255))


# ---------------------------------------------------------------- frames

def _round_image(spec: VideoSpec, round_index: int, size: tuple[int, int]) -> Image.Image:
    round_spec = spec.rounds[round_index]
    key = f"{spec.id}:{round_spec.fingerprint()}"
    _ROUNDS[key] = round_spec
    return _round_layer(key, size, active_theme()).copy()


def maze_unit(data: dict) -> float:
    """A characteristic cell size: the cell of a rectangular maze, the ring height of a circular one."""
    if is_cells(data):
        return cells_layout(data).unit
    return polar_geometry(data)["height"] * 1.1 if is_polar(data) else maze_geometry(data)["cell"]


def exit_position(round_spec: RoundSpec) -> tuple[float, float]:
    data = round_spec.data
    node = data["exits"][round_spec.answer]
    if is_cells(data):
        return cells_exit_point(cells_layout(data), node)
    if is_polar(data):
        return polar_exit_point(polar_geometry(data), node)
    return exit_point(maze_geometry(data), data["columns"], node)


def _draw_polar_markers(image: Image.Image, round_spec: RoundSpec, local: float, scale: float, arrival: float | None) -> None:
    data = round_spec.data
    geometry = polar_geometry(data)
    radius = 30.0 * scale
    for index, node in enumerate(data["exits"]):
        x, y = polar_exit_point(geometry, node)
        dim = 0.0 if arrival is None or index == round_spec.answer else _clamp(arrival / .3)
        glow = 1.0 + (.8 * (1 - _clamp(arrival / .8)) if arrival is not None and index == round_spec.answer else 0)
        _exit_portal(image, index, (x * scale, y * scale), radius, glow, dim)
    graph = geometry["graph"]
    heading = exit_polar.angle_of(geometry["sectors"], graph, data["route"][1])  # toward the one opening of the middle
    orb = min(exit_polar.CENTRE * .6, 34.0)
    _start_orb(image, (POLAR_CENTRE[0] * scale, POLAR_CENTRE[1] * scale), orb * scale, local, heading, arrow=True)


def _draw_cells_markers(image: Image.Image, round_spec: RoundSpec, local: float, scale: float, arrival: float | None) -> None:
    data = round_spec.data
    layout = cells_layout(data)
    radius = 30.0 * scale
    for index, node in enumerate(data["exits"]):
        x, y = cells_exit_point(layout, node)
        dim = 0.0 if arrival is None or index == round_spec.answer else _clamp(arrival / .3)
        glow = 1.0 + (.8 * (1 - _clamp(arrival / .8)) if arrival is not None and index == round_spec.answer else 0)
        _exit_portal(image, index, (x * scale, y * scale), radius, glow, dim)
    sx, sy = cells_xy(layout.centers[data["start"]])
    nx, ny = cells_xy(layout.centers[data["route"][1]])
    heading = math.atan2(nx - sx, -(ny - sy))  # toward the one opening of the start cell
    inradius = min(math.dist(layout.centers[data["start"]], (a[0] / 2 + b[0] / 2, a[1] / 2 + b[1] / 2))
                   for a, b in [layout.shared.get((min(data["start"], other), max(data["start"], other))) for other in layout.adj[data["start"]]])
    _start_orb(image, (sx * scale, sy * scale), max(13.0, min(26.0, inradius * 1.25)) * scale, local, heading, arrow=True)


def _draw_markers(image: Image.Image, round_spec: RoundSpec, local: float, scale: float, arrival: float | None) -> None:
    data = round_spec.data
    if is_cells(data):
        _draw_cells_markers(image, round_spec, local, scale, arrival)
        return
    if is_polar(data):
        _draw_polar_markers(image, round_spec, local, scale, arrival)
        return
    geometry = maze_geometry(data)
    columns = data["columns"]
    radius = min(34.0, max(24.0, geometry["cell"] * .36)) * scale  # exits stay readable on the tightest grids
    for index, node in enumerate(data["exits"]):
        x, y = exit_point(geometry, columns, node)
        dim = 0.0 if arrival is None or index == round_spec.answer else _clamp(arrival / .3)
        glow = 1.0 + (.8 * (1 - _clamp(arrival / .8)) if arrival is not None and index == round_spec.answer else 0)
        _exit_portal(image, index, (x * scale, y * scale), radius, glow, dim)
    sx, sy = start_point(geometry, columns, data["start"])
    _start_orb(image, (sx * scale, sy * scale), radius * .82, local)


def _smooth(points: list[tuple[float, float]], rounds: int = 3) -> list[tuple[float, float]]:
    """Round the corners of a dense polyline (a moving average, the ends fixed) without cutting the arcs short."""
    for _ in range(rounds):
        points = [points[0]] + [((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3)
                                for a, b, c in zip(points, points[1:], points[2:])] + [points[-1]]
    return points


def _turn(first: float, second: float) -> float:
    """The shortest signed angle from `first` to `second`."""
    return (second - first + math.pi) % (2 * math.pi) - math.pi


def _drop_reversals(corners: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Cut the spikes where the trace runs into a cell and straight back out along the same ring or radius."""
    result: list[tuple[float, float]] = []
    for corner in corners:
        if result and abs(result[-1][0] - corner[0]) < 1e-6 and abs(_turn(result[-1][1], corner[1])) < 1e-9:
            continue  # the same point twice
        result.append(corner)
        while len(result) >= 3:
            (r0, a0), (r1, a1), (r2, a2) = result[-3:]
            along_ring = abs(r0 - r1) < 1e-6 and abs(r1 - r2) < 1e-6 and _turn(a0, a1) * _turn(a1, a2) < 0
            along_radius = abs(_turn(a0, a1)) < 1e-9 and abs(_turn(a1, a2)) < 1e-9 and (r1 - r0) * (r2 - r1) < 0
            if not (along_ring or along_radius):
                break
            del result[-2]  # P0 -> P2 stays inside the same corridor as P0 -> P1 -> P2
    return result


def _polar_route(round_spec: RoundSpec) -> list[tuple[float, float]]:
    """The answer route of a circular maze as a neat trace: it follows the corridors (along a ring, or straight along a
    radius) instead of cutting from cell centre to cell centre, never doubles back on itself, and has rounded corners."""
    data = round_spec.data
    geometry = polar_geometry(data)
    graph, sectors, height = geometry["graph"], geometry["sectors"], geometry["height"]

    def polar(node: int) -> tuple[float, float]:
        return (exit_polar.CENTRE + (graph["ring"][node] - .5) * height, exit_polar.angle_of(sectors, graph, node))

    route = data["route"]
    corners = [(0.0, polar(route[1])[1])]  # the middle, seen from the first cell's angle
    for position, node in enumerate(route[1:], start=1):
        radius, angle = polar(node)
        if position > 1:
            before = route[position - 1]
            if graph["ring"][before] != graph["ring"][node]:
                # A radial step between rings of different sector counts: slide along the inner cell to the outer cell's
                # angle first (or leave the outer cell straight inward first), so every move stays inside a corridor.
                before_radius, before_angle = polar(before)
                corners.append((before_radius, angle) if graph["ring"][before] < graph["ring"][node] else (radius, before_angle))
        corners.append((radius, angle))
    corners.append((POLAR_EXIT_RADIUS, corners[-1][1]))  # out through the rim to the portal
    corners = _drop_reversals(corners)

    points = [POLAR_CENTRE]
    for (r1, a1), (r2, a2) in zip(corners, corners[1:]):
        turn = _turn(a1, a2)
        steps = max(1, math.ceil((abs(r2 - r1) + abs(turn) * (r1 + r2) / 2) / 8))
        points += [polar_point(r1 + (r2 - r1) * step / steps, a1 + turn * step / steps) for step in range(1, steps + 1)]
    return _smooth(points)


def _cells_route(round_spec: RoundSpec) -> list[tuple[float, float]]:
    """The answer route of a shaped maze: through the cells' middles, out through the opening, with rounded corners."""
    data = round_spec.data
    layout = cells_layout(data)
    corners = [cells_xy(layout.centers[node]) for node in data["route"]] + [cells_exit_point(layout, data["exits"][round_spec.answer])]
    points = [corners[0]]
    for (x1, y1), (x2, y2) in zip(corners, corners[1:]):
        steps = max(1, math.ceil(math.dist((x1, y1), (x2, y2)) / 8))
        points += [(x1 + (x2 - x1) * step / steps, y1 + (y2 - y1) * step / steps) for step in range(1, steps + 1)]
    return _smooth(points)


def route_polyline(round_spec: RoundSpec) -> list[tuple[float, float]]:
    data = round_spec.data
    if is_cells(data):
        return _cells_route(round_spec)
    if is_polar(data):
        return _polar_route(round_spec)
    geometry = maze_geometry(data)
    columns = data["columns"]
    return ([start_point(geometry, columns, data["start"])] + [cell_center(geometry, columns, node) for node in data["route"]]
            + [exit_point(geometry, columns, data["exits"][round_spec.answer])])


def schedule(spec: VideoSpec) -> list[tuple[float, float]]:
    """(start, duration) of every level; bigger mazes get more thinking time, so later levels last longer."""
    from ..puzzles.find_the_exit import round_thinking
    result, start = [], spec.intro_duration
    for item in spec.rounds:
        duration = exit_hard_round(round_thinking(item.data))
        result.append((start, duration))
        start += duration
    return result


CAPTIONS = ("Warm up. Stay sharp.", "A little trickier now.", "Don't trust the first path.", "More exits. More traps.",
            "Last level. Make it count.")


def level_caption(index: int, count: int) -> str:
    """A short line under the maze that eggs the viewer on: a warm-up first, a final push last, a harder tone between."""
    if index == 0:
        return CAPTIONS[0]
    if index == count - 1:
        return CAPTIONS[-1]
    middle = CAPTIONS[1:-1]
    return middle[(index - 1) % len(middle)]


def caption_y(data: dict) -> float:
    """Where the caption sits: just below the maze's plate or card."""
    if is_polar(data) or is_cells(data):
        return POLAR_CENTRE[1] + POLAR_PLATE + 78
    geometry = maze_geometry(data)
    return min(1640.0, geometry["bottom"] + geometry["cell"] * 1.15 + 78)


def _caption(image: Image.Image, text: str, y: float, scale: float, opacity: float) -> None:
    """Quiet white text with a soft shadow: it motivates without crowding the screen."""
    if opacity <= 0:
        return
    face = fitted_font(text, round(860 * scale), round(54 * scale))
    _text(image, (540 * scale, (y + 3) * scale), text, face, "#000000", opacity * .45)
    _text(image, (540 * scale, y * scale), text, face, PALETTE["text_light"], opacity * .94)


def draw_exit_hard_round(spec: VideoSpec, round_index: int, local: float, size: tuple[int, int]) -> Image.Image:
    from ..puzzles.find_the_exit import round_thinking
    scale = size[0] / 1080
    image = _round_image(spec, round_index, size)
    round_spec = spec.rounds[round_index]
    thinking = round_thinking(round_spec.data)
    think_end = EXIT_HARD_ENTRANCE + thinking
    arrival_at = think_end + EXIT_HARD_TRACE
    arrival = local - arrival_at if local >= arrival_at else None
    if local >= think_end:
        progress = ease_in_out(_clamp((local - think_end) / EXIT_HARD_TRACE))
        traced = [(x * scale, y * scale) for x, y in trace_points(route_polyline(round_spec), progress)]
        unit = maze_unit(round_spec.data)
        _trail(image, traced, unit * .2 * scale, scale)
        hx, hy = traced[-1]
        _glow_disc(image, (hx, hy), unit * .32 * scale, "#FFFFFF", .9)
    _draw_markers(image, round_spec, local, scale, arrival)
    if arrival is not None:
        ex, ey = exit_position(round_spec)
        _snap_burst(image, (ex, ey), maze_unit(round_spec.data) * 1.1, arrival, scale)
    if spec.metadata.get("captions") != "off":  # on while thinking, fading as the trace sets off
        shown = _clamp((local - .5) / .35) * (1 - _clamp((local - think_end) / .3))
        _caption(image, level_caption(round_index, spec.round_count), caption_y(round_spec.data), scale, shown)
    header = _clamp(local / .25)
    _level_header(image, round_spec.data.get("level", round_index + 1), spec.round_count, header, scale)
    if local < think_end:
        remaining = thinking if local < .35 else think_end - local
        _timer(image, remaining, thinking, header * (_clamp(local / .3) if local < .35 else 1), scale)
    else:
        _timer(image, .001, 1, 1 - _clamp((local - think_end) / .25), scale)
    if round_index > 0 and local < .3:
        alpha = round(200 * (1 - ease_out_cubic(local / .3)))
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (alpha,))
        image.paste(overlay, (0, 0), overlay)
    transition_start = exit_hard_round(thinking) - .2
    if local > transition_start and round_index < spec.round_count - 1:
        alpha = round(200 * ease_in_out((local - transition_start) / .2))
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (alpha,))
        image.paste(overlay, (0, 0), overlay)
    return image


def draw_exit_hard_intro(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    """Hook: level one's real maze is on screen from the first frame under a bold challenge line."""
    scale = size[0] / 1080
    image = _round_image(spec, 0, size)
    _draw_markers(image, spec.rounds[0], t - spec.intro_duration, scale, None)
    fade = 1 - _clamp((t - (spec.intro_duration - .22)) / .22)
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .18)))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(940 * scale), round(78 * scale)),
          PALETTE["text_light"], fade * _clamp(t / .08 + .3), slam)
    subtitle = f"{spec.round_count} LEVELS · EACH ONE HARDER"
    _text(image, (540 * scale, 232 * scale), subtitle, font(round(34 * scale)), PALETTE["accent"], fade * _clamp((t - .15) / .2))
    return image


def draw_exit_hard_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        return draw_exit_hard_intro(spec, t, size)
    levels = schedule(spec)
    rounds_end = levels[-1][0] + levels[-1][1]
    if t >= rounds_end:
        return draw_puzzle_fit_outro(spec, t - rounds_end, size)
    round_index = max(index for index, (start, _) in enumerate(levels) if t >= start)
    return draw_exit_hard_round(spec, round_index, t - levels[round_index][0], size)


def uses_exit_hard_look(spec: VideoSpec) -> bool:
    return spec.puzzle_type == "find_the_exit" and bool(spec.rounds) and spec.rounds[0].data.get("layout") in ("deceptive_v2", "polar_v1", "cells_v1")

