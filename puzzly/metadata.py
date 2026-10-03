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
    "chess_mate": "Mate in 1. Can You Find It? ♟️ #shorts",
    "matchstick": "Move 1 Match to Fix It 🔥🧠 #shorts",
    "cup_shuffle": "Where Is the Ball? Follow the Cups 🥤👀 #shorts",
    "shade_spot": "Spot the Different Shade. Can You? 🎨👀 #shorts",
    "mind_mix": "3 Games. 1 Score. Can You Beat Them All? 🧠 #shorts",
    "laser_maze": "Where Does the Laser End? 🔦🪞 #shorts",
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
    elif spec.puzzle_type == "memory_challenge" and spec.rounds[0].data.get("layout") == "levels_v8":
        variants = ("Can You Remember It All? 🧠 #shorts", f"{spec.round_count} Levels. The Board Gets Bigger 🧠👀 #shorts",
                    "What Vanished? Memory Challenge 👀🧠 #shorts", "Where Was It? Test Your Memory 🧠 #shorts")
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
    elif spec.puzzle_type == "puzzle_fit" and spec.rounds[0].data.get("version") == "fit_v12":
        variants = ("3 Pieces Are Missing. Can You Find Them? 🧩 #shorts", "Find the Missing Pieces. Comment Like A4 B1 C6 🧩 #shorts",
                    "Which Pieces Complete the Picture? 🧩🧠 #shorts", "3 Holes. 6 Pieces. Beat the Timer ⏱️🧩 #shorts")
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
    elif spec.puzzle_type == "mind_mix":
        variants = ("3 Games. 1 Score. Can You Beat Them All? 🧠 #shorts", "Memory, Colour and Puzzle in One Video 🧩🎨🧠 #shorts",
                    "Mind Mix: Remember, Spot, Solve 👀🧠 #shorts", "3 Hard Levels, 3 Different Games ⏱️🧠 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "shade_spot":
        variants = ("Spot the Different Shade. Can You? 🎨👀 #shorts", "One Tile Is Different. Which One? 🎨 #shorts",
                    f"{spec.round_count} Levels. The Colours Get Closer 🎨👀 #shorts", "Only 1 Tile Changed. Find It 👀🎨 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "cup_shuffle":
        variants = ("Where Is the Ball? Follow the Cups 🥤👀 #shorts", "3 Levels. 12 Swaps by the End. Can You Track It? 🥤 #shorts",
                    "Don't Blink. Which Cup Has the Ball? 👀🥤 #shorts", "The Cups Get Faster Every Level 🥤⚡ #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "laser_maze":
        variants = ("Where Does the Laser End? 🔦🪞 #shorts", "Follow the Beam. Which Receiver Lights Up? 🔦 #shorts",
                    f"{spec.round_count} Levels. More Mirrors Every Time 🪞🔦 #shorts", "Can You Track the Laser Through the Mirrors? 👀🔦 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "matchstick":
        variants = ("Move 1 Match to Fix It 🔥🧠 #shorts", "Only One Match Moves. Can You Fix It? 🔥 #shorts",
                    f"{spec.round_count} Matchstick Puzzles. Each One Harder 🧠 #shorts",
                    "Fix the Equation. Move Just One Match 🔥 #shorts")
        title = variants[spec.seed % len(variants)]
    elif spec.puzzle_type == "chess_mate":
        side = spec.rounds[0].data["side"].title()
        variants = ("Mate in 1. Can You Find It? ♟️ #shorts", f"{side} to Move. Checkmate in One. ♟️ #shorts",
                    "One Move. Checkmate. Comment Yours ♟️👇 #shorts",
                    f"Rated {spec.rounds[0].data['rating']}. Can You Find the Mate? ♟️ #shorts")
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
    elif spec.puzzle_type == "memory_challenge" and spec.rounds[0].data.get("layout") == "levels_v8":
        description = ("Memorize the shapes, then find where each one was and name the one that vanished. The board gets bigger "
                       "every level. Comment how many you got! 🧠")
    elif spec.puzzle_type == "memory_challenge":
        description = "Memorize the 3x3 board, then find every shape. Comment how many you got! 🧠"
    elif spec.puzzle_type == "flash_count":
        description = "The number flashes for a split second. Read it, remember it, and comment how many you got! ⚡👀"
    elif spec.puzzle_type == "lucky_pick":
        description = ("Pick one before the timer ends. The snake hunts them all; only one survives. Comment if yours made it! 👀"
                       if spec.rounds[0].data.get("map_version") == "snake_chase_v1" else
                       "Pick one before the timer ends. Only one survives the maze. Comment if yours made it! 👀")
    elif spec.puzzle_type == "puzzle_fit" and spec.rounds[0].data.get("version") == "fit_v12":
        description = ("Three pieces are missing from the picture. The pieces below are tilted, and three of them are traps. "
                       "Find the right ones and comment your answer like A4 B1 C6! 🧩🧠")
    elif spec.puzzle_type == "puzzle_fit":
        description = "Only one piece fits. Beat the timer and comment how many you got! 🧩"
    elif spec.puzzle_type == "cube_count":
        description = "The cubes flash for a moment. Count every one, including the hidden ones, and comment your score! 🧊"
    elif spec.puzzle_type == "line_follow":
        description = "Follow the glowing line with your eyes only and find its exit. Comment how many you got! 👀🌀"
    elif spec.puzzle_type == "mind_mix":
        description = ("Three games, one hard level each: remember the shapes, spot the tile that changed, and find the three missing "
                       "puzzle pieces. Comment your score out of 3! 🧠🎨🧩")
    elif spec.puzzle_type == "shade_spot":
        description = ("Two grids, one changed tile. Find it before the timer runs out. Each level the colours get closer! "
                       "Comment the spot of every level, like B3 🎨👀")
    elif spec.puzzle_type == "cup_shuffle":
        description = "Follow the ball as the cups shuffle. Each level adds a cup and gets faster. Comment the cup number for every level! 🥤👀"
    elif spec.puzzle_type == "laser_maze":
        description = ("A laser enters a board of mirrors. Follow the beam with your eyes and find the numbered receiver it ends in. "
                       "More mirrors every level. Comment the number for every level! 🔦🪞")
    elif spec.puzzle_type == "matchstick":
        description = "Move exactly one match to make each equation true. It gets harder every level. Comment how many you solved! 🔥🧠"
    elif spec.puzzle_type == "chess_mate":
        side = spec.rounds[0].data["side"].title()
        description = (f"{side} to move and checkmate in one. Find the move and comment it below! ♟️ "
                       f"Puzzle {spec.rounds[0].data['puzzle_id']} from the Lichess open puzzle database (CC0).")
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
    elif spec.puzzle_type == "mind_mix":
        tags += ",mind mix,memory game,spot the difference,jigsaw puzzle,three games,brain test"
    elif spec.puzzle_type == "shade_spot":
        tags += ",color puzzle,spot the difference,find the different color,color perception,eye test,visual test"
    elif spec.puzzle_type == "cup_shuffle":
        tags += ",cup shuffle,shell game,follow the ball,eye tracking,focus challenge"
    elif spec.puzzle_type == "laser_maze":
        tags += ",laser puzzle,mirror puzzle,follow the beam,laser maze,eye tracking,logic puzzle,visual puzzle"
    elif spec.puzzle_type == "matchstick":
        tags += ",matchstick puzzle,move one match,matchstick math,math puzzle,equation puzzle"
    elif spec.puzzle_type == "chess_mate":
        tags += ",chess,chess puzzle,mate in 1,checkmate,chess tactics,lichess"
    elif spec.puzzle_type == "line_follow":
        tags += ",line follow,tangled lines,follow the line,visual tracking"
    return {"youtube_title": title, "youtube_description": description, "youtube_tags": tags}


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
