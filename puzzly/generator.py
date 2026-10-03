from __future__ import annotations

from collections.abc import Callable
import csv
from dataclasses import dataclass, replace
from datetime import datetime
import json
import logging
from pathlib import Path
import random
import secrets
import shutil
from typing import Any
from uuid import uuid4

from .config import (BOUNCE_CTA_DURATION, DATA_DIR, HIDDEN_MOTION_DURATION,
                     INTRO_DURATION, LUCKY_INTRO_DURATION, OUTRO_DURATION,
                     PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION,
                     OUTPUT_DIR, ensure_directories, fresh_theme_for)
from .history import GenerationRecord, HistoryStore
from .metadata import write_manifest, youtube_metadata
from .models import RoundSpec, VideoSpec
from .puzzles import bounce_arena, cube_count, flash_count, hidden_motion_hunt, lucky_pick, missing_number, puzzle_fit, quick_math, find_the_exit, line_follow, memory_challenge
from .registry import ACTIVE_PUZZLE_TYPES, MIXED_PUZZLE_TYPES, SUPPORTED_PUZZLE_TYPES
from .memory_colors import COLOR_LEVEL_THEMES
from .renderer import render_video, save_cover
from .validation import validate_spec

LOGGER = logging.getLogger(__name__)
PUZZLE_TYPES = ACTIVE_PUZZLE_TYPES
THEMES = {
    "quick_math": ("numbers",),
    "missing_number": ("numbers",),
    "puzzle_fit": ("boards",),
    "find_the_exit": ("paths",),
    "line_follow": ("lines",),
    "memory_challenge": ("memory",),
    "flash_count": ("number_flash",),
    "lucky_pick": ("lucky_pick",),
    "hidden_motion_hunt": ("uploaded_background",),
    "bounce_arena": ("bounce_arena",),
    "cube_count": ("isometric_cubes",),
    "chess_mate": ("lichess",),
    "matchstick": ("matchsticks",),
    "cup_shuffle": ("cups",),
    "shade_spot": ("shades",),
    "mind_mix": ("mix",),
    "laser_maze": ("lasers",),
}


@dataclass(frozen=True)
class DraftPreview:
    spec: VideoSpec
    video_path: Path
    cover_path: Path


def generate_spec(
    puzzle_type: str, seed: int, difficulty: str = "easy", theme: str = "auto",
    operation: str = "mixed", challenges: int | None = None, background_bytes: bytes | None = None,
    placement_mode: str = "auto", manual_objects: list[dict] | None = None,
    background: str | None = None, palette: str | None = None, min_rating: int | None = None,
    maze_shape: str | None = None,
) -> VideoSpec:
    """`background` (a DARK_THEMES tone) and `palette` (an object palette) are the creator's colour choices; they are
    stored in the spec's metadata, outside the fingerprint (see puzzly.palette). None keeps the defaults.
    `min_rating` (Chess: Mate in 1 only) draws from every puzzle rated at least that instead of the difficulty band.
    `maze_shape` (Find the Exit Hard only): `rect` (default), `circle`, or `mixed`."""
    if puzzle_type != "hidden_motion_hunt" and background in (None, "random"):
        background = fresh_theme_for(puzzle_type, seed)  # stored below, so this video keeps its tone whatever the pool becomes
    spec = _generate_spec(puzzle_type, seed, difficulty, theme, operation, challenges, background_bytes,
                          placement_mode, manual_objects, background, min_rating, maze_shape)
    colours = {key: value for key, value in (("background", background), ("palette", palette))
               if value and value not in ("random", "classic")}
    return replace(spec, metadata={**spec.metadata, **colours}) if colours else spec


