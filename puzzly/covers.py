"""Per-video 3D covers for the Puzzly for You games.

Every game has a fixed 3D template (title, tilted card, floating 3D objects, call to action). Each video fills it with
its own level-1 puzzle and paints it in the same dark background tone as the video, so video and cover always match.
"""
from __future__ import annotations

from functools import lru_cache
import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .config import DARK_THEMES, PUZZLE_FIT_PALETTE, dark_theme_for, glow_strength
from .models import VideoSpec
from .visuals.text import WINDOWS_FONTS, strong_font

SS = 2  # everything is drawn at 2x and downsampled once
W, H = 1080 * SS, 1920 * SS
ACCENT = PUZZLE_FIT_PALETTE["accent"]
AMBER = "#FFB547"
SHAPE_COLORS = {"triangle": "#FFD23F", "square": "#3DA9FF", "circle": "#FF4D6D", "star": "#B388FF",
                "heart": "#FF6FB5", "hexagon": "#3DF08F", "diamond": "#FF8A3D", "pentagon": "#2EE6C5",
                "cross": "#7ED957", "moon": "#FFB547"}
# Board crops (logical 1080x1920 frame coordinates) for games whose level-1 board is taken from the real video frame.
CROPS = {
    "puzzle_fit": (60, 300, 1020, 1440),
    "find_the_exit": (90, 270, 990, 1520),
    "find_the_exit_circle": (24, 390, 1056, 1422),  # the round plate of a circular maze, portals included
    "cube_count": (100, 560, 980, 1380),
    "flash_count": (40, 670, 1040, 1050),
    "line_follow": (40, 272, 1040, 1790),
    "memory_challenge": (110, 320, 970, 1190),
    "lucky_pick": (50, 310, 1030, 1620),
    "bounce_arena": (90, 450, 990, 1400),
    "cup_shuffle": (50, 590, 1030, 1310),  # the felt mat with the cups and the ball
    "laser_maze": (44, 480, 1036, 1480),  # the card with the board, the emitter and the numbered receivers
    "memory_levels": (80, 365, 1000, 1285),  # the hook's 3x3 concept board of the three-level Memory Challenge
    "shade_spot": (200, 392, 880, 1592),  # both grids with their column letters and row numbers
}


COVER_TIER = 1  # Line Follow cover tangle: level 2's size (dense enough to look hard, quick to weave)


def S(value: float) -> int:
    return round(value * SS)


def rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def mix(a: tuple, b: tuple, t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def hex_of(color: tuple) -> str:
    return "#%02x%02x%02x" % tuple(color[:3])


@lru_cache(maxsize=32)
def face(size: float, heavy: bool = True) -> ImageFont.FreeTypeFont:
    name = "seguibl.ttf" if heavy else "seguisb.ttf"
    try:
        return ImageFont.truetype(str(WINDOWS_FONTS / name), round(size * SS))
    except OSError:
        return strong_font(round(size * SS))


# ---------------------------------------------------------------- background

def background(theme: str, accent: str) -> Image.Image:
    top, bottom, glow = (rgb(value) for value in DARK_THEMES.get(theme, DARK_THEMES["violet"]))
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    t = (y / (H - 1))[..., None]
    img = np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t
    for gx, gy, radius, color, strength in ((540, 560, 700, glow, glow_strength(theme, .55)),
                                            (540, 1150, 620, mix(glow, (0, 0, 0), .35), glow_strength(theme, .35)),
                                            (980, 260, 380, rgb(accent), .12), (120, 1650, 420, rgb(accent), .14)):
        d = np.hypot(x - S(gx), y - S(gy)) / S(radius)
        img += (np.array(color, np.float32) - img) * (np.exp(-d * d) * strength)[..., None]
    # Perspective floor grid, fading into the distance.
    horizon = S(1380)
    rows = np.arange(horizon, H)
    depth = ((rows - horizon) / (H - horizon)).astype(np.float32)
    grid = np.zeros((H, W), np.float32)
    for k in range(1, 14):
        yy = int(horizon + (H - horizon) * (k / 13) ** 1.8)
        grid[max(0, yy - S(1)):yy + S(1)] = .11 * (k / 13)
    for k in range(-12, 13):
        top_x, bottom_x = W / 2 + k * S(40), W / 2 + k * S(210)
        xs = (top_x + (bottom_x - top_x) * depth).astype(np.int32)
        for offset in range(-S(1), S(1)):
            columns = xs + offset
            valid = (columns >= 0) & (columns < W)
            grid[rows[valid], columns[valid]] = np.maximum(grid[rows[valid], columns[valid]], .11 * depth[valid])
    line_color = np.array(mix(rgb(accent), glow, .5), np.float32)
    img += line_color[None, None, :] * grid[..., None]
    vignette = np.hypot((x / W - .5) * 1.1, y / H - .5)
    img *= (1 - np.clip(vignette - .32, 0, 1) * .8)[..., None]
    image = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA")
    rng = random.Random(7)
    bokeh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bokeh)
    for _ in range(34):
        r = S(rng.uniform(4, 22))
        px, py = rng.uniform(0, W), rng.uniform(0, H)
        draw.ellipse((px - r, py - r, px + r, py + r), fill=(255, 255, 255, rng.randint(10, 28)))
    image.alpha_composite(bokeh.filter(ImageFilter.GaussianBlur(S(3))))
    return image


# ---------------------------------------------------------------- 3D pieces

def extrude(mask: Image.Image, depth: int, front: str, back: str, dx: float = .35, dy: float = 1.0) -> Image.Image:
    """Stack darkening copies of a silhouette behind it: a solid extruded side."""
    layer = Image.new("RGBA", (mask.width + round(depth * dx) + 4, mask.height + round(depth * dy) + 4), (0, 0, 0, 0))
    for step in range(depth, 0, -1):
        color = mix(rgb(back), rgb(front), 1 - step / depth)
        layer.paste(Image.new("RGBA", mask.size, color + (255,)), (round(step * dx), round(step * dy)), mask)
    return layer


