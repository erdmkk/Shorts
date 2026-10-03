"""Mind Mix in the Puzzly for You look: one hard level of Memory, Shade Spot and Puzzle Fit in one video.

A 1.0 s hook shows the three games as glossy cards. Every game then opens with a short title card (the level number, the
game's name, one line saying what to do, and a bar that fills while the viewer gets ready), so nobody wonders whether the
game has started. Then the game plays exactly as in its own video: Memory's hardest level, Shade Spot's hardest level, and
Puzzle Fit with a shorter timer. The shared end card closes the video (`?/3`).
"""
from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image, ImageDraw

from ..config import MIX_GAMES, PUZZLE_FIT_PALETTE as PALETTE, mix_section_length
from ..models import RoundSpec, VideoSpec
from ..puzzles.mind_mix import sub_round
from .easing import ease_in_out, ease_out_back, ease_out_cubic
from .effects import rounded_surface
from .jigsaw import piece_points
from .memory import token_image
from .memory_levels import _card, _gloss, _gradient, _place
from .puzzle_fit import _background, _level_header, _text, active_theme, draw_puzzle_fit_outro
from .text import fitted_font, font

HOOK_TEXT = "MIND MIX."
GAME_NAMES = {"memory_challenge": "MEMORY", "shade_spot": "SHADE SPOT", "puzzle_fit": "PUZZLE FIT"}
INSTRUCTIONS = {"memory_challenge": "Remember the shapes.", "shade_spot": "Find the tile that changed.",
                "puzzle_fit": "Find the 3 missing pieces."}
SHORT_NAMES = {"memory_challenge": "MEMORY", "shade_spot": "SHADE", "puzzle_fit": "FIT"}
COVER_TIME = 0.6


def _rgb(value: str) -> tuple[int, int, int]:
    raw = value.lstrip("#")
    return tuple(int(raw[index:index + 2], 16) for index in (0, 2, 4))


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------- timing

def schedule(spec: VideoSpec) -> list[tuple[float, float]]:
    """(start, duration) of every section: its title card and the game."""
    result, start = [], spec.intro_duration
    for item in spec.rounds:
        length = mix_section_length(item.data)
        result.append((start, length))
        start += length
    return result


# ---------------------------------------------------------------- the game cards (hook, title cards, cover)

def _icon_face(game: str, px: int) -> Image.Image:
    from .shade_spot import CONCEPT
    face = _gradient(px, (43, 54, 128), (22, 28, 70))
    draw = ImageDraw.Draw(face)
    if game == "memory_challenge":  # three numbered covers and one open card
        cell, gap = px * .36, px * .06
        left = (px - (2 * cell + gap)) / 2
        for index in range(4):
            row, column = divmod(index, 2)
            x1, y1 = left + column * (cell + gap), left + row * (cell + gap)
            box = (x1, y1, x1 + cell, y1 + cell)
            if index == 3:
                draw.rounded_rectangle(box, radius=cell * .18, fill=(30, 38, 90, 255), outline=(90, 105, 190, 255), width=max(2, round(px * .012)))
                token = token_image("ring", "#4FC3F7", round(cell * .8))
                face.alpha_composite(token, (round(x1 + cell * .1), round(y1 + cell * .1)))
            else:
                draw.rounded_rectangle(box, radius=cell * .18, fill=(124, 92, 255, 255))
                draw.text((x1 + cell / 2, y1 + cell / 2), str(index + 1), font=font(round(cell * .55)), fill=(255, 255, 255), anchor="mm")
    elif game == "shade_spot":  # a grid of near-identical violets with one pink tile
        tile, gap = px * .245, px * .04
        left = (px - (3 * tile + 2 * gap)) / 2
        for index, color in enumerate(CONCEPT["tiles"]):
            row, column = divmod(index, 3)
            x1, y1 = left + column * (tile + gap), left + row * (tile + gap)
            fill = CONCEPT["odd_color"] if index == CONCEPT["odd"] else color
            draw.rounded_rectangle((x1, y1, x1 + tile, y1 + tile), radius=tile * .2, fill=_rgb(fill) + (255,))
    else:  # one jigsaw piece
        box = (px * .22, px * .22, px * .78, px * .78)
        points = piece_points(box, [1, -1, 1, -1], (box[2] - box[0]) / 4.3)
        big = 3
        mask = Image.new("L", (px * big, px * big), 0)
        ImageDraw.Draw(mask).polygon([(x * big, y * big) for x, y in points], fill=255)
        mask = mask.resize((px, px), Image.Resampling.LANCZOS)
        face.paste(_gradient(px, (255, 176, 110), (122, 66, 152)), (0, 0), mask)
        line = Image.new("L", (px * big, px * big), 0)
        ImageDraw.Draw(line).line([(x * big, y * big) for x, y in points] + [(points[0][0] * big, points[0][1] * big)], fill=255,
                                  width=max(3, round(px * .012 * big)), joint="curve")
        face.paste(Image.new("RGBA", face.size, (11, 16, 32, 255)), (0, 0), line.resize((px, px), Image.Resampling.LANCZOS))
    _gloss(face)
    ImageDraw.Draw(face).rounded_rectangle((1, 1, px - 2, px - 2), radius=round(px * .16), outline=(110, 125, 205, 190), width=max(2, round(px * .012)))
    return face