def _generate_spec(
    puzzle_type: str, seed: int, difficulty: str, theme: str, operation: str, challenges: int | None,
    background_bytes: bytes | None, placement_mode: str, manual_objects: list[dict] | None, background: str | None,
    min_rating: int | None = None, maze_shape: str | None = None,
) -> VideoSpec:
    if puzzle_type not in SUPPORTED_PUZZLE_TYPES:
        raise ValueError(f"unsupported puzzle type: {puzzle_type}")
    if puzzle_type == "hidden_motion_hunt":
        background_hash = hidden_motion_hunt.prepare_background(background_bytes or b"")
        spec = hidden_motion_hunt.generate(seed, background_hash, placement_mode, manual_objects)
        validate_spec(spec)
        LOGGER.info("Generated seed=%s type=%s fingerprint=%s", seed, puzzle_type, spec.fingerprint())
        return spec
    rng = random.Random(f"{seed}:{puzzle_type}:{difficulty}")
    chosen_theme = rng.choice(THEMES[puzzle_type]) if theme == "auto" or theme not in THEMES[puzzle_type] else theme
    if puzzle_type == "memory_challenge" and theme in COLOR_LEVEL_THEMES:
        chosen_theme = theme  # colour similarity level picked in the UI
    factories = {
        "missing_number": missing_number.generate,
        "puzzle_fit": puzzle_fit.generate,
        "find_the_exit": find_the_exit.generate,
        "line_follow": line_follow.generate,
        "memory_challenge": memory_challenge.generate,
        "flash_count": flash_count.generate,
        "cube_count": cube_count.generate,
        "lucky_pick": lucky_pick.generate,
        "bounce_arena": bounce_arena.generate,
    }
    if puzzle_type == "quick_math":
        spec = quick_math.generate(seed, difficulty, operation, challenges)
    elif puzzle_type == "lucky_pick":
        spec = lucky_pick.generate(seed)
    elif puzzle_type == "bounce_arena":
        spec = bounce_arena.generate(seed)
    elif puzzle_type == "cup_shuffle":
        from .puzzles import cup_shuffle
        spec = cup_shuffle.generate(seed, difficulty)  # always Hard, always 3 levels
    elif puzzle_type == "laser_maze":
        from .puzzles import laser_maze
        spec = laser_maze.generate(seed, difficulty, round_count=challenges)  # always Hard, 3-5 levels
    elif puzzle_type == "mind_mix":
        from .puzzles import mind_mix
        spec = mind_mix.generate(seed)  # always Hard: one hard level of Memory, Shade Spot and Puzzle Fit
    elif puzzle_type == "shade_spot":
        from .puzzles import shade_spot
        spec = shade_spot.generate(seed, difficulty, round_count=challenges)  # always Hard, 3-5 levels
    elif puzzle_type == "matchstick":
        from .puzzles import matchstick
        spec = matchstick.generate(seed, difficulty)
    elif puzzle_type == "chess_mate":
        from .puzzles import chess_mate
        spec = chess_mate.generate(seed, difficulty, min_rating)
    elif puzzle_type == "find_the_exit" and difficulty == "hard":  # rectangles, circles, or both
        spec = find_the_exit.generate(seed, difficulty, chosen_theme, challenges, shape=maze_shape or "rect")
    elif puzzle_type == "cube_count":  # its cube colours avoid the video's background tone
        spec = cube_count.generate(seed, difficulty, chosen_theme, challenges,
                                   background=background if background not in (None, "random") else None)
    else:
        spec = factories[puzzle_type](seed, difficulty, chosen_theme, None if puzzle_type == "memory_challenge" else challenges)
    validate_spec(spec)
    LOGGER.info("Generated seed=%s type=%s fingerprint=%s", seed, puzzle_type, spec.fingerprint())
    return spec


def mixed_types(count: int, rng: random.Random) -> list[str]:
    cycle = list(MIXED_PUZZLE_TYPES)
    rng.shuffle(cycle)
    result = [cycle[index % len(cycle)] for index in range(count)]
    rng.shuffle(result)
    return result


def output_stem(sequence_no: int, spec: VideoSpec) -> str:
    no_difficulty = ("lucky_pick", "hidden_motion_hunt", "bounce_arena")
    return (f"PZ_{sequence_no:04d}_{spec.puzzle_type}" if spec.puzzle_type in no_difficulty
            else f"PZ_{sequence_no:04d}_{spec.puzzle_type}_{spec.difficulty}")