def token3d(shape: str, color: str, size: float) -> Image.Image:
    from .visuals.memory import token_image
    px = S(size)
    top = token_image(shape, color, px)
    mask = top.getchannel("A").point(lambda v: 255 if v > 110 else 0)
    base = rgb(color)
    side = extrude(mask, max(4, px // 9), hex_of(mix(base, (0, 0, 0), .35)), hex_of(mix(base, (0, 0, 0), .75)))
    out = Image.new("RGBA", side.size, (0, 0, 0, 0))
    out.alpha_composite(side)
    out.alpha_composite(top, (0, 0))
    return out


def tile3d(symbol: str, size: float, fill: str, ink: str = "#141008", empty: bool = False, outline: str = AMBER) -> Image.Image:
    px = S(size)
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, px - 1, px - 1), radius=px // 4, fill=255)
    base = rgb(fill)
    side = extrude(mask, max(6, px // 7), hex_of(mix(base, (0, 0, 0), .35)), hex_of(mix(base, (0, 0, 0), .75)), .3, 1.0)
    tile = Image.new("RGBA", side.size, (0, 0, 0, 0))
    tile.alpha_composite(side)
    top = Image.new("RGBA", (px, px), base + (255,))
    top.putalpha(mask)
    tile.alpha_composite(top)
    draw = ImageDraw.Draw(tile)
    if empty:
        draw.rounded_rectangle((S(3), S(3), px - S(3), px - S(3)), radius=px // 4, outline=rgb(outline), width=S(6))
        draw.text((px / 2, px / 2 - px * .04), "?", font=face(size * .5, False), fill=(170, 190, 200), anchor="mm")
    else:
        highlight = Image.new("RGBA", (px, px), (255, 255, 255, 0))
        hm = Image.new("L", (px, px), 0)
        ImageDraw.Draw(hm).rounded_rectangle((px * .08, px * .06, px * .92, px * .42), radius=px // 5, fill=60)
        highlight.putalpha(hm.filter(ImageFilter.GaussianBlur(px * .05)))
        tile.alpha_composite(highlight)
        draw.text((px / 2, px / 2 - px * .04), symbol, font=face(size * .6), fill=rgb(ink), anchor="mm")
    return tile


def cube3d(color: str, size: float) -> Image.Image:
    """A lit isometric cube: light top, base left, dark right (in the active object palette)."""
    from .palette import object_color
    px = S(size)
    base = rgb(object_color(color))
    image = Image.new("RGBA", (px, round(px * 1.15)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    w, h = px, px * 1.15
    top = [(w / 2, 0), (w, h * .25), (w / 2, h * .5), (0, h * .25)]
    left = [(0, h * .25), (w / 2, h * .5), (w / 2, h), (0, h * .75)]
    right = [(w / 2, h * .5), (w, h * .25), (w, h * .75), (w / 2, h)]
    draw.polygon(top, fill=mix(base, (255, 255, 255), .3))
    draw.polygon(left, fill=base)
    draw.polygon(right, fill=mix(base, (0, 0, 0), .35))
    edge = mix(base, (0, 0, 0), .6)
    for poly in (top, left, right):
        draw.line(poly + [poly[0]], fill=edge, width=S(3), joint="curve")
    return image


def piece3d(kind: str, white: bool, size: float) -> Image.Image:
    """A chess piece standing out of the cover: the game's own piece sprite on an extruded slab of its silhouette."""
    from .visuals.chess_mate import piece_sprite
    px = S(size)
    top = piece_sprite(kind, white, px)
    mask = top.getchannel("A").point(lambda v: 255 if v > 110 else 0)
    front, back = ("#B9B2A4", "#5E584E") if white else ("#15141A", "#050407")
    side = extrude(mask, max(4, px // 10), front, back)
    out = Image.new("RGBA", side.size, (0, 0, 0, 0))
    out.alpha_composite(side)
    out.alpha_composite(top, (0, 0))
    return out


def ball3d(color: str, size: float) -> Image.Image:
    from .visuals.bounce_arena import ball_sprite
    return ball_sprite(color, S(size)).copy()


def text3d(image: Image.Image, center: tuple[float, float], text: str, font, top: str, bottom: str, depth: int,
           glow: str | None = None) -> None:
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    box = probe.textbbox((0, 0), text, font=font, anchor="lt")
    mask = Image.new("L", (box[2] + S(20), box[3] + S(20)), 0)
    ImageDraw.Draw(mask).text((S(10), S(10)), text, font=font, fill=255, anchor="lt")
    side = extrude(mask, depth, "#1B1450", "#07051A", .45, 1.0)
    x, y = round(center[0] - mask.width / 2), round(center[1] - mask.height / 2)
    if glow:
        halo = Image.new("RGBA", image.size, rgb(glow) + (0,))
        big = Image.new("L", image.size, 0)
        big.paste(mask, (x, y))
        halo.putalpha(big.filter(ImageFilter.GaussianBlur(S(34))).point(lambda v: min(255, int(v * 1.3))))
        image.alpha_composite(halo)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sm = Image.new("L", image.size, 0)
    sm.paste(mask, (x + depth, y + depth * 2))
    shadow.putalpha(sm.filter(ImageFilter.GaussianBlur(S(14))).point(lambda v: v * 170 // 255))
    image.alpha_composite(shadow)
    image.alpha_composite(side, (x, y))
    gradient = Image.linear_gradient("L").resize(mask.size)
    fill = Image.composite(Image.new("RGBA", mask.size, rgb(bottom) + (255,)), Image.new("RGBA", mask.size, rgb(top) + (255,)), gradient)
    fill.putalpha(mask)
    edge = ImageChops.subtract(mask, ImageChops.offset(mask, 0, S(4)))
    highlight = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    highlight.putalpha(edge.point(lambda v: v * 200 // 255))
    image.alpha_composite(fill, (x, y))
    image.alpha_composite(highlight, (x, y))


def fitted(text: str, max_width: float, size: float, heavy: bool = True):
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    while size > 30 and probe.textlength(text, font=face(size, heavy)) > S(max_width):
        size -= 4
    return face(size, heavy)


def spaced(image: Image.Image, center: tuple[float, float], text: str, font, color: tuple, spacing: float) -> None:
    draw = ImageDraw.Draw(image)
    widths = [draw.textlength(char, font=font) for char in text]
    total = sum(widths) + S(spacing) * (len(text) - 1)
    x = center[0] - total / 2
    for char, width in zip(text, widths):
        draw.text((x, center[1]), char, font=font, fill=color, anchor="lm")
        x += width + S(spacing)


def pill(image: Image.Image, center: tuple[float, float], text: str, font, fill: str, color: tuple, pad: float = 46,
         height: float = 104) -> None:
    draw = ImageDraw.Draw(image)
    w = draw.textlength(text, font=font) + S(pad) * 2
    h = S(height)
    x1, y1 = center[0] - w / 2, center[1] - h / 2
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x1, y1 + S(12), x1 + w, y1 + h + S(12)), radius=h // 2, fill=(0, 0, 0, 150))
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(S(10))))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((x1, y1 + S(8), x1 + w, y1 + h + S(8)), radius=h // 2, fill=mix(rgb(fill), (0, 0, 0), .45))
    draw.rounded_rectangle((x1, y1, x1 + w, y1 + h), radius=h // 2, fill=rgb(fill))
    draw.text(center, text, font=font, fill=color, anchor="mm")


def _perspective_coeffs(src, dst) -> list[float]:
    matrix = []
    for (x, y), (u, v) in zip(dst, src):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    return np.linalg.solve(np.array(matrix, dtype=np.float64), np.array(src, dtype=np.float64).reshape(8)).tolist()


def tilted_card(image: Image.Image, content: Image.Image, top_y: float, glow: str, edge: str,
                max_size=(920, 760)) -> tuple[float, float]:
    """Place content on a card that leans back (narrow top), with a thick slab edge, a floor shadow, and a rim glow.

    Short cards are centred in the available height. Returns the card's top and bottom in logical pixels.
    """
    scale = min(S(max_size[0]) / content.width, S(max_size[1]) / content.height)
    content = content.resize((max(2, round(content.width * scale)), max(2, round(content.height * scale))), Image.Resampling.LANCZOS)
    bw, bh = content.size
    card = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, bw - 1, bh - 1), radius=S(56), fill=255)
    card.paste(content, (0, 0), mask)
    ImageDraw.Draw(card).rounded_rectangle((0, 0, bw - 1, bh - 1), radius=S(56), outline=rgb(edge), width=S(5))
    inset, squash = S(70) * bw / S(920), .9
    out_w, out_h = bw, round(bh * squash)
    dst = [(inset, 0), (out_w - inset, 0), (out_w, out_h), (0, out_h)]
    src = [(0, 0), (bw, 0), (bw, bh), (0, bh)]
    tilted = card.transform((out_w, out_h), Image.Transform.PERSPECTIVE, _perspective_coeffs(src, dst), Image.Resampling.BICUBIC)
    x, y = round(W / 2 - out_w / 2), S(top_y) + max(0, round((S(max_size[1]) * .9 - out_h) / 2))
    floor = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(floor).ellipse((x - S(10), y + out_h - S(30), x + out_w + S(10), y + out_h + S(110)), fill=(0, 0, 0, 190))
    image.alpha_composite(floor.filter(ImageFilter.GaussianBlur(S(40))))
    silhouette = tilted.getchannel("A")
    for step in range(S(34), 0, -1):
        tone = mix(mix(rgb(edge), (0, 0, 0), .2), (3, 4, 12), step / S(34))
        image.paste(Image.new("RGBA", silhouette.size, tone + (255,)), (x, y + step), silhouette)
    rim = Image.new("RGBA", image.size, rgb(glow) + (0,))
    rim_mask = Image.new("L", image.size, 0)
    rim_mask.paste(silhouette, (x, y))
    rim.putalpha(rim_mask.filter(ImageFilter.GaussianBlur(S(28))).point(lambda v: v * 110 // 255))
    image.alpha_composite(rim)
    image.alpha_composite(tilted, (x, y))
    return y / SS, (y + out_h) / SS


def floating(image: Image.Image, sprite: Image.Image, center: tuple[float, float], angle: float, glow: str,
             blur: float = 0.0, alpha: float = 1.0) -> None:
    sprite = sprite.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    if blur:
        sprite = sprite.filter(ImageFilter.GaussianBlur(S(blur)))
    if alpha < 1:
        sprite.putalpha(sprite.getchannel("A").point(lambda v: round(v * alpha)))
    cx, cy = S(center[0]), S(center[1])
    halo = Image.new("RGBA", image.size, rgb(glow) + (0,))
    hm = Image.new("L", image.size, 0)
    r = max(sprite.size) * .55
    ImageDraw.Draw(hm).ellipse((cx - r, cy - r, cx + r, cy + r), fill=round(70 * alpha))
    halo.putalpha(hm.filter(ImageFilter.GaussianBlur(r * .6)))
    image.alpha_composite(halo)
    image.alpha_composite(sprite, (round(cx - sprite.width / 2), round(cy - sprite.height / 2)))


# ---------------------------------------------------------------- card contents

def _equation_row(board: Image.Image, y: float, items: list, token: float = 112) -> None:
    draw = ImageDraw.Draw(board)
    op_font, num_font = face(96, False), face(104)
    widths = []
    for kind, value in items:
        widths.append(S(token) if kind == "shape" else (S(132) if kind == "q" else draw.textlength(value, font=num_font if kind == "num" else op_font)))
    gap = S(26)
    total = sum(widths) + gap * (len(widths) - 1)
    shrink = min(1.0, (board.width - S(80)) / total)
    x = board.width / 2 - total * shrink / 2
    for (kind, value), width in zip(items, widths):
        cx = x + width * shrink / 2
        if kind == "shape":
            sprite = token3d(value[0], value[1], token * shrink)
            board.alpha_composite(sprite, (round(cx - sprite.width / 2 + S(4)), round(y - S(token * shrink) / 2)))
        elif kind == "q":
            box = S(66 * shrink)
            glow = Image.new("RGBA", board.size, rgb("#FFD23F") + (0,))
            gm = Image.new("L", board.size, 0)
            ImageDraw.Draw(gm).rounded_rectangle((cx - box, y - box, cx + box, y + box), radius=S(28), fill=210)
            glow.putalpha(gm.filter(ImageFilter.GaussianBlur(S(26))))
            board.alpha_composite(glow)
            draw = ImageDraw.Draw(board)
            draw.rounded_rectangle((cx - box, y - box + S(10), cx + box, y + box + S(10)), radius=S(28), fill=rgb("#B8860B"))
            draw.rounded_rectangle((cx - box, y - box, cx + box, y + box), radius=S(28), fill=rgb("#FFD23F"))
            draw.text((cx, y - S(6)), "?", font=face(118 * shrink), fill=rgb("#1B1033"), anchor="mm")
        else:
            color = (255, 255, 255) if kind == "num" or value == "=" else (154, 163, 199)
            draw = ImageDraw.Draw(board)
            draw.text((cx, y - S(6)), value, font=num_font if kind == "num" else op_font, fill=color, anchor="mm")
        x += (width + gap) * shrink


def _terms_row(terms: list, shapes: dict) -> list:
    return [("shape", (shapes[term]["shape"], shapes[term]["color"])) if isinstance(term, str) and term.startswith("s") else ("op", term)
            for term in terms]


def shape_board(data: dict) -> Image.Image:
    shapes = {entry["name"]: entry for entry in data["shapes"]}
    rows = len(data["clues"]) + 1
    bw, bh = S(900), S(120 + 152 * (rows - 1) + 176 + 70)
    board = Image.new("RGBA", (bw, bh), rgb("#171E3B") + (255,))
    light = Image.new("RGBA", board.size, (124, 92, 255, 0))
    lm = Image.new("L", board.size, 0)
    ImageDraw.Draw(lm).ellipse((-S(100), -S(420), bw + S(100), S(300)), fill=60)
    light.putalpha(lm.filter(ImageFilter.GaussianBlur(S(60))))
    board.alpha_composite(light)
    for index, clue in enumerate(data["clues"]):
        _equation_row(board, S(120) + S(152) * index, _terms_row(clue["terms"], shapes) + [("op", "="), ("num", str(clue["result"]))])
    divider = S(120) + S(152) * (rows - 2) + S(88)
    ImageDraw.Draw(board).line((S(60), divider, bw - S(60), divider), fill=rgb("#3B4A8C"), width=S(5))
    _equation_row(board, divider + S(96), _terms_row(data["question"]["terms"], shapes) + [("op", "="), ("q", "")])
    return board


def operator_board(data: dict) -> Image.Image:
    bw, bh = S(920), S(560)
    board = Image.new("RGBA", (bw, bh), rgb("#0A2A30") + (255,))
    draw = ImageDraw.Draw(board)
    numbers = data["numbers"]
    number_font, slot = face(128), 116
    widths = []
    for index, number in enumerate(numbers):
        widths.append(draw.textlength(str(number), font=number_font))
        if index < len(numbers) - 1:
            widths.append(S(slot))
    gap = S(22)
    total = sum(widths) + gap * (len(widths) - 1)
    shrink = min(1.0, (bw - S(90)) / total)
    x, y = bw / 2 - total * shrink / 2, S(190)
    for index, width in enumerate(widths):
        cx = x + width * shrink / 2
        if index % 2 == 0:
            draw.text((cx, y), str(numbers[index // 2]), font=face(128 * shrink), fill=(255, 255, 255), anchor="mm")
        else:
            tile = tile3d("", slot * shrink, "#0F3940", empty=True)
            board.alpha_composite(tile, (round(cx - S(slot * shrink) / 2), round(y - S(slot * shrink) / 2)))
        x += (width + gap) * shrink
    target = f"= {data['target']}"
    glow = Image.new("RGBA", board.size, rgb(AMBER) + (0,))
    gm = Image.new("L", board.size, 0)
    ImageDraw.Draw(gm).text((bw / 2, S(420)), target, font=face(160), fill=200, anchor="mm")
    glow.putalpha(gm.filter(ImageFilter.GaussianBlur(S(26))))
    board.alpha_composite(glow)
    ImageDraw.Draw(board).text((bw / 2, S(420)), target, font=face(160), fill=rgb(AMBER), anchor="mm")
    return board


def portal3d(index: int, size: float) -> Image.Image:
    """A Find the Exit portal (star, moon, sun) as a thick glowing coin with an extruded rim."""
    from .palette import object_color
    from .visuals.find_the_exit import EXIT_COLORS, _symbol
    px = S(size)
    color = rgb(object_color(EXIT_COLORS[index]))
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, px - 1, px - 1), fill=255)
    side = extrude(mask, max(5, px // 8), hex_of(mix(color, (0, 0, 0), .35)), hex_of(mix(color, (0, 0, 0), .8)), .3, 1.0)
    coin = Image.new("RGBA", side.size, (0, 0, 0, 0))
    coin.alpha_composite(side)
    top = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    draw = ImageDraw.Draw(top)
    face_fill = rgb("#1B2350")
    draw.ellipse((0, 0, px - 1, px - 1), fill=face_fill, outline=color, width=max(3, px // 12))
    _symbol(draw, index, px / 2, px / 2, px * .3, color, face_fill)
    shine_mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(shine_mask).ellipse((px * .14, px * .08, px * .86, px * .46), fill=46)
    shine = Image.new("RGBA", (px, px), (255, 255, 255, 0))
    shine.putalpha(ImageChops.multiply(shine_mask.filter(ImageFilter.GaussianBlur(px * .06)), mask))
    top.alpha_composite(shine)
    coin.alpha_composite(top)
    return coin


def _orb3d(size: float, color: str) -> Image.Image:
    """A glossy sphere: radial shading with a soft specular highlight."""
    px = S(size)
    y, x = np.mgrid[0:px, 0:px].astype(np.float32)
    r = px / 2
    d = np.hypot(x - r, y - r) / r
    light = np.clip(1 - np.hypot(x - r * .7, y - r * .62) / (r * 1.25), 0, 1)
    base = np.array(rgb(color), np.float32)
    shade = base * (.45 + .55 * light[..., None]) + 255 * (light[..., None] ** 6) * .75
    alpha = np.clip((1 - d) * r, 0, 1) * 255
    return Image.fromarray(np.dstack([np.clip(shade, 0, 255), alpha]).astype(np.uint8))


def maze_board(data: dict) -> Image.Image:
    """The video's level-1 maze redrawn in 3D: raised walls, glowing portals, and the start orb (no route)."""
    from .visuals.find_the_exit import FLOOR, FLOOR_ALT, TRAIL, WALL_BOTTOM, WALL_RIM, WALL_TOP, wall_segments
    rows, columns = data["rows"], data["columns"]
    cell = S(min(780 / columns, 900 / rows))
    margin, top_pad, bottom_pad = S(60), cell * 2.0, cell * 1.6
    bw, bh = round(columns * cell + margin * 2), round(rows * cell + top_pad + bottom_pad)
    left, top = margin, top_pad
    board = Image.new("RGBA", (bw, bh), rgb("#171E3B") + (255,))
    draw = ImageDraw.Draw(board)
    for row in range(rows):
        for column in range(columns):
            x, y = left + column * cell, top + row * cell
            draw.rectangle((x, y, x + cell, y + cell), fill=rgb(FLOOR if (row + column) % 2 else FLOOR_ALT))
    # Each portal lights the floor below it.
    light = Image.new("L", board.size, 0)
    light_draw = ImageDraw.Draw(light)
    for node in data["exits"]:
        cx = left + (node % columns + .5) * cell
        light_draw.ellipse((cx - cell * 2.2, top - cell * 1.2, cx + cell * 2.2, top + cell * 2.6), fill=120)
    glow = Image.new("RGBA", board.size, rgb("#8C7BFF") + (0,))
    glow.putalpha(light.filter(ImageFilter.GaussianBlur(cell * .9)).point(lambda v: v * 70 // 255))
    board.alpha_composite(glow)
    # Walls: a soft floor shadow, an extruded side, a gradient top face, and a bright rim.
    geometry = {"cell": cell, "left": left, "top": top}
    width = max(S(6), round(cell * .27))
    mask = Image.new("L", board.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    for x1, y1, x2, y2 in wall_segments(data, geometry):
        mask_draw.line((x1, y1, x2, y2), fill=255, width=width)
        for px, py in ((x1, y1), (x2, y2)):
            mask_draw.ellipse((px - width / 2, py - width / 2, px + width / 2, py + width / 2), fill=255)
    depth = max(S(5), round(cell * .3))
    shadow = Image.new("RGBA", board.size, (0, 0, 0, 0))
    shadow.putalpha(ImageChops.offset(mask, depth, round(depth * 1.8)).filter(ImageFilter.GaussianBlur(depth)).point(lambda v: v * 190 // 255))
    board.alpha_composite(shadow)
    side = extrude(mask, depth, hex_of(mix(rgb(WALL_BOTTOM), (0, 0, 0), .3)), "#0B0F2A", .35, 1.0)
    board.alpha_composite(side.crop((0, 0, bw, bh)))
    body = Image.linear_gradient("L").resize(board.size)
    face_layer = Image.composite(Image.new("RGBA", board.size, rgb(WALL_BOTTOM) + (255,)),
                                 Image.new("RGBA", board.size, rgb(WALL_TOP) + (255,)), body)
    face_layer.putalpha(mask)
    board.alpha_composite(face_layer)
    bevel = max(S(2), round(width * .25))
    rim = Image.new("RGBA", board.size, rgb(WALL_RIM) + (0,))
    rim.putalpha(ImageChops.subtract(mask, ImageChops.offset(mask, bevel, bevel)).point(lambda v: v * 170 // 255))
    board.alpha_composite(rim)
    # Portals above the three top openings, the start orb below the bottom opening.
    portal = min(S(130), cell * 1.3)
    for index, node in enumerate(data["exits"]):
        cx, cy = left + (node % columns + .5) * cell, top - cell * 1.0
        from .palette import object_color
        halo = Image.new("RGBA", board.size, rgb(object_color(("#FFC24B", "#B69CFF", "#FF7A45")[index])) + (0,))
        hm = Image.new("L", board.size, 0)
        ImageDraw.Draw(hm).ellipse((cx - portal, cy - portal, cx + portal, cy + portal), fill=150)
        halo.putalpha(hm.filter(ImageFilter.GaussianBlur(portal * .45)))
        board.alpha_composite(halo)
        coin = portal3d(index, portal / SS)
        board.alpha_composite(coin, (round(cx - portal / 2), round(cy - portal / 2)))
    sx, sy = left + (data["start"] % columns + .5) * cell, top + rows * cell + cell * .8
    orb = cell * .95
    halo = Image.new("RGBA", board.size, rgb(TRAIL) + (0,))
    hm = Image.new("L", board.size, 0)
    ImageDraw.Draw(hm).ellipse((sx - orb * 1.3, sy - orb * 1.3, sx + orb * 1.3, sy + orb * 1.3), fill=190)
    halo.putalpha(hm.filter(ImageFilter.GaussianBlur(orb * .5)))
    board.alpha_composite(halo)
    sphere = _orb3d(orb / SS, TRAIL)
    board.alpha_composite(sphere, (round(sx - sphere.width / 2), round(sy - sphere.height / 2)))
    return board


LUCKY_PANEL = (52, 322, 1028, 1612)  # the maze panel in logical frame coordinates


def lucky_board(data: dict) -> Image.Image:
    """The Lucky Pick maze redrawn in 3D: raised neon-rimmed walls, the seven targets as 3D tokens, and the devourer
    lurking at the entrance with its jaw ajar. No selection rings: the cover is the moment before the pick."""
    from .puzzles.lucky_pick import TARGET_SIZE
    from .visuals.lucky_pick import CHARACTER_RADIUS, EYE, _maze_masks, creature
    corridors = tuple((tuple(a), tuple(b)) for a, b in data["corridors"])
    pockets = tuple(tuple(point) for point in data["valid_target_positions"])
    box = tuple(S(value) for value in LUCKY_PANEL)
    floor = _maze_masks((W, H), corridors, pockets, tuple(data["entrance"]), 0).crop(box)
    bw, bh = floor.size
    panel = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(panel).rounded_rectangle((0, 0, bw - 1, bh - 1), radius=S(46), fill=255)
    walls = ImageChops.subtract(panel, floor)
    board = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    board.alpha_composite(Image.merge("RGBA", (*Image.new("RGB", (bw, bh), rgb("#0A0D24")).split(), panel)))
    ox, oy = LUCKY_PANEL[0], LUCKY_PANEL[1]
    # Each target lights the floor of its pocket in its own colour.
    for target in data["targets"]:
        x, y = S(target["position"][0] - ox), S(target["position"][1] - oy)
        glow = Image.new("L", (bw, bh), 0)
        ImageDraw.Draw(glow).ellipse((x - S(80), y - S(80), x + S(80), y + S(80)), fill=150)
        light = Image.new("RGBA", (bw, bh), rgb(target["color_value"]) + (0,))
        light.putalpha(ImageChops.multiply(glow.filter(ImageFilter.GaussianBlur(S(36))), floor))
        board.alpha_composite(light)
    # Walls: a shadow cast into the corridors, an extruded side, a lit top face, and a neon rim along every edge.
    depth = S(20)
    shadow = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    shadow.putalpha(ImageChops.multiply(ImageChops.offset(walls, depth, round(depth * 1.6)).filter(ImageFilter.GaussianBlur(depth)), floor)
                    .point(lambda v: v * 200 // 255))
    board.alpha_composite(shadow)
    board.alpha_composite(extrude(walls, depth, "#1A2050", "#070A1C", .35, 1.0).crop((0, 0, bw, bh)))
    top_face = Image.composite(Image.new("RGBA", (bw, bh), rgb("#1E2560") + (255,)), Image.new("RGBA", (bw, bh), rgb("#3C48A8") + (255,)),
                               Image.linear_gradient("L").resize((bw, bh)))
    top_face.putalpha(walls)
    board.alpha_composite(top_face)
    edge = ImageChops.subtract(walls, walls.filter(ImageFilter.MinFilter(15)))
    neon = Image.composite(Image.new("RGBA", (bw, bh), rgb(ACCENT) + (255,)), Image.new("RGBA", (bw, bh), rgb(PUZZLE_FIT_PALETTE["primary"]) + (255,)),
                           Image.linear_gradient("L").resize((bw, bh)))
    bloom = neon.copy()
    bloom.putalpha(edge.filter(ImageFilter.GaussianBlur(S(14))).point(lambda v: min(255, v * 3)))
    board.alpha_composite(bloom)
    neon.putalpha(edge)
    board.alpha_composite(neon)
    # The targets as 3D tokens.
    for target in data["targets"]:
        x, y = S(target["position"][0] - ox), S(target["position"][1] - oy)
        token = token3d(target["shape_id"], target["color_value"], TARGET_SIZE * 1.1)
        board.alpha_composite(token, (round(x - S(TARGET_SIZE * 1.1) / 2), round(y - S(TARGET_SIZE * 1.1) / 2)))
    # The devourer rises from the entrance portal, glaring, jaw ajar.
    ex, ey = S(data["entrance"][0] - ox), S(data["entrance"][1] - oy)
    portal = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(portal).ellipse((ex - S(170), ey - S(170), ex + S(170), ey + S(170)), fill=210)
    red = Image.new("RGBA", (bw, bh), rgb(EYE) + (0,))
    red.putalpha(portal.filter(ImageFilter.GaussianBlur(S(55))))
    board.alpha_composite(red)
    monster = creature(S(CHARACTER_RADIUS * 1.75), mouth=.5, brow=1.0, look=(0, -1))
    board.alpha_composite(monster, (round(ex - monster.width / 2), round(ey - monster.height / 2 - S(60))))
    board.putalpha(ImageChops.multiply(board.getchannel("A"), panel))
    return board


def cover_snake_pose(targets: list[dict]) -> list[tuple[float, float]]:
    """A staged, spoiler-free snake for the cover: it rises out of its den in a slow S-curve, head pointing into open
    space. It is not taken from the chase, so it never hints at which target is eaten first; the head keeps well
    clear of every target."""
    from .puzzles.lucky_snake import ENTRY
    starts = [tuple(target["position"]) for target in targets]
    best: list[tuple[float, float]] = []
    for length in (340, 300, 260, 220, 180, 140):
        for phase in (0.0, math.pi, math.pi / 2, -math.pi / 2):
            points = [(ENTRY[0] + 55 * math.sin(k * 5 / 95 + phase) - 55 * math.sin(phase), ENTRY[1] - k * 5)
                      for k in range(int(length / 5))]
            points.reverse()  # head first
            if min(math.dist(points[0], start) for start in starts) >= 170:
                return points
            if not best:
                best = points
    return best[-28:]  # everything is crowded: keep the snake short, just leaving its den


def snake_board(spec: VideoSpec) -> Image.Image:
    """Lucky Pick snake chase: the empty arena with the seven targets at their start positions as 3D tokens and the
    snake rising from its den in a staged pose. Nothing on the cover hints at who is eaten or who survives."""
    from .puzzles.lucky_snake import ARENA_CENTER, ARENA_RADIUS, TARGET_SIZE
    from .visuals.lucky_snake import _arena, _portal, draw_snake
    data = spec.rounds[0].data
    from .palette import background_for, object_color
    arena = _arena((W, H), background_for(spec)).copy()
    _portal(arena, SS, .6, 0.0)
    draw_snake(arena, cover_snake_pose(data["targets"]), SS, [], [], 0.0, 1.0)
    pad = 40
    box = (round(ARENA_CENTER[0] - ARENA_RADIUS - pad), round(ARENA_CENTER[1] - ARENA_RADIUS - pad),
           round(ARENA_CENTER[0] + ARENA_RADIUS + pad), round(ARENA_CENTER[1] + ARENA_RADIUS + pad))
    board = arena.crop(tuple(S(value) for value in box)).convert("RGBA")
    size = TARGET_SIZE * 1.12
    for target in data["targets"]:
        x, y = target["position"]
        glow = Image.new("RGBA", board.size, rgb(object_color(target["color_value"])) + (0,))
        gm = Image.new("L", board.size, 0)
        gx, gy = S(x - box[0]), S(y - box[1])
        ImageDraw.Draw(gm).ellipse((gx - S(70), gy - S(70), gx + S(70), gy + S(70)), fill=110)
        glow.putalpha(gm.filter(ImageFilter.GaussianBlur(S(30))))
        board.alpha_composite(glow)
        token = token3d(target["shape_id"], target["color_value"], size)
        board.alpha_composite(token, (round(gx - S(size) / 2), round(gy - S(size) / 2)))
    return board


def frame_crop(spec: VideoSpec, moment: float, box: tuple[int, int, int, int]) -> Image.Image:
    """The real level-1 board, cut from the video's own frame at 2x."""
    from .renderer import render_frame
    frame = render_frame(spec, moment, (W, H))
    return frame.crop(tuple(S(value) for value in box)).convert("RGBA")


# ---------------------------------------------------------------- templates

def _template(spec: VideoSpec) -> dict:
    kind = spec.puzzle_type
    first = spec.rounds[0].data
    levels = f"{spec.round_count} LEVELS  ·  EACH ONE HARDER"
    if kind == "quick_math" and first.get("format") == "operators":
        return {"title": ("MISSING", "SIGNS"), "gradient": ("#FFD27A", "#FF8A3D"), "accent": AMBER, "theme": "teal",
                "subtitle": "FILL IN THE BLANKS.", "cta": "ONLY ONE COMBINATION WORKS.", "cta_ink": (26, 18, 4),
                "line": f"{spec.round_count} LEVELS  ·  THE LAST ONE HAS A TRAP", "content": operator_board(first),
                "floaters": [tile3d(symbol, 104, AMBER) for symbol in ("÷", "+", "−", "×", "×", "+")]}
    if kind == "quick_math":
        tokens = [token3d(entry["shape"], entry["color"], 118) for entry in first["shapes"]]
        return {"title": ("QUICK", "MATH"), "subtitle": "SOLVE THE SHAPES.", "cta": "NO CALCULATOR.",
                "line": f"{spec.round_count} LEVELS  ·  THE LAST ONE HAS A TRAP", "content": shape_board(first),
                "floaters": (tokens * 3)[:6]}
    if kind == "puzzle_fit" and first.get("version") == "fit_v12":  # the picture with its holes, tilted options below
        from .visuals.puzzle_fit_v12 import fit_cover_card
        return {"title": ("PUZZLE", "FIT"), "subtitle": "3 PIECES ARE MISSING.", "cta": "FIND THE MISSING PIECES",
                "line": "3 PIECES  ·  6 CHOICES", "content": fit_cover_card(spec, SS),
                "floaters": [tile3d(str(number), 104, color, "#FFFFFF") for number, color in
                             zip((1, 2, 3, 4, 5, 6), ("#7C5CFF", "#FF5F6D", "#2EE6C5", "#FFC371", "#7C5CFF", "#FF5F6D"))]}
    if kind == "puzzle_fit":
        return {"title": ("PUZZLE", "FIT"), "subtitle": "ONLY ONE FITS.", "cta": "CAN YOU FIND IT?", "line": levels,
                "content": frame_crop(spec, .6, CROPS[kind]),
                "floaters": [tile3d("?", 104, color, "#FFFFFF") for color in ("#7C5CFF", "#FF5F6D", "#2EE6C5", "#FFC371", "#7C5CFF", "#FF5F6D")]}
    # Covers never state a time: thinking and viewing times differ by level and difficulty.
    if kind == "find_the_exit" and first.get("layout") in ("polar_v1", "cells_v1"):  # a circular or shaped maze: the real level-1 plate from the frame
        return {"title": ("FIND THE", "EXIT"), "subtitle": f"{len(first['exits'])} EXITS.  1 WAY OUT.", "cta": "CAN YOU ESCAPE?",
                "line": f"{spec.round_count} MAZES  ·  EACH ONE LONGER",
                "content": frame_crop(spec, spec.intro_duration + .6, CROPS["find_the_exit_circle"]),
                "floaters": [portal3d(index, 110) for index in (0, 1, 2, 3, 4, 0)]}
    if kind == "find_the_exit":
        return {"title": ("FIND THE", "EXIT"), "subtitle": "3 EXITS.  1 WAY OUT.", "cta": "CAN YOU ESCAPE?",
                "line": f"{spec.round_count} MAZES  ·  EACH ONE LONGER", "content": maze_board(first),
                "floaters": [portal3d(index % 3, 110) for index in (0, 1, 2, 0, 1, 2)]}
    if kind == "cube_count":
        from .config import CUBE_COLORS
        colors = [CUBE_COLORS[item.data["color_id"]] for item in spec.rounds]
        return {"title": ("CUBE", "COUNT"), "subtitle": "COUNT EVERY CUBE.", "cta": "BLINK AND YOU MISS IT.", "line": levels,
                "content": frame_crop(spec, spec.intro_duration + .75, CROPS[kind]),
                "floaters": [cube3d(colors[index % len(colors)], 104) for index in range(6)]}
    if kind == "flash_count":  # its own random number and digits, drawn separately from the game: no spoiler
        import random as _random
        from .visuals.flash_count import draw_cover_card
        card = draw_cover_card(spec, (W, H)).crop(tuple(S(value) for value in CROPS[kind])).convert("RGBA")
        digits = _random.Random(f"flash_cover_tiles:{spec.id}").choices("123456789", k=6)
        return {"title": ("FLASH", "COUNT"), "subtitle": "READ IT IN A BLINK.", "cta": "WHAT WAS THE NUMBER?", "line": levels,
                "content": card,
                "floaters": [tile3d(digit, 104, color, "#FFFFFF") for digit, color in
                              zip(digits, ("#7C5CFF", "#2EE6C5", "#FF5F6D", "#FFC371", "#3DA9FF", "#7C5CFF"))]}
    if kind == "line_follow":  # a tangle of its own, woven from the video id: nothing from the game is on the cover
        import random as _random
        from .puzzles.line_weave import make_round as weave_round
        from .visuals.line_follow import board_for
        board = weave_round(0, COVER_TIER, _random.Random(f"line_cover:{spec.id}")).data
        return {"title": ("LINE", "FOLLOW"), "subtitle": "FOLLOW THE LINE.", "cta": "WHERE DOES IT END?", "line": levels,
                "content": board_for(board, (W, H)).crop(tuple(S(value) for value in CROPS[kind])).convert("RGBA"),
                "floaters": [portal3d(index % 3, 110) for index in (0, 1, 2, 0, 1, 2)]}
    if kind == "mind_mix":  # the three games as glossy cards; the floating tiles come from two of the real boards' colours
        from .visuals.mind_mix import cover_card
        from .visuals.shade_spot import _boosted
        shapes = [token3d(token["shape"], token["color_value"], 110) for token in spec.rounds[0].data["sub"]["tokens"][:3]]
        tiles = [tile3d(" ", 104, _boosted(color), "#FFFFFF") for color in spec.rounds[1].data["sub"]["tiles"][:3]]
        return {"title": ("MIND", "MIX"), "subtitle": "3 GAMES. 1 VIDEO.", "cta": "CAN YOU DO ALL 3?", "line": "3 LEVELS  ·  ONE SCORE",
                "content": cover_card(spec, SS), "floaters": shapes + tiles}
    if kind == "memory_challenge" and first.get("layout") == "levels_v8":  # the hook's concept board: never a real level
        tokens = [token3d(token["shape"], token["color_value"], 110) for token in spec.rounds[-1].data["tokens"][:6]]
        return {"title": ("MEMORY", "CHALLENGE"), "subtitle": "REMEMBER IT ALL.", "cta": "TRUST YOUR MEMORY?", "line": f"{spec.round_count} LEVELS  ·  EACH ONE BIGGER",
                "content": frame_crop(spec, .6, CROPS["memory_levels"]), "floaters": tokens}
    if kind == "memory_challenge":
        tokens = [token3d(token["shape"], token["color_value"], 110) for token in first["tokens"][:6]]
        return {"title": ("MEMORY", "CHALLENGE"), "subtitle": "REMEMBER ALL 9.",
                "cta": "TRUST YOUR MEMORY?", "line": "8 QUESTIONS  ·  ONE BOARD",
                "content": frame_crop(spec, spec.intro_duration + 1.0, CROPS[kind]), "floaters": tokens}
    if kind == "lucky_pick":
        targets = first["targets"]
        return {"title": ("LUCKY", "PICK"), "subtitle": "PICK ONE.", "cta": "ONLY ONE SURVIVES.", "line": "7 COLORS  ·  1 SURVIVOR",
                "content": snake_board(spec) if first.get("map_version") == "snake_chase_v1" else lucky_board(first),
                "floaters": [token3d(target["shape_id"], target["color_value"], 104) for target in targets[:6]]}
    if kind == "shade_spot":  # level 1's two grids side by side and large (a small spoiler is accepted: it is the video's own puzzle)
        from .visuals.shade_spot import _boosted, cover_card
        colors = [_boosted(color) for color in first["tiles"][:6]]
        return {"title": ("SHADE", "SPOT"), "subtitle": "SPOT THE DIFFERENCE.", "cta": "WHICH TILE CHANGED?", "line": levels,
                "content": cover_card(spec, SS).convert("RGBA"),
                "floaters": [tile3d(" ", 104, color, "#FFFFFF") for color in colors]}
    if kind == "laser_maze":  # level 1's real board with the laser switched on, never the beam's path
        colors = ["#FF3D5A", "#3DE0C8", "#7C5CFF", "#FFB547", "#3DA9FF", "#7ED957"]
        return {"title": ("LASER", "MAZE"), "subtitle": "FOLLOW THE LASER.", "cta": "WHERE DOES IT END?",
                "line": f"{spec.round_count} LEVELS  ·  MORE MIRRORS EACH TIME",
                "content": frame_crop(spec, .6, CROPS[kind]),
                "floaters": [tile3d(str(index + 1), 104, color, "#FFFFFF") for index, color in enumerate(colors)]}
    if kind == "cup_shuffle":  # level 1's cups with the ball showing under one of them, never a shuffle
        from .visuals.cup_shuffle import ball_sprite, cup_sprite
        return {"title": ("CUP", "SHUFFLE"), "subtitle": "FOLLOW THE BALL.", "cta": "WHERE IS IT?", "line": f"{spec.round_count} LEVELS  ·  EACH ONE FASTER",
                "content": frame_crop(spec, .6, CROPS[kind]),
                "floaters": [cup_sprite("coral", S(150)), cup_sprite("violet", S(150)), cup_sprite("teal", S(150)),
                             cup_sprite("blue", S(150)), ball_sprite(S(110)), ball_sprite(S(110))]}
    if kind == "matchstick":  # the real level-1 equation, never its answer
        from .visuals.matchstick import card_box, draw_equation, frame_for, stick_sprite
        text = first["equation"]
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw_equation(canvas, text, SS, frame=frame_for(spec))
        x1, y1, x2, y2 = card_box(text)
        board = canvas.crop((S(x1), S(y1), S(x2), S(y2)))
        return {"title": ("MATCHSTICK", "MATH"), "gradient": ("#FFD27A", "#FF8A3D"), "accent": frame_for(spec),
                "subtitle": "MOVE 1 MATCH.",
                "cta": "MAKE IT TRUE.", "line": levels, "content": board,
                "floaters": [stick_sprite(S(230)) for _ in range(6)]}
    if kind == "chess_mate":  # the real position: it never shows the answer
        from .visuals.chess_mate import board_for as chess_board, board_image
        side = first["side"]
        pieces = [piece3d(piece, index % 2 == 0, 118) for index, piece in enumerate("qnkrbq")]
        return {"title": ("MATE", "IN 1"), "subtitle": f"{side.upper()} TO MOVE.", "cta": "FIND THE CHECKMATE.",
                "line": "ONE MOVE  ·  COMMENT YOURS ↓", "content": board_image(first["fen"], side, S(880), chess_board(spec)),
                "floaters": pieces}
    if kind == "bounce_arena":
        return {"title": ("BOUNCE", "ARENA"), "subtitle": "PICK A BALL.", "cta": "LAST ONE IN WINS.", "line": "REAL PHYSICS  ·  1 SURVIVOR",
                "content": frame_crop(spec, 1.0, CROPS[kind]), "floaters": [ball3d(color, 110) for color in first["colors"]]}
    raise ValueError(f"no 3D cover template for {kind}")


def has_template(spec: VideoSpec) -> bool:
    if spec.puzzle_type == "find_the_exit":
        return bool(spec.rounds) and spec.rounds[0].data.get("layout") in ("deceptive_v2", "polar_v1", "cells_v1")
    if spec.puzzle_type == "quick_math":
        return bool(spec.rounds) and "format" in spec.rounds[0].data
    if spec.puzzle_type == "line_follow":
        return bool(spec.rounds) and spec.rounds[0].data.get("version") in ("weave_v7", "weave_v8")
    if spec.puzzle_type == "lucky_pick":
        return bool(spec.rounds) and spec.rounds[0].data.get("map_version") is not None
    if spec.puzzle_type == "bounce_arena":
        return bool(spec.rounds) and spec.rounds[0].data.get("version") == 8
    if spec.puzzle_type == "flash_count":
        return bool(spec.rounds) and spec.rounds[0].data.get("format") == "number_flash"
    if spec.puzzle_type == "chess_mate":
        return bool(spec.rounds) and spec.rounds[0].data.get("version") == "mate1_v1"
    if spec.puzzle_type == "matchstick":
        return bool(spec.rounds) and spec.rounds[0].data.get("version") == "matchstick_v1"
    if spec.puzzle_type == "cup_shuffle":
        return bool(spec.rounds) and spec.rounds[0].data.get("version") == "cups_v1"
    if spec.puzzle_type == "shade_spot":
        return bool(spec.rounds) and spec.rounds[0].data.get("version") == "shade_v1"
    if spec.puzzle_type == "laser_maze":
        return bool(spec.rounds) and spec.rounds[0].data.get("version") == "laser_v1"
    if spec.puzzle_type == "mind_mix":
        return bool(spec.rounds) and spec.rounds[0].data.get("version") == "mix_v1"
    return spec.puzzle_type in ("puzzle_fit", "cube_count", "memory_challenge")


def render_game_cover(spec: VideoSpec) -> Image.Image:
    """The video's 3D cover at 1080x1920, in the video's own background tone and object palette."""
    from .palette import background_for
    from .visuals.puzzle_fit import use_theme
    use_theme(spec)  # background tone and object palette for everything drawn below
    template = _template(spec)
    theme = template.get("theme") or background_for(spec)
    accent = template.get("accent", ACCENT)
    glow = DARK_THEMES.get(theme, DARK_THEMES["violet"])[2]
    image = background(theme, accent)
    floaters = template["floaters"]
    # Far, blurred objects first (depth of field).
    for sprite, center, angle in zip(floaters[:4], ((130, 560), (975, 330), (70, 1110), (1010, 1150)), (16, -12, -18, 14)):
        floating(image, sprite.resize((max(2, sprite.width * 9 // 10), max(2, sprite.height * 9 // 10))), center, angle, accent, 4.5, .5)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((S(410), S(118), S(446), S(154)), radius=S(10), fill=rgb(accent))
    draw.text((S(462), S(136)), "Puzzly for You", font=face(40, False), fill=(255, 255, 255), anchor="lm")
    first, second = template["title"]
    top_gradient = template.get("gradient", ("#2EE6C5", hex_of(mix(rgb(glow), (255, 255, 255), .35))))
    text3d(image, (W / 2, S(300)), first, fitted(first, 900, 180), "#FFFFFF", "#CDD3EE", S(20), glow=glow)
    text3d(image, (W / 2, S(490)), second, fitted(second, 940, 208), top_gradient[0], top_gradient[1], S(24), glow=accent)
    spaced(image, (W / 2, S(648)), template["subtitle"], face(46, False), (255, 255, 255), 9)
    top, bottom = tilted_card(image, template["content"], 760, accent, hex_of(mix(rgb(glow), (255, 255, 255), .25)))
    # Two sharp objects hug the card's top-right and bottom-left corners.
    for sprite, center, angle in zip(floaters[4:6], ((968, top - 15), (112, bottom - 60)), (-14, 10)):
        floating(image, sprite, center, angle, accent)
    cta_y = min(bottom + 150, 1690)
    pill(image, (W / 2, S(cta_y)), template["cta"], fitted(template["cta"], 820, 54), accent, template.get("cta_ink", (11, 16, 32)))
    ImageDraw.Draw(image).text((W / 2, S(cta_y + 112)), template["line"], font=face(38, False), fill=rgb(accent if accent == AMBER else "#FFD23F"),
                               anchor="mm")
    return image.convert("RGB").resize((1080, 1920), Image.Resampling.LANCZOS)
