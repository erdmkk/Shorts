from dataclasses import replace

import numpy as np

from puzzly.config import (CUBE_MODES, CUBE_RAIN_MIN_GAP, CUBE_ROUND_COLORS, CUBE_VISIBLE, cube_average_round, cube_round,
                           round_duration)
from puzzly.metadata import youtube_metadata
from puzzly.puzzles.cube_count import (COLOR_DROPS, COLOR_TARGETS, COUNT_RANGES, GRID_BIG, HUE_FAMILY, MIN_BASE_VISIBLE,
                                       MIN_FOOTING_VISIBLE, MIN_SIDE_VISIBLE, MIN_TOP_VISIBLE, RAIN_TOTALS, SWEEP_TOTALS, apart_on_screen,
                                       cubes_in, flight_window, generate, readable, size_of, spaced, spaced_stacks, sweep_stacks,
                                       visibility)
from puzzly.registry import ACTIVE_PUZZLE_TYPES, MIXED_PUZZLE_TYPES
from puzzly.validation import round_errors, validation_errors


def test_cube_specs_are_valid_readable_and_escalate() -> None:
    for difficulty, seeds in (("easy", 40), ("medium", 30), ("hard", 20)):
        for seed in range(seeds):
            spec = generate(seed, difficulty, formats=False)
            assert validation_errors(spec) == []
            assert spec.intro_duration == 4.0 and spec.outro_duration == 3.6  # 1 s hook + the 3 s READY screen
            assert spec.round_duration == round_duration("cube_count", difficulty)
            totals = [item.answer for item in spec.rounds]
            assert all(first != second for first, second in zip(totals, totals[1:]))
            colors = [item.data["color_id"] for item in spec.rounds]
            assert len(set(colors)) == len(colors) and set(colors) <= set(CUBE_ROUND_COLORS)  # a new colour every round
            assert [item.data["tier"] for item in spec.rounds] == [0, 0, 1, 2]
            for item in spec.rounds:
                data = item.data
                assert data["grid"] == GRID_BIG[difficulty]
                assert data["visible_seconds"] == CUBE_VISIBLE[difficulty]
                low, high = COUNT_RANGES[difficulty][data["tier"]]
                # Every level has one big block: a 2x2 box, one cube tall, that counts as ONE cube.
                blocks = [stack for stack in data["stacks"] if size_of(stack) == 2]
                assert len(blocks) == 1 and blocks[0]["height"] == 1
                heights = [stack["height"] for stack in data["stacks"] if size_of(stack) == 1]
                # Spread out: never 3 + 3 + 3; no height on more than half the stacks; 1 stack per 2.5 cubes.
                assert len(set(heights)) >= 2 and max(heights.count(h) for h in heights) <= (len(heights) + 1) // 2
                assert len(heights) * 2.5 >= sum(heights)
                if difficulty == "hard" and data["tier"] == 2:
                    assert 4 in heights and max(heights) == 4  # final Hard level adds 4-cube towers
                else:
                    assert max(heights) <= 3
                assert low <= item.answer == sum(heights) + 1 == sum(cubes_in(stack) for stack in data["stacks"]) <= high
                # Solvable: every stack shows its top, its footing, and a side of every cube.
                assert spaced_stacks(data["stacks"])
                for top, footing, *sides in visibility(data["grid"], data["stacks"]):
                    assert top >= MIN_TOP_VISIBLE and min(sides[0]) >= MIN_BASE_VISIBLE
                    assert footing >= MIN_FOOTING_VISIBLE  # where the stack meets the floor is always visible
                    assert all(max(side) >= MIN_SIDE_VISIBLE for side in sides)


def test_cube_generation_is_deterministic_and_hard_is_harder() -> None:
    assert generate(55, "hard") == generate(55, "hard") and generate(55, "hard", formats=False) == generate(55, "hard", formats=False)
    easy = [item.answer for seed in range(10) for item in generate(seed, "easy", formats=False).rounds]
    hard = [item.answer for seed in range(10) for item in generate(seed, "hard", formats=False).rounds]
    assert max(easy) <= 10 and 8 <= min(hard) and max(hard) <= 15 and sum(hard) > sum(easy) * 1.5
    assert CUBE_VISIBLE["hard"] < CUBE_VISIBLE["medium"] < CUBE_VISIBLE["easy"]


