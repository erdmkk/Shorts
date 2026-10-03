"""Flash Count, number flash: a number flashes for a split second, 3 s of thinking, then the answer."""
from __future__ import annotations

from dataclasses import replace

import pytest
from PIL import Image

from puzzly.config import (FLASH_DIGITS, FLASH_INTRO, FLASH_THINKING, FLASH_VISIBLE, PUZZLE_FIT_OUTRO_DURATION,
                           round_duration)
from puzzly.covers import has_template
from puzzly.generator import generate_spec, generate_unique_specs
from puzzly.history import HistoryStore
from puzzly.metadata import youtube_metadata
from puzzly.puzzles.flash_count import errors, generate, level_tier, number_errors
from puzzly.registry import ACTIVE_PUZZLE_TYPES, MIXED_PUZZLE_TYPES
from puzzly.renderer import render_frame, save_cover
from puzzly.validation import round_errors, validate_spec
from puzzly.visuals.flash_count import cover_number, draw_flash_intro, flash_state, phases


def test_videos_are_valid_deterministic_and_grow() -> None:
    for seed in range(300):
        spec = generate(seed, "hard")
        validate_spec(spec)
        assert spec == generate(seed, "hard") and spec.difficulty == "hard"
        assert (spec.intro_duration, spec.outro_duration) == (FLASH_INTRO, PUZZLE_FIT_OUTRO_DURATION) == (4.0, 3.6)
        numbers = [item.answer for item in spec.rounds]
        assert len(set(numbers)) == len(numbers)
        assert [len(number) for number in numbers] == [FLASH_DIGITS[level_tier(i, 4)] for i in range(4)] == [4, 4, 5, 6]
        for item in spec.rounds:
            assert item.answer == item.data["number"] and not number_errors(item.answer)
            assert item.data["visible_seconds"] == FLASH_VISIBLE[len(item.answer)] == (0.3 if len(item.answer) == 6 else 0.2)
            assert item.data["thinking_seconds"] == FLASH_THINKING == 3.0


def test_only_hard_videos_and_level_counts() -> None:
    """The game is produced only in Hard: any requested difficulty gives the same Hard video."""
    assert generate(7, "easy") == generate(7, "medium") == generate(7, "hard")
    assert generate_spec("flash_count", 7, "easy").difficulty == "hard"
    for count, lengths in ((3, [4, 5, 6]), (5, [4, 4, 5, 6, 6])):
        spec = generate(7, "hard", round_count=count)
        assert [len(item.answer) for item in spec.rounds] == lengths
    with pytest.raises(ValueError):
        generate(7, "hard", round_count=6)


def test_numbers_avoid_easy_chunks() -> None:
    assert not number_errors("9862")
    for bad in ("0862", "9962", "3456", "9876", "9292942", "98a2"):
        assert number_errors(bad)
    assert number_errors("98624", 4)  # wrong length for its level


def test_timeline_and_the_flash_lasts_whole_frames() -> None:
    spec = generate(21, "hard")
    data = spec.rounds[0].data
    times = phases(data)
    assert spec.round_duration == round_duration("flash_count", "hard") == pytest.approx(times["end"])
    # No mask after the flash: the number goes straight to the thinking screen.
    for local, state in ((.2, "ready"), (times["flash_start"], "flash"), (times["flash_end"] + .01, "thinking"),
                         (times["think_end"] + .2, "reveal"), (times["reveal_end"] + .1, "solved")):
        assert flash_state(local, data) == state
    # At 30 fps the number is on exactly 6 frames (0.2 s), and 9 frames (0.3 s) on 6-digit levels.
    for item in spec.rounds:
        shown = [k for k in range(round(spec.round_duration * 30)) if flash_state(k / 30, item.data) == "flash"]
        assert len(shown) == (9 if len(item.answer) == 6 else 6)
        assert phases(item.data)["end"] == pytest.approx(spec.round_duration)  # every level lasts the same


def test_tampered_rounds_are_rejected() -> None:
    spec = generate(5, "hard")
    item = spec.rounds[0]
    assert not round_errors(item, "hard")
    assert round_errors(replace(item, answer="1111"), "hard")
    assert round_errors(replace(item, data={**item.data, "number": "12"}, answer="12"), "hard")
    assert round_errors(replace(item, data={**item.data, "visible_seconds": 0.5}), "hard")
    assert errors({**item.data, "format": "geometric_tokens"}, item.answer, "medium")


def test_the_cover_number_is_random_and_never_a_level() -> None:
    covers = set()
    for seed in range(40):
        spec = generate(seed, "hard")
        number = cover_number(spec)
        assert number == cover_number(spec) and not number_errors(number, 4)
        assert number not in {item.answer for item in spec.rounds}
        covers.add(number)
    assert len(covers) >= 35  # random per video


def test_ready_screen_has_no_timer_or_number() -> None:
    import inspect
    source = inspect.getsource(draw_flash_intro)
    assert "BLINK AND YOU MISS IT." == __import__("puzzly.visuals.flash_count", fromlist=["HOOK_TEXT"]).HOOK_TEXT  # ready.py asks ARE YOU READY?
    assert "_timer" not in source and "_digit" not in source


def test_unique_specs_frames_cover_and_metadata(tmp_path) -> None:
    assert "flash_count" in ACTIVE_PUZZLE_TYPES and "flash_count" in MIXED_PUZZLE_TYPES
    unique = generate_unique_specs(6, "flash_count", "hard", base_seed=44, history=HistoryStore(tmp_path / "history.sqlite"))
    assert len({item.fingerprint() for item in unique}) == 6
    spec = replace(generate_spec("flash_count", 930, "hard"), metadata={"background": "plum", "palette": "neon"})
    assert has_template(spec)
    for moment in (.5, 2.0, spec.total_duration / 2, spec.total_duration - .2):
        assert render_frame(spec, moment, (270, 480)).size == (270, 480)
    path = tmp_path / "flash.jpg"
    save_cover(spec, path)
    with Image.open(path) as image:
        assert image.format == "JPEG" and image.size == (1080, 1920)
    meta = youtube_metadata(spec)
    assert "#shorts" in meta["youtube_title"] and "number flash" in meta["youtube_tags"]


def test_audio_and_music() -> None:
    import numpy as np
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.music import STYLES, music_enabled
    spec = replace(generate(4, "hard"), metadata={"music": "on"})
    assert music_enabled(spec) and STYLES["flash_count"]["mood"] == "tense"
    audio = timeline_audio(spec)
    assert len(audio) == round(spec.total_duration * 48000) and float(np.abs(audio).max()) <= MIX_PEAK_LIMIT + 1e-9
