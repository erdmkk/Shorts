from __future__ import annotations

import math
from functools import lru_cache
from PIL import Image, ImageDraw

from ..config import LINE_FOLLOW_FINAL_PATH_SCALE, thinking_duration
from ..models import RoundSpec
from ..puzzles.line_follow import crossing_curve, crossing_halo_curve, geometry, lane_positions, TOP, BOTTOM
from .effects import draw_progress_bar, rounded_card


def trace_points(points: list[tuple[float, float]], progress: float) -> list[tuple[float, float]]:
    progress = min(1.0, max(0.0, progress))
    remaining = sum(math.dist(a, b) for a, b in zip(points, points[1:])) * progress
    result = [points[0]]
    for a, b in zip(points, points[1:]):
        length = math.dist(a, b)
        if remaining >= length:
            result.append(b)
            remaining -= length
        else:
            fraction = remaining / max(length, 1e-9)
            result.append((a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction))
            break
    return result


def marker(draw: ImageDraw.ImageDraw, point: tuple[float, float], radius: float, index: int, color: str, background: str) -> None:
    x, y = point
    if index == 0:
        vertices = [(x + math.sin(i * math.pi / 5) * radius * (1 if i % 2 == 0 else 0.46),
                     y - math.cos(i * math.pi / 5) * radius * (1 if i % 2 == 0 else 0.46)) for i in range(10)]
        draw.polygon(vertices, fill=color)
    elif index == 1:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
        draw.ellipse((x - radius * 0.2, y - radius * 1.1, x + radius * 1.15, y + radius * 0.4), fill=background)
    elif index == 2:
        draw.ellipse((x - radius * 0.65, y - radius * 0.65, x + radius * 0.65, y + radius * 0.65), fill=color)
        for i in range(8):
            angle = i * math.pi / 4
            draw.line((x + math.cos(angle) * radius * 0.8, y + math.sin(angle) * radius * 0.8,
                       x + math.cos(angle) * radius * 1.1, y + math.sin(angle) * radius * 1.1), fill=color, width=max(2, round(radius * 0.12)))
    elif index == 3:
        draw.polygon(((x, y - radius), (x + radius, y), (x, y + radius), (x - radius, y)), fill=color)
    else:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
        draw.ellipse((x - radius * 0.48, y - radius * 0.48, x + radius * 0.48, y + radius * 0.48), fill=background)


LINE_LAYER_BOUNDS = (150.0, 380.0, 930.0, 1430.0)


