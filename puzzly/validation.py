from __future__ import annotations

from .config import DEFAULT_ROUNDS, FPS, round_duration
from .puzzles import bounce_arena, cube_count, find_the_exit, flash_count, hidden_motion_hunt, lucky_pick, line_follow, line_weave, memory_challenge
from .models import RoundSpec, VideoSpec
from .puzzles.puzzle_fit import candidate_card_bounds


class InvalidPuzzleError(ValueError):
    pass


def round_errors(round_spec: RoundSpec, difficulty: str | None = None) -> list[str]:
    data, errors = round_spec.data, []
    if round_spec.kind == "quick_math" and data.get("format") == "shapes":
        from .puzzles.quick_math import shape_errors
        errors.extend(shape_errors(data, round_spec.answer, difficulty))
    elif round_spec.kind == "quick_math" and data.get("format") == "operators":
        from .puzzles.quick_math import operator_errors
        errors.extend(operator_errors(data, round_spec.answer, difficulty))
    elif round_spec.kind == "quick_math":
        a, b, operation = data.get("a"), data.get("b"), data.get("operation")
        expected = {"addition": a + b, "subtraction": a - b, "multiplication": a * b}.get(operation) if isinstance(a, int) and isinstance(b, int) else None
        if operation == "division" and isinstance(a, int) and isinstance(b, int):
            if b == 0 or a % b:
                errors.append("division must be exact with non-zero divisor")
            else:
                expected = a // b
        if operation == "subtraction" and isinstance(round_spec.answer, int) and round_spec.answer < 0:
            errors.append("subtraction cannot be negative")
        result = data.get("result", expected)
        position = data.get("unknown_position", "result")
        if expected != result or position not in ("left", "right", "result"):
            errors.append("math answer is incorrect")
        elif round_spec.answer != {"left": a, "right": b, "result": result}[position]:
            errors.append("math unknown answer is incorrect")
        if operation not in ("addition", "subtraction", "multiplication"):
            errors.append("math operation is not supported in V7")
        if operation == "multiplication" and (a in (0, 1) or b in (0, 1)):
            errors.append("multiplication operands cannot be zero or one")
    elif round_spec.kind == "missing_number":
        sequence, shown, hidden = data.get("sequence", []), data.get("shown", []), data.get("hidden_index")
        family, value = data.get("sequence_family", "addition"), data.get("step_or_ratio", data.get("step"))
        if len(sequence) != 5 or hidden not in range(1, 4):
            errors.append("sequence or hidden index is invalid")
        if len(shown) != 5 or sum(value is None for value in shown) != 1:
            errors.append("exactly one slot must be hidden")
        if len(sequence) == 5:
            if family == "addition" and any(sequence[i + 1] - sequence[i] != value for i in range(4)):
                errors.append("addition sequence step is invalid")
            elif family == "subtraction" and any(sequence[i] - sequence[i + 1] != value for i in range(4)):
                errors.append("subtraction sequence step is invalid")
            elif family == "multiplication" and (value not in (2, 3, 4, 5) or any(sequence[i + 1] != sequence[i] * value for i in range(4))):
                errors.append("multiplication sequence ratio is invalid")
            elif family not in ("addition", "subtraction", "multiplication"):
                errors.append("sequence family is invalid")
            if min(sequence) < 0 or max(sequence) > 999:
                errors.append("sequence values are outside readable bounds")
        if hidden in range(1, 4) and sequence and round_spec.answer != sequence[hidden]:
            errors.append("sequence answer is incorrect")
    elif round_spec.kind == "puzzle_fit" and data.get("version") == "fit_v12":
        from .puzzles import puzzle_fit_v12
        errors.extend(puzzle_fit_v12.errors(data, round_spec.answer, difficulty))
    elif round_spec.kind == "puzzle_fit":
        hole, candidates, correct = data.get("hole_edges"), data.get("candidates", []), data.get("correct_index")
        cards = [tuple(bounds) for bounds in data.get("candidate_cards", [])]
        expected_count = 9 if difficulty == "hard" else 3
        if len(candidates) != expected_count or len({tuple(candidate) for candidate in candidates}) != expected_count:
            errors.append(f"puzzle fit requires {expected_count} unique candidates")
        if candidates.count(hole) != 1 or correct not in range(expected_count) or (correct in range(expected_count) and candidates[correct] != hole):
            errors.append("puzzle fit must have exactly one correct candidate")
        rows, columns = data.get("rows", 0), data.get("columns", 0)
        pieces = data.get("piece_edges", [])
        slot = data.get("hole_slot", -1)
        if data.get("board_kind") != "jigsaw" or (rows, columns) not in ((2, 2), (2, 3), (3, 3)) or len(pieces) != rows * columns or len(data.get("piece_colors", [])) != rows * columns:
            errors.append("puzzle fit board is not coherent")
        elif difficulty == "hard" and rows * columns < 6:
            errors.append("hard puzzle fit board requires at least six pieces")
        elif not isinstance(slot, int) or slot not in range(len(pieces)) or pieces[slot] != hole:
            errors.append("missing slot does not match hole")
        elif any(len(edges) != 4 or any(edge not in (-1, 0, 1) for edge in edges) for edges in pieces):
            errors.append("invalid jigsaw geometry")
        else:
            for index, edges in enumerate(pieces):
                row, column = divmod(index, columns)
                if (row == 0 and edges[0] != 0) or (column == columns - 1 and edges[1] != 0) or (row == rows - 1 and edges[2] != 0) or (column == 0 and edges[3] != 0):
                    errors.append("outer board edge must be flat")
                if column + 1 < columns and (edges[1] == 0 or edges[1] != -pieces[index + 1][3]):
                    errors.append("horizontal seam mismatch")
                if row + 1 < rows and (edges[2] == 0 or edges[2] != -pieces[index + columns][0]):
                    errors.append("vertical seam mismatch")
        if round_spec.answer != correct:
            errors.append("puzzle fit answer index is incorrect")
        from .puzzles.puzzle_fit import ART_STYLES
        if data.get("art_style") not in ART_STYLES or not isinstance(data.get("level"), int):
            errors.append("puzzle fit artwork/level metadata is invalid")
        if difficulty == "hard" and isinstance(hole, list) and any(
                sum(a != b for a, b in zip(candidate, hole)) != 1 for candidate in candidates if candidate != hole):
            errors.append("hard puzzle fit decoys must differ from the answer by exactly one edge")
        if any(len(candidate) != 4 or any(edge not in (-1, 0, 1) for edge in candidate) for candidate in candidates):
            errors.append("candidate geometry is invalid")
        if cards != list(candidate_card_bounds(difficulty or "easy")):
            errors.append("candidate bounds are invalid")
        if any(not (0 <= x1 < x2 <= 1080 and 0 <= y1 < y2 <= 1920) for x1, y1, x2, y2 in cards):
            errors.append("candidate card is clipped")
        if any(a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]
               for index, a in enumerate(cards) for b in cards[index + 1:]):
            errors.append("candidate cards overlap")
    elif round_spec.kind == "find_the_exit":
        errors.extend(find_the_exit.errors(data, round_spec.answer))
    elif round_spec.kind == "line_follow":
        errors.extend(line_follow.errors(data, round_spec.answer))
    elif round_spec.kind == "memory_challenge":
        errors.extend(memory_challenge.errors(data, round_spec.answer, difficulty))
    elif round_spec.kind == "flash_count":
        errors.extend(flash_count.errors(data, round_spec.answer, difficulty))
    elif round_spec.kind == "lucky_pick":
        errors.extend(lucky_pick.errors(data, round_spec.answer))
    elif round_spec.kind == "cube_count":
        errors.extend(cube_count.errors(data, round_spec.answer, difficulty))
    elif round_spec.kind == "hidden_motion_hunt":
        errors.extend(hidden_motion_hunt.errors(data))
    elif round_spec.kind == "bounce_arena":
        errors.extend(bounce_arena.errors(data, round_spec.answer))
    elif round_spec.kind == "cup_shuffle":
        from .puzzles import cup_shuffle
        errors.extend(cup_shuffle.errors(data, round_spec.answer, difficulty))
    elif round_spec.kind == "shade_spot":
        from .puzzles import shade_spot
        errors.extend(shade_spot.errors(data, round_spec.answer, difficulty))
    elif round_spec.kind == "laser_maze":
        from .puzzles import laser_maze
        errors.extend(laser_maze.errors(data, round_spec.answer, difficulty))
    elif round_spec.kind == "mind_mix":
        from .puzzles import mind_mix
        errors.extend(mind_mix.errors(data, round_spec.answer, difficulty))
    elif round_spec.kind == "matchstick":
        from .puzzles import matchstick
        errors.extend(matchstick.errors(data, round_spec.answer, difficulty))
    elif round_spec.kind == "chess_mate":
        from .puzzles import chess_mate
        errors.extend(chess_mate.errors(data, round_spec.answer, difficulty))
    else:
        errors.append("unsupported round kind")
    return errors