def generate_unique_specs(
    count: int, puzzle_type: str = "mixed", difficulty: str = "easy", theme: str = "auto",
    base_seed: int | None = None, history: HistoryStore | None = None, retry_limit: int = 100,
    operation: str = "mixed", challenges: int | None = None, background_bytes: bytes | None = None,
    placement_mode: str = "auto", manual_objects: list[dict] | None = None,
    background: str | None = None, palette: str | None = None, min_rating: int | None = None,
    maze_shape: str | None = None,
) -> list[VideoSpec]:
    if count < 1:
        raise ValueError("count must be positive")
    if puzzle_type != "mixed" and puzzle_type not in ACTIVE_PUZZLE_TYPES:
        raise ValueError(f"puzzle type is not active for production: {puzzle_type}")
    history = history or HistoryStore()
    existing = history.load()
    rng = random.Random(base_seed) if base_seed is not None else random.Random(secrets.randbits(64))
    types = mixed_types(count, rng) if puzzle_type == "mixed" else [puzzle_type] * count
    specs: list[VideoSpec] = []
    selected: set[str] = set()
    for selected_type in types:
        for attempt in range(retry_limit):
            seed = rng.randrange(0, 2**31)
            spec = generate_spec(selected_type, seed, difficulty, theme, operation, challenges, background_bytes,
                                 placement_mode, manual_objects, background, palette, min_rating, maze_shape)
            fingerprint = spec.fingerprint()
            if fingerprint not in existing and fingerprint not in selected:
                specs.append(spec)
                selected.add(fingerprint)
                break
        else:
            raise RuntimeError(f"Could not create a unique {selected_type} puzzle after {retry_limit} tries")
    return specs


