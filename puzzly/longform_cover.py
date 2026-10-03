"""16:9 3D YouTube thumbnail for the long-form Quick Math compilation.

The thumbnail uses the video's own dark background tone. On the left is a huge extruded headline ("TEST YOUR MATH")
over a "CAN YOU GET 25+ RIGHT?" pill. On the right is a tilted 3D puzzle card with a real Shape Equations round, bold
near-white operators, and a "30 PUZZLES" sticker slapped on its top-left corner (never over a clue). The answer slot
pops out of the card as a big glowing yellow "?", and a short, thick 3D arrow swoops up to it. A few floating shapes
with depth-of-field blur, a perspective floor grid, and a vignette complete it. The answer and the shape values are
never drawn, and nothing important sits in the corners where YouTube draws its close/duration overlays.

Everything is drawn at 2x (3840x2160) and downsampled once with LANCZOS to 1920x1080, as in puzzly.covers.
"""
from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from .config import DARK_THEMES, glow_strength
from .covers import SS, S, extrude, face, fitted, floating, hex_of, mix, pill, rgb, tile3d, token3d

LOGICAL_W, LOGICAL_H = 1920, 1080
W, H = LOGICAL_W * SS, LOGICAL_H * SS
YELLOW = "#FFD23F"
ACCENT = "#2EE6C5"
HOT = "#FF3D6E"
INK = "#140E2A"
QUESTION_SCALE = 1.56  # the popped-out "?" tile, relative to the answer slot it sits on
# Per background tone: challenge-pill fill, and the arrow/sticker colour (face, shade) that stands out against it.
THEME_POP = {
    "violet": (ACCENT, HOT, "#D81B4F"), "ocean": (ACCENT, HOT, "#D81B4F"), "plum": (ACCENT, HOT, "#D81B4F"),
    "teal": ("#F2F4FF", HOT, "#D81B4F"), "emerald": ("#F2F4FF", HOT, "#D81B4F"),
    "crimson": (ACCENT, "#3DA9FF", "#1B6FD1"), "ember": (ACCENT, HOT, "#D81B4F"), "gold": (ACCENT, HOT, "#D81B4F"),
}


def _theme(theme: str) -> tuple[tuple, tuple, tuple]:
    return tuple(rgb(value) for value in DARK_THEMES.get(theme, DARK_THEMES["violet"]))


# ---------------------------------------------------------------- background

def _background(theme: str) -> Image.Image:
    """Theme gradient, a strong glow behind the card and a softer one behind the headline, a perspective floor grid,
    and a vignette. Computed at 1x (it is smooth), then scaled up; bokeh is drawn at 2x."""
    top, bottom, glow = _theme(theme)
    y, x = np.mgrid[0:LOGICAL_H, 0:LOGICAL_W].astype(np.float32)
    t = np.clip(y / LOGICAL_H * .8 + x / LOGICAL_W * .2, 0, 1)[..., None]
    img = np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t
    for gx, gy, radius, color, strength in ((1430, 470, 700, glow, glow_strength(theme, .66)), (470, 360, 620, glow, glow_strength(theme, .42)),
                                            (960, 1120, 760, mix(glow, (0, 0, 0), .3), glow_strength(theme, .34)),
                                            (1720, 760, 300, rgb(YELLOW), .10), (90, 120, 360, rgb(ACCENT), .10)):
        d = np.hypot(x - gx, y - gy) / radius
        img += (np.array(color, np.float32) - img) * (np.exp(-d * d) * strength)[..., None]
    horizon, vx = 700, 960
    rows = np.arange(horizon, LOGICAL_H)
    depth = ((rows - horizon) / (LOGICAL_H - horizon)).astype(np.float32)
    grid = np.zeros((LOGICAL_H, LOGICAL_W), np.float32)
    for k in range(1, 12):
        yy = int(horizon + (LOGICAL_H - horizon) * (k / 11) ** 1.8)
        grid[yy:yy + 2] = .22 * (k / 11)
    for k in range(-18, 19):
        xs = (vx + k * 30 + (k * 300 - k * 30) * depth).astype(np.int32)
        for offset in (0, 1):
            columns = xs + offset
            valid = (columns >= 0) & (columns < LOGICAL_W)
            grid[rows[valid], columns[valid]] = np.maximum(grid[rows[valid], columns[valid]], .22 * depth[valid])
    img += np.array(mix(rgb(ACCENT), glow, .45), np.float32)[None, None, :] * grid[..., None]
    vignette = np.hypot((x / LOGICAL_W - .5) * 1.0, (y / LOGICAL_H - .5) * .9)
    img *= (1 - np.clip(vignette - .30, 0, 1) * 1.1)[..., None]
    image = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).resize((W, H), Image.Resampling.BICUBIC).convert("RGBA")
    rng = random.Random("longform_bokeh")
    bokeh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(bokeh)
    for _ in range(40):
        r = S(rng.uniform(4, 20))
        px, py = rng.uniform(0, W), rng.uniform(0, H)
        draw.ellipse((px - r, py - r, px + r, py + r), fill=(255, 255, 255, rng.randint(10, 26)))
    image.alpha_composite(bokeh.filter(ImageFilter.GaussianBlur(S(3))))
    return image


