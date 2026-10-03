"""The three-level Memory Challenge (V8): a growing board and a question that changes."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from puzzly.config import (MEMORY_LEVELS, memory_average_round, memory_level_round, memory_levels_total, PUZZLE_FIT_OUTRO_DURATION,
                           READY_INTRO_DURATION)
from puzzly.generator import generate_spec
from puzzly.memory_colors import GRID_COLOR_LEVELS, GRID_COLOR_RULES, GRID_COLORS, perceptual_distance
from puzzly.puzzles.memory_challenge import generate
from puzzly.puzzles.memory_levels import SHAPES_V8, errors
from puzzly.validation import round_errors, validate_spec, validation_errors
from puzzly.visuals.memory import shape_mask, token_image, token_layout
from puzzly.visuals.memory_levels import (AREA_WIDTH, card_center, grid_layout, layout_of, phases, question_times, schedule,
                                          target_center, total_questions)


def test_levels_are_valid_deterministic_and_grow() -> None:
    for seed in range(150):
        level = GRID_COLOR_LEVELS[seed % len(GRID_COLOR_LEVELS)]
        spec = generate(7000 + seed, "hard", f"colors_{level}")
        validate_spec(spec)
        assert spec.round_count == 3 and spec.difficulty == "hard" and spec.puzzle_type == "memory_challenge"
        assert spec.intro_duration == READY_INTRO_DURATION == 4.0 and spec.outro_duration == PUZZLE_FIT_OUTRO_DURATION
        assert [item.data["kind"] for item in spec.rounds] == ["where", "vanish", "where"]
        assert [len(item.data["tokens"]) for item in spec.rounds] == [4, 6, 9]
        assert [item.data["question_count"] for item in spec.rounds] == [2, 2, 3] and total_questions(spec) == 7
        assert [(item.data["rows"], item.data["cols"]) for item in spec.rounds] == [(2, 2), (2, 3), (3, 3)]
        assert spec.round_duration == memory_average_round([item.data for item in spec.rounds])
        assert spec.total_duration == pytest.approx(spec.intro_duration + memory_levels_total() + spec.outro_duration, abs=1e-3)
        for item in spec.rounds:
            data = item.data
            shapes = [token["shape"] for token in data["tokens"]]
            assert len(set(shapes)) == len(shapes) and set(shapes) <= set(SHAPES_V8)
            assert not {"heart", "moon", "star"} & set(shapes)  # plain geometry only
            assert not {"pentagon", "hexagon"} <= set(shapes)
            assert len({token["color_id"] for token in data["tokens"]}) == len(shapes)
            colors = [GRID_COLORS[token["color_id"]] for token in data["tokens"]]
            closest = min(perceptual_distance(a, b) for index, a in enumerate(colors) for b in colors[index + 1:])
            assert closest >= GRID_COLOR_RULES[data["color_level"]]["min_distance"] - 1e-9 and data["color_level"] == level
            assert errors(data, item.answer, "hard") == []
            assert sorted(data["questions"]) == sorted(set(data["questions"]))
    assert generate(90210, "hard") == generate(90210, "easy")  # difficulty is ignored: always Hard
    with pytest.raises(ValueError):
        generate(5, "hard", round_count=4)


def test_the_selector_makes_the_new_game_and_the_classic_board_stays_available() -> None:
    spec = generate_spec("memory_challenge", 3, "easy")
    assert spec.round_count == 3 and spec.difficulty == "hard" and spec.rounds[0].data["layout"] == "levels_v8"
    classic = generate(3, "hard", classic=True)
    assert classic.round_count == 1 and classic.rounds[0].data["layout"] == "grid3" and validation_errors(classic) == []
    assert classic.fingerprint() != spec.fingerprint()


def test_every_moment_of_a_level_is_inside_its_timeline() -> None:
    spec = generate(11, "hard")
    previous_end = spec.intro_duration
    for (start, duration), item in zip(schedule(spec), spec.rounds):
        assert start == pytest.approx(previous_end) and duration == memory_level_round(item.data)
        previous_end = start + duration
        times = phases(item)
        assert times["end"] == pytest.approx(duration)
        windows = question_times(item)
        assert len(windows) == item.data["question_count"]
        assert windows[0]["start"] == pytest.approx(times["questions_start"])
        for first, second in zip(windows, windows[1:]):
            assert first["answer"] <= second["start"] + 1e-9
        for window in windows:
            assert window["think_end"] - window["think_start"] == pytest.approx(item.data["thinking_seconds"])
            assert window["think_end"] <= window["answer"] + 1e-9 <= times["questions_end"] + 1e-9
    assert previous_end == pytest.approx(spec.intro_duration + sum(memory_level_round(item.data) for item in spec.rounds))


def test_cards_are_big_centred_and_inside_the_screen() -> None:
    sizes = []
    for rows, cols in ((2, 2), (2, 3), (3, 3)):
        layout = grid_layout(rows, cols)
        sizes.append(layout["size"])
        xs = [card_center(layout, position)[0] for position in range(1, rows * cols + 1)]
        ys = [card_center(layout, position)[1] for position in range(1, rows * cols + 1)]
        assert abs(sum(xs) / len(xs) - 540) < 1e-6
        assert min(xs) - layout["size"] / 2 >= 100 - 1e-6 and max(xs) + layout["size"] / 2 <= 980 + 1e-6
        assert layout["width"] <= AREA_WIDTH + 1e-6 and layout["top"] >= 380 and layout["top"] + layout["height"] <= 1270
        cx, cy = target_center(layout)
        assert cx == 540 and cy - 105 > layout["top"] + layout["height"] and cy + 105 < 1600  # clear of the board and the bottom
    assert sizes == [330.0, 272.0, 272.0]  # the earlier board's cards were 250: they are larger now


def test_new_plain_shapes_fit_their_cards() -> None:
    for shape in ("ring", "semicircle", "parallelogram"):
        image = token_image(shape, "#4FC3F7", 256)
        box = image.getchannel("A").getbbox()
        assert box is not None and box[0] > 0 and box[1] > 0 and box[2] < 256 and box[3] < 256
        mask_box = shape_mask(shape, 256).getbbox()
        expected_x, expected_y = token_layout(shape, 256)["optical_center"]
        assert abs((mask_box[0] + mask_box[2]) / 2 - expected_x) <= 1.5 and abs((mask_box[1] + mask_box[3]) / 2 - expected_y) <= 1.5
    hole = np.asarray(shape_mask("ring", 256))[128, 128]
    assert hole == 0  # a ring has a hole


def test_bad_levels_are_rejected() -> None:
    item = generate(5, "hard").rounds[2]
    data = item.data
    twin = [dict(token) for token in data["tokens"]]
    twin[1]["shape"] = twin[0]["shape"]
    assert round_errors(replace(item, data={**data, "tokens": twin}), "hard")  # a shape twice
    same = [dict(token) for token in data["tokens"]]
    same[1]["color_id"], same[1]["color_value"] = same[0]["color_id"], same[0]["color_value"]
    assert round_errors(replace(item, data={**data, "tokens": same}), "hard")  # a colour twice
    assert round_errors(replace(item, data={**data, "questions": [1, 1, 2], "question_count": 3}), "hard")
    assert round_errors(replace(item, data={**data, "questions": [1, 2, 10]}), "hard")
    assert round_errors(replace(item, answer={"questions": [9, 9, 9]}), "hard")
    assert round_errors(replace(item, data={**data, "kind": "teleport"}), "hard")
    assert round_errors(replace(item, data={**data, "tokens": data["tokens"][:8]}), "hard")  # a missing card
    assert round_errors(replace(item, data={**data, "memorize_seconds": 30.0}), "hard")
    spec = generate(5, "hard")
    swapped = replace(spec, rounds=(spec.rounds[2], spec.rounds[1], spec.rounds[0]))
    assert validation_errors(swapped)  # boards must grow level by level


def test_retuning_the_levels_never_changes_a_made_video(monkeypatch) -> None:
    import puzzly.config as config
    spec = generate(6, "hard")
    before = [memory_level_round(item.data) for item in spec.rounds]
    monkeypatch.setattr(config, "MEMORY_LEVELS", tuple({**level, "memorize": 7.0, "thinking": 5.0} for level in MEMORY_LEVELS))
    assert [memory_level_round(item.data) for item in spec.rounds] == before
    assert validation_errors(spec) == []


def test_frames_show_each_level_and_every_phase() -> None:
    from puzzly.renderer import render_frame
    spec = generate_spec("memory_challenge", 21, "hard", background="lemon")
    start_of = dict(enumerate(schedule(spec)))
    pictures = {}
    for index, item in enumerate(spec.rounds):
        start = start_of[index][0]
        times, windows = phases(item), question_times(item)
        moments = {"memorize": 1.5, "think": windows[0]["think_start"] + 1.0, "answer": windows[0]["answer"] + .9,
                   "finale": times["questions_end"] + .9}
        for name, moment in moments.items():
            pictures[(index, name)] = np.asarray(render_frame(spec, start + moment, (540, 960))).astype(int)
    for index in range(3):
        assert np.abs(pictures[(index, "memorize")] - pictures[(index, "think")]).mean() > 1.0  # the board changes
        assert np.abs(pictures[(index, "think")] - pictures[(index, "finale")]).mean() > 1.0
    assert np.abs(pictures[(0, "memorize")] - pictures[(2, "memorize")]).mean() > 3  # three different boards
    # `vanish`: during thinking one card is a socket; the board is face up all along.
    assert np.abs(pictures[(1, "memorize")] - pictures[(1, "think")]).mean() > 1.0
    assert render_frame(spec, 0.5, (540, 960)).size == (540, 960)  # the hook
    assert render_frame(spec, 2.5, (540, 960)).size == (540, 960)  # the READY screen
    assert render_frame(spec, spec.total_duration - 1.0, (540, 960)).size == (540, 960)  # the end card


def test_ready_text_matches_the_version() -> None:
    from puzzly.visuals.ready import ready_text
    assert ready_text(generate(3, "hard")) == "You will memorize the shapes."
    assert ready_text(generate(3, "hard", classic=True)) == "You will memorize 9 shapes."


def test_metadata_cover_audio_and_music() -> None:
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.metadata import youtube_metadata
    from puzzly.music import _windows
    from puzzly.renderer import render_cover
    spec = generate_spec("memory_challenge", 8, "hard")
    meta = youtube_metadata(spec)
    assert "#shorts" in meta["youtube_title"] and "Level" in meta["youtube_description"] or "level" in meta["youtube_description"]
    assert render_cover(spec).size == (1080, 1920)
    audio = timeline_audio(spec)
    assert audio.shape[0] == round(spec.total_duration * 48000) and 0.03 < np.abs(audio).max() <= MIX_PEAK_LIMIT + 1e-9
    windows = _windows(replace(spec, metadata={**spec.metadata, "music": "on"}))
    assert len(windows) == 3 + total_questions(spec)  # a memorize window per level and one per question
    assert all(window["think_start"] < window["think_end"] for window in windows)


def test_the_cover_never_shows_a_real_level() -> None:
    from puzzly.renderer import render_cover
    first = generate_spec("memory_challenge", 8, "hard")
    other = generate_spec("memory_challenge", 9, "hard", background=first.metadata.get("background"))
    assert first.metadata.get("background") == other.metadata.get("background")
    difference = np.abs(np.asarray(render_cover(first)).astype(int) - np.asarray(render_cover(other)).astype(int))
    card = difference[760:1560, 100:980]  # the card holds the hook's fixed concept board, so it is the same in every video
    assert card.mean() < difference.mean() * 2 + 1.0


def test_the_portal_has_paused_memory_challenge() -> None:
    from streamlit.testing.v1 import AppTest
    from puzzly.generator import generate_unique_specs
    app = AppTest.from_file("app.py").run()
    assert "Memory Challenge" not in app.selectbox[0].options  # it plays inside Mind Mix, and in the Brain Test
    with pytest.raises(ValueError):
        generate_unique_specs(1, "memory_challenge")