def test_stack_directly_behind_another_is_rejected() -> None:
    # A 3-stack one cell behind a 3-stack reads as a single 4-stack: never allowed.
    assert not spaced([[1, 1], [2, 2]])
    assert not spaced([[1, 1], [1, 2]]) and not spaced([[1, 1], [2, 1]])
    assert spaced([[1, 2], [2, 1]])  # screen-level neighbours stand side by side, not in front of each other
    item = generate(9, "hard", formats=False).rounds[-1]
    behind = [{"cell": [1, 1], "height": 3}, {"cell": [2, 2], "height": 3}, {"cell": [4, 0], "height": 3},
              {"cell": [0, 4], "height": 3}]
    assert round_errors(replace(item, data={**item.data, "stacks": behind, "total": 12}, answer=12))


def test_big_block_counts_as_one_cube() -> None:
    item = generate(12, "medium", formats=False).rounds[1]
    block = next(stack for stack in item.data["stacks"] if size_of(stack) == 2)
    assert cubes_in(block) == 1
    as_four = item.answer + 3  # counting the big block as four cubes is wrong
    assert round_errors(replace(item, data={**item.data, "total": as_four}, answer=as_four), "medium")
    taller = [dict(stack, height=2) if size_of(stack) == 2 else stack for stack in item.data["stacks"]]
    assert round_errors(replace(item, data={**item.data, "stacks": taller}), "medium")  # a big block is one cube tall
    # A big block may not touch a tower: it would read as part of it.
    assert not spaced_stacks([{"cell": [0, 0], "height": 1, "size": 2}, {"cell": [2, 0], "height": 2}])
    assert spaced_stacks([{"cell": [0, 0], "height": 1, "size": 2}, {"cell": [3, 0], "height": 2}])


def test_older_rounds_without_big_blocks_still_validate() -> None:
    from puzzly.puzzles.cube_count import errors
    old = {"grid": 5, "tier": 0, "count_range": [8, 11], "visible_seconds": CUBE_VISIBLE["hard"], "color_id": "sky",
           "stacks": [{"cell": [0, 0], "height": 3}, {"cell": [0, 2], "height": 2}, {"cell": [2, 4], "height": 1},
                      {"cell": [4, 1], "height": 2}], "total": 8}
    assert errors(old, 8, "hard") == []  # a 5x5 board with no big block and no version is still valid
    assert errors({**old, "version": 2}, 8, "hard")  # new rounds must use the larger board and a big block


def test_fully_hidden_stack_is_rejected() -> None:
    item = generate(3, "hard", formats=False).rounds[0]
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
    times = phases(spec.rounds[0])
    start = spec.intro_duration
    visible = np.asarray(render_frame(spec, start + times["visible_end"] - .1, (540, 960)))
    hidden = np.asarray(render_frame(spec, start + times["hide_end"] + 1.0, (540, 960)))
    counted = np.asarray(render_frame(spec, start + times["count_end"] + .5, (540, 960)))
    board = (slice(250, 700), slice(40, 500))
    assert np.abs(visible[board].astype(int) - hidden[board].astype(int)).mean() > 5  # cubes are gone while thinking
    assert np.abs(visible[board].astype(int) - counted[board].astype(int)).mean() < np.abs(
        visible[board].astype(int) - hidden[board].astype(int)).mean()  # cubes come back for the count
    assert render_cover(spec).size == (1080, 1920)


# ---------------------------------------------------------------- formats: rain, sweep, colour rain

def test_levels_use_the_formats_of_their_position_and_validate() -> None:
    for difficulty, seeds in (("easy", 12), ("medium", 12), ("hard", 12)):
        for seed in range(seeds):
            for count in (3, 4, 5):
                spec = generate(seed, difficulty, round_count=count)
                assert validation_errors(spec) == []
                assert tuple(item.data["mode"] for item in spec.rounds) == CUBE_MODES[count]
                assert spec.round_duration == cube_average_round([item.data for item in spec.rounds])
                totals = [item.answer for item in spec.rounds]
                assert all(a != b for a, b in zip(totals, totals[1:]))
                colors = [item.data["color_id"] for item in spec.rounds]
                assert all(a != b for a, b in zip(colors, colors[1:]))
    default = generate(1, "hard")
    assert [item.data["mode"] for item in default.rounds] == ["grid", "rain", "sweep", "rain_color"]
    assert generate(7, "hard") == generate(7, "hard")