def validation_errors(spec: VideoSpec) -> list[str]:
    from .config import memory_round_duration
    errors: list[str] = []
    if spec.puzzle_type not in DEFAULT_ROUNDS or spec.fps != FPS:
        errors.append("unsupported video type or FPS")
    memory_levels = spec.puzzle_type == "memory_challenge" and bool(spec.rounds) and spec.rounds[0].data.get("layout") == "levels_v8"
    if memory_levels:
        from .config import MEMORY_LEVEL_TIERS, memory_average_round
        if [item.data.get("tier") for item in spec.rounds] != list(MEMORY_LEVEL_TIERS.get(len(spec.rounds), ())):
            errors.append("memory levels must grow from the first tier to the last")
        else:
            counts = [len(item.data.get("tokens", [])) for item in spec.rounds]
            if counts != sorted(counts) or len(set(counts)) != len(counts):
                errors.append("memory boards must grow level by level")
            if abs(spec.round_duration - memory_average_round([item.data for item in spec.rounds])) > 1e-3:
                errors.append("round duration does not match the memory levels")
        if spec.difficulty != "hard":
            errors.append("memory challenge is produced in hard")
    elif spec.puzzle_type in ("memory_challenge", "lucky_pick", "hidden_motion_hunt", "bounce_arena", "chess_mate") or (
            spec.puzzle_type == "puzzle_fit" and spec.rounds and spec.rounds[0].data.get("version") == "fit_v12"):
        if len(spec.rounds) != 1:
            errors.append(f"{spec.puzzle_type} video must contain exactly one game")
    elif not 3 <= len(spec.rounds) <= 5:
        errors.append("video must contain 3 to 5 rounds")
    if spec.puzzle_type == "flash_count" and spec.rounds:
        numbers = [item.data.get("number") for item in spec.rounds]
        if len(set(numbers)) != len(numbers):
            errors.append("flash video must not show the same number twice")
        if [item.data.get("tier") for item in spec.rounds] != [flash_count.level_tier(index, len(spec.rounds))
                                                                for index in range(len(spec.rounds))]:
            errors.append("flash levels must grow from the opening to the final tier")
    if spec.puzzle_type == "cube_count" and spec.rounds:
        totals = [item.answer for item in spec.rounds]
        colors = [item.data.get("color_id") for item in spec.rounds]
        if any(first == second for first, second in zip(colors, colors[1:])):
            errors.append("cube consecutive rounds must use different colors")
        if any(first == second for first, second in zip(totals, totals[1:])):
            errors.append("cube consecutive rounds must not repeat a total")
    if spec.puzzle_type in ("lucky_pick", "bounce_arena"):
        if not spec.rounds or spec.round_duration != spec.rounds[0].data.get("timeline_duration"):
            errors.append(f"{spec.puzzle_type} round duration does not match its timeline")
    elif spec.puzzle_type == "quick_math" and spec.rounds and "format" in spec.rounds[0].data:
        from .config import quick_math_average_round
        if spec.round_duration != quick_math_average_round(spec.difficulty, [item.data.get("tier", 0) for item in spec.rounds]):
            errors.append("round duration does not match the quick math levels")
    elif memory_levels:
        pass  # checked above
    elif spec.puzzle_type == "laser_maze" and spec.rounds:
        from .config import LASER_TIER_SETS, laser_average_round
        if [item.data.get("tier") for item in spec.rounds] != list(LASER_TIER_SETS.get(len(spec.rounds), ())):
            errors.append("laser levels must use the tiers of their number of levels, easiest first")
        elif abs(spec.round_duration - laser_average_round([item.data for item in spec.rounds])) > 1e-3:
            errors.append("round duration does not match the laser levels")
        if spec.difficulty != "hard":
            errors.append("laser maze is produced in hard")
    elif spec.puzzle_type == "mind_mix" and spec.rounds:
        from .config import MIX_GAMES, mix_average_round
        if [item.data.get("game") for item in spec.rounds] != list(MIX_GAMES) or [item.data.get("level") for item in spec.rounds] != [1, 2, 3]:
            errors.append("mind mix has one level of each game, in order")
        elif abs(spec.round_duration - mix_average_round([item.data for item in spec.rounds])) > 1e-3:
            errors.append("round duration does not match the mind mix sections")
        if spec.difficulty != "hard":
            errors.append("mind mix is produced in hard")
    elif spec.puzzle_type == "memory_challenge" and spec.rounds:  # the earlier single board
        if spec.round_duration != memory_round_duration(spec.difficulty):
            errors.append("round duration does not match puzzle type")
    elif spec.puzzle_type == "shade_spot" and spec.rounds:
        from .config import SHADE_TIERS, shade_average_round
        if [item.data.get("tier") for item in spec.rounds] != list(SHADE_TIERS.get(len(spec.rounds), ())):
            errors.append("shade levels must grow from the first tier to the last")
        elif abs(spec.round_duration - shade_average_round([item.data for item in spec.rounds])) > 1e-3:
            errors.append("round duration does not match the shade levels")
        deltas, grids = [item.data.get("delta", 0) for item in spec.rounds], [item.data.get("grid", 0) for item in spec.rounds]
        if any(b > a for a, b in zip(deltas, deltas[1:])) or any(b < a for a, b in zip(grids, grids[1:])):
            errors.append("shade levels must get harder: bigger grids and smaller differences")
        if any(a.answer == b.answer for a, b in zip(spec.rounds, spec.rounds[1:])):
            errors.append("shade consecutive levels must not share an answer")
    elif spec.puzzle_type == "cup_shuffle" and spec.rounds:
        from .config import cup_average_round
        if len(spec.rounds) != 3 or [item.data.get("cups") for item in spec.rounds] != [3, 4, 5]:
            errors.append("cup shuffle has three levels with 3, 4 and 5 cups")
        elif abs(spec.round_duration - cup_average_round([item.data for item in spec.rounds])) > 1e-3:
            errors.append("round duration does not match the cup shuffle levels")
    elif spec.puzzle_type == "puzzle_fit" and spec.rounds and spec.rounds[0].data.get("version") == "fit_v12":
        from .config import fit_round
        if len(spec.rounds) != 1 or spec.round_duration != fit_round(spec.difficulty):
            errors.append("puzzle fit is one picture with its own duration")
    elif spec.puzzle_type == "line_follow" and spec.rounds and line_weave.is_weave(spec.rounds[0].data):
        if abs(spec.round_duration - line_weave.average_round(spec.rounds)) > 1e-3:
            errors.append("round duration does not match the line follow levels")
    elif spec.puzzle_type == "find_the_exit" and spec.rounds and spec.rounds[0].data.get("layout") in (find_the_exit.HARD_LAYOUT, "polar_v1", "cells_v1"):
        if abs(spec.round_duration - find_the_exit.hard_average_round(spec.rounds)) > 1e-3:
            errors.append("round duration does not match the maze levels")
    elif spec.puzzle_type == "cube_count" and spec.rounds and "mode" in spec.rounds[0].data:
        from .config import CUBE_MODES, cube_average_round, cube_mode
        modes = tuple(cube_mode(item.data) for item in spec.rounds)
        if modes != CUBE_MODES.get(len(spec.rounds)):
            errors.append("cube levels must use the formats of their position")
        elif abs(spec.round_duration - cube_average_round([item.data for item in spec.rounds])) > 1e-3:
            errors.append("round duration does not match the cube levels")
    elif spec.puzzle_type in DEFAULT_ROUNDS and spec.round_duration != round_duration(spec.puzzle_type, spec.difficulty):
        errors.append("round duration does not match puzzle type")
    if spec.puzzle_type in ("lucky_pick", "bounce_arena") and spec.difficulty is not None:
        errors.append(f"{spec.puzzle_type} must not have a difficulty")
    if spec.puzzle_type == "chess_mate":  # one still position, no intro, no reveal, no outro
        if spec.intro_duration != 0 or spec.outro_duration != 0:
            errors.append("chess_mate must have no intro or outro")
    elif spec.puzzle_type == "hidden_motion_hunt":
        if spec.difficulty is not None or spec.intro_duration != 0 or spec.outro_duration != 0:
            errors.append(f"{spec.puzzle_type} must have no difficulty, intro, or outro")
    elif spec.puzzle_type == "bounce_arena":
        from .config import BOUNCE_CTA_DURATION
        stored = float(spec.rounds[0].data.get("cta_duration", BOUNCE_CTA_DURATION)) if spec.rounds else BOUNCE_CTA_DURATION
        if spec.difficulty is not None or spec.intro_duration != 0 or abs(spec.outro_duration - stored) > 1e-6:
            errors.append("bounce_arena must have no difficulty/intro and must use its CTA outro")
    else:
        from .config import READY_GAMES
        intro_limit = 4.5 if spec.puzzle_type in READY_GAMES else 1.5  # hook + the 3 s READY screen (older videos: 1-2 s)
        adult_look = spec.puzzle_type in ("puzzle_fit", "cube_count", "flash_count", "memory_challenge", "matchstick", "cup_shuffle", "shade_spot", "mind_mix", "laser_maze") or (
            spec.puzzle_type == "quick_math" and bool(spec.rounds) and "format" in spec.rounds[0].data) or (spec.puzzle_type == "find_the_exit" and spec.difficulty == "hard") or (
            spec.puzzle_type == "lucky_pick" and bool(spec.rounds) and spec.rounds[0].data.get("map_version") is not None) or (
            spec.puzzle_type == "line_follow" and bool(spec.rounds) and line_weave.is_weave(spec.rounds[0].data))
        outro_limits = (1.2, 4.0) if adult_look else (0.7, 1.0)  # the shared end card is 3.6 s (older videos: 1.6 s)
        if not 0 < spec.intro_duration <= intro_limit or not outro_limits[0] <= spec.outro_duration <= outro_limits[1]:
            errors.append("intro/outro timing is invalid")
    fingerprints = [round_spec.fingerprint() for round_spec in spec.rounds]
    if len(fingerprints) != len(set(fingerprints)):
        errors.append("duplicate rounds are not allowed")
    for index, round_spec in enumerate(spec.rounds):
        if round_spec.index != index or round_spec.kind != spec.puzzle_type:
            errors.append(f"round {index} identity is invalid")
        errors.extend(f"round {index}: {error}" for error in round_errors(round_spec, spec.difficulty))
    return errors


def validate_spec(spec: VideoSpec) -> None:
    errors = validation_errors(spec)
    if errors:
        raise InvalidPuzzleError("; ".join(errors))
