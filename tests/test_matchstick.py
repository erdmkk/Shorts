"""Matchstick Math: move one match, exactly one solution, three levels that get harder."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from puzzly.config import MATCH_THINKING, PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION
from puzzly.generator import generate_spec, output_stem
from puzzly.puzzles import matchstick as ms
from puzzly.registry import ACTIVE_PUZZLE_TYPES, MIXED_PUZZLE_TYPES
from puzzly.validation import validation_errors


def test_every_glyph_is_one_distinct_stick_pattern() -> None:
    patterns = [frozenset(value) for value in ms.DIGITS.values()]
    assert len(set(patterns)) == 10
    assert [len(ms.DIGITS[digit]) for digit in range(10)] == [6, 2, 5, 5, 4, 5, 6, 3, 7, 6]
    assert ms.is_true("8-4=4") and not ms.is_true("8-4=5") and not ms.is_true("08+1=9")


@pytest.mark.parametrize("difficulty,count", [("easy", 150), ("medium", 150), ("hard", 300)])
def test_videos_are_valid_unique_escalating_and_deterministic(difficulty, count) -> None:
    fingerprints = set()
    for seed in range(count):
        spec = generate_spec("matchstick", seed, difficulty)
        assert validation_errors(spec) == []
        fingerprints.add(spec.fingerprint())
        assert [item.data["tier"] for item in spec.rounds] == [0, 1, 2]
        equations = [item.data["equation"] for item in spec.rounds]
        assert len(set(equations)) == 3
        for item in spec.rounds:
            found = ms.moves(item.data["equation"])
            assert list(found) == [item.answer] and not ms.is_true(item.data["equation"])
            assert ms.is_true(item.answer)
        thinking = [item.data["thinking_seconds"] for item in spec.rounds]
        assert thinking == list(MATCH_THINKING[difficulty]) and thinking == sorted(thinking) and max(thinking) <= 15
        # Levels last different times; the total is exact.
        from puzzly.visuals.matchstick import schedule
        levels = schedule(spec)
        assert abs(levels[-1][0] + levels[-1][1] + PUZZLE_FIT_OUTRO_DURATION - spec.total_duration) < 1e-3
        assert levels[0][0] == PUZZLE_FIT_INTRO_DURATION
    assert len(fingerprints) == count
    assert generate_spec("matchstick", 5, difficulty) == generate_spec("matchstick", 5, difficulty)


def test_levels_really_get_harder() -> None:
    for seed in range(60):
        spec = generate_spec("matchstick", seed, "hard")
        first, second, third = spec.rounds
        assert len(first.data["equation"]) == 5  # single digits
        assert len(second.data["equation"]) > 5 and second.data["move"]["from"][0] != second.data["move"]["to"][0]
        equals = third.data["equation"].index("=")
        source, target = third.data["move"]["from"][0], third.data["move"]["to"][0]
        operator = next(i for i, char in enumerate(third.data["equation"]) if char in "+-")
        assert (source < equals) != (target < equals) or operator in (source, target)


def test_tampered_rounds_are_rejected() -> None:
    spec = generate_spec("matchstick", 3, "hard")
    item = spec.rounds[0]
    wrong = replace(spec, rounds=(replace(item, answer="1+1=2"),) + spec.rounds[1:])
    assert any("does not solve" in error for error in validation_errors(wrong))
    already = replace(spec, rounds=(replace(item, data={**item.data, "equation": "4+3=7"}),) + spec.rounds[1:])
    assert validation_errors(already)
    many = next(text for text in (f"{a}+{b}={c}" for a in range(1, 10) for b in range(10) for c in range(10))
                if not ms.is_true(text) and len(ms.moves(text)) > 1)
    ambiguous = replace(spec, rounds=(replace(item, data={**item.data, "equation": many}),) + spec.rounds[1:])
    assert any("exactly one solution" in error for error in validation_errors(ambiguous))


def test_registration_filename_and_standalone() -> None:
    assert "matchstick" in ACTIVE_PUZZLE_TYPES and "matchstick" not in MIXED_PUZZLE_TYPES
    assert output_stem(7, generate_spec("matchstick", 1, "hard")) == "PZ_0007_matchstick_hard"


def test_frames_cover_audio_and_metadata() -> None:
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.covers import has_template, render_game_cover
    from puzzly.metadata import youtube_metadata
    from puzzly.renderer import render_frame
    from puzzly.visuals.matchstick import phases, schedule
    spec = generate_spec("matchstick", 11, "hard")
    start, _ = schedule(spec)[0]
    times = phases(spec.rounds[0])
    moments = [0.4, start + 3, start + times["think_end"] + .6, start + times["hold"], spec.total_duration - .5]
    frames = [np.asarray(render_frame(spec, t, (270, 480)), dtype=int) for t in moments]
    assert all(frame.shape == (480, 270, 3) for frame in frames)
    assert np.abs(frames[1] - frames[3]).mean() > 1  # the solved card differs from the puzzle
    assert has_template(spec) and render_game_cover(spec).size == (1080, 1920)
    audio = timeline_audio(replace(spec, metadata={"music": "on"}))
    assert audio.shape == (round(spec.total_duration * 48000), 2) and float(np.abs(audio).max()) <= MIX_PEAK_LIMIT + 1e-9
    meta = youtube_metadata(spec)
    assert "#shorts" in meta["youtube_title"] and "matchstick" in meta["youtube_tags"]


def test_ui_offers_matchstick_math_without_a_challenge_count() -> None:
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("app.py").run()
    next(box for box in app.selectbox if box.label == "Puzzle Type").select("Matchstick Math").run()
    assert not app.exception
    labels = [box.label for box in app.selectbox]
    assert "Difficulty" in labels and "Challenges per video" not in labels
    assert any("Kibrit çöpü" in item.value for item in app.caption)


def test_table_surface_and_frame_colour_are_parameters() -> None:
    from puzzly.config import MATCH_FRAMES
    from puzzly.renderer import render_frame
    from puzzly.visuals.matchstick import frame_for, schedule
    from puzzly.visuals.surfaces import table
    spec = generate_spec("matchstick", 4, "hard")
    assert frame_for(spec) == MATCH_FRAMES["teal"][1] and len(MATCH_FRAMES) >= 5
    pink = replace(spec, metadata={"frame": "pink"})
    assert frame_for(pink) == MATCH_FRAMES["pink"][1] and pink.fingerprint() == spec.fingerprint()
    t = schedule(spec)[0][0] + 3
    a = np.asarray(render_frame(spec, t, (270, 480)), dtype=int)
    b = np.asarray(render_frame(pink, t, (270, 480)), dtype=int)
    assert np.abs(a - b).mean() > .5
    # The wood table follows the background tone and is lit in the middle, dark at the edges.
    gold = np.asarray(table((108, 192), "gold", "wood", (540, 930)), dtype=float)
    violet = np.asarray(table((108, 192), "violet", "wood", (540, 930)), dtype=float)
    assert np.abs(gold - violet).mean() > 3
    assert gold[93, 54].mean() > 2 * gold[5, 5].mean()


def test_ui_offers_a_frame_colour_for_matchsticks() -> None:
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("app.py").run()
    next(box for box in app.selectbox if box.label == "Puzzle Type").select("Matchstick Math").run()
    box = next(box for box in app.selectbox if box.label == "Çerçeve rengi")
    assert not app.exception and box.value == "teal" and "Rastgele" in box.options
