"""Procedural picture scenes for Puzzle Fit: simple, recognisable illustrations drawn locally (no image assets).

Every scene is a deterministic function of (kind, seed, size): a sky gradient, a sun or moon, and layered silhouettes.
They give each piece a clear place in the picture while staying calm enough that the shapes still read.
"""
from __future__ import annotations

from functools import lru_cache
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SCENES = ("mountains", "city", "sea", "dunes")


def _mix(a, b, t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _sky(width: int, height: int, top, bottom, horizon: float) -> Image.Image:
    y = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    t = np.clip(y / max(.05, horizon), 0, 1) ** 1.2
    rgb = np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t
    return Image.fromarray(np.repeat(rgb, width, axis=1).astype(np.uint8))


def _glow(image: Image.Image, center, radius: float, color, strength: int) -> None:
    layer = Image.new("L", image.size, 0)
    x, y = center
    ImageDraw.Draw(layer).ellipse((x - radius, y - radius, x + radius, y + radius), fill=strength)
    layer = layer.filter(ImageFilter.GaussianBlur(radius * .6))
    image.paste(Image.new("RGB", image.size, color), (0, 0), layer)


def _ridge(width: int, base: float, amplitude: float, rng: random.Random, points: int = 9) -> list[tuple[float, float]]:
    xs = np.linspace(-.05, 1.05, points)
    ys = [base - rng.uniform(.25, 1.0) * amplitude for _ in xs]
    line = []
    for index in range(len(xs) - 1):
        for step in range(12):
            t = step / 12
            smooth = t * t * (3 - 2 * t)
            line.append((float(xs[index] + (xs[index + 1] - xs[index]) * t) * width, ys[index] + (ys[index + 1] - ys[index]) * smooth))
    return line


@lru_cache(maxsize=8)
def scene(kind: str, seed: int, width: int, height: int) -> Image.Image:
    rng = random.Random(f"scene:{kind}:{seed}")
    W, H = width, height
    if kind == "mountains":
        image = _sky(W, H, (38, 52, 120), (255, 170, 110), .62)
        sun = (rng.uniform(.3, .7) * W, .42 * H)
        _glow(image, sun, .22 * H, (255, 214, 150), 150)
        ImageDraw.Draw(image).ellipse((sun[0] - .08 * H, sun[1] - .08 * H, sun[0] + .08 * H, sun[1] + .08 * H), fill=(255, 236, 190))
        layers = ((150, 92, 118), (104, 64, 104), (66, 42, 82), (40, 28, 58))
        for depth, color in enumerate(layers):
            base = (.52 + depth * .13) * H
            ridge = _ridge(W, base, (.22 - depth * .03) * H, rng, 7 + depth * 2)
            ImageDraw.Draw(image).polygon(ridge + [(W, H), (0, H)], fill=color)
        return image
    if kind == "city":
        image = _sky(W, H, (14, 18, 52), (86, 62, 140), .75)
        draw = ImageDraw.Draw(image)
        for _ in range(60):
            x, y = rng.uniform(0, W), rng.uniform(0, .5 * H)
            r = rng.uniform(.6, 1.8) * W / 800
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(235, 235, 255))
        moon = (rng.uniform(.62, .85) * W, .2 * H)
        _glow(image, moon, .12 * H, (220, 225, 255), 120)
        draw = ImageDraw.Draw(image)
        draw.ellipse((moon[0] - .06 * H, moon[1] - .06 * H, moon[0] + .06 * H, moon[1] + .06 * H), fill=(245, 245, 230))
        for row, (color, lo, hi) in enumerate((((52, 44, 98), .35, .6), ((30, 26, 64), .45, .75))):
            x = -rng.uniform(0, .05) * W
            while x < W:
                w = rng.uniform(.07, .13) * W
                top = H * (1 - rng.uniform(lo, hi) * (.75 if row == 0 else .62))
                draw.rectangle((x, top, x + w, H), fill=color)
                if row == 1:
                    for wy in np.arange(top + .03 * H, H - .03 * H, .045 * H):
                        for wx in np.arange(x + .015 * W, x + w - .02 * W, .03 * W):
                            if rng.random() < .45:
                                draw.rectangle((wx, wy, wx + .012 * W, wy + .02 * H), fill=(255, 214, 120))
                x += w + rng.uniform(0, .015) * W
        return image
    if kind == "sea":
        image = _sky(W, H, (60, 40, 110), (255, 140, 110), .55)
        sun = (rng.uniform(.3, .7) * W, .5 * H)
        _glow(image, sun, .25 * H, (255, 190, 130), 170)
        draw = ImageDraw.Draw(image)
        draw.ellipse((sun[0] - .1 * H, sun[1] - .1 * H, sun[0] + .1 * H, sun[1] + .1 * H), fill=(255, 220, 160))
        horizon = .56 * H
        sea = _sky(W, round(H - horizon), (70, 58, 130), (20, 22, 60), 1.0)
        image.paste(sea, (0, round(horizon)))
        draw = ImageDraw.Draw(image)
        for index in range(26):
            y = horizon + (index + 1) ** 1.35 * .012 * H
            width = (.05 + index * .012) * W
            draw.line(((sun[0] - width, y), (sun[0] + width, y)), fill=(255, 190, 140), width=max(1, round(H * .006)))
        bx, by = rng.uniform(.15, .85) * W, horizon + .1 * H
        draw.polygon(((bx - .07 * W, by), (bx + .07 * W, by), (bx + .05 * W, by + .025 * H), (bx - .05 * W, by + .025 * H)), fill=(24, 18, 40))
        draw.polygon(((bx, by - .15 * H), (bx, by - .01 * H), (bx + .06 * W, by - .01 * H)), fill=(24, 18, 40))
        return image
    # dunes
    image = _sky(W, H, (255, 196, 120), (255, 120, 80), .5)
    sun = (rng.uniform(.25, .75) * W, .3 * H)
    _glow(image, sun, .2 * H, (255, 240, 200), 150)
    draw = ImageDraw.Draw(image)
    draw.ellipse((sun[0] - .09 * H, sun[1] - .09 * H, sun[0] + .09 * H, sun[1] + .09 * H), fill=(255, 245, 215))
    for depth, color in enumerate(((236, 140, 80), (206, 108, 64), (170, 80, 52), (128, 56, 44))):
        base = (.55 + depth * .12) * H
        phase, frequency = rng.uniform(0, math.tau), rng.uniform(1.2, 2.2)
        line = [(x, base - math.sin(x / W * math.tau * frequency / 2 + phase) * .06 * H) for x in np.linspace(0, W, 80)]
        draw.polygon(line + [(W, H), (0, H)], fill=color)
    return image