@lru_cache(maxsize=24)
def icon_sprite(game: str, px: int):
    return _card(px, _icon_face(game, px))


def cover_card(spec: VideoSpec, scale: float = 2.0) -> Image.Image:
    """The cover's card face: the three games as glossy cards in a row, never a real level."""
    width, height = round(1000 * scale), round(470 * scale)
    image = Image.new("RGBA", (width, height), (13, 16, 30, 255))
    px = round(270 * scale)
    for index, game in enumerate(MIX_GAMES):
        sprite, (ax, ay) = icon_sprite(game, px)
        x, y = (180 + index * 320) * scale, 205 * scale
        image.alpha_composite(sprite, (round(x - ax), round(y - ay)))
        ImageDraw.Draw(image).text((x, 410 * scale), SHORT_NAMES[game], font=font(round(36 * scale)), fill=(255, 255, 255), anchor="mm")
    return image


# ---------------------------------------------------------------- hook and title cards

def draw_hook(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    scale = size[0] / 1080
    image = _background(size, 900, active_theme()).copy()
    px = round(270 * scale)
    for index, game in enumerate(MIX_GAMES):
        x, y = 540 + (index - 1) * 310, 940
        _place(image, icon_sprite(game, px), (x, y), scale, zoom=max(.05, ease_out_back((t - index * .08) / .3)))
        _text(image, (x * scale, (y + 205) * scale), SHORT_NAMES[game], font(round(36 * scale)), PALETTE["text_light"],
              _clamp((t - .2 - index * .08) / .2))
    fade = 1 - _clamp((t - (spec.intro_duration - .22)) / .22)
    slam = 1 + .35 * (1 - ease_out_cubic(_clamp(t / .18)))
    _text(image, (540 * scale, 150 * scale), HOOK_TEXT, fitted_font(HOOK_TEXT, round(940 * scale), round(96 * scale)),
          PALETTE["text_light"], fade * _clamp(t / .08 + .3), slam)
    _text(image, (540 * scale, 238 * scale), "3 GAMES · 3 LEVELS · 1 SCORE", font(round(36 * scale)), PALETTE["accent"],
          fade * _clamp((t - .15) / .2))
    return image


def draw_section_intro(spec: VideoSpec, index: int, local: float, size: tuple[int, int]) -> Image.Image:
    """The title card before a game: level, name, what to do, and a bar that fills while the viewer gets ready."""
    scale = size[0] / 1080
    data = spec.rounds[index].data
    game, intro = data["game"], float(data["intro_seconds"])
    image = _background(size, 860, active_theme()).copy()
    _level_header(image, index + 1, spec.round_count, _clamp(local / .2), scale)
    _place(image, icon_sprite(game, round(420 * scale)), (540, 690), scale, zoom=max(.05, ease_out_back(local / .35)))
    name = GAME_NAMES[game]
    face = fitted_font(name, round(860 * scale), round(64 * scale))
    appear = _clamp((local - .15) / .25)
    width = ImageDraw.Draw(image).textlength(name, font=face) + 110 * scale
    height, y = 112 * scale, 1010 * scale
    rounded_surface(image, (540 * scale - width / 2, y - height / 2, 540 * scale + width / 2, y + height / 2), height / 2,
                    _rgb(PALETTE["accent"]) + (round(255 * appear),))
    _text(image, (540 * scale, y - 2 * scale), name, face, PALETTE["background"], appear)
    text = INSTRUCTIONS[game]
    _text(image, (540 * scale, 1135 * scale), text, fitted_font(text, round(900 * scale), round(58 * scale)), PALETTE["text_light"],
          _clamp((local - .25) / .25))
    ready = _clamp((local - .2) / .25)
    _text(image, (540 * scale, 1265 * scale), "GET READY", font(round(34 * scale)), PALETTE["accent"], ready)
    x1, x2, bar_y, bar_h = 290 * scale, 790 * scale, 1325 * scale, 22 * scale
    track = _rgb(PALETTE["surface_edge"]) + (round(255 * ready),)
    rounded_surface(image, (x1, bar_y - bar_h / 2, x2, bar_y + bar_h / 2), bar_h / 2, track)
    fill = _clamp((local - .3) / max(.1, intro - .5))
    if fill > 0:
        rounded_surface(image, (x1, bar_y - bar_h / 2, x1 + max(bar_h, (x2 - x1) * fill), bar_y + bar_h / 2), bar_h / 2,
                        _rgb(PALETTE["accent"]) + (255,))
    fade = _clamp((local - (intro - .15)) / .15)
    if fade > 0:
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (round(200 * fade),))
        image.paste(overlay, (0, 0), overlay)
    return image


