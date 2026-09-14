from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .models import VideoSpec

TITLES = {
    "find_the_exit": "Can You Find the Exit? ⭐ #shorts",
    "line_follow": "Where Does This Line Go? 🌀 #shorts",
    "missing_number": "Can You Find All {round_count} Missing Numbers? 🔢 #shorts",
    "puzzle_fit": "Which Piece Fits? 🧩 #shorts",
    "memory_challenge": "How Good Is Your Memory? 🧠 #shorts",
    "flash_count": "Flash Count Challenge! ⚡👀 #shorts",
    "lucky_pick": "Pick One... Will It Survive? 👀 #shorts",
    "hidden_motion_hunt": "Can You Find All 7 Moving Objects? 👀 #shorts",
}
DESCRIPTION = "A quick visual puzzle from Puzzly for Kids. Think, play and learn! 🧩"
TAGS = "puzzly,kids puzzles,brain games,educational shorts,visual puzzle,learning through play,shorts"
FIELDS = (
    "filename", "cover_filename", "sequence_no", "video_id", "puzzle_type", "theme", "difficulty", "seed", "question",
    "answer", "youtube_title", "youtube_description", "youtube_tags", "created_at",
    "round_count", "duration_seconds", "token_shapes", "color_ids", "token_positions",
    "question_order", "final_auto_reveal",
    "shape_id", "color_id", "displayed_counts", "flash_positions",
    "circle_count", "lucky_color_ids", "lucky_positions", "winner_index", "winner_color", "elimination_order",
    "corridor_template_id", "mirrored", "target_terminal_mapping",
    "equation_templates", "operations", "sequence_families", "steps_or_ratios",
    "background_hash", "placement_mode", "object_count", "hidden_object_positions", "hidden_object_tiers",
    "hidden_object_diameters", "hidden_object_shapes", "hidden_object_colors",
    "hidden_object_jump_heights", "hidden_object_bounce_speeds", "hidden_object_sources",
    "hidden_object_png_hashes", "motion_parameters",
    "render_seconds", "validation_status",
)


def youtube_metadata(spec: VideoSpec) -> dict[str, str]:
    if spec.puzzle_type == "quick_math":
        title = f"Can You Solve All {spec.round_count}? ➕🧠 #shorts" if spec.seed % 2 == 0 else f"{spec.round_count} Quick Math Challenges! 🔢 #shorts"
    elif spec.puzzle_type == "memory_challenge":
        variants = ("Can You Remember All 5? 🧠 #shorts", "Test Your Color Memory! 🧠🎨 #shorts", "How Good Is Your Visual Memory? 👀🧠 #shorts", "Remember the Shapes! 🧠 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "flash_count":
        variants = ("How Many Did You See? 👀 #shorts", "Count Them Before They Disappear! 👀🧠 #shorts", "Flash Count Challenge! ⚡👀 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "lucky_pick":
        variants = ("Pick One... Will It Survive? 👀 #shorts", "Choose a Color! Which One Wins? 🌈 #shorts",
                    "Pick One Before It Starts! 👀✨ #shorts", "Will Your Color Survive? 🎯 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "hidden_motion_hunt":
        title = TITLES["hidden_motion_hunt"]
    else:
        title = TITLES[spec.puzzle_type].format(round_count=spec.round_count)
    if spec.puzzle_type == "memory_challenge":
        description = "Watch the colors and shapes, then test your visual memory with Puzzly. 🧩"
    elif spec.puzzle_type == "flash_count":
        description = "Look quickly, remember the shapes, and count how many you saw."
    elif spec.puzzle_type == "lucky_pick":
        description = "Pick one color and see if your choice is the last one standing!"
    elif spec.puzzle_type == "hidden_motion_hunt":
        description = "Look closely and find all 7 moving objects hidden in the scene."
    else:
        description = DESCRIPTION
    tags = TAGS
    if spec.puzzle_type == "flash_count":
        tags += ",flash count,focus challenge"
    elif spec.puzzle_type == "lucky_pick":
        tags += ",lucky pick,pick one"
    elif spec.puzzle_type == "hidden_motion_hunt":
        tags += ",hidden objects,visual search,moving objects"
    return {"youtube_title": title, "youtube_description": description, "youtube_tags": tags}


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