def _manifest_row(
    spec: VideoSpec, record: GenerationRecord, elapsed: float, quality: str,
) -> dict[str, Any]:
    meta = youtube_metadata(spec)
    memory_data = spec.rounds[0].data if spec.puzzle_type == "memory_challenge" else {}
    memory_levels = memory_data.get("layout") == "levels_v8"  # three levels: every level's tokens and questions are recorded
    memory_tokens = ([token for item in spec.rounds for token in item.data["tokens"]] if memory_levels
                     else memory_data.get("tokens", []))
    lucky_data = spec.rounds[0].data if spec.puzzle_type == "lucky_pick" else {}
    hidden_data = spec.rounds[0].data if spec.puzzle_type == "hidden_motion_hunt" else {}
    bounce_data = spec.rounds[0].data if spec.puzzle_type == "bounce_arena" else {}
    hidden_objects = hidden_data.get("objects", [])
    return {
        "filename": record.output_filename, "cover_filename": record.cover_filename,
        "sequence_no": record.sequence_no, "video_id": spec.id, "puzzle_type": spec.puzzle_type,
        "theme": spec.theme, "difficulty": spec.difficulty or "", "seed": spec.seed,
        "quality": quality,
        "question": json.dumps([round_spec.data for round_spec in spec.rounds], ensure_ascii=False),
        "answer": json.dumps([round_spec.answer for round_spec in spec.rounds], ensure_ascii=False), **meta,
        "round_count": spec.round_count, "duration_seconds": spec.total_duration,
        "token_shapes": json.dumps([token.get("shape") for token in memory_tokens], ensure_ascii=False),
        "color_ids": json.dumps([token.get("color_id") for token in memory_tokens], ensure_ascii=False),
        "token_positions": json.dumps([token.get("position") for token in memory_tokens], ensure_ascii=False),
        "question_order": json.dumps([item.data["questions"] for item in spec.rounds] if memory_levels
                                     else memory_data.get("question_order", []), ensure_ascii=False),
        "final_auto_reveal": memory_data.get("final_position", ""),
        "shape_id": lucky_data.get("shape_id", ""),
        "color_id": "",
        "displayed_counts": json.dumps([item.data.get("number") if item.kind == "flash_count" else item.data.get("total")
                                        for item in spec.rounds if item.kind in ("flash_count", "cube_count")]),
        "flash_positions": "",
        "circle_count": lucky_data.get("target_count", ""),
        "lucky_color_ids": json.dumps([target.get("color_id") for target in lucky_data.get("targets", [])]),
        "lucky_positions": json.dumps([target.get("position") for target in lucky_data.get("targets", [])]),
        "winner_index": lucky_data.get("winner_index", ""), "winner_color": lucky_data.get("winner_color", ""),
        "elimination_order": json.dumps(lucky_data.get("elimination_order", [])),
        "corridor_template_id": lucky_data.get("corridor_template_id")
        or (f"{lucky_data['map_version']}:{lucky_data['map_seed']}" if lucky_data.get("map_version") else ""),
        "mirrored": lucky_data.get("mirrored", ""),
        "target_terminal_mapping": json.dumps(lucky_data.get("targets", [])),
        "equation_templates": json.dumps([item.data.get("equation_template") for item in spec.rounds if "equation_template" in item.data]),
        "operations": json.dumps([item.data.get("operation") for item in spec.rounds if "operation" in item.data]),
        "sequence_families": json.dumps([item.data.get("sequence_family") for item in spec.rounds if "sequence_family" in item.data]),
        "steps_or_ratios": json.dumps([item.data.get("step_or_ratio") for item in spec.rounds if "step_or_ratio" in item.data]),
        "background_hash": hidden_data.get("background_hash", ""),
        "placement_mode": hidden_data.get("placement_mode", ""),
        "object_count": hidden_data.get("object_count", ""),
        "hidden_object_positions": json.dumps([item.get("position") for item in hidden_objects]),
        "hidden_object_tiers": json.dumps([item.get("tier") for item in hidden_objects]),
        "hidden_object_diameters": json.dumps([item.get("diameter") for item in hidden_objects]),
        "hidden_object_shapes": json.dumps([item.get("shape") for item in hidden_objects]),
        "hidden_object_colors": json.dumps([item.get("color") for item in hidden_objects]),
        "hidden_object_jump_heights": json.dumps([item.get("jump_height_px") for item in hidden_objects]),
        "hidden_object_bounce_speeds": json.dumps([item.get("bounce_speed") for item in hidden_objects]),
        "hidden_object_sources": json.dumps([item.get("source_type") for item in hidden_objects]),
        "hidden_object_png_hashes": json.dumps([item.get("png_asset_hash") for item in hidden_objects]),
        "motion_parameters": json.dumps([{
            "x_amplitude": item.get("x_amplitude"), "y_amplitude": item.get("y_amplitude"),
            "scale_amplitude": item.get("scale_amplitude"), "cycles": item.get("cycles"),
            "phase": item.get("phase"), "bounce_speed": item.get("bounce_speed"),
        } for item in hidden_objects]),
        "bounce_initial_positions": json.dumps(bounce_data.get("initial_positions", [])),
        "bounce_initial_velocities": json.dumps(bounce_data.get("initial_velocities", [])),
        "bounce_opening": json.dumps(bounce_data.get("arena", {})),
        "bounce_elimination_order": json.dumps(bounce_data.get("elimination_order", [])),
        "bounce_winner": bounce_data.get("winner", ""),
        "bounce_simulation_duration": bounce_data.get("simulation_duration", ""),
        "bounce_initial_condition_attempt": bounce_data.get("initial_condition_attempt", ""),
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "render_seconds": f"{elapsed:.2f}", "validation_status": "valid",
    }


def _write_manifests(batch_dir: Path, rows: list[dict[str, Any]], batch_stamp: str) -> None:
    try:
        write_manifest(batch_dir / "metadata.csv", rows)
        write_manifest(batch_dir / f"metadata_{batch_stamp}.csv", rows)
    except OSError:
        LOGGER.warning("Video and cover succeeded but disposable metadata CSV could not be written", exc_info=True)


