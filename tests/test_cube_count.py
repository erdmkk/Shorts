from dataclasses import replace

import numpy as np

from puzzly.config import CUBE_ROUND_COLORS, CUBE_VISIBLE, round_duration
from puzzly.metadata import youtube_metadata
from puzzly.puzzles.cube_count import (COUNT_RANGES, GRID, MIN_BASE_VISIBLE, MIN_FOOTING_VISIBLE, MIN_SIDE_VISIBLE,
                                       MIN_TOP_VISIBLE, generate, readable, spaced, visibility)
from puzzly.registry import ACTIVE_PUZZLE_TYPES, MIXED_PUZZLE_TYPES
from puzzly.validation import round_errors, validation_errors


def test_cube_specs_are_valid_readable_and_escalate() -> None:
    for difficulty, seeds in (("easy", 40), ("medium", 30), ("hard", 20)):
        for seed in range(seeds):
            spec = generate(seed, difficulty)
            assert validation_errors(spec) == []
            assert spec.intro_duration == 1.0 and spec.outro_duration == 1.6
            assert spec.round_duration == round_duration("cube_count", difficulty)
            totals = [item.answer for item in spec.rounds]
            assert all(first != second for first, second in zip(totals, totals[1:]))
            colors = [item.data["color_id"] for item in spec.rounds]
            assert len(set(colors)) == len(colors) and set(colors) <= set(CUBE_ROUND_COLORS)  # a new colour every round
            assert [item.data["tier"] for item in spec.rounds] == [0, 0, 1, 2]
            for item in spec.rounds:
                data = item.data
                assert data["grid"] == GRID[difficulty]
                assert data["visible_seconds"] == CUBE_VISIBLE[difficulty]
                low, high = COUNT_RANGES[difficulty][data["tier"]]
                heights = [stack["height"] for stack in data["stacks"]]
                # Spread out: never 3 + 3 + 3; no height on more than half the stacks; 1 stack per 2.5 cubes.
                assert len(set(heights)) >= 2 and max(heights.count(h) for h in heights) <= (len(heights) + 1) // 2
                assert len(heights) * 2.5 >= sum(heights)
                if difficulty == "hard" and data["tier"] == 2:
                    assert 4 in heights and max(heights) == 4  # final Hard level adds 4-cube towers
                else:
                    assert max(heights) <= 3
                assert low <= item.answer == sum(stack["height"] for stack in data["stacks"]) <= high
                # Solvable: every stack shows its top, its footing, and a side of every cube.
                assert spaced([stack["cell"] for stack in data["stacks"]])
                for top, footing, *sides in visibility(data["grid"], data["stacks"]):
                    assert top >= MIN_TOP_VISIBLE and min(sides[0]) >= MIN_BASE_VISIBLE
                    assert footing >= MIN_FOOTING_VISIBLE  # where the stack meets the floor is always visible
                    assert all(max(side) >= MIN_SIDE_VISIBLE for side in sides)


def test_cube_generation_is_deterministic_and_hard_is_harder() -> None:
    assert generate(55, "hard") == generate(55, "hard")
    easy = [item.answer for seed in range(10) for item in generate(seed, "easy").rounds]
    hard = [item.answer for seed in range(10) for item in generate(seed, "hard").rounds]
    assert max(easy) <= 10 and 8 <= min(hard) and max(hard) <= 15 and sum(hard) > sum(easy) * 1.5
    assert CUBE_VISIBLE["hard"] < CUBE_VISIBLE["medium"] < CUBE_VISIBLE["easy"]


def test_stack_directly_behind_another_is_rejected() -> None:
    # A 3-stack one cell behind a 3-stack reads as a single 4-stack: never allowed.
    assert not spaced([[1, 1], [2, 2]])
    assert not spaced([[1, 1], [1, 2]]) and not spaced([[1, 1], [2, 1]])
    assert spaced([[1, 2], [2, 1]])  # screen-level neighbours stand side by side, not in front of each other
    item = generate(9, "hard").rounds[-1]
    behind = [{"cell": [1, 1], "height": 3}, {"cell": [2, 2], "height": 3}, {"cell": [4, 0], "height": 3},
              {"cell": [0, 4], "height": 3}]
    assert round_errors(replace(item, data={**item.data, "stacks": behind, "total": 12}, answer=12))


def test_fully_hidden_stack_is_rejected() -> None:
    item = generate(3, "hard").rounds[0]
    wall = [{"cell": [4, column], "height": 3} for column in range(5)] + [{"cell": [3, 2], "height": 1}]
    # A short stack directly behind a full-height row is not readable.
    assert not readable(5, [{"cell": [3, 3], "height": 1}, {"cell": [4, 4], "height": 3}, {"cell": [4, 3], "height": 3},
                           {"cell": [3, 4], "height": 3}])
    assert round_errors(replace(item, data={**item.data, "stacks": wall, "total": 16}, answer=16))
    assert round_errors(replace(item, answer=item.answer + 1))


def test_cube_count_is_registered_for_ui_and_mixed_mode() -> None:
    assert "cube_count" in ACTIVE_PUZZLE_TYPES and "cube_count" in MIXED_PUZZLE_TYPES
    spec = generate(8, "medium")
    meta = youtube_metadata(spec)
    assert "#shorts" in meta["youtube_title"] and "cube" in meta["youtube_tags"]


def test_cube_frames_render_flash_hide_and_count() -> None:
    from puzzly.renderer import render_cover, render_frame
    from puzzly.visuals.cube_count import phases
    spec = generate(21, "hard")
    times = phases(spec)
    start = spec.intro_duration
    visible = np.asarray(render_frame(spec, start + times["visible_end"] - .1, (540, 960)))
    hidden = np.asarray(render_frame(spec, start + times["hide_end"] + 1.0, (540, 960)))
    counted = np.asarray(render_frame(spec, start + times["count_end"] + .5, (540, 960)))
    board = (slice(250, 700), slice(40, 500))
    assert np.abs(visible[board].astype(int) - hidden[board].astype(int)).mean() > 5  # cubes are gone while thinking
    assert np.abs(visible[board].astype(int) - counted[board].astype(int)).mean() < np.abs(
        visible[board].astype(int) - hidden[board].astype(int)).mean()  # cubes come back for the count
    assert render_cover(spec).size == (1080, 1920)