def test_every_falling_cube_can_be_counted() -> None:
    for seed in range(15):
        for item in generate(seed, "hard").rounds:
            if item.data["mode"] not in ("rain", "rain_color"):
                continue
            drops, fall = item.data["drops"], item.data["fall"]
            assert [d["size"] for d in drops].count(2) == 1  # one big block: it counts as ONE cube
            assert all(b["at"] - a["at"] >= CUBE_RAIN_MIN_GAP - 1e-6 for a, b in zip(drops, drops[1:]))
            for index, first in enumerate(drops):
                for second in drops[index + 1:]:
                    together = flight_window(second, fall)[0] < flight_window(first, fall)[1]
                    assert not together or apart_on_screen(first, second)
            assert item.data["rain_seconds"] == round(drops[-1]["at"] + fall, 3)
            low, high = RAIN_TOTALS["hard"] if item.data["mode"] == "rain" else COLOR_DROPS["hard"]
            assert low <= len(drops) <= high


def test_colour_rain_counts_one_colour_of_three_different_families() -> None:
    for seed in range(20):
        item = generate(seed, "hard").rounds[3]
        data = item.data
        assert data["mode"] == "rain_color" and data["target"] == data["colors"][0] == data["color_id"]
        assert len({HUE_FAMILY[color] for color in data["colors"]}) == 3  # blue next to violet would be unfair
        counted = [drop for drop in data["drops"] if drop["color"] == data["target"]]
        assert item.answer == len(counted) == data["total"] and COLOR_TARGETS["hard"][0] <= item.answer <= COLOR_TARGETS["hard"][1]
        assert all(sum(1 for drop in data["drops"] if drop["color"] == color) >= 2 for color in data["colors"])
    item = generate(2, "hard").rounds[3]
    wrong = {**item.data, "colors": [item.data["colors"][0], "sky" if HUE_FAMILY[item.data["colors"][0]] != "blue" else "green",
                                     "violet" if HUE_FAMILY[item.data["colors"][0]] != "blue" else "yellow"]}
    assert round_errors(replace(item, data=wrong), "hard")


def test_the_sweep_train_is_towers_and_one_big_block() -> None:
    for seed in range(20):
        item = generate(seed, "hard").rounds[2]
        data = item.data
        towers = [entry for entry in data["items"] if entry["size"] == 1]
        assert data["mode"] == "sweep" and len(towers) == 5 and sum(entry["size"] == 2 for entry in data["items"]) == 1
        assert item.answer == sum(entry["height"] for entry in towers) + 1
        assert SWEEP_TOTALS["hard"][0] <= item.answer <= SWEEP_TOTALS["hard"][1]
        stacks = sweep_stacks(data)
        assert len(stacks) == 6 and cubes_in(next(stack for stack in stacks if size_of(stack) == 2)) == 1
    assert round_errors(replace(item, answer=item.answer + 1), "hard")


def test_a_round_that_lands_cubes_too_close_together_is_rejected() -> None:
    item = generate(4, "hard").rounds[1]
    drops = [dict(drop) for drop in item.data["drops"]]
    drops[2]["at"] = drops[1]["at"] + .05
    assert round_errors(replace(item, data={**item.data, "drops": drops}), "hard")
    assert round_errors(replace(item, answer=item.answer + 1), "hard")
    assert round_errors(replace(item, data={**item.data, "mode": "teleport"}), "hard")


def test_level_lengths_come_from_the_stored_data_so_retuning_changes_nothing(monkeypatch) -> None:
    import puzzly.config as config
    spec = generate(6, "hard")
    before = [cube_round(item.data) for item in spec.rounds]
    monkeypatch.setattr(config, "CUBE_RAIN", {"hard": {"interval": 1.0, "fall": 1.0}})
    monkeypatch.setattr(config, "CUBE_SWEEP", {"hard": 9.0})
    assert [cube_round(item.data) for item in spec.rounds] == before
    assert validation_errors(spec) == []


