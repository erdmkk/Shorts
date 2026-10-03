from dataclasses import replace
from statistics import mean

import pytest

from puzzly.config import (DEFAULT_ROUNDS, MEMORY_GRID_QUESTIONS, MEMORY_GRID_TOKENS, MEMORY_MEMORIZE,
                           MEMORY_QUESTION_DURATION, MEMORY_THINKING_DURATION, PUZZLE_FIT_INTRO_DURATION,
                           PUZZLE_FIT_OUTRO_DURATION, memory_round_duration)
from puzzly.memory_colors import GRID_COLOR_LEVELS, GRID_COLOR_RULES, GRID_COLORS, GRID_MIN_LIGHTNESS, distance_stats
from puzzly.models import RoundSpec
from puzzly.puzzles.memory_challenge import MEMORY_SHAPES, errors, generate as generate_current
from puzzly.validation import validate_spec
from puzzly.visuals.memory import grid_center, grid_phases, memory_state, shape_mask, token_image, token_layout


def generate(*args, **kwargs):
    """The earlier single 3x3 board (the three-level game is tested in test_memory_levels.py)."""
    return generate_current(*args, classic=True, **kwargs)


@pytest.mark.parametrize("difficulty,video_count", [("easy", 500), ("medium", 500), ("hard", 700)])
def test_grid_boards_are_valid_deterministic_and_follow_color_rules(difficulty: str, video_count: int) -> None:
    for seed in range(video_count):
        level = GRID_COLOR_LEVELS[seed % len(GRID_COLOR_LEVELS)]
        spec = generate(100_000 + seed, difficulty, f"colors_{level}")
        validate_spec(spec)
        assert spec.round_count == 1 and spec.intro_duration == PUZZLE_FIT_INTRO_DURATION + 3.0  # hook + READY screen
        assert spec.total_duration == pytest.approx(spec.intro_duration + memory_round_duration(difficulty)
                                                    + PUZZLE_FIT_OUTRO_DURATION)
        board = spec.rounds[0]
        tokens = board.data["tokens"]
        shapes = {token["shape"] for token in tokens}
        assert len(tokens) == MEMORY_GRID_TOKENS == 9 and len(shapes) == 9 and shapes <= set(MEMORY_SHAPES)
        assert not {"pentagon", "hexagon"} <= shapes
        assert len({token["color_id"] for token in tokens}) == 9
        assert [token["position"] for token in tokens] == list(range(1, 10))
        questions, final = board.data["question_order"], board.data["final_position"]
        assert len(questions) == len(set(questions)) == MEMORY_GRID_QUESTIONS == 8
        assert final not in questions and set(questions) | {final} == set(range(1, 10))
        assert board.data["memorization_seconds"] == MEMORY_MEMORIZE[difficulty]
        assert errors(board.data, board.answer, difficulty) == []
        colors = [GRID_COLORS[token["color_id"]] for token in tokens]
        assert board.data["color_level"] == level
        assert distance_stats(colors)[0] >= GRID_COLOR_RULES[level]["min_distance"] - 1e-9
        assert all(color.lightness >= GRID_MIN_LIGHTNESS for color in colors)
    assert generate(90210, difficulty) == generate(90210, difficulty)


def test_color_level_orders_color_closeness_and_memorize_time() -> None:
    stats = {}
    for level in GRID_COLOR_LEVELS:
        pairs = [distance_stats(GRID_COLORS[token["color_id"]]
                                for token in generate(seed, "hard", f"colors_{level}").rounds[0].data["tokens"])
                 for seed in range(60)]
        stats[level] = (mean(item[0] for item in pairs), mean(item[1] for item in pairs))
    assert stats[1][1] > stats[2][1] > stats[3][1] > stats[4][1]  # higher level = closer colours
    assert stats[1][0] > stats[4][0]
    assert generate(1, "hard").rounds[0].data["color_level"] == 1  # distinct colours unless the UI asks otherwise
    assert MEMORY_MEMORIZE["easy"] >= MEMORY_MEMORIZE["medium"] >= MEMORY_MEMORIZE["hard"] == 7.0


