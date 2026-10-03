"""Line Follow, Weave V7: the figure's line through a board full of same-colour cables; produced only in Hard."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import math

from puzzly.config import LINE_THINKING, line_average_round, line_round
from puzzly.generator import generate_spec
from puzzly.metadata import youtube_metadata
from puzzly.puzzles import line_follow as lf
from puzzly.puzzles import line_weave as lw
from puzzly.registry import ACTIVE_PUZZLE_TYPES, MIXED_PUZZLE_TYPES
from puzzly.renderer import render_cover, render_frame
from puzzly.validation import round_errors, validate_spec

SPEC = lf.generate(3)  # the default: 5 levels
SHORT = lf.generate(8, round_count=3)


def test_videos_are_valid_deterministic_hard_and_ramp_up() -> None:
    for spec in (SPEC, SHORT):
        validate_spec(spec)
        assert spec.difficulty == "hard"
    assert [item.data["tier"] for item in SPEC.rounds] == [0, 1, 2, 3, 4]
    assert [item.data["tier"] for item in SHORT.rounds] == [0, 2, 4]
    assert lf.generate(3) == SPEC
    # Every level is harder: longer lines, and the figure's line crosses at least the level's (growing) minimum.
    budgets = [lw.TIERS[item.data["tier"]]["length"] for item in SPEC.rounds]
    assert all(a < b for a, b in zip(budgets, budgets[1:])) and budgets[-1] >= 1.8 * budgets[0]
    # One more target and line as the levels climb: 4, 5, 5, 6, 6.
    assert [len(item.data["lines"]) for item in SPEC.rounds] == [4, 5, 5, 6, 6]
    assert [len(item.data["lines"]) for item in SHORT.rounds] == [4, 5, 6]
    drawn = [len(lw.line_points(item.data["lines"][0])) * lw.SAMPLE for item in SPEC.rounds]
    assert drawn[-1] >= 1.3 * drawn[0]  # six lines share the last boards, so the figure's line grows less than in V7
    minimums = [lw.TIERS[item.data["tier"]]["min_cross"] for item in SPEC.rounds]
    assert minimums == sorted(minimums) and minimums[0] >= 8
    assert all(item.data["answer_crossings"] >= minimum for item, minimum in zip(SPEC.rounds, minimums))


def test_only_the_figures_line_reaches_the_bottom() -> None:
    for item in SPEC.rounds:
        data = item.data
        count = len(data["lines"])
        figure = tuple(data["figure"])
        assert [line["kind"] for line in data["lines"]] == ["answer"] + ["decoy"] * (count - 1)
        assert sorted(line["target"] for line in data["lines"]) == list(range(count))
        assert data["lines"][0]["target"] == item.answer
        assert item.answer != lw.straight_up(figure[0], count)  # guessing straight up never works
        for index, line in enumerate(data["lines"]):
            points = lw.line_points(line)
            target = (lw.slots(count)[line["target"]], lw.TOP_Y)
            if index == 0:  # the only line that reaches the figure; it runs from the figure up to its target
                assert math.dist(points[0], figure) < 1e-6 and math.dist(points[-1], target) < 1e-6
            else:
                assert math.dist(points[0], target) < 1e-6
                # A loose end well above the bottom row, and never near the figure: one start point only.
                assert points[-1][1] <= lw.END_MAX_Y
                assert min(math.dist(point, figure) for point in points) >= lw.FIGURE_CLEAR


def test_the_board_is_full_and_tangled() -> None:
    for item in SPEC.rounds:
        data, tier = item.data, lw.TIERS[item.data["tier"]]
        filled = lw.coverage([lw.line_points(line) for line in data["lines"]], tuple(data["figure"]))
        assert filled == data["coverage"] >= tier["min_cover"]
        assert data["answer_crossings"] >= tier["min_cross"]
        # The figure's line is long: it wanders the whole board before it comes home.
        assert len(lw.line_points(data["lines"][0])) * lw.SAMPLE >= tier["length"] * lw.EARLY_HOME
        # So are the others, and they grow level by level too.
        assert all(len(lw.line_points(line)) * lw.SAMPLE >= tier["decoy"][0] * lw.MIN_DECOY_SHARE - lw.STEP
                   for line in data["lines"][1:])
    # The board fills up level by level: the acceptance floors rise, and from level 2 on it holds far more line than
    # level 1 (with six lines the last levels are as full as the readability rules allow).
    floors = [(lw.TIERS[tier]["min_cover"], lw.TIERS[tier]["min_cross"]) for tier in range(len(lw.TIERS))]
    assert all(a[0] < b[0] and a[1] < b[1] for a, b in zip(floors, floors[1:]))
    ink = [sum(len(lw.line_points(line)) for line in item.data["lines"]) * lw.SAMPLE for item in SPEC.rounds]
    assert all(value >= 1.2 * ink[0] for value in ink[1:])
    assert SPEC.rounds[-1].data["coverage"] > SPEC.rounds[0].data["coverage"]


def test_the_tangle_is_smooth_and_readable() -> None:
    for item in SPEC.rounds:
        data = item.data
        for index, line in enumerate(data["lines"]):
            points = lw.line_points(line)
            assert max(math.dist(a, b) for a, b in zip(points, points[1:])) <= lw.SAMPLE + 1e-6  # continuous
            assert lw._smooth_from(points, 4)  # no kinks
            assert all(abs(x - points[0][0]) < 1e-6 for x, _ in points[:6])  # straight out of its start
            if index == 0:
                assert all(abs(x - points[-1][0]) < 1.5 for x, _ in points[-6:])  # straight up into its target
        crossings = lw.crossings_of(data)
        assert all(crossing["angle"] >= lw.CROSS_ANGLE - 1e-6 for crossing in crossings)
        spots = [crossing["point"] for crossing in crossings]
        assert all(math.dist(a, b) >= lw.CROSS_GAP for i, a in enumerate(spots) for b in spots[i + 1:])
        assert data["crossing_count"] == len(crossings)


def test_thinking_time_grows_and_the_total_is_exact() -> None:
    assert [item.data["thinking_seconds"] for item in SPEC.rounds] == list(LINE_THINKING)
    assert SPEC.round_duration == line_average_round(5)
    from puzzly.visuals.line_follow import schedule
    levels = schedule(SPEC)
    assert [duration for _, duration in levels] == [line_round(t) for t in LINE_THINKING]
    assert abs(levels[-1][0] + levels[-1][1] + SPEC.outro_duration - SPEC.total_duration) < 1e-3


def test_tampered_rounds_are_rejected() -> None:
    item = SPEC.rounds[2]
    assert round_errors(replace(item, answer=(item.answer + 1) % len(item.data["targets"])))
    lines = [dict(line) for line in item.data["lines"]]
    decoy = next(line for line in lines if line["kind"] == "decoy")
    decoy["controls"] = decoy["controls"][:6] + [[decoy["controls"][5][0] + 60, decoy["controls"][5][1] - 60]] + decoy["controls"][6:]
    assert round_errors(replace(item, data={**item.data, "lines": lines}))  # a kink
    assert round_errors(replace(item, data={**item.data, "thinking_seconds": 3.0}))
    assert round_errors(replace(item, data={**item.data, "answer_crossings": 2}))


def test_line_follow_is_back_hard_only_and_renders() -> None:
    assert "line_follow" in ACTIVE_PUZZLE_TYPES and "line_follow" in MIXED_PUZZLE_TYPES
    spec = replace(SHORT, metadata={"background": "plum", "palette": "neon"})
    for moment in (.5, 3.0, spec.total_duration / 2, spec.total_duration - .2):
        assert render_frame(spec, moment, (270, 480)).size == (270, 480)
    assert render_cover(spec).size == (1080, 1920)
    meta = youtube_metadata(spec)
    assert "#shorts" in meta["youtube_title"] and "line follow" in meta["youtube_tags"]
    assert generate_spec("line_follow", 8, "easy", challenges=3).difficulty == "hard"


def test_audio_and_music() -> None:
    import numpy as np
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.music import STYLES, music_enabled
    spec = replace(SHORT, metadata={"music": "on"})
    assert music_enabled(spec) and STYLES["line_follow"]["mood"] == "tense"
    audio = timeline_audio(spec)
    assert len(audio) == round(spec.total_duration * 48000) and float(np.abs(audio).max()) <= MIX_PEAK_LIMIT + 1e-9


def test_earlier_light_theme_version_still_validates() -> None:
    spec = lf.generate_legacy(5, "hard")
    for item in spec.rounds:
        assert lf.errors(item.data, item.answer) == []


def test_earlier_weave_v7_records_still_validate(monkeypatch) -> None:
    import random
    # Weave V7 had 5, 5, 5, 4, 4 lines and 7..15 s: rebuild one of its level-4 boards and validate it with today's code.
    monkeypatch.setattr(lw, "TIERS", lw.TIERS_V7)
    monkeypatch.setattr(lw, "LINE_THINKING", lw.LINE_THINKING_V7)
    monkeypatch.setattr(lw, "VERSION", "weave_v7")
    old = lw.make_round(3, 3, random.Random("v7-record"))
    monkeypatch.undo()
    assert old.data["version"] == "weave_v7" and len(old.data["lines"]) == 4 and old.data["thinking_seconds"] == 13.0
    assert lf.errors(old.data, old.answer) == []
    assert lw.is_weave(old.data) and lw.tier_table(old.data) is lw.TIERS_V7
    assert lf.errors({**old.data, "version": lw.VERSION}, old.answer)  # the same board is not a valid V8 level 4