# ---------------------------------------------------------------- the games

def _sub_spec(spec: VideoSpec, index: int) -> VideoSpec:
    """The game's own video spec for one section, so its own drawing code renders it. Memory and Shade Spot read the level
    number from their data and the level count from the spec, so their three rounds are copies with the real one at `index`."""
    game = spec.rounds[index].data["game"]
    item = sub_round(spec.rounds[index])
    rounds = (item,) if game == "puzzle_fit" else (item, item, item)
    return VideoSpec(f"{spec.id}-s{index}", game, spec.seed, "hard", "mix", rounds, 0.0, 0.0, 0.0, metadata=spec.metadata)


def draw_section(spec: VideoSpec, index: int, local: float, size: tuple[int, int]) -> Image.Image:
    from ..config import mix_sub_length
    data = spec.rounds[index].data
    game = data["game"]
    local = min(local, mix_sub_length(data) - 1e-3)
    sub = _sub_spec(spec, index)
    if game == "memory_challenge":
        from .memory_levels import draw_level
        return draw_level(sub, index, local, size).convert("RGB")
    if game == "shade_spot":
        from .shade_spot import draw_shade_round
        return draw_shade_round(sub, index, local, size).convert("RGB")
    from .puzzle_fit_v12 import _frame
    image = _frame(sub, local, size).convert("RGB")
    length = mix_sub_length(data)
    fade = max(1 - _clamp(local / .2), _clamp((local - (length - .2)) / .2))
    if fade > 0:
        overlay = Image.new("RGBA", size, _rgb(PALETTE["background"]) + (round(200 * fade),))
        image.paste(overlay, (0, 0), overlay)
    return image


def draw_mix_frame(spec: VideoSpec, t: float, size: tuple[int, int]) -> Image.Image:
    if t < spec.intro_duration:
        return draw_hook(spec, t, size).convert("RGB")
    sections = schedule(spec)
    end = sections[-1][0] + sections[-1][1]
    if t >= end - 1e-9:
        return draw_puzzle_fit_outro(spec, t - end, size, total=len(spec.rounds)).convert("RGB")
    index = max(position for position, (start, _) in enumerate(sections) if t >= start - 1e-9)
    local = t - sections[index][0]
    intro = float(spec.rounds[index].data["intro_seconds"])
    if local < intro:
        return draw_section_intro(spec, index, local, size).convert("RGB")
    return draw_section(spec, index, local - intro, size)


# ---------------------------------------------------------------- sound and music

def _game_times(item: RoundSpec) -> dict:
    """The game's own moments (seconds from the game's start) that the sound and music follow."""
    game = item.data["game"]
    sub = sub_round(item)
    if game == "memory_challenge":
        from .memory_levels import phases, question_times
        return {"phases": phases(sub), "questions": question_times(sub), "cards": len(sub.data["tokens"])}
    if game == "shade_spot":
        from .shade_spot import phases
        return {"phases": phases(sub)}
    from .puzzle_fit_v12 import phases
    return {"phases": phases(sub)}