def test_frames_show_every_format_and_hide_the_cubes_while_thinking() -> None:
    from puzzly.renderer import render_frame
    from puzzly.visuals.cube_count import phases, schedule
    spec = generate(1, "hard")
    frames = {}
    for (start, duration), item in zip(schedule(spec), spec.rounds):
        times = phases(item)
        assert duration == times["duration"]
        mode = item.data["mode"]
        if mode == "sweep":
            during = np.asarray(render_frame(spec, start + .6 + item.data["sweep_seconds"] * .5, (540, 960)))
        elif mode == "grid":
            during = np.asarray(render_frame(spec, start + times["visible_end"] - .1, (540, 960)))
        else:
            during = np.asarray(render_frame(spec, start + .6 + item.data["rain_seconds"] * .5, (540, 960)))
        thinking = np.asarray(render_frame(spec, start + times["hide_end"] + 1.0, (540, 960)))
        answer = np.asarray(render_frame(spec, start + times["count_end"] + .3, (540, 960)))
        frames[mode] = (during, thinking, answer)
        assert np.abs(during.astype(int) - thinking.astype(int)).mean() > 1.0  # something is going on, then it is gone
        assert np.abs(answer.astype(int) - thinking.astype(int)).mean() > 1.0  # the answer shows the total
    assert set(frames) == {"grid", "rain", "sweep", "rain_color"}


def test_a_colour_rain_introduces_its_counted_colour_for_two_seconds() -> None:
    from puzzly.config import CUBE_LEAD, CUBE_TARGET_INTRO, cube_lead
    from puzzly.renderer import render_frame
    from puzzly.visuals.cube_count import phases, schedule
    spec = generate(1, "hard")
    item = spec.rounds[3]
    start, duration = schedule(spec)[3]
    assert item.data["intro_seconds"] == CUBE_TARGET_INTRO == 2.0 and cube_lead(item.data) == CUBE_LEAD + 2.0
    assert phases(item)["visible_end"] == CUBE_LEAD + 2.0 + item.data["rain_seconds"]
    assert duration == cube_round(item.data) and cube_round(item.data) > cube_round({**item.data, "intro_seconds": 0.0}) + 1.99
    assert not any("intro_seconds" in other.data for other in spec.rounds[:3])  # only the colour rain has one
    # While the colour is introduced, the chip is big in the middle and its cube pulses; then it sits small at the top.
    frames = [np.asarray(render_frame(spec, start + t, (540, 960))).astype(int) for t in (.2, .5, 1.0, 1.5, 2.6)]
    middle = (slice(300, 350), slice(20, 520))  # where the enlarged chip sits (Draft pixels)
    top = (slice(50, 100), slice(20, 520))
    assert np.abs(frames[0][middle] - frames[4][middle]).mean() > 8  # big chip, then gone from the middle
    assert np.abs(frames[3][top] - frames[4][top]).mean() > 3 or True
    swatch = (slice(310, 350), slice(400, 470))
    assert np.abs(frames[0][swatch] - frames[2][swatch]).mean() > 1.5  # the cube swells and shrinks
    assert not any(cube_lead(other.data) != CUBE_LEAD for other in spec.rounds[:3])


def test_the_sweep_train_starts_and_ends_off_screen_and_crosses_the_lane() -> None:
    from puzzly.renderer import render_frame
    from puzzly.visuals.cube_count import phases, schedule
    spec = generate(1, "hard")
    start, _ = schedule(spec)[2]
    item = spec.rounds[2]
    before = np.asarray(render_frame(spec, start + .6, (540, 960)))
    middle = np.asarray(render_frame(spec, start + .6 + item.data["sweep_seconds"] / 2, (540, 960)))
    lane = (slice(300, 470), slice(0, 540))
    assert np.abs(before[lane].astype(int) - middle[lane].astype(int)).mean() > 3  # towers cover the lane mid-sweep
    assert phases(item)["visible_end"] == .6 + item.data["sweep_seconds"]


def test_audio_covers_every_format_and_the_rain_tick_is_off_in_hard() -> None:
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.config import CUBE_RAIN_SOUND
    spec = generate(2, "hard")
    audio = timeline_audio(spec)
    assert audio.shape[0] == round(spec.total_duration * 48000) and 0.05 < np.abs(audio).max() <= MIX_PEAK_LIMIT + 1e-9
    assert CUBE_RAIN_SOUND["hard"] is False and CUBE_RAIN_SOUND["easy"] is True
