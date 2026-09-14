from __future__ import annotations

from .config import DEFAULT_ROUNDS, FPS, round_duration
from .puzzles import find_the_exit, flash_count, hidden_motion_hunt, lucky_pick, line_follow, memory_challenge
from .models import RoundSpec, VideoSpec
from .puzzles.puzzle_fit import candidate_card_bounds


class InvalidPuzzleError(ValueError):
    pass


def round_errors(round_spec: RoundSpec, difficulty: str | None = None) -> list[str]:
    data, errors = round_spec.data, []
    if round_spec.kind == "quick_math":
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
    elif round_spec.kind == "puzzle_fit":
        hole, candidates, correct = data.get("hole_edges"), data.get("candidates", []), data.get("correct_index")
        cards = [tuple(bounds) for bounds in data.get("candidate_cards", [])]
        expected_count = 4 if difficulty == "hard" else 3
        if len(candidates) != expected_count or len({tuple(candidate) for candidate in candidates}) != expected_count:
            errors.append(f"puzzle fit requires {expected_count} unique candidates")
        if candidates.count(hole) != 1 or correct not in range(expected_count) or (correct in range(expected_count) and candidates[correct] != hole):
            errors.append("puzzle fit must have exactly one correct candidate")
        rows, columns = data.get("rows", 0), data.get("columns", 0)
        pieces = data.get("piece_edges", [])
        slot = data.get("hole_slot", -1)
        if data.get("board_kind") != "jigsaw" or (rows, columns) not in ((2, 2), (2, 3), (3, 3)) or len(pieces) != rows * columns or len(data.get("piece_colors", [])) != rows * columns:
            errors.append("puzzle fit board is not coherent")
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
    elif round_spec.kind == "hidden_motion_hunt":
        errors.extend(hidden_motion_hunt.errors(data))
    else:
        errors.append("unsupported round kind")
    return errors


def validation_errors(spec: VideoSpec) -> list[str]:
    errors: list[str] = []
    if spec.puzzle_type not in DEFAULT_ROUNDS or spec.fps != FPS:
        errors.append("unsupported video type or FPS")
    if spec.puzzle_type in ("memory_challenge", "lucky_pick", "hidden_motion_hunt"):
        if len(spec.rounds) != 1:
            errors.append(f"{spec.puzzle_type} video must contain exactly one game")
    elif not 3 <= len(spec.rounds) <= 5:
        errors.append("video must contain 3 to 5 rounds")
    if spec.puzzle_type == "flash_count" and spec.rounds:
        identities = {(item.data.get("shape_id"), item.data.get("color_id")) for item in spec.rounds}
        counts = [item.data.get("displayed_count") for item in spec.rounds]
        if len(identities) != 1:
            errors.append("flash video must use one shape and one color identity")
        if any(first == second for first, second in zip(counts, counts[1:])):
            errors.append("flash consecutive rounds must not repeat a count")
    if spec.puzzle_type == "lucky_pick":
        if not spec.rounds or spec.round_duration != spec.rounds[0].data.get("timeline_duration"):
            errors.append("lucky round duration does not match its route timeline")
    elif spec.puzzle_type in DEFAULT_ROUNDS and spec.round_duration != round_duration(spec.puzzle_type, spec.difficulty):
        errors.append("round duration does not match puzzle type")
    if spec.puzzle_type == "lucky_pick" and spec.difficulty is not None:
        errors.append("lucky pick must not have a difficulty")
    if spec.puzzle_type == "hidden_motion_hunt":
        if spec.difficulty is not None or spec.intro_duration != 0 or spec.outro_duration != 0:
            errors.append("hidden motion hunt must have no difficulty, intro, or outro")
    else:
        intro_limit = 2.0 if spec.puzzle_type == "memory_challenge" else 1.5
        if not 0 < spec.intro_duration <= intro_limit or not 0.7 <= spec.outro_duration <= 1.0:
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