def _smooth_stroke(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], fill: str, width: int) -> None:
    if len(points) < 2:
        return
    draw.line(points, fill=fill, width=width, joint="curve")
    radius = (width - 1) / 2
    # Only cap the two ends. Capping every densely sampled vertex caused the
    # old scalloped, hand-drawn edge after integer raster quantization.
    for x, y in (points[0], points[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def _layer_points(points: list[tuple[float, float]], scale: float) -> list[tuple[int, int]]:
    left, top, _, _ = LINE_LAYER_BOUNDS
    # Quantize only at the final high-resolution raster boundary.
    return [(round((x - left) * scale), round((y - top) * scale)) for x, y in points]


def _new_line_layer(scale: float) -> Image.Image:
    left, top, right, bottom = LINE_LAYER_BOUNDS
    return Image.new("RGBA", (round((right - left) * scale), round((bottom - top) * scale)), (0, 0, 0, 0))


@lru_cache(maxsize=10)
def _static_line_layer(swaps: tuple[int, ...], path_count: int, target_width: int, color: str, surface: str) -> Image.Image:
    composition_scale = target_width / 1080
    # Final composition is 2×; paths alone rasterize at 4× Final and then
    # downsample into that composition. Draft paths get inexpensive 2× AA.
    render_scale = float(LINE_FOLLOW_FINAL_PATH_SCALE) if target_width >= 2160 else max(1.0, composition_scale)
    layer = _new_line_layer(render_scale)
    draw = ImageDraw.Draw(layer)
    paths, crossings, _ = geometry(list(swaps), path_count)
    for path in paths:
        _smooth_stroke(draw, _layer_points(path, render_scale), color, round(18 * render_scale))
    for crossing in crossings:
        halo = _layer_points(crossing_halo_curve(list(swaps), path_count, crossing), render_scale)
        bridge = _layer_points(crossing_curve(list(swaps), path_count, crossing), render_scale)
        # A clean surface halo clears only the underpass; the complete top
        # centerline is then redrawn continuously as an intentional bridge.
        _smooth_stroke(draw, halo, surface, round(44 * render_scale))
        _smooth_stroke(draw, bridge, color, round(18 * render_scale))
    target_size = (round(layer.width * composition_scale / render_scale),
                   round(layer.height * composition_scale / render_scale))
    return layer.resize(target_size, Image.Resampling.LANCZOS) if layer.size != target_size else layer


def _reveal_line_layer(item: RoundSpec, progress: float, target_width: int, color: str, neutral: str, surface: str) -> Image.Image:
    composition_scale = target_width / 1080
    render_scale = float(LINE_FOLLOW_FINAL_PATH_SCALE) if target_width >= 2160 else max(1.0, composition_scale)
    layer = _new_line_layer(render_scale)
    draw = ImageDraw.Draw(layer)
    swaps, path_count, source = item.data["swaps"], item.data["path_count"], item.data["source"]
    paths, crossings, _ = geometry(swaps, path_count)
    traced = trace_points(paths[source], progress)
    _smooth_stroke(draw, _layer_points(traced, render_scale), color, round(18 * render_scale))
    for crossing in crossings:
        if crossing["under"] == source:
            halo = _layer_points(crossing_halo_curve(swaps, path_count, crossing), render_scale)
            bridge = _layer_points(crossing_curve(swaps, path_count, crossing), render_scale)
            _smooth_stroke(draw, halo, surface, round(44 * render_scale))
            _smooth_stroke(draw, bridge, neutral, round(18 * render_scale))
    target_size = (round(layer.width * composition_scale / render_scale),
                   round(layer.height * composition_scale / render_scale))
    return layer.resize(target_size, Image.Resampling.LANCZOS) if layer.size != target_size else layer


def draw_path_puzzle(image: Image.Image, item: RoundSpec, local: float, difficulty: str, palette: dict[str, str]) -> None:
    if item.kind == "line_follow":
        draw_line_puzzle(image, item, local, difficulty, palette)
        return
    scale = image.width / 1080
    point = lambda xy: (xy[0] * scale, xy[1] * scale)
    box = lambda values: tuple(round(v * scale) for v in values)
    width = lambda value: max(1, round(value * scale))
    rounded_card(image, box((100, 280, 980, 1480)), width(50), palette["surface"], palette["outline"], width(5))
    draw = ImageDraw.Draw(image)
    data = item.data
    reveal_at = 0.35 + thinking_duration(item.kind, difficulty)
    progress = min(1.0, max(0.0, (local - reveal_at) / 1.25))
    n = data["size"]
    cell, left, top = 760 / n, 160, 460
    center = lambda node: (left + (node % n + 0.5) * cell, top + (node // n + 0.5) * cell)
    edges = {tuple(sorted(edge)) for edge in data["edges"]}
    # Draw each wall once; the three top gaps are natural exits.
    for row in range(n):
        for column in range(n):
            node = row * n + column
            x, y = left + column * cell, top + row * cell
            if row == 0 and node not in data["exits"]:
                draw.line((point((x, y)), point((x + cell, y))), fill=palette["outline"], width=width(10))
            if column == 0:
                draw.line((point((x, y)), point((x, y + cell))), fill=palette["outline"], width=width(10))
            if column == n - 1 or tuple(sorted((node, node + 1))) not in edges:
                draw.line((point((x + cell, y)), point((x + cell, y + cell))), fill=palette["outline"], width=width(10))
            if row == n - 1:
                if node != data["start"]:
                    draw.line((point((x, y + cell)), point((x + cell, y + cell))), fill=palette["outline"], width=width(10))
            elif tuple(sorted((node, node + n))) not in edges:
                draw.line((point((x, y + cell)), point((x + cell, y + cell))), fill=palette["outline"], width=width(10))
    destinations = [(center(node)[0], 385) for node in data["exits"]]
    source = (center(data["start"])[0], 1340)
    route = [source, *[center(node) for node in data["route"]], destinations[item.answer]]
    for index, destination in enumerate(destinations):
        marker(draw, point(destination), 31 * scale, index, palette["accent"] if index != 1 else palette["lavender"], palette["surface"])
    sx, sy = point(source)
    draw.ellipse((sx - 25 * scale, sy - 25 * scale, sx + 25 * scale, sy + 25 * scale), fill=palette["primary"], outline=palette["outline"], width=width(4))
    draw.polygon([point((source[0] - 10, source[1] + 6)), point((source[0], source[1] - 10)), point((source[0] + 10, source[1] + 6))], fill=palette["text_light"])
    if local >= reveal_at:
        traced = [point(p) for p in trace_points(route, progress)]
        draw.line(traced, fill=palette["primary"], width=width(17), joint="curve")
        x, y = traced[-1]
        draw.ellipse((x - 12 * scale, y - 12 * scale, x + 12 * scale, y + 12 * scale), fill=palette["accent"])
        if progress >= 1:
            x, y = point(destinations[item.answer])
            draw.ellipse((x - 45 * scale, y - 45 * scale, x + 45 * scale, y + 45 * scale), outline=palette["success"], width=width(5))
    if 0.35 <= local < reveal_at:
        draw_progress_bar(image, box((245, 1550, 835, 1572)), 1 - (local - 0.35) / (reveal_at - 0.35), palette["background_2"], palette["primary"])


def draw_line_puzzle(image: Image.Image, item: RoundSpec, local: float, difficulty: str, palette: dict[str, str]) -> None:
    scale = image.width / 1080
    point = lambda xy: (xy[0] * scale, xy[1] * scale)
    box = lambda values: tuple(round(v * scale) for v in values)
    width = lambda value: max(1, round(value * scale))
    rounded_card(image, box((100, 280, 980, 1480)), width(50), palette["surface"], palette["outline"], width(5))
    draw = ImageDraw.Draw(image)
    path_count = item.data["path_count"]
    lanes = lane_positions(path_count)
    reveal_at = 0.35 + thinking_duration(item.kind, difficulty)
    progress = min(1.0, max(0.0, (local - reveal_at) / 1.25))
    source = item.data["source"]
    color = palette["outline"]
    static = _static_line_layer(tuple(item.data["swaps"]), path_count, image.width, color, palette["surface"])
    origin = point((LINE_LAYER_BOUNDS[0], LINE_LAYER_BOUNDS[1]))
    image.paste(static, (round(origin[0]), round(origin[1])), static)
    if local >= reveal_at:
        overlay = _reveal_line_layer(item, progress, image.width, palette["primary"], color, palette["surface"])
        image.paste(overlay, (round(origin[0]), round(origin[1])), overlay)
        traced = trace_points(geometry(item.data["swaps"], path_count)[0][source], progress)
        x, y = point(traced[-1])
        draw.ellipse((x - 10 * scale, y - 10 * scale, x + 10 * scale, y + 10 * scale), fill=palette["accent"])
    destination_colors = (palette["accent"], palette["lavender"], palette["secondary"], palette["coral"], palette["success"])
    for index, x in enumerate(lanes):
        active = index == source
        radius = 27 if active else 10
        draw.ellipse(box((x - radius, TOP - radius, x + radius, TOP + radius)), fill=palette["primary"] if active else color)
        if active:
            draw.polygon([point((x - 10, TOP - 6)), point((x + 10, TOP - 6)), point((x, TOP + 10))], fill=palette["text_light"])
            draw.ellipse(box((x - 39, TOP - 39, x + 39, TOP + 39)), outline=palette["primary"], width=width(4))
        marker(draw, point((x, BOTTOM + 65)), 27 * scale, index, destination_colors[index], palette["surface"])
        draw.line((point((x, BOTTOM)), point((x, BOTTOM + 25))), fill=palette["primary"] if progress >= 1 and index == item.answer else color, width=width(18))
        if progress >= 1 and index == item.answer:
            draw.ellipse(box((x - 44, BOTTOM + 21, x + 44, BOTTOM + 109)), outline=palette["success"], width=width(5))
    if 0.35 <= local < reveal_at:
        draw_progress_bar(image, box((245, 1550, 835, 1572)), 1 - (local - 0.35) / (reveal_at - 0.35), palette["background_2"], palette["primary"])
