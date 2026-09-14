from __future__ import annotations

import logging
import math
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageDraw
from moviepy import AudioArrayClip, VideoClip

from .audio import ensure_sound_effects, timeline_audio
from .branding import draw_brand_mark
from .config import AUDIO_RATE, FPS, LUCKY_PALETTE, RENDER_QUALITIES, ensure_directories, palette_for, thinking_duration
from .models import RoundSpec, VideoSpec
from .puzzles.puzzle_fit import visual_state
from .validation import validate_spec
from .visuals.backgrounds import create_background
from .visuals.jigsaw import piece_points
from .visuals.paths import draw_path_puzzle
from .visuals.memory import draw_memory_intro, draw_memory_round
from .visuals.flash_count import draw_flash_intro, draw_flash_round
from .visuals.lucky_pick import draw_lucky_game, draw_lucky_intro
from .visuals.hidden_motion import draw_hidden_motion
from .visuals.easing import ease_in_out, ease_out_back, ease_out_cubic
from .visuals.effects import draw_progress_bar, draw_sparkles, rounded_card, rounded_surface
from .visuals.layout import scale_point
from .visuals.text import fitted_font, font

LOGGER = logging.getLogger(__name__)


@lru_cache(maxsize=24)
def _tutorial_round(kind: str, seed: int, excluded: tuple[str, ...]) -> RoundSpec:
    from .puzzles import puzzle_fit, find_the_exit, line_follow
    factory = {"puzzle_fit": puzzle_fit.generate, "find_the_exit": find_the_exit.generate, "line_follow": line_follow.generate}[kind]
    for offset in range(100):
        for item in factory(-seed - 9000 - offset, "easy", round_count=3).rounds:
            if item.fingerprint() not in excluded:
                return item
    raise ValueError("Could not create a distinct tutorial puzzle")


def _scaled(value: float, size: tuple[int, int]) -> int:
    return max(1, round(value * size[0] / 1080))


def _bounds(values: tuple[float, float, float, float], size: tuple[int, int]) -> tuple[int, int, int, int]:
    left, top = scale_point((values[0], values[1]), size)
    right, bottom = scale_point((values[2], values[3]), size)
    return left, top, right, bottom


def _palette(spec: VideoSpec, round_index: int = 0) -> dict[str, str]:
    if spec.puzzle_type == "lucky_pick":
        return dict(LUCKY_PALETTE)
    return palette_for(spec.difficulty, spec.seed + round_index)


def _round_indicator(draw: ImageDraw.ImageDraw, size: tuple[int, int], current: int, total: int, palette: dict[str, str]) -> None:
    radius, gap = _scaled(10, size), _scaled(32, size)
    center_x, y = scale_point((540, 205), size)
    start = center_x - gap * (total - 1) / 2
    for index in range(total):
        x = round(start + gap * index)
        fill = palette["primary"] if index <= current else palette["surface"]
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill, outline=palette["outline"], width=_scaled(3, size))


def _scaled_card(image: Image.Image, logical: tuple[float, float, float, float], palette: dict[str, str], scale: float = 1.0) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = logical
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    values = (cx + (x1 - cx) * scale, cy + (y1 - cy) * scale, cx + (x2 - cx) * scale, cy + (y2 - cy) * scale)
    bounds = _bounds(values, image.size)
    rounded_card(image, bounds, _scaled(52, image.size), palette["surface"], palette["outline"], _scaled(6, image.size))
    return bounds


