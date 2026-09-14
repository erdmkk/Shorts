from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
import logging
from pathlib import Path
import random
import secrets
from typing import Any
from uuid import uuid4

from .config import OUTPUT_DIR, ensure_directories
from .history import HistoryStore
from .metadata import write_manifest, youtube_metadata
from .models import VideoSpec
from .puzzles import flash_count, hidden_motion_hunt, lucky_pick, missing_number, puzzle_fit, quick_math, find_the_exit, line_follow, memory_challenge
from .registry import ACTIVE_PUZZLE_TYPES, MIXED_PUZZLE_TYPES, SUPPORTED_PUZZLE_TYPES
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
    "flash_count": ("geometric_tokens",),
    "lucky_pick": ("lucky_pick",),
    "hidden_motion_hunt": ("uploaded_background",),
}


def generate_spec(
    puzzle_type: str, seed: int, difficulty: str = "easy", theme: str = "auto",
    operation: str = "mixed", challenges: int | None = None, background_bytes: bytes | None = None,
    placement_mode: str = "auto", manual_objects: list[dict] | None = None,
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
    factories = {
        "missing_number": missing_number.generate,
        "puzzle_fit": puzzle_fit.generate,
        "find_the_exit": find_the_exit.generate,
        "line_follow": line_follow.generate,
        "memory_challenge": memory_challenge.generate,
        "flash_count": flash_count.generate,
        "lucky_pick": lucky_pick.generate,
    }
    if puzzle_type == "quick_math":
        spec = quick_math.generate(seed, difficulty, operation, challenges)
    elif puzzle_type == "lucky_pick":
        spec = lucky_pick.generate(seed)
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


def generate_unique_specs(
    count: int, puzzle_type: str = "mixed", difficulty: str = "easy", theme: str = "auto",
    base_seed: int | None = None, history: HistoryStore | None = None, retry_limit: int = 100,
    operation: str = "mixed", challenges: int | None = None, background_bytes: bytes | None = None,
    placement_mode: str = "auto", manual_objects: list[dict] | None = None,
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
                                 placement_mode, manual_objects)
            fingerprint = spec.fingerprint()
            if fingerprint not in existing and fingerprint not in selected:
                specs.append(spec)
                selected.add(fingerprint)
                break
        else:
            raise RuntimeError(f"Could not create a unique {selected_type} puzzle after {retry_limit} tries")
    return specs


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
                stem = (f"PZ_{sequence_no:04d}_{spec.puzzle_type}" if spec.puzzle_type in ("lucky_pick", "hidden_motion_hunt")
                        else f"PZ_{sequence_no:04d}_{spec.puzzle_type}_{spec.difficulty}")
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
            )
        except Exception:
            for generated_path in finalized:
                generated_path.unlink(missing_ok=True)
            temporary_video.unlink(missing_ok=True)
            temporary_cover.unlink(missing_ok=True)
            raise
        filename, cover_filename = record.output_filename, record.cover_filename
        path = batch_dir / filename
        meta = youtube_metadata(spec)
        memory_data = spec.rounds[0].data if spec.puzzle_type == "memory_challenge" else {}
        memory_tokens = memory_data.get("tokens", [])
        flash_data = spec.rounds[0].data if spec.puzzle_type == "flash_count" else {}
        lucky_data = spec.rounds[0].data if spec.puzzle_type == "lucky_pick" else {}
        hidden_data = spec.rounds[0].data if spec.puzzle_type == "hidden_motion_hunt" else {}
        hidden_objects = hidden_data.get("objects", [])
        rows.append({
            "filename": filename, "cover_filename": cover_filename, "sequence_no": record.sequence_no,
            "video_id": spec.id, "puzzle_type": spec.puzzle_type,
            "theme": spec.theme, "difficulty": spec.difficulty or "", "seed": spec.seed,
            "question": json.dumps([round_spec.data for round_spec in spec.rounds], ensure_ascii=False),
            "answer": json.dumps([round_spec.answer for round_spec in spec.rounds], ensure_ascii=False), **meta,
            "round_count": spec.round_count, "duration_seconds": spec.total_duration,
            "token_shapes": json.dumps([token.get("shape") for token in memory_tokens], ensure_ascii=False),
            "color_ids": json.dumps([token.get("color_id") for token in memory_tokens], ensure_ascii=False),
            "token_positions": json.dumps([token.get("position") for token in memory_tokens], ensure_ascii=False),
            "question_order": json.dumps(memory_data.get("question_order", []), ensure_ascii=False),
            "final_auto_reveal": memory_data.get("final_position", ""),
            "shape_id": flash_data.get("shape_id", lucky_data.get("shape_id", "")),
            "color_id": flash_data.get("color_id", ""),
            "displayed_counts": json.dumps([item.data.get("displayed_count") for item in spec.rounds if item.kind == "flash_count"]),
            "flash_positions": json.dumps([item.data.get("positions") for item in spec.rounds if item.kind == "flash_count"]),
            "circle_count": lucky_data.get("target_count", ""),
            "lucky_color_ids": json.dumps([target.get("color_id") for target in lucky_data.get("targets", [])]),
            "lucky_positions": json.dumps([target.get("position") for target in lucky_data.get("targets", [])]),
            "winner_index": lucky_data.get("winner_index", ""), "winner_color": lucky_data.get("winner_color", ""),
            "elimination_order": json.dumps(lucky_data.get("elimination_order", [])),
            "corridor_template_id": lucky_data.get("corridor_template_id", ""),
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
            "motion_parameters": json.dumps([{"x_amplitude": item.get("x_amplitude"),
                                               "y_amplitude": item.get("y_amplitude"),
                                               "scale_amplitude": item.get("scale_amplitude"),
                                               "cycles": item.get("cycles"), "phase": item.get("phase"),
                                               "bounce_speed": item.get("bounce_speed")}
                                              for item in hidden_objects]),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "render_seconds": f"{elapsed:.2f}", "validation_status": "valid",
        })
        outputs.append(path)
        try:
            write_manifest(batch_dir / "metadata.csv", rows)
            write_manifest(batch_dir / f"metadata_{batch_stamp}.csv", rows)
        except OSError:
            LOGGER.warning("Video and cover succeeded but disposable metadata CSV could not be written", exc_info=True)
        if progress:
            progress(position, len(specs), spec, "complete")
    return batch_dir, outputs
