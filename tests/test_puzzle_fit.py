from dataclasses import replace

import pytest

from puzzly.config import round_duration, thinking_duration
from puzzly.puzzles.puzzle_fit import CARD_BOUNDS, HARD_CARD_BOUNDS, generate, visual_state
from puzzly.validation import validation_errors


def test_at_least_1000_puzzle_fit_rounds_are_valid() -> None:
    rounds_seen = 0
    for seed in range(70):
        for difficulty in ("easy", "medium", "hard"):
            spec = generate(seed, difficulty)
            assert validation_errors(spec) == []
            for round_spec in spec.rounds:
                rounds_seen += 1
                data = round_spec.data
                expected = 9 if difficulty == "hard" else 3
                assert len(data["candidates"]) == len({tuple(candidate) for candidate in data["candidates"]}) == expected
                assert data["board_kind"] == "jigsaw"
                assert len(data["piece_edges"]) == data["rows"] * data["columns"]
                assert data["candidates"].count(data["hole_edges"]) == 1
                assert data["candidates"][data["correct_index"]] == data["hole_edges"]
    assert rounds_seen >= 1000


def test_puzzle_fit_is_deterministic() -> None:
    assert generate(701, "hard", round_count=5) == generate(701, "hard", round_count=5)


def test_visual_state_progression_teaches_the_game() -> None:
    assert [visual_state(moment) for moment in (0.1, 0.5, 2.0, 5.4, 5.8, 6.0, 6.4)] == [
        "choices", "thinking", "thinking", "eliminating", "eliminating", "moving", "solved",
    ]


def test_hard_uses_nine_choices_five_second_thinking_and_complex_board() -> None:
    assert all(thinking_duration("puzzle_fit", difficulty) == 5.0 for difficulty in ("easy", "medium", "hard"))
    assert round_duration("puzzle_fit", "hard") == round_duration("puzzle_fit", "medium") == 7.2
    assert visual_state(5.3, "hard") == "thinking"
    assert visual_state(5.4, "hard") == "eliminating"
    for difficulty, expected_bounds in (("easy", CARD_BOUNDS), ("medium", CARD_BOUNDS), ("hard", HARD_CARD_BOUNDS)):
        spec = generate(120, difficulty)
        assert spec.round_duration == round_duration("puzzle_fit", difficulty)
        for item in spec.rounds:
            assert tuple(tuple(bounds) for bounds in item.data["candidate_cards"]) == expected_bounds
            assert len(item.data["candidates"]) == (9 if difficulty == "hard" else 3)
            if difficulty == "hard":
                assert item.data["rows"] * item.data["columns"] in (6, 9)


def test_hard_uses_both_readable_six_and_nine_piece_layouts() -> None:
    layouts = {
        (item.data["rows"], item.data["columns"])
        for seed in range(40) for item in generate(seed, "hard").rounds
    }
    assert layouts == {(2, 3), (3, 3)}
    assert len(HARD_CARD_BOUNDS) == 9


def test_hole_geometry_exactly_matches_correct_piece() -> None:
    for difficulty in ("easy", "medium", "hard"):
        for round_spec in generate(888, difficulty).rounds:
            data = round_spec.data
            assert data["piece_edges"][data["hole_slot"]] == data["hole_edges"]
            assert data["candidates"][data["correct_index"]] == data["hole_edges"]
            assert all(candidate != data["hole_edges"] for index, candidate in enumerate(data["candidates"]) if index != data["correct_index"])


def test_board_variety_includes_corner_edge_and_center_holes() -> None:
    layouts, piece_kinds = set(), set()
    for seed in range(40):
        for item in generate(seed, "medium").rounds:
            data = item.data
            layouts.add((data["rows"], data["columns"]))
            piece_kinds.add(data["hole_edges"].count(0))
    assert layouts == {(2, 2), (2, 3), (3, 3)}
    assert {0, 1, 2}.issubset(piece_kinds)


def test_thinking_does_not_reveal_or_move_the_answer() -> None:
    from puzzly.puzzles.puzzle_fit import phase_times
    from puzzly.visuals.puzzle_fit import BOB_AMPLITUDE, bob_offset, elimination_order
    spec = generate(44, "hard")
    think_end = phase_times("hard")["think_end"]
    for item in spec.rounds:
        data = item.data
        order = elimination_order(data)
        assert sorted(order + [data["correct_index"]]) == list(range(9))
        # Every candidate floats with the same amplitude, so motion never singles out the answer.
        for index in range(9):
            assert max(abs(bob_offset(index, step / 30)) for step in range(60)) == pytest.approx(BOB_AMPLITUDE, rel=.02)
    assert all(visual_state(moment, "hard") in ("choices", "thinking") for moment in (0.0, 1.0, think_end - .01))


def test_hook_intro_and_cover_show_first_level_unsolved() -> None:
    import numpy as np
    from puzzly.renderer import render_cover, render_frame
    from puzzly.visuals.puzzle_fit import COVER_TIME
    spec = generate(44, "hard")
    changed = replace(spec, rounds=generate(99, "hard").rounds)
    assert not np.array_equal(np.asarray(render_frame(spec, .6, (540, 960))), np.asarray(render_frame(changed, .6, (540, 960))))
    assert render_cover(spec).size == (1080, 1920)
    assert COVER_TIME < spec.intro_duration


def test_levels_escalate_within_each_video() -> None:
    for seed in range(30):
        for difficulty in ("easy", "medium", "hard"):
            rounds = generate(seed, difficulty).rounds
            assert [item.data["level"] for item in rounds] == [1, 2, 3, 4, 5]
            sizes = [item.data["rows"] * item.data["columns"] for item in rounds]
            assert sizes == sorted(sizes) and sizes[0] < sizes[-1]
            assert len({item.data["art_style"] for item in rounds}) == 5
        final = generate(seed, "hard").rounds[-1].data
        assert final["hole_slot"] == 4 and 0 not in final["hole_edges"]
