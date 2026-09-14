from dataclasses import replace

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
                expected = 4 if difficulty == "hard" else 3
                assert len(data["candidates"]) == len({tuple(candidate) for candidate in data["candidates"]}) == expected
                assert data["board_kind"] == "jigsaw"
                assert len(data["piece_edges"]) == data["rows"] * data["columns"]
                assert data["candidates"].count(data["hole_edges"]) == 1
                assert data["candidates"][data["correct_index"]] == data["hole_edges"]
    assert rounds_seen >= 1000


def test_puzzle_fit_is_deterministic() -> None:
    assert generate(701, "hard", round_count=5) == generate(701, "hard", round_count=5)


def test_visual_state_progression_teaches_the_game() -> None:
    assert [visual_state(moment) for moment in (0.1, 0.5, 2.0, 4.4, 4.8, 5.4)] == [
        "choices", "thinking", "thinking", "highlight", "moving", "solved",
    ]


def test_hard_has_one_extra_second_and_four_choices_in_two_by_two_layout() -> None:
    assert thinking_duration("puzzle_fit", "easy") == thinking_duration("puzzle_fit", "medium") == 4.0
    assert thinking_duration("puzzle_fit", "hard") == 5.0
    assert round_duration("puzzle_fit", "hard") == round_duration("puzzle_fit", "medium") + 1.0
    assert visual_state(4.8, "hard") == "thinking"
    assert visual_state(5.4, "hard") == "highlight"
    for difficulty, expected_bounds in (("easy", CARD_BOUNDS), ("medium", CARD_BOUNDS), ("hard", HARD_CARD_BOUNDS)):
        spec = generate(120, difficulty)
        assert spec.round_duration == round_duration("puzzle_fit", difficulty)
        for item in spec.rounds:
            assert tuple(tuple(bounds) for bounds in item.data["candidate_cards"]) == expected_bounds
            assert len(item.data["candidates"]) == (4 if difficulty == "hard" else 3)


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
    import numpy as np
    from puzzly.renderer import render_cover, render_frame
    spec = generate(44)
    early = np.asarray(render_frame(spec, spec.intro_duration + 0.4, (540, 960)))
    late = np.asarray(render_frame(spec, spec.intro_duration + 4.2, (540, 960)))
    # Board and loose candidates remain identical; only the timer changes below.
    assert np.array_equal(early[140:750], late[140:750])


def test_intro_is_fixed_concept_art_and_does_not_use_first_board() -> None:
    import numpy as np
    from puzzly.renderer import render_cover, render_frame
    spec = generate(44, "hard")
    changed = replace(spec, rounds=generate(99, "hard").rounds)
    assert np.array_equal(np.asarray(render_frame(spec, .9, (540, 960))),
                          np.asarray(render_frame(changed, .9, (540, 960))))
    assert np.array_equal(np.asarray(render_cover(spec)), np.asarray(render_cover(changed)))
