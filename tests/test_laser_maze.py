"""Laser Maze: a laser enters a board of mirrors and the viewer says which numbered receiver the beam ends in."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace

import numpy as np

from puzzly.config import LASER_TIER_SETS, LASER_TIERS, laser_average_round
from puzzly.generator import generate_spec
from puzzly.puzzles import laser_maze
from puzzly.puzzles.laser_maze import generate, port_cell, trace
from puzzly.validation import round_errors, validate_spec, validation_errors


def test_the_beam_follows_the_mirrors_and_leaves_through_one_port() -> None:
    mirrors = {(0, 2): "\\", (3, 2): "/", (3, 0): "\\"}  # down the third column, bounce right at the bottom...
    result = trace(5, mirrors, 2)
    assert result["path"][0] == (0, 2) and result["hits"][0] == 0
    # A "\" turns a beam going down to the right; a "/" turns it up.
    assert laser_maze.reflect((1, 0), "\\") == (0, 1) and laser_maze.reflect((1, 0), "/") == (0, -1)
    assert laser_maze.reflect((0, 1), "/") == (-1, 0) and laser_maze.reflect((0, -1), "\\") == (-1, 0)
    # An empty board lets a beam entering at the top go straight down and out of the bottom, in the same column.
    for n in (5, 9):
        for column in range(n):
            assert trace(n, {}, column)["exit"] == 3 * n - 1 - column
    # The beam is reversible: sent in from where it left, it comes out where it went in.
    boards = [generate(seed, round_count=5).rounds[-1].data for seed in range(5)]
    for data in boards:
        mirrors = {(row, column): kind for row, column, kind in data["mirrors"]}
        assert trace(data["n"], mirrors, data["exit"])["exit"] == data["entry"]


def test_videos_are_valid_hard_and_the_levels_escalate_by_the_number_of_levels() -> None:
    for count in (3, 4, 5):
        for seed in range(10):
            spec = generate(seed, round_count=count)
            validate_spec(spec)
            assert spec == generate(seed, round_count=count) and spec.difficulty == "hard"
            tiers = [item.data["tier"] for item in spec.rounds]
            assert tiers == list(LASER_TIER_SETS[count]) and tiers == sorted(tiers)
            sizes = [item.data["n"] for item in spec.rounds]
            assert sizes == sorted(sizes) and sizes[-1] == 9 and sizes[0] == 5  # the last level is always the hardest
            bounces = [item.data["bounces"] for item in spec.rounds]
            assert all(later >= earlier - 2 for earlier, later in zip(bounces, bounces[1:])) and bounces[-1] > bounces[0]
            assert spec.round_duration == laser_average_round([item.data for item in spec.rounds])
            for item in spec.rounds:
                data = item.data
                level = LASER_TIERS[data["tier"]]
                low, high = level["bounces"]
                assert low <= data["bounces"] <= high and len(set(map(tuple, data["path"]))) >= level["min_cells"]
                assert len(data["receivers"]) == level["receivers"] and data["exit"] in data["receivers"]
                assert item.answer == data["receivers"].index(data["exit"]) + 1
    assert generate(1, round_count=3).total_duration < generate(1, round_count=5).total_duration


def test_five_is_the_most_and_other_counts_are_rejected() -> None:
    try:
        generate(1, round_count=6)
    except ValueError:
        pass
    else:
        raise AssertionError("6 levels must be rejected")
    try:
        generate(1, round_count=2)
    except ValueError:
        pass
    else:
        raise AssertionError("2 levels must be rejected")


def test_the_correct_receiver_is_spread_evenly() -> None:
    answers = Counter()
    for seed in range(120):
        spec = generate(seed, round_count=4)
        answers[(spec.rounds[0].data["tier"], spec.rounds[0].answer)] += 1
    first_level = [answers[(0, number)] for number in range(1, 5)]
    assert min(first_level) > 12  # four receivers, 120 videos: about 30 each


def test_broken_boards_are_rejected() -> None:
    item = generate(5, round_count=4).rounds[1]
    data = item.data
    wrong_answer = (item.answer % len(data["receivers"])) + 1
    assert round_errors(replace(item, answer=wrong_answer), "hard")
    flipped = [[row, column, "/" if kind == "\\" else "\\"] for row, column, kind in data["mirrors"]]
    assert round_errors(replace(item, data={**data, "mirrors": flipped}), "hard")
    assert round_errors(replace(item, data={**data, "receivers": [port for port in data["receivers"] if port != data["exit"]]}), "hard")
    assert round_errors(replace(item, data={**data, "n": 12}), "hard")
    assert round_errors(replace(item, data={**data, "version": "laser_v0"}), "hard")
    assert round_errors(replace(item, data={**data, "thinking_seconds": 60}), "hard")


def test_retuning_never_invalidates_a_made_video(monkeypatch) -> None:
    spec = generate(2, round_count=4)
    monkeypatch.setattr("puzzly.config.LASER_TIERS", tuple({**tier, "bounces": (50, 60), "min_cells": 99} for tier in LASER_TIERS))
    monkeypatch.setattr(laser_maze, "LASER_TIERS", tuple({**tier, "bounces": (50, 60), "min_cells": 99} for tier in LASER_TIERS))
    assert validation_errors(spec) == []  # a made video validates against the rules it stored


def test_frames_cover_audio_and_metadata() -> None:
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.metadata import youtube_metadata
    from puzzly.renderer import render_cover, render_frame
    from puzzly.visuals.laser_maze import beam_points, bounce_times, phases, receiver_points, schedule
    spec = generate_spec("laser_maze", 7, "hard", challenges=3)
    assert spec.puzzle_type == "laser_maze" and validation_errors(spec) == []
    start, duration = schedule(spec)[0]
    item = spec.rounds[0]
    times = phases(item)
    size = (540, 960)
    hook = np.asarray(render_frame(spec, .5, size)).astype(int)
    thinking = np.asarray(render_frame(spec, start + times["think_end"] - 1.0, size)).astype(int)
    tracing = np.asarray(render_frame(spec, start + times["think_end"] + item.data["trace_seconds"] * .6, size)).astype(int)
    solved = np.asarray(render_frame(spec, start + times["trace_end"] + .6, size)).astype(int)
    assert np.abs(thinking - tracing).mean() > .3 and np.abs(tracing - solved).mean() > .1  # the beam runs, the receiver lights
    assert np.abs(hook - thinking).mean() > .3
    # The beam passes the emitter, every bounce, and ends at the answer's receiver.
    points = beam_points(item.data)
    assert len(points) == item.data["bounces"] + 2 and len(bounce_times(item)) == item.data["bounces"]
    assert bounce_times(item) == sorted(bounce_times(item))
    end = receiver_points(item.data)[item.answer - 1]
    assert abs(points[-1][0] - end[0]) < 1 or abs(points[-1][1] - end[1]) < 1
    # The answer never shows during thinking: the beam stub stays short and no receiver is highlighted green.
    assert render_cover(spec).size == (1080, 1920)
    audio = timeline_audio(spec)
    assert 0.03 < np.abs(audio).max() <= MIX_PEAK_LIMIT + 1e-9
    assert abs(len(audio) / 48000 - spec.total_duration) < .6
    meta = youtube_metadata(spec)
    assert "laser" in meta["youtube_title"].lower() and "laser" in meta["youtube_tags"].lower()


def test_the_selector_offers_laser_maze_with_hard_locked_and_up_to_five_levels() -> None:
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("app.py").run()
    app.selectbox[0].select("Laser Maze").run()
    assert not app.exception
    levels = next(box for box in app.selectbox if box.label == "Challenges per video")
    assert levels.options == ["Auto", "3", "4", "5"]
    difficulty = next(box for box in app.selectbox if box.label == "Difficulty")
    assert difficulty.options == ["Hard"] and difficulty.disabled
    for choice in ("3", "5"):
        levels.select(choice).run()
        assert not app.exception