def _draw_puzzle_fit_intro(image: Image.Image, t: float, palette: dict[str, str]) -> None:
    """Draw a fixed concept motif that cannot disclose a generated round."""
    draw = ImageDraw.Draw(image)
    size = image.size
    draw.text(scale_point((540, 205), size), "PUZZLE FIT", font=font(_scaled(68, size)),
              fill=palette["text_dark"], anchor="mm")
    amount = max(.12, ease_out_back(t / .55))
    cell = 210
    left, top = 330, 365
    pieces = (
        ((left, top, left + cell, top + cell), [0, 1, 1, 0], palette["secondary"]),
        ((left + cell, top, left + 2 * cell, top + cell), [0, 0, 1, -1], palette["accent"]),
        ((left, top + cell, left + cell, top + 2 * cell), [-1, 1, 0, 0], palette["coral"]),
    )
    for logical, edges, color in pieces:
        x1, y1, x2, y2 = logical
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        half = cell * amount / 2
        _jigsaw_piece(draw, _bounds((cx-half, cy-half, cx+half, cy+half), size), edges,
                      color, palette["outline"], _scaled(5, size))
    hole = (left + cell, top + cell, left + 2 * cell, top + 2 * cell)
    hole_edges = [-1, 0, 0, -1]
    _dashed_hole(draw, _bounds(hole, size), hole_edges, palette["background"],
                 palette["primary"], _scaled(7, size))
    candidate = _bounds((448, 865, 632, 1049), size)
    shadow = tuple(value + _scaled(7, size) for value in candidate)
    _jigsaw_piece(draw, shadow, hole_edges, palette["background_2"], palette["background_2"], _scaled(3, size))
    _jigsaw_piece(draw, candidate, hole_edges, palette["success"], palette["outline"], _scaled(5, size))


def _intro_frame(spec: VideoSpec, t: float, size: tuple[int, int], base: Image.Image) -> Image.Image:
    image = base.copy()
    palette = _palette(spec)
    progress = ease_out_back(t / 0.65)
    draw = ImageDraw.Draw(image)
    if spec.puzzle_type == "quick_math":
        draw.text(scale_point((540, 220), size), "QUICK MATH", font=font(_scaled(68, size)),
                  fill=palette["text_dark"], anchor="mm")
        for index, symbol in enumerate(("+", "−", "×", "÷")):
            x = 285 + index * 170
            amount = ease_out_back((t - 0.12 - index * 0.06) / 0.45)
            half = 62 * max(0.12, amount)
            rounded_card(image, _bounds((x - half, 405 - half, x + half, 405 + half), size), _scaled(22, size), palette["surface"], palette["outline"], _scaled(4, size))
            draw.text(scale_point((x, 405), size), symbol, font=font(_scaled(62, size)), fill=palette["secondary"], anchor="mm")
    elif spec.puzzle_type == "missing_number":
        for index, label in enumerate(("2", "?", "4")):
            x = 350 + index * 190
            rounded_card(image, _bounds((x - 68, 335, x + 68, 475), size), _scaled(30, size), palette["accent"] if label == "?" else palette["surface"], palette["outline"], _scaled(4, size))
            draw.text(scale_point((x, 405), size), label, font=font(_scaled(62, size)), fill=palette["text_dark"], anchor="mm")
    elif spec.puzzle_type in ("find_the_exit", "line_follow"):
        tutorial = Image.new("RGB", size, palette["background"])
        from .config import thinking_duration
        moment = 0.35 + thinking_duration(spec.puzzle_type, spec.difficulty) + max(0, t - 0.2) * 1.4
        item = _tutorial_round(spec.puzzle_type, spec.seed, tuple(r.fingerprint() for r in spec.rounds))
        draw_path_puzzle(tutorial, item, moment, spec.difficulty, palette)
        crop = tutorial.crop(_bounds((100, 280, 980, 1480), size))
        crop = crop.resize((_scaled(550, size), _scaled(750, size)), Image.Resampling.LANCZOS)
        image.paste(crop, scale_point((265, 240), size))
    elif spec.puzzle_type == "memory_challenge":
        draw_memory_intro(image, t, palette)
    elif spec.puzzle_type == "flash_count":
        draw_flash_intro(image, spec, t, palette)
    elif spec.puzzle_type == "lucky_pick":
        draw_lucky_intro(image, spec, t, palette)
    elif spec.puzzle_type == "puzzle_fit":
        _draw_puzzle_fit_intro(image, t, palette)
    if spec.puzzle_type in ("quick_math", "missing_number"):
        diameter = _scaled(210 * max(0.15, progress), size)
        draw_brand_mark(image, scale_point((540, 880), size), diameter, palette,
                        symbol=None if spec.puzzle_type == "quick_math" else "?")
    show_badge = spec.puzzle_type != "memory_challenge" or t >= 1.08
    if show_badge and spec.puzzle_type != "lucky_pick":
        badge_amount = ease_out_back((t - 1.08) / 0.22) if spec.puzzle_type == "memory_challenge" else 1.0
        half_w, half_h = 150 * max(.08, badge_amount), 50 * max(.08, badge_amount)
        badge = _bounds((540-half_w, 1130-half_h, 540+half_w, 1130+half_h), size)
        rounded_card(image, badge, _scaled(38, size), palette["primary"], palette["outline"], _scaled(4, size))
        if badge_amount > .55:
            draw.text(scale_point((540, 1130), size), spec.difficulty.upper(), font=font(_scaled(48, size)), fill=palette["text_light"], anchor="mm")
    return image


