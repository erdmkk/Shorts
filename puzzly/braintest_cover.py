"""16:9 3D thumbnail for the Brain Test long-form, built so consecutive uploads never look alike.

Everything that changes is derived from the episode number (`BRAIN TEST #n`, saved videos only), so neighbouring episodes
always differ in every dimension, and a Draft that is never saved reuses its number and therefore its look:
  * layout: one of six (`LAYOUTS`), stepping by 5 through 6 so the next episode never repeats it;
  * colour palette: one of ten (`PALETTES`, background tone, headline gradient, pill and sticker colours), stepping by 3
    through 10;
  * hero game: the card shows the video's real hook frame of one game, rotating through all ten (`BrainPlan.hero_key`);
  * headline: one of eight honest lines, and a rotating challenge pill.
Answers are never shown, nothing claims an IQ or a percentage, and the corners stay free for YouTube's overlays.
Everything is drawn at 2x (3840x2160) and downsampled once to 1920x1080, as in puzzly.longform_cover.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageOps

from .covers import SS, S, face, fitted, floating, hex_of, mix, pill, rgb, tile3d
from .longform_cover import INK, LOGICAL_H, LOGICAL_W, _background, _sticker, _text3d, _theme, _tilted_card


@dataclass(frozen=True)
class Palette:
    theme: str
    top: str  # headline gradient
    bottom: str
    pill: str  # challenge pill fill
    pop: str  # sticker colour
    pop_dark: str


PALETTES = (
    Palette("violet", "#FFF06A", "#FF9A2E", "#2EE6C5", "#FF3D6E", "#D81B4F"),
    Palette("ocean", "#E9FBFF", "#5FE0FF", "#FFC24B", "#FF5F6D", "#D6384A"),
    Palette("gold", "#FFFFFF", "#FFD23F", "#2EE6C5", "#7C5CFF", "#5237D6"),
    Palette("emerald", "#F4FFF0", "#8CFF6B", "#FFD23F", "#FF3D6E", "#D81B4F"),
    Palette("ember", "#FFF2E0", "#FF8A3D", "#2EE6C5", "#3DA9FF", "#1B6FD1"),
    Palette("plum", "#FFEAF7", "#FF6FB5", "#FFD23F", "#2EE6C5", "#12A58C"),
    Palette("teal", "#FFFFFF", "#2EE6C5", "#FFC24B", "#FF3D6E", "#D81B4F"),
    Palette("crimson", "#FFFFFF", "#FFC24B", "#F2F4FF", "#3DA9FF", "#1B6FD1"),
    Palette("lemon", "#FFFFFF", "#FF3D6E", "#2EE6C5", "#7C5CFF", "#5237D6"),
    Palette("cyan", "#FFF7B0", "#FFC24B", "#FF3D6E", "#7C5CFF", "#5237D6"),
)


@dataclass(frozen=True)
class Layout:
    cx: float  # centre of the headline column
    cy: float  # vertical centre of the headline block (two lines and the pill)
    card: tuple[float, float, float, float]
    mirror: bool = False  # the card is on the left, leans the other way, and the glows switch sides
    second: tuple[float, float, float, float] | None = None  # a second, smaller card behind (another game)
    strip: bool = False  # a row of the game chips along the bottom
    width: float = 840  # widest a headline line may be


LAYOUTS = (
    Layout(470, 520, (1090, 64, 1800, 1016)),
    Layout(1450, 520, (120, 64, 830, 1016), mirror=True, width=860),
    Layout(470, 500, (1190, 54, 1830, 930), second=(930, 200, 1420, 1000), width=780),
    Layout(470, 480, (1090, 64, 1800, 984), strip=True),
    Layout(1450, 480, (120, 64, 830, 984), mirror=True, second=(590, 260, 1010, 960), strip=True, width=780),
    Layout(470, 520, (960, 260, 1900, 1400), width=800),
)
SYMBOLS = ("+", "×", "?", "=", "÷", "9", "7")
HEADLINES = (
    ("BRAIN", "TEST"),
    ("10 GAMES.", "1 SCORE."),
    ("CAN YOU", "FINISH ALL?"),
    ("{n} PUZZLES", "NO CALCULATOR"),
    ("PEN READY?", "SCORE IT."),
    ("HOW SHARP", "IS YOUR BRAIN?"),
    ("MATH. MEMORY.", "CHESS & MORE"),
    ("YOUR BRAIN", "VS 10 GAMES"),
)
PILLS = ("CAN YOU SCORE {t}+?", "GRAB A PEN. KEEP SCORE.", "PAUSE ANYTIME.", "COMMENT YOUR SCORE")


def variant(episode: int) -> tuple[int, int, int, int]:
    """(layout, palette, headline, pill) indices for an episode: each steps by a number coprime with its count."""
    return ((episode * 5 + 2) % len(LAYOUTS), (episode * 3 + 1) % len(PALETTES),
            (episode * 3 + 5) % len(HEADLINES), (episode * 3 + 1) % len(PILLS))


def _slot_for(plan, key: str):
    return next(slot for slot in plan.slots if slot.key == key)


def _place_card(image: Image.Image, slot, box, glow: tuple, edge: tuple, mirror: bool) -> None:
    """A tilted 3D card holding the game's real hook picture; mirrored layouts flip the whole lean."""
    from .braintest import _preview
    board = _preview(slot).convert("RGBA")
    used = box
    if mirror:
        board = ImageOps.mirror(board)
        used = (LOGICAL_W - box[2], box[1], LOGICAL_W - box[0], box[3])
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    _tilted_card(layer, board, used, glow, edge)
    image.alpha_composite(ImageOps.mirror(layer) if mirror else layer)