def sound_cues(spec: VideoSpec) -> list[tuple[float, str, float]]:
    """(time, sound name, pan) for the whole video: a whoosh and a pop for every title card, then the game's own sounds."""
    from ..config import FIT_PLACE, MEMORY_V8_ENTRANCE, mix_sub_length
    cues: list[tuple[float, str, float]] = []
    for index, (start, length) in enumerate(schedule(spec)):
        item = spec.rounds[index]
        game = item.data["game"]
        base = start + float(item.data["intro_seconds"])
        cues += [(start + .05, "transition_whoosh", 0.0), (start + .3, "object_pop", 0.0), (base - .35, "pulse", 0.0)]
        info = _game_times(item)
        times = info["phases"]
        if game == "memory_challenge":
            for card in range(min(info["cards"], 6)):
                cues.append((base + .04 + card * .05, "object_pop", (card % 3 - 1) * .22))
            for remaining in (3.0, 2.0, 1.0):
                if times["memorize_end"] - remaining > MEMORY_V8_ENTRANCE:
                    cues.append((base + times["memorize_end"] - remaining, "pulse", 0.0))
            cues.append((base + times["memorize_end"], "transition_whoosh", 0.0))
            for window in info["questions"]:
                cues += [(base + window["start"] + .05, "object_pop", 0.0), (base + window["think_end"] - 1.0, "pulse", 0.0),
                         (base + window["answer"], "puzzle_snap", 0.0), (base + window["answer"] + .28, "answer_ding", 0.0)]
            cues += [(base + times["questions_end"] + .1, "puzzle_snap", 0.0), (base + times["end"] - .8, "sparkle", 0.0)]
        elif game == "shade_spot":
            cues += [(base + .05, "object_pop", -.3), (base + .15, "object_pop", .3)]
            cues += [(base + times["think_end"] - remaining, "pulse", 0.0) for remaining in (3.0, 2.0, 1.0)]
            cues += [(base + times["think_end"] + .05, "transition_whoosh", 0.0), (base + times["think_end"] + .3, "puzzle_snap", 0.0),
                     (base + times["answer"] + .1, "answer_ding", 0.0), (base + times["answer"] + .22, "sparkle", 0.0)]
        else:
            cues += [(base + .1 + card * .06, "object_pop", (card % 3 - 1) * .3) for card in range(6)]
            cues += [(base + times["think_end"] - remaining, "pulse", 0.0) for remaining in (3.0, 2.0, 1.0)]
            for piece in range(3):
                cues += [(base + times["place"] + piece * FIT_PLACE, "transition_whoosh", 0.0),
                         (base + times["place"] + piece * FIT_PLACE + FIT_PLACE * .8, "puzzle_snap", 0.0)]
            cues += [(base + times["shine"], "answer_ding", 0.0), (base + times["shine"] + .15, "sparkle", 0.0)]
        cues.append((start + length - .15, "transition_whoosh", 0.0))
    return cues


def music_windows(spec: VideoSpec) -> list[dict]:
    """Thinking windows and answer moments for the music: a memorize window and one per question for Memory, one window per
    other game (the title cards carry no tension)."""
    from ..config import MEMORY_V8_ENTRANCE
    windows: list[dict] = []
    for index, (start, _) in enumerate(schedule(spec)):
        item = spec.rounds[index]
        base = start + float(item.data["intro_seconds"])
        info = _game_times(item)
        times = info["phases"]
        if item.data["game"] == "memory_challenge":
            windows.append({"think_start": base + MEMORY_V8_ENTRANCE, "think_end": base + times["memorize_end"], "answer": None})
            windows += [{"think_start": base + window["think_start"], "think_end": base + window["think_end"], "answer": base + window["answer"]}
                        for window in info["questions"]]
        elif item.data["game"] == "shade_spot":
            windows.append({"think_start": base + .5, "think_end": base + times["think_end"], "answer": base + times["answer"]})
        else:
            windows.append({"think_start": base + .5, "think_end": base + times["think_end"], "answer": base + times["shine"]})
    return windows