def _equation_frame(image: Image.Image, round_spec: RoundSpec, local: float, spec: VideoSpec, palette: dict[str, str]) -> None:
    entrance = ease_out_back(local / 0.35)
    card_scale = max(0.82, entrance)
    _scaled_card(image, (100, 500, 980, 1160), palette, card_scale)
    draw = ImageDraw.Draw(image)
    data = round_spec.data
    revealed = local >= 4.35
    position = data.get("unknown_position", "result")
    values = {"left": data["a"], "right": data["b"], "result": data.get("result", round_spec.answer)}
    parts = [str(values["left"]), f'  {data["symbol"]}  ', str(values["right"]), "  =  ", str(values["result"])]
    answer_index = {"left": 0, "right": 2, "result": 4}[position]
    parts[answer_index] = str(round_spec.answer) if revealed else "?"
    prefix, answer, suffix = "".join(parts[:answer_index]), parts[answer_index], "".join(parts[answer_index + 1:])
    text_size = _scaled(122, image.size)
    face = fitted_font(prefix + answer + suffix, _scaled(760, image.size), text_size, _scaled(62, image.size))
    prefix_width = draw.textlength(prefix, font=face)
    answer_width = draw.textlength(answer, font=face)
    suffix_width = draw.textlength(suffix, font=face)
    total_width = prefix_width + answer_width + suffix_width
    x = image.width / 2 - total_width / 2
    y = scale_point((0, 795), image.size)[1]
    draw.text((x, y), prefix, font=face, fill=palette["text_dark"], anchor="lm")
    bounce = math.sin(min(1, max(0, (local - 4.35) / 0.45)) * math.pi) * _scaled(16, image.size) if revealed else 0
    draw.text((x + prefix_width, y - bounce), answer, font=face, fill=palette["coral"] if revealed else palette["secondary"], anchor="lm")
    draw.text((x + prefix_width + answer_width, y), suffix, font=face, fill=palette["text_dark"], anchor="lm")
    if 0.35 <= local < 4.35:
        remaining = 1 - (local - 0.35) / 4.0
        draw_progress_bar(image, _bounds((220, 1030, 860, 1052), image.size), remaining, palette["background_2"], palette["primary"])
    if local >= 4.35:
        draw_sparkles(draw, image.size, palette["accent"], (local - 4.35) / 0.6)


def _sequence_frame(image: Image.Image, round_spec: RoundSpec, local: float, palette: dict[str, str]) -> None:
    entrance = ease_out_back(local / 0.4)
    _scaled_card(image, (70, 510, 1010, 1160), palette, max(0.84, entrance))
    draw = ImageDraw.Draw(image)
    data = round_spec.data
    revealed = local >= 4.35
    labels = [str(value) for value in data["sequence"]]
    labels[data["hidden_index"]] = str(round_spec.answer) if revealed else "?"
    chip_width, gap = _scaled(150, image.size), _scaled(20, image.size)
    widths = [chip_width] * 5
    total_width = chip_width * 5 + gap * 4
    cursor = image.width / 2 - total_width / 2
    y = scale_point((0, 815), image.size)[1]
    for index, (label, width) in enumerate(zip(labels, widths)):
        cx = cursor + width / 2
        chip_height = _scaled(150, image.size)
        fill = palette["accent"] if index == data["hidden_index"] else palette["background"]
        rounded_surface(image, (cx - width / 2, y - chip_height / 2, cx + width / 2, y + chip_height / 2), _scaled(38, image.size), fill, palette["outline"], _scaled(5, image.size))
        face = fitted_font(label, int(width - _scaled(24, image.size)), _scaled(96, image.size), _scaled(56, image.size))
        bounce = math.sin(min(1, max(0, (local - 4.35) / 0.5)) * math.pi) * _scaled(12, image.size) if revealed and index == data["hidden_index"] else 0
        draw.text((cx, y - bounce), label, font=face, fill=palette["text_dark"], anchor="mm")
        cursor += width + gap
    if 0.35 <= local < 4.35:
        remaining = 1 - (local - 0.35) / 4.0
        draw_progress_bar(image, _bounds((220, 1040, 860, 1062), image.size), remaining, palette["background_2"], palette["primary"])
    if local >= 4.35:
        draw_sparkles(draw, image.size, palette["success"], (local - 4.35) / 0.7)


