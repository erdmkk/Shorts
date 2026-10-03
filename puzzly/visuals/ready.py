"""The READY screen for games that show something for a moment (Cube Count, Cup Shuffle, Memory Challenge, Flash Count).

After the 1.0 s hook, a 3.0 s screen tells the viewer what they are about to do (`You will count the cubes.`), asks
`ARE YOU READY?` and runs a 3-2-1 countdown, so nobody misses the flash. The game starts right after it. The video's
`intro_duration` is `READY_INTRO_DURATION` (hook + ready); older videos have the short intro and no ready screen.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from ..config import PUZZLE_FIT_PALETTE as PALETTE, READY_GAMES, READY_SECONDS
from ..models import VideoSpec
from .easing import ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .puzzle_fit import _background, _outro_glow, _spaced_text, _text, active_theme
from .text import fitted_font, font

HOOK_SECONDS = 1.0
READY_TEXT = {
    "cube_count": "You will count the cubes.",
    "cup_shuffle": "You will follow the ball.",
    "memory_challenge": "You will memorize 9 shapes.",
    "flash_count": "You will read a number.",
    "shade_spot": "You will find the odd tile.",
}


def ready_text(spec: VideoSpec) -> str:
    """What the viewer is about to do. Memory's three-level version memorizes shapes of several sizes, not nine."""
    if spec.puzzle_type == "memory_challenge" and spec.rounds and spec.rounds[0].data.get("layout") == "levels_v8":
        return "You will memorize the shapes."
    return READY_TEXT.get(spec.puzzle_type, "Get ready!")


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def has_ready(spec: VideoSpec) -> bool:
    """True for videos made with the ready screen (older ones have a plain 1 s hook intro)."""
    return spec.puzzle_type in READY_GAMES and spec.intro_duration >= HOOK_SECONDS + READY_SECONDS - 1e-6


def hook_end(spec: VideoSpec) -> float:
    """When the hook ends: after the hook alone, or at the end of the whole intro for older videos."""
    return HOOK_SECONDS if has_ready(spec) else spec.intro_duration


def _lines(text: str, face, max_width: float) -> list[str]:
    """Greedy word wrap into at most two balanced lines."""
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    words = text.split()
    if probe.textlength(text, font=face) <= max_width:
        return [text]
    best = None
    for cut in range(1, len(words)):
        first, second = " ".join(words[:cut]), " ".join(words[cut:])
        worst = max(probe.textlength(first, font=face), probe.textlength(second, font=face))
        if best is None or worst < best[0]:
            best = (worst, [first, second])
    return best[1]


def draw_ready_screen(spec: VideoSpec, local: float, size: tuple[int, int], background: Image.Image | None = None) -> Image.Image:
    """`local` runs 0..READY_SECONDS; the countdown shows 3, then 2, then 1. `background` is the game's own ground."""
    scale = size[0] / 1080
    image = (background if background is not None else _background(size, 900)).copy().convert("RGB")
    appear = _clamp(local / .25)
    accent = PALETTE["accent"]
    _spaced_text(image, (540 * scale, 400 * scale), "GET READY", font(round(44 * scale)), accent, appear, 10 * scale)
    text = ready_text(spec)
    face = font(round(86 * scale))
    lines = _lines(text, face, 900 * scale)
    if len(lines) == 2:
        face = font(round(92 * scale))
    slam = 1 + .25 * (1 - ease_out_cubic(_clamp(local / .3)))
    for index, line in enumerate(lines):
        y = (560 + index * 110 - (len(lines) - 1) * 40) * scale
        _text(image, (540 * scale, y), line, face, PALETTE["text_light"], appear, slam)
    # ARE YOU READY? on a big pill.
    pill_y = 850 * scale
    pill_face = font(round(64 * scale))
    label = "ARE YOU READY?"
    width = ImageDraw.Draw(image).textlength(label, font=pill_face) + 110 * scale
    height = 118 * scale
    pulse = 1 + .04 * math.sin(local * 7)
    w, h = width * pulse, height * pulse
    rounded_surface(image, (540 * scale - w / 2, pill_y - h / 2, 540 * scale + w / 2, pill_y + h / 2), h / 2,
                    _rgb(accent) + (round(255 * _clamp((local - .1) / .25)),), shadow=True)
    _text(image, (540 * scale, pill_y - 2 * scale), label, pill_face, PALETTE["background"], _clamp((local - .1) / .25), pulse)
    # The countdown ring: the number pops in, and the ring drains over each second.
    number = max(1, 3 - int(local)) if local < READY_SECONDS else 1
    phase = local - int(local) if local < READY_SECONDS else 1.0
    cx, cy, ring = 540 * scale, 1290 * scale, 205 * scale
    glow = _outro_glow(max(4, round(ring * 1.05)), accent)
    faded = glow.copy()
    faded.putalpha(glow.getchannel("A").point(lambda value: round(value * (.55 + .35 * (1 - phase)) * appear)))
    image.paste(faded, (round(cx - faded.width / 2), round(cy - faded.height / 2)), faded)
    draw = ImageDraw.Draw(image, "RGBA")
    width_px = max(4, round(20 * scale))
    draw.ellipse((cx - ring, cy - ring, cx + ring, cy + ring), fill=_rgb(PALETTE["background"]) + (232,),
                 outline=_rgb(PALETTE["surface_edge"]) + (255,), width=width_px)
    draw.arc((cx - ring, cy - ring, cx + ring, cy + ring), -90, -90 + 360 * (1 - phase), fill=_rgb(accent) + (255,), width=width_px)
    zoom = 1 + .30 * (1 - ease_out_back(_clamp(phase / .4)))
    color = PALETTE["warning"] if number == 1 else PALETTE["text_light"]
    _text(image, (cx, cy - 6 * scale), str(number), font(round(300 * scale)), color, appear, max(.4, zoom))
    fade = 1 - _clamp((local - (READY_SECONDS - .2)) / .2)
    if fade < 1:
        image.paste(_rgb(PALETTE["background"]), (0, 0), Image.new("L", image.size, round(200 * (1 - fade))))
    return image