# ---------------------------------------------------------------- 3D text

def _text3d(image: Image.Image, center: tuple[float, float], text: str, font, top: str, bottom: str, depth: int,
            side: tuple[tuple, tuple], glow: tuple | None = None, outline: int = 0) -> tuple[int, int, int, int]:
    """Extruded text with a gradient face, a lit top rim, a soft floor shadow, and an optional glow and dark outline.
    Returns the face's pixel bounds."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    box = probe.textbbox((0, 0), text, font=font, anchor="lt")
    pad = S(12) + outline
    mask = Image.new("L", (box[2] + pad * 2, box[3] + pad * 2), 0)
    ImageDraw.Draw(mask).text((pad, pad), text, font=font, fill=255, anchor="lt")
    body = mask
    if outline:
        body = Image.new("L", mask.size, 0)
        ImageDraw.Draw(body).text((pad, pad), text, font=font, fill=255, anchor="lt", stroke_width=outline, stroke_fill=255)
    x, y = round(center[0] - mask.width / 2), round(center[1] - mask.height / 2)
    if glow:
        halo = Image.new("RGBA", image.size, glow + (0,))
        big = Image.new("L", image.size, 0)
        big.paste(mask, (x, y))
        halo.putalpha(big.filter(ImageFilter.GaussianBlur(S(40))).point(lambda v: min(255, int(v * 1.2))))
        image.alpha_composite(halo)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sm = Image.new("L", image.size, 0)
    sm.paste(body, (x + depth, y + depth * 2))
    shadow.putalpha(sm.filter(ImageFilter.GaussianBlur(S(16))).point(lambda v: v * 190 // 255))
    image.alpha_composite(shadow)
    image.alpha_composite(extrude(body, depth, hex_of(side[0]), hex_of(side[1]), .45, 1.0), (x, y))
    if outline:
        ring = Image.new("RGBA", mask.size, side[1] + (255,))
        ring.putalpha(body)
        image.alpha_composite(ring, (x, y))
    gradient = Image.linear_gradient("L").resize(mask.size)
    fill = Image.composite(Image.new("RGBA", mask.size, rgb(bottom) + (255,)), Image.new("RGBA", mask.size, rgb(top) + (255,)), gradient)
    fill.putalpha(mask)
    image.alpha_composite(fill, (x, y))
    rim = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    rim.putalpha(ImageChops.subtract(mask, ImageChops.offset(mask, 0, S(5))).point(lambda v: v * 210 // 255))
    image.alpha_composite(rim, (x, y))
    ink = mask.getbbox() or (0, 0, 0, 0)
    return x + ink[0], y + ink[1], x + ink[2], y + ink[3]


# ---------------------------------------------------------------- the puzzle card

def _homography(src, dst) -> list[float]:
    """Coefficients that map a point of dst to src (PIL's PERSPECTIVE convention)."""
    matrix, vector = [], []
    for (x, y), (u, v) in zip(dst, src):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        vector += [u, v]
    return np.linalg.solve(np.array(matrix, np.float64), np.array(vector, np.float64)).tolist()


def _apply(c: list[float], x: float, y: float) -> tuple[float, float]:
    d = c[6] * x + c[7] * y + 1
    return (c[0] * x + c[1] * y + c[2]) / d, (c[3] * x + c[4] * y + c[5]) / d


def _shadowed_text(board: Image.Image, center: tuple[float, float], text: str, font, fill: tuple) -> None:
    """Text with a soft dark drop shadow, so thin glyphs (+, −, ×, =) survive a phone-size downscale and a nearby glow."""
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    box = probe.textbbox((0, 0), text, font=font, anchor="mm")
    pad = S(22)
    size = (box[2] - box[0] + pad * 2, box[3] - box[1] + pad * 2)
    local = (size[0] / 2 - (box[0] + box[2]) / 2, size[1] / 2 - (box[1] + box[3]) / 2)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).text(local, text, font=font, fill=255, anchor="mm")
    origin = (round(center[0] - local[0]), round(center[1] - local[1]))
    shadow = Image.new("RGBA", size, (4, 3, 14, 0))
    shadow.putalpha(ImageChops.offset(mask, S(3), S(5)).filter(ImageFilter.GaussianBlur(S(5))).point(lambda v: v * 220 // 255))
    board.alpha_composite(shadow, origin)
    glyph = Image.new("RGBA", size, fill + (0,))
    glyph.putalpha(mask)
    board.alpha_composite(glyph, origin)


def _hero_board(hero: dict, surface: tuple, line: tuple) -> tuple[Image.Image, tuple[float, float], float, list]:
    """The clues with their results and the question row, the "=" signs in one column. The question's answer slot is
    left as an empty outlined socket; the glowing "?" is added on top after the card is tilted. Operators and "=" are
    bold and near-white so "+" versus "×" still reads at phone size. Returns the board, the slot centre, the slot size
    (pixels), and each row's content box (board pixels)."""
    shapes = {entry["name"]: entry for entry in hero["shapes"]}
    token, gap, row_h = S(124), S(18), S(164)
    op_font, num_font = face(112), face(118)
    op_color = (240, 242, 255)
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))

    def term_width(term) -> float:
        return token if term in shapes else probe.textlength(term, font=op_font)

    rows = [(clue["terms"], str(clue["result"])) for clue in hero["clues"]] + [(hero["question"]["terms"], None)]
    lefts = [sum(term_width(term) for term in terms) + gap * (len(terms) - 1) for terms, _ in rows]
    equals = probe.textlength("=", font=op_font)
    slot = S(146)
    # Results sit left-aligned after the "=". The column is as wide as the popped-out "?" tile (QUESTION_SCALE times
    # the slot), whose left edge lines up with the results, so it never covers the "=" before it.
    tile = slot * QUESTION_SCALE
    right = max([tile] + [probe.textlength(result, font=num_font) for _, result in rows if result])
    pad_x, pad_top, divider_gap = S(64), S(100), S(70)
    after_equals = S(44)
    bw = round(max(lefts) + gap + equals + after_equals + right + pad_x * 2)
    bh = round(pad_top * 2 + row_h * (len(rows) - 1) + divider_gap)
    board = Image.new("RGBA", (bw, bh), surface + (255,))
    light = Image.new("RGBA", board.size, mix(surface, (255, 255, 255), .5) + (0,))
    lm = Image.new("L", board.size, 0)
    ImageDraw.Draw(lm).ellipse((-S(160), -S(480), bw + S(160), S(260)), fill=70)
    light.putalpha(lm.filter(ImageFilter.GaussianBlur(S(70))))
    board.alpha_composite(light)
    equals_x = pad_x + max(lefts) + gap
    result_left = equals_x + equals + after_equals
    result_x = result_left + tile / 2
    slot_center = (0.0, 0.0)
    boxes = []
    for index, (terms, result) in enumerate(rows):
        y = pad_top + row_h * index + (divider_gap if result is None else 0)
        x = equals_x - gap - lefts[index]
        boxes.append((x, y - token / 2 - S(6), result_left + right, y + token / 2 + S(10)))
        for term in terms:
            width = term_width(term)
            if term in shapes:
                sprite = token3d(shapes[term]["shape"], shapes[term]["color"], token / SS)
                board.alpha_composite(sprite, (round(x + S(3)), round(y - token / 2 - S(4))))
            else:
                _shadowed_text(board, (x + width / 2, y - S(4)), term, op_font, op_color)
            x += width + gap
        _shadowed_text(board, (equals_x + equals / 2, y - S(4)), "=", op_font, (255, 255, 255))
        draw = ImageDraw.Draw(board)
        if result is None:
            slot_center = (result_x, y)
            half = slot / 2
            draw.rounded_rectangle((result_x - half, y - half, result_x + half, y + half), radius=S(30),
                                   fill=mix(surface, (0, 0, 0), .35), outline=rgb(YELLOW), width=S(5))
        else:
            draw.text((result_left, y - S(2)), result, font=num_font, fill=(255, 255, 255), anchor="lm")
    divider = pad_top + row_h * (len(rows) - 2) + row_h / 2 + divider_gap / 2
    ImageDraw.Draw(board).line((pad_x * .7, divider, bw - pad_x * .7, divider), fill=line, width=S(5))
    return board, slot_center, slot, boxes


