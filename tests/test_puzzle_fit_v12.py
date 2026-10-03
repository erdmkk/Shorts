"""Puzzle Fit V12: one big picture, three missing pieces, six tilted numbered options, three of them traps."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from puzzly.config import FIT_THINKING, fit_round
from puzzly.generator import generate_spec
from puzzly.puzzles import puzzle_fit_v12 as fit
from puzzly.validation import validation_errors


@pytest.mark.parametrize("difficulty,count", [("easy", 150), ("medium", 150), ("hard", 500)])
def test_pictures_are_valid_and_have_one_answer_per_hole(difficulty, count) -> None:
    answers, scenes = set(), set()
    for seed in range(count):
        spec = generate_spec("puzzle_fit", seed, difficulty)
        assert validation_errors(spec) == []
        assert spec.round_count == 1 and spec.round_duration == fit_round(difficulty)
        item = spec.rounds[0]
        data = item.data
        assert data["thinking_seconds"] == FIT_THINKING[difficulty]
        holes = data["holes"]
        assert len(holes) == 3 and not set(holes) & fit.CORNERS and set(holes) & fit.INNER
        for option in data["options"]:
            fitting = [letter for letter, slot in zip(fit.LETTERS, holes) if fit.fits(option["edges"], data["piece_edges"][slot])]
            assert fitting == ([option["hole"]] if option["hole"] else [])
            assert 12 <= abs(option["tilt"]) <= 30  # every option lies tilted
            # Traps show a hole's own picture, so the picture alone never gives the answer.
            assert option["art_slot"] in holes
        assert sum(option["hole"] is None for option in data["options"]) == 3
        answers.add(item.answer)
        scenes.add(data["scene"])
    assert len(answers) >= min(100, count // 2) and scenes == set(fit.SCENES)  # 120 possible answers (6 x 5 x 4)
    assert generate_spec("puzzle_fit", 4, difficulty) == generate_spec("puzzle_fit", 4, difficulty)


def test_turns_follow_the_difficulty() -> None:
    easy = [option["turns"] for seed in range(40) for option in generate_spec("puzzle_fit", seed, "easy").rounds[0].data["options"]]
    hard = [option["turns"] for seed in range(40) for option in generate_spec("puzzle_fit", seed, "hard").rounds[0].data["options"]]
    assert set(easy) == {0} and set(hard) == {0, 1, 2, 3}


def test_tampered_pictures_are_rejected() -> None:
    spec = generate_spec("puzzle_fit", 6, "hard")
    item = spec.rounds[0]
    assert validation_errors(replace(spec, rounds=(replace(item, answer="A1 B2 C3"),))) or item.answer == "A1 B2 C3"
    options = [dict(option) for option in item.data["options"]]
    trap = next(index for index, option in enumerate(options) if option["hole"] is None)
    hole_edges = item.data["piece_edges"][item.data["holes"][0]]
    options[trap] = {**options[trap], "base": list(hole_edges), "turns": 0, "edges": list(hole_edges)}
    broken = replace(spec, rounds=(replace(item, data={**item.data, "options": options}),))
    assert any("trap fits" in error for error in validation_errors(broken))


def test_old_puzzle_fit_records_still_validate() -> None:
    from puzzly.puzzles.puzzle_fit import legacy_generate
    assert validation_errors(legacy_generate(12, "hard", round_count=5)) == []


def test_frames_cover_audio_and_metadata() -> None:
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.covers import has_template, render_game_cover
    from puzzly.metadata import youtube_metadata
    from puzzly.renderer import render_frame
    from puzzly.visuals.puzzle_fit_v12 import phases
    spec = generate_spec("puzzle_fit", 13, "hard")
    times = phases(spec.rounds[0])
    start = spec.intro_duration
    moments = [.5, start + 3, start + times["place"] + .5, start + times["shine"] + .3, spec.total_duration - .3]
    frames = [np.asarray(render_frame(spec, t, (270, 480)), dtype=int) for t in moments]
    assert all(frame.shape == (480, 270, 3) for frame in frames)
    assert np.abs(frames[1] - frames[3]).mean() > 1
    assert has_template(spec) and render_game_cover(spec).size == (1080, 1920)
    audio = timeline_audio(replace(spec, metadata={"music": "on"}))
    assert audio.shape == (round(spec.total_duration * 48000), 2) and float(np.abs(audio).max()) <= MIX_PEAK_LIMIT + 1e-9
    meta = youtube_metadata(spec)
    assert "#shorts" in meta["youtube_title"] and spec.rounds[0].answer not in meta["youtube_description"]


def test_the_portal_has_paused_puzzle_fit_but_mind_mix_uses_it() -> None:
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("app.py").run()
    options = next(box for box in app.selectbox if box.label == "Puzzle Type").options
    assert "Puzzle Fit" not in options and "Mind Mix" in options
    from puzzly.puzzles.mind_mix import generate as mix
    assert mix(5).rounds[2].data["game"] == "puzzle_fit"
