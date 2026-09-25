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

from .config import DARK_THEMES, PUZZLE_FIT_PALETTE, dark_theme_for
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
    "cube_count": (100, 560, 980, 1380),
    "memory_challenge": (110, 320, 970, 1190),
    "lucky_pick": (50, 310, 1030, 1620),
    "bounce_arena": (90, 450, 990, 1400),
}


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
    for gx, gy, radius, color, strength in ((540, 560, 700, glow, .55), (540, 1150, 620, mix(glow, (0, 0, 0), .35), .35),
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
    """A lit isometric cube: light top, base left, dark right."""
    px = S(size)
    base = rgb(color)
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
    if kind == "puzzle_fit":
        return {"title": ("PUZZLE", "FIT"), "subtitle": "ONLY ONE FITS.", "cta": "CAN YOU FIND IT?", "line": levels,
                "content": frame_crop(spec, .6, CROPS[kind]),
                "floaters": [tile3d("?", 104, color, "#FFFFFF") for color in ("#7C5CFF", "#FF5F6D", "#2EE6C5", "#FFC371", "#7C5CFF", "#FF5F6D")]}
    if kind == "find_the_exit":
        return {"title": ("FIND THE", "EXIT"), "subtitle": "ONLY ONE IS OPEN.", "cta": "WHICH ONE?", "line": levels,
                "content": frame_crop(spec, .6, CROPS[kind]),
                "floaters": [token3d(shape, color, 110) for shape, color in
                             (("star", "#FFD23F"), ("moon", "#B388FF"), ("circle", "#FF8A3D"), ("star", "#FFD23F"), ("moon", "#B388FF"), ("circle", "#FF8A3D"))]}
    if kind == "cube_count":
        from .config import CUBE_COLORS, CUBE_VISIBLE
        colors = [CUBE_COLORS[item.data["color_id"]] for item in spec.rounds]
        seconds = CUBE_VISIBLE.get(spec.difficulty or "hard", .5)
        return {"title": ("CUBE", "COUNT"), "subtitle": "COUNT EVERY CUBE.", "cta": f"{seconds:g} SECONDS TO LOOK.", "line": levels,
                "content": frame_crop(spec, spec.intro_duration + .75, CROPS[kind]),
                "floaters": [cube3d(colors[index % len(colors)], 104) for index in range(6)]}
    if kind == "memory_challenge":
        tokens = [token3d(token["shape"], token["color_value"], 110) for token in first["tokens"][:6]]
        return {"title": ("MEMORY", "CHALLENGE"), "subtitle": "REMEMBER ALL 9.",
                "cta": f"{first['memorization_seconds']:g} SECONDS TO MEMORIZE.", "line": "8 QUESTIONS  ·  ONE BOARD",
                "content": frame_crop(spec, spec.intro_duration + 1.0, CROPS[kind]), "floaters": tokens}
    if kind == "lucky_pick":
        targets = first["targets"]
        return {"title": ("LUCKY", "PICK"), "subtitle": "PICK ONE.", "cta": "ONLY ONE SURVIVES.", "line": "7 COLORS  ·  1 SURVIVOR",
                "content": frame_crop(spec, .6, CROPS[kind]),
                "floaters": [token3d(target["shape_id"], target["color_value"], 104) for target in targets[:6]]}
    if kind == "bounce_arena":
        return {"title": ("BOUNCE", "ARENA"), "subtitle": "PICK A BALL.", "cta": "LAST ONE IN WINS.", "line": "REAL PHYSICS  ·  1 SURVIVOR",
                "content": frame_crop(spec, 1.0, CROPS[kind]), "floaters": [ball3d(color, 110) for color in first["colors"]]}
    raise ValueError(f"no 3D cover template for {kind}")


def has_template(spec: VideoSpec) -> bool:
    if spec.puzzle_type == "find_the_exit":
        return bool(spec.rounds) and spec.rounds[0].data.get("layout") == "deceptive_v2"
    if spec.puzzle_type == "quick_math":
        return bool(spec.rounds) and "format" in spec.rounds[0].data
    if spec.puzzle_type == "lucky_pick":
        return bool(spec.rounds) and spec.rounds[0].data.get("map_version") is not None
    if spec.puzzle_type == "bounce_arena":
        return bool(spec.rounds) and spec.rounds[0].data.get("version") == 8
    return spec.puzzle_type in ("puzzle_fit", "cube_count", "memory_challenge")


def render_game_cover(spec: VideoSpec) -> Image.Image:
    """The video's 3D cover at 1080x1920, in the video's own background tone."""
    template = _template(spec)
    theme = template.get("theme") or dark_theme_for(spec.puzzle_type, spec.seed)
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