def _tilted_card(image: Image.Image, board: Image.Image, box: tuple[float, float, float, float], glow: tuple,
                 edge: tuple):
    """Put the board on a thick card that faces the headline (its far, left edge is shorter) and leans back.

    Returns a function that maps a board pixel to an image pixel, and a function that gives the local horizontal
    scale (image pixels per board pixel) at a board pixel."""
    x1, y1, x2, y2 = (S(value) for value in box)
    scale = min((x2 - x1) / board.width, (y2 - y1) / board.height)
    bw, bh = max(2, round(board.width * scale)), max(2, round(board.height * scale))
    content = board.resize((bw, bh), Image.Resampling.LANCZOS)
    radius = S(54)
    card = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    mask = Image.new("L", (bw, bh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, bw - 1, bh - 1), radius=radius, fill=255)
    card.paste(content, (0, 0), mask)
    ImageDraw.Draw(card).rounded_rectangle((0, 0, bw - 1, bh - 1), radius=radius, outline=edge, width=S(6))
    src = [(0, 0), (bw, 0), (bw, bh), (0, bh)]
    dst = [(bw * .075, bh * .085), (bw * .985, 0), (bw, bh * .955), (0, bh * .885)]
    back = _homography(src, dst)
    tilted = card.transform((bw, bh), Image.Transform.PERSPECTIVE, back, Image.Resampling.BICUBIC)
    x, y = round((x1 + x2) / 2 - bw / 2), round((y1 + y2) / 2 - bh / 2)
    floor = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(floor).ellipse((x - S(20), y + bh * .8, x + bw + S(30), y + bh + S(120)), fill=(0, 0, 0, 200))
    image.alpha_composite(floor.filter(ImageFilter.GaussianBlur(S(44))))
    silhouette = tilted.getchannel("A")
    rim = Image.new("RGBA", image.size, glow + (0,))
    rim_mask = Image.new("L", image.size, 0)
    rim_mask.paste(silhouette, (x, y))
    rim.putalpha(rim_mask.filter(ImageFilter.GaussianBlur(S(34))).point(lambda v: v * 150 // 255))
    image.alpha_composite(rim)
    thickness = S(34)
    for step in range(thickness, 0, -1):
        tone = mix(mix(edge, (0, 0, 0), .25), (3, 4, 12), step / thickness)
        image.paste(Image.new("RGBA", silhouette.size, tone + (255,)), (x + round(step * .35), y + step), silhouette)
    image.alpha_composite(tilted, (x, y))
    forward = _homography(dst, src)

    def to_image(px: float, py: float) -> tuple[float, float]:
        cx, cy = _apply(forward, px * scale, py * scale)
        return x + cx, y + cy

    def local_scale(px: float, py: float) -> float:
        return (to_image(px + 40, py)[0] - to_image(px - 40, py)[0]) / 80

    return to_image, local_scale


# ---------------------------------------------------------------- focal pieces

def _question_tile(size: float) -> Image.Image:
    """The answer slot as a chunky glowing 3D "?" key: a bright yellow face on a deep gold slab."""
    px = S(size)
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, px - 1, px - 1), radius=px // 4, fill=255)
    tile = Image.new("RGBA", (px + px // 3, px + px // 3), (0, 0, 0, 0))
    tile.alpha_composite(extrude(mask, max(8, px // 7), "#C98F06", "#5A3A00", .3, 1.0))
    face_fill = Image.composite(Image.new("RGBA", (px, px), rgb("#FFB81F") + (255,)), Image.new("RGBA", (px, px), rgb("#FFE66B") + (255,)),
                                Image.linear_gradient("L").resize((px, px)))
    face_fill.putalpha(mask)
    tile.alpha_composite(face_fill)
    shine = Image.new("L", (px, px), 0)
    ImageDraw.Draw(shine).rounded_rectangle((px * .08, px * .05, px * .92, px * .40), radius=px // 5, fill=90)
    gloss = Image.new("RGBA", (px, px), (255, 255, 255, 0))
    gloss.putalpha(shine.filter(ImageFilter.GaussianBlur(px * .04)))
    tile.alpha_composite(gloss)
    ImageDraw.Draw(tile).text((px / 2, px / 2 - px * .02), "?", font=face(size * .74), fill=rgb(INK), anchor="mm")
    return tile


def _rays(image: Image.Image, center: tuple[float, float], radius: float, color: tuple, count: int = 18, strength: int = 70) -> None:
    """A soft sunburst behind the focal point, fading to nothing well inside its canvas."""
    cx, cy = center
    r = S(radius)
    size = round(r * 2)
    wedges = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(wedges)
    for index in range(count):
        a = 2 * math.pi * index / count
        b = a + math.pi / count
        draw.polygon([(r, r), (r + r * math.cos(a), r + r * math.sin(a)), (r + r * math.cos(b), r + r * math.sin(b))], fill=255)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.hypot(xx - r, yy - r) / r
    falloff = Image.fromarray((np.clip(1 - d, 0, 1) ** 1.6 * strength).astype(np.uint8))
    layer = Image.new("RGBA", (size, size), color + (0,))
    layer.putalpha(ImageChops.multiply(wedges.filter(ImageFilter.GaussianBlur(S(6))), falloff))
    image.alpha_composite(layer, (round(cx - r), round(cy - r)))


def _halo(image: Image.Image, center: tuple[float, float], radius: float, color: tuple, alpha: int,
          cut_x: float | None = None, feather: float = 40) -> None:
    """A soft glow. With cut_x (image pixels), it fades out to the left of that line, so it never washes out the "="."""
    cx, cy = center
    r = S(radius)
    pad = round(r * 2.6)
    local = Image.new("L", (pad * 2, pad * 2), 0)
    ImageDraw.Draw(local).ellipse((pad - r, pad - r, pad + r, pad + r), fill=alpha)
    glow = local.filter(ImageFilter.GaussianBlur(r * .5))
    ox, oy = round(cx - pad), round(cy - pad)
    if cut_x is not None:
        xs = np.arange(pad * 2, dtype=np.float32) + ox
        ramp = np.clip((xs - (cut_x - S(feather))) / S(feather), 0, 1)
        glow = Image.fromarray((np.asarray(glow, np.float32) * ramp[None, :]).astype(np.uint8))
    layer = Image.new("RGBA", local.size, color + (0,))
    layer.putalpha(glow)
    image.alpha_composite(layer, (ox, oy))


def _sparkle(image: Image.Image, center: tuple[float, float], size: float, color: tuple) -> None:
    """A four-point glint with a soft glow."""
    cx, cy = center
    r = S(size)
    pad = round(r * 1.6)
    local = Image.new("L", (pad * 2, pad * 2), 0)
    draw = ImageDraw.Draw(local)
    thin = r * .16
    draw.polygon([(pad, pad - r), (pad + thin, pad - thin), (pad + r, pad), (pad + thin, pad + thin), (pad, pad + r),
                  (pad - thin, pad + thin), (pad - r, pad), (pad - thin, pad - thin)], fill=255)
    glow = Image.new("RGBA", local.size, color + (0,))
    glow.putalpha(local.filter(ImageFilter.GaussianBlur(r * .25)))
    image.alpha_composite(glow, (round(cx - pad), round(cy - pad)))
    white = Image.new("RGBA", local.size, (255, 255, 255, 0))
    white.putalpha(local)
    image.alpha_composite(white, (round(cx - pad), round(cy - pad)))


def _arrow(image: Image.Image, points: list[tuple[float, float]], width: float, head: float, fill: tuple[str, str]) -> None:
    """A bold 3D arrow along a quadratic curve (logical points: start, control, tip), with a white outline."""
    (x0, y0), (x1, y1), (x2, y2) = [(S(px), S(py)) for px, py in points]
    samples = [((1 - t) ** 2 * x0 + 2 * (1 - t) * t * x1 + t * t * x2, (1 - t) ** 2 * y0 + 2 * (1 - t) * t * y1 + t * t * y2)
               for t in (index / 80 for index in range(81))]
    lengths = [0.0]
    for a, b in zip(samples, samples[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    head_len = S(head)
    cut = next(index for index, length in enumerate(lengths) if length >= lengths[-1] - head_len)
    shaft = samples[:cut + 1]
    left, right = [], []
    for index, (px, py) in enumerate(shaft):
        ax, ay = shaft[max(0, index - 1)]
        bx, by = shaft[min(len(shaft) - 1, index + 1)]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1
        nx, ny = -dy / norm, dx / norm
        half = S(width) / 2 * (.55 + .45 * index / (len(shaft) - 1))
        left.append((px + nx * half, py + ny * half))
        right.append((px - nx * half, py - ny * half))
    bx, by = shaft[-1]
    dx, dy = x2 - bx, y2 - by
    norm = math.hypot(dx, dy) or 1
    nx, ny = -dy / norm, dx / norm
    wing = S(width) * 1.15
    polygon = left + [(bx + nx * wing, by + ny * wing), (x2, y2), (bx - nx * wing, by - ny * wing)] + right[::-1]
    margin = S(width) * 2
    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    ox, oy = round(min(xs) - margin), round(min(ys) - margin)
    size = (round(max(xs) - min(xs) + margin * 2), round(max(ys) - min(ys) + margin * 2))
    local = [(px - ox, py - oy) for px, py in polygon]
    tail_x, tail_y = shaft[0][0] - ox, shaft[0][1] - oy
    tail = S(width) * .55 / 2
    body = Image.new("L", size, 0)
    ImageDraw.Draw(body).polygon(local, fill=255)
    ImageDraw.Draw(body).ellipse((tail_x - tail, tail_y - tail, tail_x + tail, tail_y + tail), fill=255)
    outer = body.copy()
    ImageDraw.Draw(outer).line(local + [local[0]], fill=255, width=S(18), joint="curve")
    ImageDraw.Draw(outer).ellipse((tail_x - tail - S(9), tail_y - tail - S(9), tail_x + tail + S(9), tail_y + tail + S(9)), fill=255)
    depth = S(16)
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    shadow.putalpha(ImageChops.offset(outer, depth, depth * 2).filter(ImageFilter.GaussianBlur(S(12))).point(lambda v: v * 180 // 255))
    image.alpha_composite(shadow, (ox, oy))
    base = rgb(fill[1])
    image.alpha_composite(extrude(outer, depth, hex_of(mix(base, (0, 0, 0), .45)), hex_of(mix(base, (0, 0, 0), .8)), .35, 1.0), (ox, oy))
    white = Image.new("RGBA", size, (255, 255, 255, 0))
    white.putalpha(outer)
    image.alpha_composite(white, (ox, oy))
    gradient = Image.composite(Image.new("RGBA", size, rgb(fill[1]) + (255,)), Image.new("RGBA", size, rgb(fill[0]) + (255,)),
                               Image.linear_gradient("L").resize(size))
    gradient.putalpha(body)
    image.alpha_composite(gradient, (ox, oy))
    rim = Image.new("RGBA", size, (255, 255, 255, 0))
    rim.putalpha(ImageChops.subtract(body, ImageChops.offset(body, 0, S(5))).point(lambda v: v * 150 // 255))
    image.alpha_composite(rim, (ox, oy))


def _sticker(size: float, big: str, small: str, fill: str, ink: tuple) -> Image.Image:
    """A round scalloped 3D sticker: a big number over a small spaced word."""
    px = S(size)
    r = px / 2
    points = []
    for index in range(56):
        angle = math.pi * index / 28
        radius = r * (1 if index % 2 == 0 else .93)
        points.append((r + radius * math.cos(angle), r + radius * math.sin(angle)))
    mask = Image.new("L", (px, px), 0)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    base = rgb(fill)
    sticker = Image.new("RGBA", (px + px // 5, px + px // 5), (0, 0, 0, 0))
    sticker.alpha_composite(extrude(mask, max(6, px // 14), hex_of(mix(base, (0, 0, 0), .4)), hex_of(mix(base, (0, 0, 0), .8)), .3, 1.0))
    top = Image.composite(Image.new("RGBA", (px, px), mix(base, (0, 0, 0), .12) + (255,)), Image.new("RGBA", (px, px), mix(base, (255, 255, 255), .12) + (255,)),
                          Image.linear_gradient("L").resize((px, px)))
    top.putalpha(mask)
    sticker.alpha_composite(top)
    draw = ImageDraw.Draw(sticker)
    inner = r * .86
    draw.ellipse((r - inner, r - inner, r + inner, r + inner), outline=(255, 255, 255), width=S(4))
    big_size = size * .42
    while big_size > 20 and draw.textlength(big, font=face(big_size)) > inner * 1.35:
        big_size -= 2
    draw.text((r, r - px * .11), big, font=face(big_size), fill=ink, anchor="mm")
    # The small word is as big as the inner ring allows, so it still reads at phone size.
    small_size, spacing = size * .15, S(size * .006)
    while small_size > 8:
        small_font = face(small_size)
        widths = [draw.textlength(char, font=small_font) for char in small]
        if sum(widths) + spacing * (len(small) - 1) <= inner * 1.5:
            break
        small_size -= 1
    x = r - (sum(widths) + spacing * (len(small) - 1)) / 2
    for char, width in zip(small, widths):
        draw.text((x, r + px * .19), char, font=small_font, fill=ink, anchor="lm")
        x += width + spacing
    return sticker


# ---------------------------------------------------------------- thumbnail

def _rotated(sprite: Image.Image, face_size: float, angle: float):
    """Rotate a 3D tile sprite whose top face is the square (0, 0, face_size, face_size). Returns the rotated sprite
    and a function that maps a point of the unrotated sprite to the rotated one."""
    rotated = sprite.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    a = math.radians(angle)
    cos, sin = math.cos(a), math.sin(a)

    def where(px: float, py: float) -> tuple[float, float]:
        dx, dy = px - sprite.width / 2, py - sprite.height / 2
        return rotated.width / 2 + dx * cos + dy * sin, rotated.height / 2 - dx * sin + dy * cos

    return rotated, where


def _circle_hits_box(center: tuple[float, float], radius: float, box: tuple[float, float, float, float]) -> bool:
    nx = min(max(center[0], box[0]), box[2])
    ny = min(max(center[1], box[1]), box[3])
    return math.hypot(center[0] - nx, center[1] - ny) < radius


def _circle_hits_quad(center: tuple[float, float], radius: float, quad: list[tuple[float, float]]) -> bool:
    """Whether a circle overlaps a convex quadrilateral (a clue row on the tilted card)."""
    cx, cy = center
    signs = []
    for (ax, ay), (bx, by) in zip(quad, quad[1:] + quad[:1]):
        signs.append((bx - ax) * (cy - ay) - (by - ay) * (cx - ax) > 0)
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((cx - ax) * dx + (cy - ay) * dy) / ((dx * dx + dy * dy) or 1)))
        if math.hypot(cx - (ax + t * dx), cy - (ay + t * dy)) < radius:
            return True
    return all(signs) or not any(signs)


def _sticker_spot(corner: tuple[float, float], radius: float, rows: list, headline: tuple) -> tuple[float, float]:
    """Where the round sticker goes (image pixels): slapped over the card's top-left corner, nudged up and out only as
    far as needed so it never covers a clue and keeps clear of the headline."""
    best, best_score = None, None
    for dy in range(0, -141, -10):
        for dx in range(-20, 101, 10):
            center = (corner[0] + S(dx), corner[1] + S(dy))
            covers = any(_circle_hits_quad(center, radius + S(12), quad) for quad in rows)
            crowds = _circle_hits_box(center, radius + S(44), headline)
            leaves = center[1] - radius < S(24)
            score = (covers, crowds or leaves, math.hypot(dx, dy * 1.2))
            if best_score is None or score < best_score:
                best, best_score = center, score
    return best


def render_longform_thumbnail(theme: str, hero: dict, puzzle_count: int = 30, best_score: int = 31) -> Image.Image:
    """The long-form Quick Math thumbnail: RGB 1920x1080 in the video's background tone. Shows the hero round's clues
    with their results and the question ending in a glowing "?"; never the answer or any shape value."""
    _, bottom, glow = _theme(theme)
    pill_fill, pop, pop_dark = THEME_POP.get(theme, THEME_POP["violet"])
    image = _background(theme)
    hero_shapes = [token3d(entry["shape"], entry["color"], 120) for entry in hero["shapes"]]
    # Far, blurred objects (depth of field), all fully inside the frame and clear of the corners.
    for sprite, center, angle, blur in ((tile3d("+", 112, "#7C5CFF", "#FFFFFF"), (1480, 88), 14, 5.0),
                                        (hero_shapes[0], (66, 668), -16, 5.0)):
        floating(image, sprite.resize((max(2, sprite.width * 4 // 5), max(2, sprite.height * 4 // 5))), center, angle, hex_of(glow), blur, .55)
    # Headline.
    side = (mix(glow, (0, 0, 0), .45), mix(glow, (0, 0, 0), .88))
    headline = _text3d(image, (S(515), S(282)), "TEST YOUR", fitted("TEST YOUR", 880, 156), "#FFFFFF", "#D6DBF2", S(18), side, glow=glow)
    _text3d(image, (S(508), S(528)), "MATH", fitted("MATH", 920, 330), "#FFF06A", "#FF9A2E", S(30), side, glow=rgb("#FF9A2E"))
    # Challenge pill: an honest target out of the video's puzzles.
    target = max(1, min(puzzle_count, round(best_score * .8)))
    question = f"CAN YOU GET {target}+ RIGHT?"
    pill(image, (S(508), S(810)), question, fitted(question, 800, 64), pill_fill, rgb(INK), pad=48, height=116)
    # The puzzle card (on its own layer, so the sunburst can sit behind it). Green and blue tones get a more neutral
    # card, so same-hued shape tokens keep their contrast.
    surface = mix(mix(bottom, glow, .24), (255, 255, 255), .03)
    if theme in ("teal", "emerald", "ocean"):
        surface = mix(surface, rgb(INK), .35)
    board, slot, slot_size, rows = _hero_board(hero, surface, mix(glow, (255, 255, 255), .25))
    edge = mix(glow, (255, 255, 255), .3)
    card_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    to_image, local = _tilted_card(card_layer, board, (1000, 168, 1850, 942), glow, edge)
    qx, qy = to_image(*slot)
    q_size = slot_size * local(*slot) / SS * QUESTION_SCALE
    _rays(image, (qx, qy), 560, rgb(YELLOW), strength=70)
    image.alpha_composite(card_layer)
    # The popped-out "?" tile: its face centre sits on the slot, tilted a little.
    q_px = S(q_size)
    q_tile, where = _rotated(_question_tile(q_size), q_px, -8)
    face_center = (qx + S(4), qy + S(6))
    fx, fy = where(q_px / 2, q_px / 2)
    origin = (round(face_center[0] - fx), round(face_center[1] - fy))
    corners = [(origin[0] + px, origin[1] + py) for px, py in (where(0, 0), where(q_px, 0), where(q_px, q_px), where(0, q_px))]
    face_left = min(px for px, _ in corners)
    _halo(image, (qx + S(q_size * .1), qy), q_size * .82, rgb(YELLOW), 200, cut_x=face_left + S(24), feather=44)
    image.alpha_composite(q_tile, origin)
    for dx, dy, size in ((.7, -.62, .13), (.5, .9, .19), (.8, .5, .08)):
        _sparkle(image, (face_center[0] + S(q_size * dx), face_center[1] + S(q_size * dy)), q_size * size, rgb(YELLOW))
    # A short, thick arrow swoops up from under the card and stops just off the "?" tile's lower-left corner.
    depth = max(8, q_px // 7)
    lower_left = corners[3]
    tip = ((lower_left[0] - S(18)) / SS, (lower_left[1] + depth + S(18)) / SS)
    ux, uy = face_center[0] / SS - tip[0], face_center[1] / SS - tip[1]
    norm = math.hypot(ux, uy) or 1
    control = (tip[0] - ux / norm * 190, tip[1] - uy / norm * 190)
    _arrow(image, [(tip[0] - 400, 1000), control, tip], 74, 112, (pop, pop_dark))
    # "30 PUZZLES" sticker slapped on the card's top-left corner.
    sticker_size = 236
    card_corner = to_image(0, 0)
    headline_box = (headline[0], headline[1], headline[2], headline[3])
    row_quads = [[to_image(x1, y1), to_image(x2, y1), to_image(x2, y2), to_image(x1, y2)] for x1, y1, x2, y2 in rows]
    sx, sy = _sticker_spot(card_corner, S(sticker_size / 2), row_quads, headline_box)
    offset = sticker_size / 10  # the sprite canvas has room for the extrusion below-right of the disc
    floating(image, _sticker(sticker_size, str(puzzle_count), "PUZZLES", pop, (255, 255, 255)),
             (sx / SS + offset, sy / SS + offset), -12, pop)
    # One sharp shape in the free bottom-left corner.
    floating(image, hero_shapes[1 % len(hero_shapes)], (150, 962), -14, hex_of(glow))
    # Brand mark.
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((S(56), S(46), S(88), S(78)), radius=S(9), fill=rgb(ACCENT))
    draw.text((S(102), S(62)), "Puzzly for You", font=face(34, False), fill=(255, 255, 255), anchor="lm")
    return image.convert("RGB").resize((LOGICAL_W, LOGICAL_H), Image.Resampling.LANCZOS)
