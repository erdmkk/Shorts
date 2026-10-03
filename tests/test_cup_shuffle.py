"""Cup Shuffle: follow the ball under the cup. Three levels with 3, 4 and 5 cups, shuffling more and faster each time."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace

import numpy as np
import pytest

from puzzly.config import CUP_LEVELS, cup_round
from puzzly.generator import generate_spec, output_stem
from puzzly.puzzles import cup_shuffle as cs
from puzzly.registry import ACTIVE_PUZZLE_TYPES, MIXED_PUZZLE_TYPES
from puzzly.validation import validation_errors


def test_replay_follows_the_ball() -> None:
    swaps = [[0, 1, 0], [1, 2, 2], [0, 2, 0]]
    order, final = cs.replay(3, 0, swaps)  # [0,1,2] -> [1,0,2] -> [1,2,0] -> [0,2,1]: cup 0 travels 0 -> 1 -> 2 -> 0
    assert order == [0, 2, 1] and final == 0
    assert cs.states(3, swaps) == [[0, 1, 2], [1, 0, 2], [1, 2, 0], [0, 2, 1]]
    assert cs.ball_swaps(3, 0, swaps) == 3
    order, final = cs.replay(3, 2, swaps)  # the ball under cup 2 is only moved by the middle swap
    assert final == 1 and cs.ball_swaps(3, 2, swaps) == 1


def test_videos_are_valid_three_levels_that_get_faster_and_deterministic() -> None:
    answers = [Counter() for _ in range(3)]
    for seed in range(300):
        spec = generate_spec("cup_shuffle", seed, "medium")  # any difficulty gives the same Hard video
        assert spec.difficulty == "hard" and validation_errors(spec) == []
        assert spec.round_count == 3 and [item.data["cups"] for item in spec.rounds] == [3, 4, 5]
        swaps = [len(item.data["swaps"]) for item in spec.rounds]
        seconds = [item.data["swap_seconds"] for item in spec.rounds]
        assert swaps == sorted(swaps) and seconds == sorted(seconds, reverse=True)
        assert len({item.data["color"] for item in spec.rounds}) == 3  # a different cup colour on every level
        for level, item in enumerate(spec.rounds):
            data = item.data
            _, final = cs.replay(data["cups"], data["start"], data["swaps"])
            assert item.answer == final + 1 and final != data["start"]
            assert cs.ball_swaps(data["cups"], data["start"], data["swaps"]) >= max(3, round(len(data["swaps"]) / 2))
            assert all(a < b and front in (a, b) for a, b, front in data["swaps"])
            assert all((x[0], x[1]) != (y[0], y[1]) for x, y in zip(data["swaps"], data["swaps"][1:]))
            answers[level][item.answer] += 1
        assert spec.round_duration == pytest.approx(sum(cup_round(item.data) for item in spec.rounds) / 3, abs=1e-3)
    # No cup is favoured: every position is the answer about equally often on every level.
    for level, counts in enumerate(answers):
        cups = 3 + level
        assert sorted(counts) == list(range(1, cups + 1)) and max(counts.values()) < 1.6 * min(counts.values())
    assert generate_spec("cup_shuffle", 9, "hard") == generate_spec("cup_shuffle", 9, "easy")


def test_speed_lives_in_the_config_but_made_videos_keep_theirs(monkeypatch) -> None:
    import puzzly.config as config
    spec = generate_spec("cup_shuffle", 5, "hard")
    assert [item.data["swap_seconds"] for item in spec.rounds] == [level["swap_seconds"] for level in CUP_LEVELS]
    faster = tuple({**level, "swap_seconds": round(level["swap_seconds"] * .8, 3)} for level in CUP_LEVELS)  # stays above the 0.15 s minimum
    monkeypatch.setattr(config, "CUP_LEVELS", faster)
    monkeypatch.setattr(cs, "CUP_LEVELS", faster)
    assert validation_errors(spec) == []  # the stored video still validates and lasts as long as before
    assert generate_spec("cup_shuffle", 5, "hard").rounds[0].data["swap_seconds"] == faster[0]["swap_seconds"]


def test_tampered_rounds_are_rejected() -> None:
    spec = generate_spec("cup_shuffle", 4, "hard")
    item = spec.rounds[1]
    wrong = replace(spec, rounds=(spec.rounds[0], replace(item, answer=item.answer % 4 + 1), spec.rounds[2]))
    assert any("answer does not match" in error for error in validation_errors(wrong))
    repeated = [list(swap) for swap in item.data["swaps"]]
    repeated[1] = list(repeated[0])
    assert any("same swap" in error for error in validation_errors(
        replace(spec, rounds=(spec.rounds[0], replace(item, data={**item.data, "swaps": repeated}), spec.rounds[2]))))
    still = replace(spec, rounds=(spec.rounds[0], replace(item, data={**item.data, "swaps": []}), spec.rounds[2]))
    assert validation_errors(still)


def test_registration_and_filename() -> None:
    assert "cup_shuffle" in ACTIVE_PUZZLE_TYPES and "cup_shuffle" not in MIXED_PUZZLE_TYPES
    assert output_stem(3, generate_spec("cup_shuffle", 1, "hard")) == "PZ_0003_cup_shuffle_hard"


def test_the_ball_is_only_drawn_while_it_may_be_seen(monkeypatch) -> None:
    from puzzly.visuals import cup_shuffle as visuals
    spec = generate_spec("cup_shuffle", 12, "hard")
    item = spec.rounds[1]
    times = visuals.phases(item)
    calls = []
    real = visuals.ball_sprite
    monkeypatch.setattr(visuals, "ball_sprite", lambda px: (calls.append(px), real(px))[1])
    size = (270, 480)
    for local in np.arange(times["shuffle_start"] + .05, times["think_end"] - .05, .25):
        visuals.draw_cup_round(spec, 1, float(local), size)
    assert calls == []  # never during the shuffle or while the viewer guesses
    visuals.draw_cup_round(spec, 1, (times["lift_end"] + times["show_end"]) / 2, size)
    visuals.draw_cup_round(spec, 1, times["reveal_end"] + .2, size)
    assert len(calls) == 2


def test_swaps_move_cups_and_the_answer_cup_ends_where_the_answer_says() -> None:
    from puzzly.visuals import cup_shuffle as visuals
    spec = generate_spec("cup_shuffle", 21, "hard")
    for item in spec.rounds:
        data, times = item.data, visuals.phases(item)
        poses = visuals.cup_poses(data, times["shuffle_start"] + data["swap_seconds"] * .5)
        first, second, _ = data["swaps"][0]
        moving = [pose for pose in poses if pose["y"] != visuals.BASE_Y]
        assert len(moving) == 2 and {pose["cup"] for pose in moving} == {first, second}  # start order: cup i at position i
        end = visuals.cup_poses(data, times["shuffle_end"] + .01)
        xs, _ = visuals.layout(data["cups"])
        ball = next(pose for pose in end if pose["cup"] == data["start"])
        assert ball["x"] == xs[item.answer - 1] and ball["y"] == visuals.BASE_Y


def test_frames_cover_audio_and_metadata() -> None:
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.covers import has_template, render_game_cover
    from puzzly.metadata import youtube_metadata
    from puzzly.renderer import render_frame
    from puzzly.visuals.cup_shuffle import phases, schedule
    spec = generate_spec("cup_shuffle", 13, "hard")
    start, _ = schedule(spec)[2]
    times = phases(spec.rounds[2])
    moments = [.5, start + .2, start + times["lift_end"] + .3, start + times["shuffle_start"] + 1, start + times["shuffle_end"] + 1,
               start + times["reveal_end"] + .3, spec.total_duration - .3]
    frames = [np.asarray(render_frame(spec, t, (270, 480)), dtype=int) for t in moments]
    assert all(frame.shape == (480, 270, 3) for frame in frames)
    assert np.abs(frames[2] - frames[4]).mean() > 1
    assert has_template(spec) and render_game_cover(spec).size == (1080, 1920)
    audio = timeline_audio(replace(spec, metadata={"music": "on"}))
    assert audio.shape == (round(spec.total_duration * 48000), 2) and float(np.abs(audio).max()) <= MIX_PEAK_LIMIT + 1e-9
    meta = youtube_metadata(spec)
    assert "#shorts" in meta["youtube_title"] and "cup shuffle" in meta["youtube_tags"]


def test_ui_locks_hard_and_hides_the_challenge_count() -> None:
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("app.py").run()
    next(box for box in app.selectbox if box.label == "Puzzle Type").select("Cup Shuffle").run()
    assert not app.exception
    difficulty = next(box for box in app.selectbox if box.label == "Difficulty")
    assert difficulty.value == "Hard" and difficulty.disabled
    assert "Challenges per video" not in [box.label for box in app.selectbox]
    assert any("Topu takip et" in item.value for item in app.caption)