def test_eight_questions_then_the_ninth_opens_by_itself() -> None:
    spec = generate(44, "medium")
    item = spec.rounds[0]
    times = grid_phases(item)
    assert DEFAULT_ROUNDS["memory_challenge"] == 1 and MEMORY_THINKING_DURATION == 3.0
    assert memory_state(times["memorize_start"] + .5, item)["phase"] == "memorize"
    assert memory_state(times["questions"] - .1, item)["phase"] == "cover"
    for index in range(8):
        state = memory_state(times["questions"] + index * MEMORY_QUESTION_DURATION + .5, item)
        assert state["phase"] == "question" and state["timer_active"] and len(state["open_positions"]) == index
        assert state["target_position"] == item.data["question_order"][index]
        revealed = memory_state(times["questions"] + (index + 1) * MEMORY_QUESTION_DURATION - .05, item)
        assert len(revealed["open_positions"]) == index + 1
    waiting = memory_state(times["final"] + .1, item)
    assert waiting["phase"] == "final_wait" and len(waiting["open_positions"]) == 8 and not waiting["timer_active"]
    completed = memory_state(spec.round_duration - .1, item)
    assert completed["phase"] == "completed" and len(completed["open_positions"]) == 9
    with pytest.raises(ValueError):
        generate(44, "medium", round_count=4)


def test_grid_is_centered_and_every_shape_fits_its_card() -> None:
    assert sum(grid_center(position)[0] for position in range(1, 10)) / 9 == 540
    xs = sorted({grid_center(position)[0] for position in range(1, 10)})
    assert len(xs) == 3 and xs[0] >= 100 and xs[-1] <= 980
    for shape in MEMORY_SHAPES:
        image = token_image(shape, "#4FC3F7", 256)
        box = image.getchannel("A").getbbox()
        assert box is not None and box[0] > 0 and box[1] > 0 and box[2] < 256 and box[3] < 256
        mask_box = shape_mask(shape, 256).getbbox()
        expected_x, expected_y = token_layout(shape, 256)["optical_center"]
        assert abs((mask_box[0] + mask_box[2]) / 2 - expected_x) <= 1.5
        assert abs((mask_box[1] + mask_box[3]) / 2 - expected_y) <= 1.5


def test_fingerprint_covers_question_order_and_tokens() -> None:
    spec = generate(123, "easy")
    board = spec.rounds[0]
    changed = {**board.data, "question_order": list(reversed(board.data["question_order"]))}
    changed_board = RoundSpec(0, board.kind, changed, {"question_order": changed["question_order"],
                                                       "final_position": board.data["final_position"]})
    assert board.fingerprint() != changed_board.fingerprint()
    assert spec.fingerprint() != replace(spec, rounds=(changed_board,)).fingerprint()


def test_invalid_boards_are_rejected() -> None:
    board = generate(5, "hard", "colors_4").rounds[0]
    easy_colors = generate(5, "hard", "colors_1").rounds[0].data["tokens"]
    mixed = [{**token, "color_id": easy["color_id"], "color_value": easy["color_value"]}
             for token, easy in zip(board.data["tokens"], easy_colors)]
    assert errors({**board.data, "tokens": mixed}, board.answer, "hard")  # level 4 must use close tones
    assert errors({**board.data, "question_order": board.data["question_order"][:4]}, board.answer, "hard")


def test_memory_frames_render_board_questions_and_cover() -> None:
    import numpy as np
    from puzzly.renderer import render_cover, render_frame
    spec = generate(21, "hard")
    times = grid_phases(spec.rounds[0])
    start = spec.intro_duration
    memorize = np.asarray(render_frame(spec, start + 1.0, (540, 960)))
    question = np.asarray(render_frame(spec, start + times["questions"] + 1.0, (540, 960)))
    assert np.abs(memorize.astype(int) - question.astype(int)).mean() > 5
    assert render_cover(spec).size == (1080, 1920)
