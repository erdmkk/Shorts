"""The shared Puzzly for You end card (3.6 s): a score ring, the social accounts, and a big FOLLOW FOR MORE button.

Timeline (`local` seconds): the ring fills and a confetti burst goes off (0-0.5); `COMMENT YOUR SCORE` and a bobbing chevron
(0.35-0.65); the social panel slides in (0.5-0.85) with the YouTube row (0.75) and the Instagram row (0.95) popping in
after it; the FOLLOW FOR MORE button rises (1.15-1.45) and shines; a finger glides in and taps the + icon (2.0), which
presses the button and fires a second confetti burst; then it holds with sweeping shine, twinkling sparkles, falling
confetti and slowly turning light rays. Handles come from `config.SOCIAL_HANDLES`.
"""
from __future__ import annotations

from functools import lru_cache
import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from ..branding import draw_profile_mark
from ..config import PUZZLE_FIT_PALETTE as PALETTE, SOCIAL_HANDLES
from ..models import VideoSpec
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .text import fitted_font, font

BRAND_NAME = "Puzzly for You"
HERO = (540.0, 400.0)
RING = 160.0
LINE_Y, CHEVRON_Y = 632.0, 694.0
PANEL = (90.0, 770.0, 990.0, 1130.0)
ROW_YS = (866.0, 1036.0)
ROW_STARTS = (.75, .95)
BUTTON = (540.0, 1300.0, 820.0, 144.0)  # centre x, centre y, width, height
BUTTON_START, TAP = 1.15, 2.0
BRAND_Y = 1500.0
SPARKLES = ((140, 300, 0.0), (940, 330, 1.7), (95, 800, 3.1), (985, 1100, 4.4), (150, 1420, 2.2), (935, 1450, .8),
            (540, 1180, 5.3), (860, 560, 3.7))