def render_batch(
    specs: list[VideoSpec], quality: str = "final", output_dir: Path | None = None,
    history: HistoryStore | None = None,
    progress: Callable[[int, int, VideoSpec, str], None] | None = None,
) -> tuple[Path, list[Path]]:
    ensure_directories()
    history = history or HistoryStore()
    batch_dir = output_dir or OUTPUT_DIR / datetime.now().strftime("%Y-%m-%d")
    batch_dir.mkdir(parents=True, exist_ok=True)
    batch_stamp = datetime.now().strftime("%H%M%S_%f")
    rows: list[dict[str, Any]] = []
    outputs: list[Path] = []
    for position, spec in enumerate(specs, start=1):
        temporary_stem = f".puzzly-{uuid4().hex}"
        temporary_video = batch_dir / f"{temporary_stem}.mp4"
        temporary_cover = batch_dir / f"{temporary_stem}.jpg"
        finalized: list[Path] = []
        if progress:
            progress(position, len(specs), spec, "rendering")
        try:
            elapsed = render_video(spec, temporary_video, quality=quality, logger=None)
            save_cover(spec, temporary_cover)

            def finalize_files(sequence_no: int) -> tuple[str, str]:
                stem = output_stem(sequence_no, spec)
                video_path, cover_path = batch_dir / f"{stem}.mp4", batch_dir / f"{stem}.jpg"
                if video_path.exists() or cover_path.exists():
                    raise FileExistsError(f"Output already exists for sequence {sequence_no}")
                temporary_video.replace(video_path)
                finalized.append(video_path)
                try:
                    temporary_cover.replace(cover_path)
                except Exception:
                    video_path.replace(temporary_video)
                    finalized.clear()
                    raise
                finalized.append(cover_path)
                return video_path.name, cover_path.name

            record = history.commit_success(
                puzzle_type=spec.puzzle_type,
                difficulty=spec.difficulty or "",
                seed=spec.seed,
                fingerprint=spec.fingerprint(),
                finalize_files=finalize_files,
                spec_json=spec.to_json(),
                quality=quality,
            )
        except Exception:
            for generated_path in finalized:
                generated_path.unlink(missing_ok=True)
            temporary_video.unlink(missing_ok=True)
            temporary_cover.unlink(missing_ok=True)
            raise
        path = batch_dir / record.output_filename
        rows.append(_manifest_row(spec, record, elapsed, quality))
        outputs.append(path)
        _write_manifests(batch_dir, rows, batch_stamp)
        if progress:
            progress(position, len(specs), spec, "complete")
    return batch_dir, outputs


def render_draft_previews(
    specs: list[VideoSpec],
    progress: Callable[[int, int, VideoSpec, str], None] | None = None,
    preview_root: Path | None = None,
) -> tuple[Path, list[DraftPreview]]:
    """Render disposable Draft previews without publishing or touching history."""
    ensure_directories()
    preview_dir = (preview_root or DATA_DIR / "draft_previews") / uuid4().hex
    preview_dir.mkdir(parents=True, exist_ok=False)
    previews: list[DraftPreview] = []
    try:
        for position, spec in enumerate(specs, start=1):
            if progress:
                progress(position, len(specs), spec, "rendering")
            video_path = preview_dir / f"draft_preview_{position:02d}.mp4"
            cover_path = preview_dir / f"draft_preview_{position:02d}.jpg"
            render_video(spec, video_path, quality="draft", logger=None)
            save_cover(spec, cover_path)
            previews.append(DraftPreview(spec, video_path, cover_path))
            if progress:
                progress(position, len(specs), spec, "complete")
    except Exception:
        shutil.rmtree(preview_dir, ignore_errors=True)
        raise
    return preview_dir, previews


