from __future__ import annotations

import math
from PIL import Image, ImageDraw


def draw_fish(draw: ImageDraw.ImageDraw, center: tuple[int, int], scale: float, color: str, facing_left: bool = False) -> None:
    x, y = center
    w, h = int(150 * scale), int(92 * scale)
    outline = "#173B45"
    draw.ellipse((x - w // 2, y - h // 2, x + w // 2, y + h // 2), fill=color, outline=outline, width=max(2, int(8 * scale)))
    if facing_left:
        tail = [(x + w // 2 - 5, y), (x + w, y - h // 2), (x + w, y + h // 2)]
        eye_x = x - w // 4
    else:
        tail = [(x - w // 2 + 5, y), (x - w, y - h // 2), (x - w, y + h // 2)]
        eye_x = x + w // 4
    draw.polygon(tail, fill=color, outline=outline)
    eye_r = max(3, int(7 * scale))
    draw.ellipse((eye_x - eye_r, y - h // 6 - eye_r, eye_x + eye_r, y - h // 6 + eye_r), fill=outline)


def draw_apple(draw: ImageDraw.ImageDraw, center: tuple[int, int], scale: float, color: str, flipped_leaf: bool = False) -> None:
    x, y = center
    r = int(55 * scale)
    outline = "#173B45"
    draw.ellipse((x - r, y - r, x + 8, y + r), fill=color, outline=outline, width=max(2, int(7 * scale)))
    draw.ellipse((x - 8, y - r, x + r, y + r), fill=color, outline=outline, width=max(2, int(7 * scale)))
    draw.line((x, y - r, x, y - r - int(35 * scale)), fill=outline, width=max(2, int(9 * scale)))
    side = -1 if flipped_leaf else 1
    draw.ellipse((x + side * int(5 * scale), y - r - int(35 * scale), x + side * int(50 * scale), y - r - int(5 * scale)), fill="#70C44A", outline=outline, width=max(2, int(5 * scale)))


def draw_star(draw: ImageDraw.ImageDraw, center: tuple[int, int], scale: float, color: str) -> None:
    x, y = center
    radii = (65 * scale, 29 * scale)
    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = radii[i % 2]
        points.append((x + radius * math.cos(angle), y + radius * math.sin(angle)))
    draw.polygon(points, fill=color, outline="#173B45", width=max(2, int(7 * scale)))


def draw_balloon(draw: ImageDraw.ImageDraw, center: tuple[int, int], scale: float, color: str) -> None:
    x, y = center
    rw, rh = int(50 * scale), int(68 * scale)
    draw.ellipse((x - rw, y - rh, x + rw, y + rh), fill=color, outline="#173B45", width=max(2, int(7 * scale)))
    draw.polygon([(x, y + rh), (x - 9, y + rh + 15), (x + 9, y + rh + 15)], fill="#173B45")
    draw.line((x, y + rh + 15, x + int(15 * scale), y + int(125 * scale)), fill="#617780", width=max(1, int(3 * scale)))


def draw_flower(draw: ImageDraw.ImageDraw, center: tuple[int, int], scale: float, color: str) -> None:
    x, y = center
    petal = int(30 * scale)
    for dx, dy in ((0, -42), (40, -12), (25, 35), (-25, 35), (-40, -12)):
        px, py = x + int(dx * scale), y + int(dy * scale)
        draw.ellipse((px - petal, py - petal, px + petal, py + petal), fill=color, outline="#173B45", width=max(2, int(5 * scale)))
    core = int(27 * scale)
    draw.ellipse((x - core, y - core, x + core, y + core), fill="#FFD166", outline="#173B45", width=max(2, int(5 * scale)))


def draw_shape(draw: ImageDraw.ImageDraw, center: tuple[int, int], scale: float, color: str, odd: bool = False) -> None:
    x, y = center
    r = int(58 * scale)
    if odd:
        draw.rounded_rectangle((x - r, y - r, x + r, y + r), radius=int(18 * scale), fill=color, outline="#173B45", width=max(2, int(7 * scale)))
    else:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color, outline="#173B45", width=max(2, int(7 * scale)))


def draw_object(draw: ImageDraw.ImageDraw, theme: str, center: tuple[int, int], scale: float, color: str, odd: bool = False) -> None:
    if theme == "fish":
        draw_fish(draw, center, scale, color, facing_left=odd)
    elif theme == "apple":
        draw_apple(draw, center, scale, color, flipped_leaf=odd)
    elif theme == "star":
        draw_star(draw, center, scale, color)
    elif theme == "balloon":
        draw_balloon(draw, center, scale, color)
    elif theme == "flower":
        draw_flower(draw, center, scale, color)
    else:
        draw_shape(draw, center, scale, color, odd=odd)