CONFETTI = ("#3DF08F", "#FFC24B", "#FF4D6D", "#7C5CFF", "#2EE6C5", "#FF6FB5", "#FFFFFF")


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _mix(a, b, t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


# ---------------------------------------------------------------- social icons

@lru_cache(maxsize=8)
def youtube_icon(height: int) -> Image.Image:
    """The YouTube play button: a red rounded rectangle with a white triangle (about 1.42 x as wide as high)."""
    k = 3
    h = height * k
    w = round(h * 1.42)
    ramp = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    rgb = np.array((255, 64, 64), np.float32) * (1 - ramp) + np.array((205, 0, 0), np.float32) * ramp
    image = Image.fromarray(np.repeat(rgb, w, axis=1).astype(np.uint8)).convert("RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=h * .3, fill=255)
    ImageDraw.Draw(image).polygon(((w * .40, h * .27), (w * .40, h * .73), (w * .69, h * .5)), fill=(255, 255, 255, 255))
    gloss = Image.new("L", (w, h), 0)
    ImageDraw.Draw(gloss).rounded_rectangle((h * .06, h * .05, w - h * .06, h * .46), radius=h * .24, fill=42)
    image.paste((255, 255, 255, 255), (0, 0), ImageChops.multiply(gloss, mask))
    image.putalpha(mask)
    return image.resize((w // k, height), Image.Resampling.LANCZOS)


@lru_cache(maxsize=8)
def instagram_icon(size: int) -> Image.Image:
    """The Instagram glyph: a warm-to-purple gradient square with a white camera outline."""
    k = 3
    s = size * k
    y, x = np.mgrid[0:s, 0:s].astype(np.float32)
    t = np.clip(.5 * (x / s) + .5 * (1 - y / s) + .08 * np.sin(x / s * 3), 0, 1)
    stops = (0.0, .30, .55, .80, 1.0)
    colors = ((254, 218, 117), (250, 126, 30), (214, 41, 118), (150, 47, 191), (79, 91, 213))
    rgb = np.stack([np.interp(t, stops, [c[i] for c in colors]) for i in range(3)], axis=-1)
    image = Image.fromarray(rgb.astype(np.uint8)).convert("RGBA")
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=s * .27, fill=255)
    d = ImageDraw.Draw(image)
    stroke = round(s * .07)
    d.rounded_rectangle((s * .19, s * .19, s * .81, s * .81), radius=s * .17, outline=(255, 255, 255, 255), width=stroke)
    d.ellipse((s * .5 - s * .21, s * .5 - s * .21, s * .5 + s * .21, s * .5 + s * .21), outline=(255, 255, 255, 255), width=stroke)
    d.ellipse((s * .69, s * .23, s * .77, s * .31), fill=(255, 255, 255, 255))
    image.putalpha(mask)
    return image.resize((size, size), Image.Resampling.LANCZOS)


# ---------------------------------------------------------------- light, confetti, sparkles

@lru_cache(maxsize=4)
def _falloff(size: tuple[int, int], cx: float, cy: float, radius: float) -> Image.Image:
    y, x = np.mgrid[0:size[1], 0:size[0]].astype(np.float32)
    value = np.clip(1 - np.hypot(x - cx, y - cy) / radius, 0, 1) ** 1.25
    return Image.fromarray((value * 255).astype(np.uint8))


def _rays(image: Image.Image, local: float, scale: float, color: str) -> None:
    """Slowly turning light rays behind the ring, drawn small and scaled up (they are soft anyway)."""
    shrink = 4
    small = (image.width // shrink, image.height // shrink)
    cx, cy = HERO[0] * scale / shrink, HERO[1] * scale / shrink
    mask = Image.new("L", small, 0)
    draw = ImageDraw.Draw(mask)
    reach = 2400 * scale / shrink
    count = 14
    for index in range(count):
        angle = math.radians(index * 360 / count + local * 9)
        half = math.radians(6.2)
        draw.polygon(((cx, cy), (cx + reach * math.cos(angle - half), cy + reach * math.sin(angle - half)),
                      (cx + reach * math.cos(angle + half), cy + reach * math.sin(angle + half))), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.4))  # soft ray edges
    mask = ImageChops.multiply(mask, _falloff(small, cx, cy, 1250 * scale / shrink)).point(lambda value: value * 50 // 255)
    image.paste(Image.new("RGB", image.size, _rgb(color)), (0, 0), mask.resize(image.size, Image.Resampling.BILINEAR))


def _pieces(seed: int, count: int, speed: tuple[float, float], up: float) -> list[dict]:
    rng = random.Random(seed)
    pieces = []
    for _ in range(count):
        angle = rng.uniform(0, math.tau)
        power = rng.uniform(*speed)
        pieces.append({"vx": math.cos(angle) * power, "vy": math.sin(angle) * power - up, "size": rng.uniform(11, 24),
                       "rot": rng.uniform(0, math.tau), "spin": rng.uniform(-9, 9), "color": rng.choice(CONFETTI),
                       "life": rng.uniform(1.5, 2.3), "flip": rng.uniform(5, 12)})
    return pieces


BURST_ONE = _pieces(11, 70, (350, 1150), 250)
BURST_TWO = _pieces(23, 46, (300, 900), 350)


def _tumble(draw: ImageDraw.ImageDraw, x: float, y: float, size: float, angle: float, flip: float, color, alpha: int) -> None:
    """A confetti strip that turns over as it falls (its width follows |cos|)."""
    half_w, half_h = max(1.5, size * .5 * abs(math.cos(flip))), size * .3
    corners = [(-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)]
    cos, sin = math.cos(angle), math.sin(angle)
    draw.polygon([(x + px * cos - py * sin, y + px * sin + py * cos) for px, py in corners], fill=_rgb(color) + (alpha,))


def _burst(draw: ImageDraw.ImageDraw, pieces: list[dict], since: float, origin: tuple[float, float], scale: float) -> None:
    if since < 0:
        return
    drag = 1.7
    for piece in pieces:
        if since > piece["life"]:
            continue
        travelled = (1 - math.exp(-drag * since)) / drag
        x = origin[0] + piece["vx"] * travelled
        y = origin[1] + piece["vy"] * travelled + 450 * since * since
        alpha = round(255 * _clamp((piece["life"] - since) / .5))
        _tumble(draw, x * scale, y * scale, piece["size"] * scale, piece["rot"] + piece["spin"] * since, piece["flip"] * since, piece["color"], alpha)


def _falling(draw: ImageDraw.ImageDraw, local: float, scale: float) -> None:
    rng = random.Random(5)
    fade = _clamp((local - .4) / .5)
    for _ in range(44):
        x0, speed, sway, start = rng.uniform(30, 1050), rng.uniform(90, 230), rng.uniform(20, 60), rng.uniform(0, 2100)
        size, phase, color = rng.uniform(9, 17), rng.uniform(0, math.tau), rng.choice(CONFETTI)
        y = (start + local * speed) % 2100 - 90
        x = x0 + sway * math.sin(local * 1.6 + phase)
        _tumble(draw, x * scale, y * scale, size * scale, phase + local * 2.2, local * 6 + phase, color, round(190 * fade))


def _sparkle(draw: ImageDraw.ImageDraw, x: float, y: float, radius: float, color, alpha: int) -> None:
    if radius < 1.5 or alpha <= 0:
        return
    points = []
    for index in range(8):
        angle = index * math.pi / 4 - math.pi / 2
        r = radius if index % 2 == 0 else radius * .24
        points.append((x + r * math.cos(angle), y + r * math.sin(angle)))
    draw.polygon(points, fill=color + (alpha,))


def _sparkles(draw: ImageDraw.ImageDraw, local: float, scale: float, accent: str) -> None:
    fade = _clamp((local - .6) / .5)
    for x, y, phase in SPARKLES:
        twinkle = max(0.0, math.sin(local * 4.2 + phase)) ** 2
        _sparkle(draw, x * scale, y * scale, (10 + 26 * twinkle) * scale, (255, 255, 255), round(255 * fade * (.35 + .65 * twinkle)))
        _sparkle(draw, x * scale, y * scale, (6 + 14 * twinkle) * scale, _rgb(accent), round(200 * fade * twinkle))


# ---------------------------------------------------------------- pieces of the card

def _shine(image: Image.Image, box: tuple[int, int, int, int], radius: float, progress: float, strength: int) -> None:
    """A diagonal band of light sweeping across a rounded rectangle."""
    if not 0 < progress < 1:
        return
    x1, y1, x2, y2 = box
    width, height = x2 - x1, y2 - y1
    band = Image.new("L", (width, height), 0)
    x = -width * .3 + width * 1.6 * progress
    ImageDraw.Draw(band).polygon(((x, 0), (x + width * .16, 0), (x - width * .06, height), (x - width * .22, height)),
                                 fill=round(strength * math.sin(progress * math.pi)))
    shape = Image.new("L", (width, height), 0)
    ImageDraw.Draw(shape).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
    image.paste((255, 255, 255), (x1, y1), ImageChops.multiply(band.filter(ImageFilter.GaussianBlur(max(1, height * .04))), shape))


@lru_cache(maxsize=8)
def _button_fill(width: int, height: int, color: str) -> Image.Image:
    ramp = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    top = np.array(_mix(_rgb(color), (255, 255, 255), .28), np.float32)
    bottom = np.array(_mix(_rgb(color), (0, 0, 0), .16), np.float32)
    rgb = top * (1 - ramp) + bottom * ramp
    return Image.fromarray(np.repeat(rgb, width, axis=1).astype(np.uint8))


def _social_row(image: Image.Image, center_y: float, kind: str, handle: str, start: float, local: float, scale: float,
                accent: str) -> None:
    t = _clamp((local - start) / .4)
    if t <= 0:
        return
    pop = ease_out_back(t)
    slide = (1 - ease_out_cubic(t)) * (-150 if kind == "youtube" else 150)
    alpha = _clamp(t * 2.2)
    cx = 540 + slide
    row_w, row_h = 780.0, 132.0
    box = (cx - row_w / 2, center_y - row_h / 2, cx + row_w / 2, center_y + row_h / 2)
    rounded_surface(image, tuple(v * scale for v in box), row_h / 2 * scale, (255, 255, 255, round(22 * alpha)),
                    outline=(255, 255, 255, round(70 * alpha)), width=max(1, round(2.5 * scale)))
    height = round(84 * scale * min(1.0, pop))
    icon = youtube_icon(max(2, height)) if kind == "youtube" else instagram_icon(max(2, round(height * 1.02)))
    icon_x = cx - 230
    if alpha < 1:
        icon = icon.copy()
        icon.putalpha(icon.getchannel("A").point(lambda value: round(value * alpha)))
    image.paste(icon, (round(icon_x * scale - icon.width / 2), round(center_y * scale - icon.height / 2)), icon)
    face = fitted_font(handle, round(470 * scale), round(64 * scale))
    draw = ImageDraw.Draw(image, "RGBA")
    draw.text(((icon_x + 78) * scale, (center_y - 2) * scale), handle, font=face, fill=(255, 255, 255, round(255 * alpha)), anchor="lm")


def draw_end_card(spec: VideoSpec, local: float, size: tuple[int, int], question_text: str | None = None,
                  prompt_text: str | None = None, *, palette: dict | None = None, background: Image.Image | None = None,
                  hero=None, total: int | None = None) -> Image.Image:
    from .puzzle_fit import _background, _outro_glow, _spaced_text, _text
    pal = {**PALETTE, **(palette or {})}
    scale = size[0] / 1080
    image = (background if background is not None else _background(size, 800)).copy().convert("RGB")
    accent = pal["accent"]
    _rays(image, local, scale, accent)
    draw = ImageDraw.Draw(image, "RGBA")
    _falling(draw, local, scale)
    # Hero ring: the score question (or the winner of a pick game).
    cx, cy, ring = HERO[0] * scale, HERO[1] * scale, RING * scale
    pop = ease_out_back(_clamp(local / .35))
    glow = _outro_glow(max(4, round(ring * 1.05)), accent)
    pulse = .85 + .15 * math.sin(local * 6)
    faded = glow.copy()
    faded.putalpha(glow.getchannel("A").point(lambda value: round(value * pulse * _clamp(local / .3))))
    image.paste(faded, (round(cx - faded.width / 2), round(cy - faded.height / 2)), faded)
    draw = ImageDraw.Draw(image, "RGBA")
    radius = ring * max(.3, pop)
    width = max(3, round(16 * scale))
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=_rgb(pal["background"]) + (232,),
                 outline=_rgb(pal["surface_edge"]) + (255,), width=width)
    progress = ease_out_cubic(_clamp((local - .1) / .6))
    if progress > 0:
        draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), -90, -90 + 360 * progress, fill=_rgb(accent) + (255,), width=width)
        end = math.radians(-90 + 360 * progress)
        dot = width * .9
        ex, ey = cx + math.cos(end) * (radius - width / 2), cy + math.sin(end) * (radius - width / 2)
        draw.ellipse((ex - dot, ey - dot, ex + dot, ey + dot), fill=(255, 255, 255, 255))
    inner = ease_out_back(_clamp((local - .15) / .35))
    if inner > 0:
        if hero is not None:
            sprite = hero(max(2, round(190 * scale * inner)))
            image.paste(sprite, (round(cx - sprite.width / 2), round(cy - sprite.height / 2)), sprite)
        else:
            count = total or spec.round_count
            big, small = font(round(158 * scale)), font(round(92 * scale))
            suffix = f"/{count}"
            w_big, w_small = draw.textlength("?", font=big), draw.textlength(suffix, font=small)
            start = cx - (w_big + w_small) / 2
            _text(image, (start + w_big / 2, cy - 8 * scale), "?", big, accent, 1.0, inner)
            _text(image, (start + w_big + w_small / 2, cy + 26 * scale), suffix, small, pal["text_light"], 1.0, inner)
    # One short line and a bobbing chevron.
    line = (question_text or "").upper() if hero is not None else "COMMENT YOUR SCORE"
    line_face = fitted_font(line, round(900 * scale), round(52 * scale))
    _spaced_text(image, (540 * scale, LINE_Y * scale), line, line_face, pal["text_light"], _clamp((local - .3) / .25), 6 * scale)
    chevron = _clamp((local - .4) / .25)
    if chevron > 0:
        y = CHEVRON_Y * scale + 8 * math.sin(local * 9) * scale
        draw = ImageDraw.Draw(image, "RGBA")
        draw.line(((540 * scale - 24 * scale, y - 11 * scale), (540 * scale, y + 11 * scale), (540 * scale + 24 * scale, y - 11 * scale)),
                  fill=_rgb(accent) + (round(255 * chevron),), width=max(2, round(8 * scale)), joint="curve")
    # The social panel: a glass card, with the YouTube and Instagram rows popping in one after the other.
    panel_t = _clamp((local - .5) / .35)
    if panel_t > 0:
        lift = (1 - ease_out_cubic(panel_t)) * 70
        box = tuple(value * scale for value in (PANEL[0], PANEL[1] + lift, PANEL[2], PANEL[3] + lift))
        rounded_surface(image, box, 56 * scale, (12, 16, 38, round(214 * _clamp(panel_t * 1.6))),
                        outline=_rgb(accent) + (round(190 * panel_t),), width=max(2, round(4 * scale)), shadow=True)
        _shine(image, tuple(round(v) for v in box), 56 * scale, ((local - 1.0) / .55) % 2.8 if local >= 1.0 else 0.0, 70)
        if panel_t >= .5:
            handles = dict(SOCIAL_HANDLES)
            for kind, y, start in zip(("youtube", "instagram"), ROW_YS, ROW_STARTS):
                _social_row(image, y + lift, kind, handles.get(kind, "@puzzlyforyou"), start, local, scale, accent)
    # The FOLLOW FOR MORE button, pressed by a tapping finger.
    appear = ease_out_cubic(_clamp((local - BUTTON_START) / .3))
    bx, by, bw, bh = BUTTON
    if appear > 0:
        press = math.sin(math.pi * _clamp((local - TAP) / .16)) if local >= TAP else 0.0
        idle = 1 + .014 * math.sin(local * 7) * _clamp((local - TAP - .3) / .3)
        zoom = (1 - .07 * press) * idle
        w, h = bw * zoom * scale, bh * zoom * scale
        cy_button = (by + 70 * (1 - appear)) * scale
        halo = _outro_glow(max(4, round(h * 1.15)), accent)
        strength = appear * (.55 + .25 * math.sin(local * 5) + .5 * press)
        blurred = halo.copy()
        blurred.putalpha(halo.getchannel("A").point(lambda value: round(min(255, value * strength))))
        image.paste(blurred, (round(bx * scale - blurred.width / 2), round(cy_button - blurred.height / 2)), blurred)
        x1, y1 = round(bx * scale - w / 2), round(cy_button - h / 2)
        box = (x1, y1, x1 + round(w), y1 + round(h))
        rounded_surface(image, (box[0], box[1] + 12 * scale, box[2], box[3] + 12 * scale), h / 2, (0, 0, 0, round(130 * appear)))
        fill = _button_fill(round(w), round(h), accent)
        flash = _clamp(1 - (local - TAP) / .4) if local >= TAP else 0.0
        if flash:
            fill = Image.blend(fill, Image.new("RGB", fill.size, (255, 255, 255)), .35 * flash)
        pill = Image.new("L", fill.size, 0)
        ImageDraw.Draw(pill).rounded_rectangle((0, 0, fill.width - 1, fill.height - 1), radius=h / 2, fill=round(255 * appear))
        image.paste(fill, box[:2], pill)
        for start in (1.5, 2.55, 3.1):
            _shine(image, box, h / 2, (local - start) / .5, 120)
        draw = ImageDraw.Draw(image, "RGBA")
        ink = _rgb(pal["background"]) + (round(255 * appear),)
        icon_x, icon_r = box[0] + 86 * scale * zoom, 36 * scale * zoom
        draw.ellipse((icon_x - icon_r, cy_button - icon_r, icon_x + icon_r, cy_button + icon_r), outline=ink, width=max(2, round(7 * scale)))
        arm = icon_r * .5
        draw.line(((icon_x - arm, cy_button), (icon_x + arm, cy_button)), fill=ink, width=max(2, round(7 * scale)))
        draw.line(((icon_x, cy_button - arm), (icon_x, cy_button + arm)), fill=ink, width=max(2, round(7 * scale)))
        label = "FOLLOW FOR MORE"
        face = fitted_font(label, round((bw - 230) * scale * zoom), round(62 * scale * zoom))
        _text(image, (box[0] + (w + 86 * scale * zoom) / 2 + 30 * scale, cy_button - 3 * scale), label, face, pal["background"], appear)
        # The finger glides in, taps the + icon (never covering the label), and a ripple spreads.
        if local >= 1.65:
            travel = ease_out_cubic(_clamp((local - 1.65) / .35))
            tx = icon_x + 200 * scale * (1 - travel)
            ty = cy_button + 250 * scale * (1 - travel) + 16 * scale
            fade = _clamp(1 - (local - TAP - .35) / .3)
            finger = (32 - 7 * press) * scale
            draw.ellipse((tx - finger, ty - finger + 9 * scale, tx + finger, ty + finger + 9 * scale), fill=(0, 0, 0, round(95 * fade)))
            draw.ellipse((tx - finger, ty - finger, tx + finger, ty + finger), fill=(255, 255, 255, round(238 * fade)),
                         outline=_rgb(pal["background"]) + (round(200 * fade),), width=max(1, round(3 * scale)))
            if local >= TAP:
                ripple = ease_out_cubic(_clamp((local - TAP) / .55))
                r = (32 + 170 * ripple) * scale
                draw.ellipse((tx - r, ty - r, tx + r, ty + r), outline=(255, 255, 255, round(210 * (1 - ripple))),
                             width=max(2, round(7 * (1 - ripple) * scale) + 1))
    # Sparkles, the two confetti bursts, and the small brand.
    draw = ImageDraw.Draw(image, "RGBA")
    _sparkles(draw, local, scale, accent)
    _burst(draw, BURST_ONE, local - .12, HERO, scale)
    _burst(draw, BURST_TWO, local - TAP - .05, (BUTTON[0], BUTTON[1]), scale)
    brand = _clamp((local - .8) / .3)
    if brand > 0:
        mark = round(56 * scale)
        name_face = font(round(34 * scale))
        name_w = ImageDraw.Draw(image).textlength(BRAND_NAME, font=name_face)
        start = 540 * scale - (mark + 16 * scale + name_w) / 2
        draw_profile_mark(image, (round(start + mark / 2), round(BRAND_Y * scale)), mark, pal)
        _text(image, (start + mark + 16 * scale + name_w / 2, BRAND_Y * scale), BRAND_NAME, name_face, pal["text_muted"], brand)
    return image