def save_draft_preview(
    preview: DraftPreview, output_dir: Path | None = None, history: HistoryStore | None = None,
) -> tuple[GenerationRecord, Path]:
    """Publish an already-rendered Draft only after the user explicitly saves it."""
    if not preview.video_path.is_file() or not preview.cover_path.is_file():
        raise FileNotFoundError("Draft preview files are no longer available")
    history = history or HistoryStore()
    batch_dir = output_dir or OUTPUT_DIR / datetime.now().strftime("%Y-%m-%d")
    batch_dir.mkdir(parents=True, exist_ok=True)
    temporary_stem = f".puzzly-save-{uuid4().hex}"
    temporary_video = batch_dir / f"{temporary_stem}.mp4"
    temporary_cover = batch_dir / f"{temporary_stem}.jpg"
    shutil.copy2(preview.video_path, temporary_video)
    shutil.copy2(preview.cover_path, temporary_cover)
    finalized: list[Path] = []

    def finalize_files(sequence_no: int) -> tuple[str, str]:
        stem = output_stem(sequence_no, preview.spec)
        video_path, cover_path = batch_dir / f"{stem}.mp4", batch_dir / f"{stem}.jpg"
        if video_path.exists() or cover_path.exists():
            raise FileExistsError(f"Output already exists for sequence {sequence_no}")
        temporary_video.replace(video_path)
        finalized.append(video_path)
        try:
            temporary_cover.replace(cover_path)
        except Exception:
            video_path.replace(temporary_video)
            finalized.clear()
            raise
        finalized.append(cover_path)
        return video_path.name, cover_path.name

    try:
        record = history.commit_success(
            puzzle_type=preview.spec.puzzle_type, difficulty=preview.spec.difficulty,
            seed=preview.spec.seed, fingerprint=preview.spec.fingerprint(),
            finalize_files=finalize_files, spec_json=preview.spec.to_json(), quality="draft",
        )
    except Exception:
        for path in finalized:
            path.unlink(missing_ok=True)
        temporary_video.unlink(missing_ok=True)
        temporary_cover.unlink(missing_ok=True)
        raise
    _write_manifests(
        batch_dir, [_manifest_row(preview.spec, record, 0.0, "draft")],
        datetime.now().strftime("%H%M%S_%f"),
    )
    return record, batch_dir / record.output_filename