def _strip(image: Image.Image, plan, y: float) -> None:
    """One row of the video's games as small chips along the bottom, centred and never wider than the frame."""
    from .braintest import GAMES
    keys = list(dict.fromkeys(slot.key for slot in plan.slots))
    draw = ImageDraw.Draw(image)
    font = face(23, False)
    widths = [draw.textlength(GAMES[key].short, font=font) + S(34) for key in keys]
    gap = S(10)
    x = image.width / 2 - (sum(widths) + gap * (len(keys) - 1)) / 2
    for key, width in zip(keys, widths):
        color = rgb(GAMES[key].color)
        draw.rounded_rectangle((x, S(y) - S(23), x + width, S(y) + S(23)), radius=S(23), fill=mix(color, (0, 0, 0), .55) + (255,),
                               outline=color + (255,), width=S(3))
        draw.text((x + width / 2, S(y) - S(1)), GAMES[key].short, font=font, fill=(255, 255, 255), anchor="mm")
        x += width + gap


def _line(image: Image.Image, cx: float, ink_center: float, text: str, font, top: str, bottom: str, depth: int, side, glow) -> None:
    """3D text whose glyphs (not the padded mask) are centred on `ink_center` (logical pixels)."""
    box = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=font, anchor="lt")
    _text3d(image, (S(cx), S(ink_center) - box[1] / 2), text, font, top, bottom, depth, side, glow=glow)


def _ink_height(text: str, font) -> float:
    box = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), text, font=font, anchor="lt")
    return (box[3] - box[1]) / 2  # logical pixels


def render_braintest_thumbnail(plan) -> Image.Image:
    """RGB 1920x1080 in the palette and layout of the plan's episode, featuring one game's real hook frame."""
    layout_i, palette_i, headline_i, pill_i = variant(plan.episode)
    layout, palette = LAYOUTS[layout_i], PALETTES[palette_i]
    _, _, glow = _theme(palette.theme)
    image = _background(palette.theme)
    if layout.mirror:
        image = ImageOps.mirror(image)
    hero = _slot_for(plan, plan.hero_key)
    edge = mix(glow, (255, 255, 255), .3)
    # Far objects first, then the second card, so the hero card and the headline sit in front. They live in the gap
    # between the headline column and the card and in the far corners, never behind the text.
    sprites = [tile3d(symbol, 108, hex_of(mix(rgb(palette.top), rgb(palette.bottom), .5 + .1 * index)), INK) for index, symbol in enumerate(SYMBOLS)]
    gap = layout.cx + layout.width / 2 + 45 if not layout.mirror else layout.cx - layout.width / 2 - 45
    far = 1850 if layout.mirror else 70
    turn = plan.episode % len(SYMBOLS)
    for index, (x, y, angle, blur) in enumerate(((gap, 140, -14, 0.0), (gap, 930, 16, 4.0), (far, 1000 if not layout.strip else 900, -12, 5.0), (far, 130, 14, 5.0))):
        floating(image, sprites[(turn + index * 2) % len(sprites)], (x, y), angle, hex_of(glow), blur, .6 if blur else 1.0)
    if layout.second:
        order = [key for key in dict.fromkeys(slot.key for slot in plan.slots) if key != plan.hero_key]
        _place_card(image, _slot_for(plan, order[(plan.episode + 2) % len(order)]), layout.second, glow, mix(edge, (0, 0, 0), .45), layout.mirror)
    _place_card(image, hero, layout.card, glow, edge, layout.mirror)
    # Headline block: a white first line, a big gradient second line, and the challenge pill, centred as one group.
    line1, line2 = (text.format(n=plan.total_points) for text in HEADLINES[headline_i])
    font1, font2 = fitted(line1, layout.width, 170), fitted(line2, layout.width, 300)
    h1, h2 = _ink_height(line1, font1), _ink_height(line2, font2)
    pill_h, gap1, gap2 = 112, 44, 62
    top = layout.cy - (h1 + gap1 + h2 + gap2 + pill_h) / 2
    side = (mix(glow, (0, 0, 0), .45), mix(glow, (0, 0, 0), .88))
    _line(image, layout.cx, top + h1 / 2, line1, font1, "#FFFFFF", "#D6DBF2", S(18), side, glow)
    _line(image, layout.cx, top + h1 + gap1 + h2 / 2, line2, font2, palette.top, palette.bottom, S(28), side, rgb(palette.bottom))
    pill_y = top + h1 + gap1 + h2 + gap2 + pill_h / 2
    text = PILLS[pill_i].format(t=max(1, round(plan.total_points * .7)))
    pill_font = fitted(text, layout.width - 60, 62)
    pill(image, (S(layout.cx), S(pill_y)), text, pill_font, palette.pill, rgb(INK), pad=48, height=pill_h)
    # The episode sticker sits beside the pill, on the side facing the card: the number that keeps every upload distinct.
    half = (ImageDraw.Draw(image).textlength(text, font=pill_font) / SS) / 2 + 48
    step = -1 if layout.mirror else 1
    sticker_x = layout.cx + step * (half + 128)
    floating(image, _sticker(232, f"#{plan.episode}", "BRAIN TEST", palette.pop, (255, 255, 255)),
             (sticker_x + 23, pill_y + 23 - 10), 10 if layout.mirror else -10, palette.pop)
    if layout.strip:
        _strip(image, plan, 1046)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((S(56), S(46), S(88), S(78)), radius=S(9), fill=rgb(palette.pill))
    draw.text((S(102), S(62)), "Puzzly for You", font=face(34, False), fill=(255, 255, 255), anchor="lm")
    return image.convert("RGB").resize((LOGICAL_W, LOGICAL_H), Image.Resampling.LANCZOS)
