from dataclasses import replace
from statistics import mean

import pytest

from puzzly.config import (DEFAULT_ROUNDS, MEMORY_BOARD_ENTRANCE, MEMORY_COVER_DURATION,
                           MEMORY_INTRO_DURATION, MEMORY_MEMORIZATION_DURATION,
                           MEMORY_QUESTION_DURATION, MEMORY_ROUND_DURATION,
                           MEMORY_THINKING_DURATION, OUTRO_DURATION)
from puzzly.memory_colors import COLOR_RULES, COLORS, distance_stats
from puzzly.models import RoundSpec
from puzzly.puzzles.memory_challenge import SHAPES, TIMED_QUESTIONS, TOKEN_COUNT, errors, generate
from puzzly.validation import validate_spec
from puzzly.visuals.memory import POSITIONS, SHAPE_LAYOUT, draw_memory_intro, memory_state, shape_mask, token_image, token_layout


@pytest.mark.parametrize("difficulty,video_count", [("easy", 500), ("medium", 500), ("hard", 700)])
def test_memory_volume_structure_determinism_and_color_rules(difficulty: str, video_count: int) -> None:
    minimums, averages = [], []
    for seed in range(video_count):
        spec = generate(100_000 + seed, difficulty); validate_spec(spec)
        assert spec.round_count == 1 and spec.total_duration == pytest.approx(MEMORY_INTRO_DURATION + MEMORY_ROUND_DURATION + OUTRO_DURATION)
        board = spec.rounds[0]; tokens = board.data["tokens"]
        assert len(tokens) == TOKEN_COUNT == 5
        assert len({token["shape"] for token in tokens}) == 5
        assert set(token["shape"] for token in tokens) <= set(SHAPES)
        assert len({token["color_id"] for token in tokens}) == 5
        assert [token["position"] for token in tokens] == [1, 2, 3, 4, 5]
        questions, final = board.data["question_order"], board.data["final_position"]
        assert len(questions) == TIMED_QUESTIONS == len(set(questions)) == 4
        assert final not in questions and set(questions) | {final} == {1,2,3,4,5}
        assert errors(board.data, board.answer, difficulty) == []
        minimum, average = distance_stats(COLORS[token["color_id"]] for token in tokens)
        assert minimum >= COLOR_RULES[difficulty]["min_distance"] - 1e-9
        minimums.append(minimum); averages.append(average)
    anchor = generate(90210, difficulty)
    assert anchor == generate(90210, difficulty) and anchor.fingerprint() == generate(90210, difficulty).fingerprint()
    test_memory_volume_structure_determinism_and_color_rules.stats[difficulty] = (mean(minimums), mean(averages))


test_memory_volume_structure_determinism_and_color_rules.stats = {}


def test_color_difficulty_statistics_are_ordered() -> None:
    stats = {}
    for difficulty, count in (("easy", 500), ("medium", 500), ("hard", 700)):
        pairs = [distance_stats(COLORS[token["color_id"]] for token in generate(seed, difficulty).rounds[0].data["tokens"]) for seed in range(count)]
        stats[difficulty] = (mean(item[0] for item in pairs), mean(item[1] for item in pairs))
    assert stats["easy"][0] > stats["medium"][0] > stats["hard"][0]
    assert stats["easy"][1] > stats["medium"][1] > stats["hard"][1]
    assert stats["hard"][0] >= COLOR_RULES["hard"]["min_distance"]


def test_single_board_timing_and_reveal_progression() -> None:
    spec = generate(44, "medium"); item = spec.rounds[0]
    assert DEFAULT_ROUNDS["memory_challenge"] == 1
    assert MEMORY_MEMORIZATION_DURATION == MEMORY_THINKING_DURATION == 3.0
    questions_start = MEMORY_BOARD_ENTRANCE + MEMORY_MEMORIZATION_DURATION + MEMORY_COVER_DURATION
    assert memory_state(.5, item)["phase"] == "memorize"
    assert memory_state(questions_start-.1, item)["phase"] == "cover"
    for index in range(4):
        state = memory_state(questions_start + index*MEMORY_QUESTION_DURATION + .5, item)
        assert state["phase"] == "question" and state["timer_active"]
        assert len(state["open_positions"]) == index
        revealed = memory_state(questions_start + index*MEMORY_QUESTION_DURATION + MEMORY_QUESTION_DURATION-.05, item)
        assert len(revealed["open_positions"]) == index + 1
    final_wait = memory_state(questions_start + 4*MEMORY_QUESTION_DURATION + .1, item)
    assert final_wait["phase"] == "final_wait" and len(final_wait["open_positions"]) == 4 and not final_wait["timer_active"]
    completed = memory_state(MEMORY_ROUND_DURATION-.1, item)
    assert completed["phase"] == "completed" and len(completed["open_positions"]) == 5 and not completed["timer_active"]
    with pytest.raises(ValueError): generate(44, "medium", round_count=4)


def test_shapes_fit_container_without_clipping() -> None:
    assert sum(x for x, _ in POSITIONS[:3]) / 3 == 540
    assert sum(x for x, _ in POSITIONS[3:]) / 2 == 540
    for shape in SHAPES:
        image = token_image(shape, "#397FAF", 256); box = image.getchannel("A").getbbox()
        assert box is not None and box[0] > 0 and box[1] > 0 and box[2] < 256 and box[3] < 256
        mask_box = shape_mask(shape, 256).getbbox(); assert mask_box is not None
        expected_x, expected_y = token_layout(shape, 256)["optical_center"]
        assert abs((mask_box[0]+mask_box[2])/2-expected_x) <= 1.5
        assert abs((mask_box[1]+mask_box[3])/2-expected_y) <= 1.5
        # The complete token, including its soft lower shadow, remains centered by eye.
        assert abs((box[0]+box[2])/2-128) <= 8
        assert abs((box[1]+box[3])/2-128) <= 8


def test_v6_2_intro_is_simple_and_uses_per_shape_optical_layout() -> None:
    import inspect
    source = inspect.getsource(draw_memory_intro)
    assert "_tile(" not in source and "number" not in source
    assert '"?"' in source and len(SHAPE_LAYOUT) == len(SHAPES)
    assert any(offset_y != 0 for _, _, offset_y in SHAPE_LAYOUT.values())


def test_fingerprint_covers_question_order_and_tokens() -> None:
    spec = generate(123, "easy"); board = spec.rounds[0]
    changed_data = {**board.data, "question_order": list(reversed(board.data["question_order"]))}
    changed_board = RoundSpec(0, board.kind, changed_data, {"question_order": changed_data["question_order"], "final_position": board.data["final_position"]})
    assert board.fingerprint() != changed_board.fingerprint()
    assert spec.fingerprint() != replace(spec, rounds=(changed_board,)).fingerprint()


def test_active_memory_pipeline_has_no_object_asset_fields() -> None:
    data = generate(8, "hard").rounds[0].data
    assert not ({"object_ids", "target_id", "similarity_groups"} & data.keys())