def _jigsaw_points(bounds: tuple[int, int, int, int], edges: list[int], tab: int) -> list[tuple[float, float]]:
    return piece_points(bounds, edges, tab)


def _jigsaw_piece(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], edges: list[int], fill: str, outline: str, width: int) -> None:
    points = _jigsaw_points(bounds, edges, max(8, (bounds[2] - bounds[0]) // 7))
    draw.polygon(points, fill=fill)
    draw.line(points + [points[0]], fill=outline, width=width, joint="curve")


def _lerp_bounds(start: tuple[int, int, int, int], end: tuple[int, int, int, int], progress: float) -> tuple[int, int, int, int]:
    return tuple(round(a + (b - a) * progress) for a, b in zip(start, end))  # type: ignore[return-value]


def _dashed_hole(draw: ImageDraw.ImageDraw, bounds: tuple[int, int, int, int], edges: list[int], fill: str, outline: str, width: int) -> None:
    points = _jigsaw_points(bounds, edges, max(8, (bounds[2] - bounds[0]) // 7))
    draw.polygon(points, fill=fill)
    phase, dash = 0.0, max(8, width * 3)
    stroke = []
    for start, end in zip(points, points[1:] + points[:1]):
        distance = math.dist(start, end)
        steps = max(1, math.ceil(distance / max(1, width / 2)))
        for step in range(steps):
            a, b = step / steps, (step + 1) / steps
            if int((phase + distance * a) / dash) % 2 == 0:
                first = (start[0] + (end[0] - start[0]) * a, start[1] + (end[1] - start[1]) * a)
                last = (start[0] + (end[0] - start[0]) * b, start[1] + (end[1] - start[1]) * b)
                stroke.extend((first, last))
            elif stroke:
                draw.line(stroke, fill=outline, width=width, joint="curve")
                stroke = []
        phase += distance
    if stroke:
        draw.line(stroke, fill=outline, width=width, joint="curve")


def _fit_frame(image: Image.Image, round_spec: RoundSpec, local: float, palette: dict[str, str], difficulty: str) -> None:
    draw = ImageDraw.Draw(image)
    data, size = round_spec.data, image.size
    rounded_card(image, _bounds((105, 280, 975, 1120), size), _scaled(70, size), palette["surface"], palette["outline"], _scaled(7, size))
    rows, columns = data["rows"], data["columns"]
    cell = min(660 / columns, 660 / rows)
    left, top = 540 - columns * cell / 2, 700 - rows * cell / 2
    slots = [_bounds((left + column * cell, top + row * cell, left + (column + 1) * cell, top + (row + 1) * cell), size)
             for row in range(rows) for column in range(columns)]
    hole = slots[data["hole_slot"]]
    color = palette[data["piece_colors"][data["hole_slot"]]]
    for index, bounds in enumerate(slots):
        if index != data["hole_slot"]:
            _jigsaw_piece(draw, bounds, data["piece_edges"][index], palette[data["piece_colors"][index]], palette["outline"], _scaled(5, size))
    state = visual_state(local, difficulty)
    think_end = 0.35 + thinking_duration("puzzle_fit", difficulty)
    move_start, solved_at = think_end + 0.20, think_end + 0.90
    _dashed_hole(draw, hole, data["hole_edges"], palette["background"], palette["primary"], _scaled(7, size))
    candidates = []
    for index, logical in enumerate(data["candidate_cards"]):
        x1, y1, x2, y2 = logical
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        lift = 14 * ease_out_cubic((local - think_end) / 0.20) if state == "highlight" and index == data["correct_index"] else 0
        bounds = _bounds((cx - 92, cy - 92 - lift, cx + 92, cy + 92 - lift), size)
        candidates.append(bounds)
        if state in ("moving", "solved") and index == data["correct_index"]:
            continue
        shadow = tuple(value + _scaled(7, size) for value in bounds)
        _jigsaw_piece(draw, shadow, data["candidates"][index], palette["background_2"], palette["background_2"], _scaled(3, size))
        outline = palette["success"] if state == "highlight" and index == data["correct_index"] else palette["outline"]
        _jigsaw_piece(draw, bounds, data["candidates"][index], color, outline, _scaled(5, size))
    if state == "moving":
        source = candidates[data["correct_index"]]
        source = (source[0], source[1] - _scaled(14, size), source[2], source[3] - _scaled(14, size))
        _jigsaw_piece(draw, _lerp_bounds(source, hole, ease_in_out((local - move_start) / 0.70)), data["hole_edges"], color, palette["outline"], _scaled(5, size))
    elif state == "solved":
        _jigsaw_piece(draw, hole, data["hole_edges"], color, palette["outline"], _scaled(5, size))
        draw_sparkles(draw, size, palette["success"], (local - solved_at) / 0.55)
    if 0.35 <= local < think_end:
        progress_y = 1710 if difficulty == "hard" else 1550
        draw_progress_bar(image, _bounds((245, progress_y, 835, progress_y + 22), size),
                          1 - (local - 0.35) / thinking_duration("puzzle_fit", difficulty),
                          palette["background_2"], palette["primary"])


def render_frame(spec: VideoSpec, t: float, size: tuple[int, int], background: Image.Image | None = None) -> Image.Image:
    t = max(0.0, min(spec.total_duration - 1 / FPS, t))
    if spec.puzzle_type == "hidden_motion_hunt":
        return draw_hidden_motion(spec.rounds[0], t, size)
    if t < spec.intro_duration:
        base = background or create_background(size, _palette(spec), 0 if spec.puzzle_type == "lucky_pick" else spec.seed % 3)
        return _intro_frame(spec, t, size, base)
    rounds_end = spec.intro_duration + spec.round_count * spec.round_duration
    if t >= rounds_end:
        palette = _palette(spec)
        image = (background or create_background(size, palette, 0 if spec.puzzle_type == "lucky_pick" else spec.seed % 3)).copy()
        progress = ease_out_back((t - rounds_end) / spec.outro_duration)
        draw_brand_mark(image, scale_point((540, 860), size), _scaled(270 * max(0.2, progress), size), palette)
        draw_sparkles(ImageDraw.Draw(image), size, palette["accent"], progress)
        return image
    elapsed = t - spec.intro_duration
    round_index = min(spec.round_count - 1, int(elapsed / spec.round_duration))
    local = elapsed - round_index * spec.round_duration
    palette = _palette(spec, round_index)
    image = create_background(size, palette, 0 if spec.puzzle_type == "lucky_pick" else (spec.seed + round_index) % 3)
    draw = ImageDraw.Draw(image)
    if spec.puzzle_type not in ("memory_challenge", "lucky_pick"):
        _round_indicator(draw, size, round_index, spec.round_count, palette)
    round_spec = spec.rounds[round_index]
    if spec.puzzle_type == "quick_math":
        _equation_frame(image, round_spec, local, spec, palette)
    elif spec.puzzle_type == "missing_number":
        _sequence_frame(image, round_spec, local, palette)
    elif spec.puzzle_type == "puzzle_fit":
        _fit_frame(image, round_spec, local, palette, spec.difficulty)
    elif spec.puzzle_type == "memory_challenge":
        draw_memory_round(image, round_spec, local, palette)
    elif spec.puzzle_type == "flash_count":
        draw_flash_round(image, round_spec, local, palette)
    elif spec.puzzle_type == "lucky_pick":
        draw_lucky_game(image, round_spec, local, palette)
    else:
        draw_path_puzzle(image, round_spec, local, spec.difficulty, palette)
    transition_start = spec.round_duration - (0.2 if spec.puzzle_type == "puzzle_fit" else 0.4)
    if local > transition_start and round_index < spec.round_count - 1:
        alpha = int(90 * ease_in_out((local - transition_start) / 0.4))
        overlay = Image.new("RGBA", size, palette["background"] + f"{alpha:02x}")
        image.paste(overlay, (0, 0), overlay)
    return image


def render_quality_frame(spec: VideoSpec, t: float, quality: str) -> Image.Image:
    if quality not in RENDER_QUALITIES:
        raise ValueError("quality must be 'draft' or 'final'")
    settings = RENDER_QUALITIES[quality]
    image = render_frame(spec, t, settings.internal_size)
    if settings.supersampling > 1:
        image = image.resize(settings.output_size, Image.Resampling.LANCZOS)
    return image


def render_cover(spec: VideoSpec) -> Image.Image:
    """Render a stable full-quality hero frame directly from the puzzle spec."""
    settings = RENDER_QUALITIES["final"]
    if spec.puzzle_type == "hidden_motion_hunt":
        return render_frame(spec, 0.0, settings.internal_size).resize(settings.output_size, Image.Resampling.LANCZOS)
    if spec.puzzle_type in ("quick_math", "puzzle_fit", "memory_challenge", "flash_count", "lucky_pick"):
        image = render_frame(spec, min(1.25, spec.intro_duration - 1 / FPS), settings.internal_size)
    else:
        image = render_frame(spec, spec.intro_duration + 0.34, settings.internal_size)
        palette = _palette(spec)
        draw = ImageDraw.Draw(image)
        badge_center_y = 1760 if spec.puzzle_type == "puzzle_fit" and spec.difficulty == "hard" else 1620
        badge = _bounds((390, badge_center_y - 50, 690, badge_center_y + 50), image.size)
        rounded_card(image, badge, _scaled(38, image.size), palette["primary"], palette["outline"], _scaled(4, image.size))
        draw.text(scale_point((540, badge_center_y), image.size), spec.difficulty.upper(),
                  font=font(_scaled(48, image.size)), fill=palette["text_light"], anchor="mm")
    return image.resize(settings.output_size, Image.Resampling.LANCZOS)


def save_cover(spec: VideoSpec, output_path: Path, quality: int = 94) -> None:
    validate_spec(spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    render_cover(spec).convert("RGB").save(output_path, format="JPEG", quality=quality, optimize=True, subsampling=0)


def render_video(spec: VideoSpec, output_path: Path, quality: str = "final", logger: str | None = "bar") -> float:
    validate_spec(spec)
    if quality not in RENDER_QUALITIES:
        raise ValueError("quality must be 'draft' or 'final'")
    ensure_directories()
    ensure_sound_effects()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    settings = RENDER_QUALITIES[quality]
    output_size, internal_size = settings.output_size, settings.internal_size
    frame_cache: OrderedDict[int, np.ndarray] = OrderedDict()

    def frame_at(t: float) -> np.ndarray:
        visual_fps = settings.internal_visual_fps
        key = min(math.floor(t * visual_fps), math.ceil(spec.total_duration * visual_fps) - 1)
        if key not in frame_cache:
            frame_cache[key] = np.asarray(render_quality_frame(spec, key / visual_fps, quality))
            while len(frame_cache) > 3:
                frame_cache.popitem(last=False)
        else:
            frame_cache.move_to_end(key)
        return frame_cache[key]

    started = time.perf_counter()
    video = VideoClip(frame_function=frame_at, duration=spec.total_duration).with_fps(FPS)
    audio = AudioArrayClip(timeline_audio(spec), fps=AUDIO_RATE)
    final = video.with_audio(audio)
    try:
        final.write_videofile(str(output_path), fps=FPS, codec="libx264", audio_codec="aac", audio_fps=AUDIO_RATE,
            pixel_format="yuv420p", preset=settings.encoder_preset,
            ffmpeg_params=["-crf", str(settings.crf), "-movflags", "+faststart", "-ar", str(AUDIO_RATE)], logger=logger)
    finally:
        final.close(); audio.close(); video.close()
    elapsed = time.perf_counter() - started
    LOGGER.info("Rendered %s duration=%.2fs in %.2fs", output_path, spec.total_duration, elapsed)
    return elapsed
