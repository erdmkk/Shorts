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
    "flash_count": "Can You Read the Number in a Blink? ⚡👀 #shorts",
    "lucky_pick": "Pick One... Will It Survive? 👀 #shorts",
    "hidden_motion_hunt": "Can You Find All 7 Moving Objects? 👀 #shorts",
    "bounce_arena": "Pick a Ball. Last One in the Ring Wins. 🔴🔵🟡 #shorts",
    "cube_count": "How Many Cubes Did You See? 🧊 #shorts",
}
DESCRIPTION = "A quick visual challenge from Puzzly for You. How many can you solve? 🧩"
TAGS = "puzzly,puzzly for you,brain teaser,puzzle challenge,visual puzzle,brain games,shorts"
FIELDS = (
    "filename", "cover_filename", "sequence_no", "video_id", "puzzle_type", "theme", "difficulty", "seed", "quality", "question",
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
    "bounce_initial_positions", "bounce_initial_velocities", "bounce_opening",
    "bounce_elimination_order", "bounce_winner", "bounce_simulation_duration",
    "bounce_initial_condition_attempt",
    "render_seconds", "validation_status",
)


def youtube_metadata(spec: VideoSpec) -> dict[str, str]:
    if spec.puzzle_type == "quick_math":
        variants = (("Fill In the Missing Signs. No Calculator. 🧠 #shorts", "+ − × ÷  Which Signs Are Missing? #shorts",
                     "Only One Combination Works. Find It. 🧠 #shorts", f"{spec.round_count} Levels. The Last One Has a Trap. ➗ #shorts")
                    if spec.operation == "operators" else None) or ("Solve the Shapes. No Calculator. 🔺🟦 #shorts", f"{spec.round_count} Levels of Shape Math. Can You Finish? 🧠 #shorts",
                    "The Last Level Has a Trap. 🔺➕🟦 #shorts", "Find the Value of Every Shape ⏱️🧠 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "memory_challenge":
        seconds = spec.rounds[0].data["memorization_seconds"]
        variants = ("Can You Remember All 9? 🧠 #shorts", f"{seconds:g} Seconds to Memorize 9 Shapes ⏱️🧠 #shorts",
                    "How Good Is Your Visual Memory? 👀🧠 #shorts", "Where Was It? 8 Questions 🧠 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "flash_count":
        variants = ("Can You Read the Number in a Blink? ⚡👀 #shorts", "What Was the Number? Don't Blink! 👀🧠 #shorts",
                    f"{spec.round_count} Numbers. One Blink Each. ⚡ #shorts", "How Fast Are Your Eyes? 👀⚡ #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "lucky_pick":
        snake = spec.rounds[0].data.get("map_version") == "snake_chase_v1"
        variants = ("Pick One. Only One Survives. 👀 #shorts", "Pick Before the Timer Ends. Will Yours Survive? ⏱️👀 #shorts",
                    "7 Colors. 1 Survivor. Pick Now. 🎯 #shorts",
                    "Can Your Color Outrun the Snake? 🐍👀 #shorts" if snake else "Will Your Color Survive the Maze? 👀 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "puzzle_fit":
        variants = ("Only One Piece Fits. Can You Find It? 🧩 #shorts", f"{spec.round_count} Levels. Each One Harder. 🧩 #shorts",
                    "Which Piece Fits? Beat the Timer ⏱️🧩 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "cube_count":
        seconds = spec.rounds[0].data["visible_seconds"]
        variants = ("How Many Cubes Did You See? 🧊 #shorts", f"{seconds:g} {'Second' if seconds == 1 else 'Seconds'} to Count the Cubes ⏱️🧊 #shorts",
                    f"{spec.round_count} Levels of Cube Counting 🧠🧊 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "line_follow":
        variants = ("Where Does This Line Go? 🌀 #shorts", "Follow the Line. Only Your Eyes. 👀 #shorts",
                    f"{spec.round_count} Levels of Tangled Lines. Each One Harder 🧠 #shorts", "Which Exit Does It Reach? 🌀👀 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "hidden_motion_hunt":
        title = TITLES["hidden_motion_hunt"]
    elif spec.puzzle_type == "bounce_arena":
        title = TITLES["bounce_arena"]
    else:
        title = TITLES[spec.puzzle_type].format(round_count=spec.round_count)
    if spec.puzzle_type == "quick_math" and spec.operation == "operators":
        description = "Put the right signs between the numbers. Only one combination works. Comment how many you solved! 🧠"
    elif spec.puzzle_type == "quick_math":
        description = "Find the value of every shape, then solve the last line. No calculator. Comment how many you solved! 🧠"
    elif spec.puzzle_type == "memory_challenge":
        description = "Memorize the 3x3 board, then find every shape. Comment how many you got! 🧠"
    elif spec.puzzle_type == "flash_count":
        description = "The number flashes for a split second. Read it, remember it, and comment how many you got! ⚡👀"
    elif spec.puzzle_type == "lucky_pick":
        description = ("Pick one before the timer ends. The snake hunts them all; only one survives. Comment if yours made it! 👀"
                       if spec.rounds[0].data.get("map_version") == "snake_chase_v1" else
                       "Pick one before the timer ends. Only one survives the maze. Comment if yours made it! 👀")
    elif spec.puzzle_type == "puzzle_fit":
        description = "Only one piece fits. Beat the timer and comment how many you got! 🧩"
    elif spec.puzzle_type == "cube_count":
        description = "The cubes flash for a moment. Count every one, including the hidden ones, and comment your score! 🧊"
    elif spec.puzzle_type == "line_follow":
        description = "Follow the glowing line with your eyes only and find its exit. Comment how many you got! 👀🌀"
    elif spec.puzzle_type == "hidden_motion_hunt":
        description = "Look closely and find all 7 moving objects hidden in the scene."
    elif spec.puzzle_type == "bounce_arena":
        description = "Pick a ball before the timer ends. Real physics, one spinning gap, one survivor. Comment your color! 🎯"
    else:
        description = DESCRIPTION
    tags = TAGS
    if spec.puzzle_type == "flash_count":
        tags += ",flash count,number flash,speed reading,focus challenge,visual memory"
    elif spec.puzzle_type == "lucky_pick":
        tags += ",lucky pick,pick one"
    elif spec.puzzle_type == "hidden_motion_hunt":
        tags += ",hidden objects,visual search,moving objects"
    elif spec.puzzle_type == "bounce_arena":
        tags += ",bounce arena,pick one,physics game"
    elif spec.puzzle_type == "cube_count":
        tags += ",cube count,block counting,spatial reasoning"
    elif spec.puzzle_type == "line_follow":
        tags += ",line follow,tangled lines,follow the line,visual tracking"
    return {"youtube_title": title, "youtube_description": description, "youtube_tags": tags}


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