def _spec_from_manifest(record: GenerationRecord, output_root: Path) -> VideoSpec | None:
    manifests = sorted(output_root.rglob("metadata_*.csv"), reverse=True)
    manifests.extend(sorted(output_root.rglob("metadata.csv"), reverse=True))
    for manifest in manifests:
        try:
            with manifest.open(encoding="utf-8-sig", newline="") as handle:
                row = next((item for item in csv.DictReader(handle)
                            if item.get("filename") == record.output_filename), None)
            if row is None:
                continue
            round_data = json.loads(row["question"])
            answers = json.loads(row["answer"])
            if not isinstance(round_data, list) or not isinstance(answers, list) or len(round_data) != len(answers):
                continue
            puzzle_type = row["puzzle_type"]
            rounds = tuple(RoundSpec(index, puzzle_type, data, answers[index])
                           for index, data in enumerate(round_data))
            total = float(row["duration_seconds"])
            before_long_end_card = str(row.get("created_at", ""))[:10] < "2026-09-30"  # the end card grew from 1.6 s to 3.6 s
            end_card = 1.6 if before_long_end_card else PUZZLE_FIT_OUTRO_DURATION
            from .config import READY_GAMES, READY_INTRO_DURATION
            if puzzle_type in ("hidden_motion_hunt", "chess_mate"):
                intro, outro = 0.0, 0.0
            elif puzzle_type == "bounce_arena":
                intro, outro = 0.0, 1.7 if before_long_end_card else BOUNCE_CTA_DURATION
            elif puzzle_type == "lucky_pick" and not (round_data and round_data[0].get("map_version")):
                intro, outro = LUCKY_INTRO_DURATION, OUTRO_DURATION  # older corridor-template videos
            elif puzzle_type == "line_follow" and round_data and round_data[0].get("version") in ("weave_v7", "weave_v8"):
                intro, outro = PUZZLE_FIT_INTRO_DURATION, end_card
            elif puzzle_type == "flash_count" and round_data and round_data[0].get("format"):
                from .config import FLASH_INTRO
                intro, outro = (2.0 if before_long_end_card else FLASH_INTRO), end_card
            elif puzzle_type == "shade_spot" and str(row.get("created_at", ""))[:10] < "2026-10-02":
                intro, outro = PUZZLE_FIT_INTRO_DURATION, end_card  # made before its READY screen
            elif puzzle_type in READY_GAMES and not before_long_end_card:
                intro, outro = READY_INTRO_DURATION, end_card
            elif puzzle_type in ("puzzle_fit", "cube_count", "flash_count", "memory_challenge", "lucky_pick", "matchstick", "cup_shuffle", "shade_spot", "laser_maze") or (
                    puzzle_type == "quick_math" and round_data and round_data[0].get("format")) or (puzzle_type == "find_the_exit"
                                                   and round_data and round_data[0].get("layout") in ("deceptive_v2", "polar_v1", "cells_v1")):
                intro, outro = PUZZLE_FIT_INTRO_DURATION, end_card
            else:
                intro, outro = INTRO_DURATION, OUTRO_DURATION
            round_duration_value = (total - intro - outro) / max(1, len(rounds))
            operation = "mixed"
            if puzzle_type == "quick_math":
                operations = json.loads(row.get("operations") or "[]")
                unique_operations = {str(value) for value in operations if value}
                if len(unique_operations) == 1:
                    operation = unique_operations.pop()
            return VideoSpec(
                row["video_id"], puzzle_type, int(row["seed"]), row.get("difficulty") or None,
                row.get("theme") or "auto", rounds, intro, round_duration_value, outro,
                operation=operation,
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
    return None


def spec_for_record(record: GenerationRecord, output_root: Path = OUTPUT_DIR) -> VideoSpec:
    if record.spec_json:
        return VideoSpec.from_json(record.spec_json)
    recovered = _spec_from_manifest(record, output_root)
    if recovered is None:
        raise ValueError("Bu eski kayıt için birebir VideoSpec bulunamadı; metadata dosyası gerekli.")
    return recovered


def rerender_record_final(
    record: GenerationRecord, *, output_root: Path = OUTPUT_DIR, history: HistoryStore | None = None,
) -> Path:
    """Atomically replace a saved Draft with a Final render using the exact stored spec."""
    history = history or HistoryStore()
    spec = spec_for_record(record, output_root)
    matches = list(output_root.rglob(record.output_filename)) if output_root.exists() else []
    target_video = matches[0] if matches else output_root / datetime.now().strftime("%Y-%m-%d") / record.output_filename
    target_video.parent.mkdir(parents=True, exist_ok=True)
    target_cover = target_video.with_name(record.cover_filename)
    token = uuid4().hex
    temporary_video = target_video.parent / f".puzzly-final-{token}.mp4"
    temporary_cover = target_video.parent / f".puzzly-final-{token}.jpg"
    backup_video = target_video.parent / f".puzzly-backup-{token}.mp4"
    backup_cover = target_video.parent / f".puzzly-backup-{token}.jpg"
    elapsed = render_video(spec, temporary_video, quality="final", logger=None)
    save_cover(spec, temporary_cover)
    had_video = target_video.exists()
    had_cover = target_cover.exists()
    try:
        if had_video:
            shutil.copy2(target_video, backup_video)
        if had_cover:
            shutil.copy2(target_cover, backup_cover)
        temporary_video.replace(target_video)
        temporary_cover.replace(target_cover)
        history.update_render(record.sequence_no, spec_json=spec.to_json(), quality="final")
    except Exception:
        if backup_video.exists():
            backup_video.replace(target_video)
        elif not had_video:
            target_video.unlink(missing_ok=True)
        if backup_cover.exists():
            backup_cover.replace(target_cover)
        elif not had_cover:
            target_cover.unlink(missing_ok=True)
        temporary_video.unlink(missing_ok=True)
        temporary_cover.unlink(missing_ok=True)
        raise
    finally:
        backup_video.unlink(missing_ok=True)
        backup_cover.unlink(missing_ok=True)
    updated = history.record(record.sequence_no)
    assert updated is not None
    _write_manifests(
        target_video.parent, [_manifest_row(spec, updated, elapsed, "final")],
        datetime.now().strftime("%H%M%S_%f"),
    )
    return target_video
