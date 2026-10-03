"""Mind Mix: one hard level each of Memory, Shade Spot and Puzzle Fit in one video."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from puzzly.config import (FIT_THINKING, MEMORY_LEVELS, MIX_FIT_THINKING, MIX_GAMES, MIX_SECTION_INTRO, SHADE_LEVELS, fit_round,
                           mix_average_round, mix_section_length, mix_sub_length, round_duration)
from puzzly.generator import generate_spec, generate_unique_specs
from puzzly.puzzles.mind_mix import errors, generate, sub_round
from puzzly.registry import ACTIVE_PUZZLE_TYPES, MIXED_PUZZLE_TYPES, PAUSED_PUZZLE_TYPES, SUPPORTED_PUZZLE_TYPES
from puzzly.validation import round_errors, validate_spec, validation_errors
from puzzly.visuals.mind_mix import cover_card, icon_sprite, music_windows, schedule, sound_cues


def test_every_video_has_one_hard_level_of_each_game_in_order() -> None:
    for seed in range(60):
        spec = generate(8000 + seed)
        validate_spec(spec)
        assert spec.puzzle_type == "mind_mix" and spec.difficulty == "hard" and spec.round_count == 3
        assert spec.intro_duration == 1.0 and spec.outro_duration == 3.6
        assert [item.data["game"] for item in spec.rounds] == list(MIX_GAMES) == ["memory_challenge", "shade_spot", "puzzle_fit"]
        assert [item.data["level"] for item in spec.rounds] == [1, 2, 3]
        memory, shade, fit = (item.data["sub"] for item in spec.rounds)
        assert memory["kind"] == "where" and len(memory["tokens"]) == 9 and memory["question_count"] == 3  # Memory's level 3
        assert shade["grid"] == 5 and shade["delta"] == SHADE_LEVELS[-1]["delta"]  # Shade Spot's level 4, the hardest
        assert fit["version"] == "fit_v12" and fit["thinking_seconds"] == MIX_FIT_THINKING < FIT_THINKING["hard"]
        assert spec.round_duration == mix_average_round([item.data for item in spec.rounds])
        assert spec.total_duration == pytest.approx(1.0 + sum(mix_section_length(item.data) for item in spec.rounds) + 3.6, abs=1e-3)
    assert generate(4) == generate(4) and generate(4) != generate(5)
    with pytest.raises(ValueError):
        generate(4, round_count=4)


def test_puzzle_fit_is_shorter_in_the_mix_but_its_content_is_unchanged() -> None:
    spec = generate(11)
    fit = spec.rounds[2].data["sub"]
    assert mix_sub_length(spec.rounds[2].data) < fit_round("hard") - 7  # 12 s instead of 20 s of thinking
    assert round_errors(spec.rounds[2], "hard") == []
    from puzzly.puzzles import puzzle_fit_v12
    assert puzzle_fit_v12.errors(fit, spec.rounds[2].answer, None) == []  # three pieces, six options, three traps
    assert len([o for o in fit["options"] if o["hole"] is not None]) == 3 and len(fit["options"]) == 6


def test_the_games_are_paused_in_the_portal_but_still_supported() -> None:
    for kind in ("puzzle_fit", "memory_challenge", "shade_spot"):
        assert kind not in ACTIVE_PUZZLE_TYPES and kind not in MIXED_PUZZLE_TYPES
        assert kind in PAUSED_PUZZLE_TYPES and kind in SUPPORTED_PUZZLE_TYPES
        assert generate_spec(kind, 3, "hard").puzzle_type == kind  # the Brain Test and old records still need them
        with pytest.raises(ValueError):
            generate_unique_specs(1, kind)
    assert "mind_mix" in ACTIVE_PUZZLE_TYPES and "mind_mix" not in MIXED_PUZZLE_TYPES


def test_bad_sections_are_rejected() -> None:
    spec = generate(5)
    memory, shade, fit = spec.rounds
    assert round_errors(replace(memory, data={**memory.data, "game": "cup_shuffle"}), "hard")
    assert round_errors(replace(shade, data={**shade.data, "level": 1}), "hard")  # numbering mismatch
    assert round_errors(replace(fit, data={**fit.data, "sub": {**fit.data["sub"], "thinking_seconds": 90.0}}), "hard")
    assert round_errors(replace(shade, answer="Z9"), "hard")
    easy_shade = {**shade.data["sub"]}  # a smaller grid is not Shade Spot's hardest level
    assert errors({**shade.data, "sub": {**easy_shade, "grid": 3}}, shade.answer, "hard")
    assert errors({**memory.data, "intro_seconds": 9.0}, memory.answer, "hard")
    swapped = replace(spec, rounds=(spec.rounds[1], spec.rounds[0], spec.rounds[2]))
    assert validation_errors(swapped)  # the order is fixed
    assert validation_errors(replace(spec, round_duration=spec.round_duration + 1))


def test_retuning_never_changes_a_made_video(monkeypatch) -> None:
    import puzzly.config as config
    spec = generate(6)
    before = [mix_section_length(item.data) for item in spec.rounds]
    monkeypatch.setattr(config, "MIX_FIT_THINKING", 25.0)
    monkeypatch.setattr(config, "MIX_SECTION_INTRO", 3.0)
    monkeypatch.setattr(config, "MEMORY_LEVELS", tuple({**level, "memorize": 7.0} for level in MEMORY_LEVELS))
    assert [mix_section_length(item.data) for item in spec.rounds] == before
    assert validation_errors(spec) == []


def test_default_duration_matches_a_real_video() -> None:
    spec = generate(2)
    assert round_duration("mind_mix", "hard") == pytest.approx(spec.round_duration, abs=1e-3)
    assert 55 <= spec.total_duration <= 65


def test_every_section_opens_with_a_title_card_and_every_frame_renders() -> None:
    from puzzly.renderer import render_cover, render_frame
    spec = generate_spec("mind_mix", 21, "hard", background="lemon")
    sections = schedule(spec)
    assert sections[0][0] == spec.intro_duration and sections[-1][0] + sections[-1][1] + 3.6 == pytest.approx(spec.total_duration, abs=1e-3)
    pictures = {}
    for index, (start, length) in enumerate(sections):
        card = np.asarray(render_frame(spec, start + .9, (540, 960))).astype(int)  # the title card
        game = np.asarray(render_frame(spec, start + MIX_SECTION_INTRO + 2.0, (540, 960))).astype(int)  # the game itself
        pictures[index] = (card, game)
        assert np.abs(card - game).mean() > 3  # the card is not the game: the viewer is told what is coming first
        assert render_frame(spec, start + length - .05, (540, 960)).size == (540, 960)
    assert np.abs(pictures[0][1] - pictures[1][1]).mean() > 3 and np.abs(pictures[1][1] - pictures[2][1]).mean() > 3
    assert render_frame(spec, .5, (540, 960)).size == (540, 960)  # the hook
    assert render_frame(spec, spec.total_duration - 1.0, (540, 960)).size == (540, 960)  # the end card
    assert render_cover(spec).size == (1080, 1920)


def test_title_cards_say_what_to_do() -> None:
    from puzzly.visuals.mind_mix import GAME_NAMES, INSTRUCTIONS
    assert set(GAME_NAMES) == set(INSTRUCTIONS) == set(MIX_GAMES)
    assert INSTRUCTIONS["memory_challenge"].startswith("Remember") and "3 missing pieces" in INSTRUCTIONS["puzzle_fit"]
    assert "changed" in INSTRUCTIONS["shade_spot"] and all(len(text) <= 32 for text in INSTRUCTIONS.values())


def test_the_cover_and_hook_show_the_three_games_without_a_real_level() -> None:
    spec = generate(9)
    card = cover_card(spec, 2.0)
    assert card.size == (2000, 940) and np.asarray(card.convert("RGB")).std() > 20
    for game in MIX_GAMES:
        sprite, (ax, ay) = icon_sprite(game, 270)
        assert sprite.width > 270 and ax > 100 and sprite.getchannel("A").getbbox() is not None
    other = cover_card(generate(10), 2.0)
    assert np.array_equal(np.asarray(card), np.asarray(other))  # fixed concept icons: nothing of a real board is on the cover


def test_audio_and_music_follow_the_sections() -> None:
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.music import _windows, supports_music
    spec = generate_spec("mind_mix", 8, "hard")
    audio = timeline_audio(spec)
    assert audio.shape[0] == round(spec.total_duration * 48000) and 0.03 < np.abs(audio).max() <= MIX_PEAK_LIMIT + 1e-9
    cues = sound_cues(spec)
    assert all(0 <= moment <= spec.total_duration for moment, _, _ in cues)
    assert sum(1 for _, name, _ in cues if name == "answer_ding") == 3 + 1 + 1  # memory's three answers, shade's, and fit's
    assert supports_music(spec)
    windows = _windows(replace(spec, metadata={**spec.metadata, "music": "on"}))
    assert windows == music_windows(spec) and len(windows) == 1 + 3 + 1 + 1  # memory's memorize and three questions, shade, fit
    assert all(window["think_start"] < window["think_end"] for window in windows)


def test_metadata_and_manifest_are_complete() -> None:
    from puzzly.metadata import youtube_metadata
    spec = generate_spec("mind_mix", 8, "hard")
    meta = youtube_metadata(spec)
    assert "#shorts" in meta["youtube_title"] and "3" in meta["youtube_description"] and "mind mix" in meta["youtube_tags"]
    assert all(item.answer not in meta["youtube_description"] for item in spec.rounds if isinstance(item.answer, str))


def test_sub_rounds_are_the_games_own_rounds() -> None:
    spec = generate(12)
    for item in spec.rounds:
        sub = sub_round(item)
        assert sub.kind == item.data["game"] and sub.data == item.data["sub"] and sub.answer == item.answer
