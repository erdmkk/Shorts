"""Chess: Mate in 1 — real Lichess positions, validated with python-chess, shown without the answer."""
from __future__ import annotations

from dataclasses import replace

import chess
import numpy as np
import pytest

from puzzly.generator import generate_spec, output_stem
from puzzly.puzzles import chess_mate as cm
from puzzly.registry import ACTIVE_PUZZLE_TYPES, MIXED_PUZZLE_TYPES
from puzzly.validation import validation_errors


def test_the_dataset_is_local_and_every_band_is_well_stocked() -> None:
    puzzles = cm.load_puzzles()
    assert len({row["id"] for row in puzzles}) == len(puzzles)
    for difficulty in cm.RATING_BANDS:
        assert len(cm.pool(difficulty)) >= 1000


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
def test_specs_are_valid_deterministic_and_have_one_mating_move(difficulty) -> None:
    ids = set()
    for seed in range(60):
        spec = generate_spec("chess_mate", seed, difficulty)
        assert validation_errors(spec) == []
        assert spec == generate_spec("chess_mate", seed, difficulty)
        assert spec.total_duration == 30.0 and spec.intro_duration == 0 and spec.outro_duration == 0
        data, answer = spec.rounds[0].data, spec.rounds[0].answer
        board = chess.Board(data["fen"])
        mates = cm.mating_moves(board)
        assert [move.uci() for move in mates] == [answer["uci"]]
        assert data["side"] == ("white" if board.turn else "black")
        low, high = cm.RATING_BANDS[difficulty]
        assert low <= data["rating"] <= high
        ids.add(data["puzzle_id"])
    assert len(ids) >= 55  # seeds spread over the pool


def test_a_wrong_answer_or_a_broken_position_is_rejected() -> None:
    spec = generate_spec("chess_mate", 3, "hard")
    item = spec.rounds[0]
    wrong = replace(spec, rounds=(replace(item, answer={"uci": "a1a2", "san": "Ra2"}),))
    assert any("mating move" in error for error in validation_errors(wrong))
    broken = replace(spec, rounds=(replace(item, data={**item.data, "fen": "8/8/8/8/8/8/8/8 w - - 0 1"}),))
    assert validation_errors(broken)
    easy_band = replace(spec, difficulty="easy")
    assert any("rating" in error for error in validation_errors(easy_band))


def test_it_is_a_standalone_active_type_with_difficulty_in_the_filename() -> None:
    assert "chess_mate" in ACTIVE_PUZZLE_TYPES and "chess_mate" not in MIXED_PUZZLE_TYPES
    spec = generate_spec("chess_mate", 5, "hard")
    assert output_stem(12, spec) == "PZ_0012_chess_mate_hard"


def test_the_frame_is_a_still_that_never_shows_the_answer() -> None:
    from puzzly.renderer import render_frame
    spec = generate_spec("chess_mate", 7, "hard")
    first = np.asarray(render_frame(spec, 0.0, (270, 480)))
    last = np.asarray(render_frame(spec, 29.9, (270, 480)))
    assert first.shape == (480, 270, 3) and np.array_equal(first, last)


def test_black_to_move_turns_the_board() -> None:
    from puzzly.visuals.chess_mate import square_at
    assert square_at(7, 0, False) == chess.A1 and square_at(0, 7, False) == chess.H8
    assert square_at(7, 0, True) == chess.H8 and square_at(0, 7, True) == chess.A1


def test_cover_metadata_and_audio() -> None:
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.covers import has_template, render_game_cover
    from puzzly.metadata import youtube_metadata
    spec = generate_spec("chess_mate", 9, "hard")
    assert has_template(spec) and render_game_cover(spec).size == (1080, 1920)
    meta = youtube_metadata(spec)
    san = spec.rounds[0].answer["san"]
    assert san not in meta["youtube_title"] and san not in meta["youtube_description"]
    assert "Lichess" in meta["youtube_description"]
    silent = timeline_audio(spec)
    assert silent.shape == (30 * 48000, 2) and not np.any(silent)  # no effects at all
    music = timeline_audio(replace(spec, metadata={"music": "on"}))
    assert 0.01 < float(np.abs(music).max()) <= MIX_PEAK_LIMIT + 1e-9


def test_ui_offers_chess_without_a_challenge_count() -> None:
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("app.py").run()
    type_box = next(box for box in app.selectbox if box.label == "Puzzle Type")
    type_box.select("Chess: Mate in 1").run()
    assert not app.exception
    labels = [box.label for box in app.selectbox]
    assert "Difficulty" not in labels and "Challenges per video" not in labels
    assert app.number_input[0].label == "Min rating" and app.number_input[0].value == 1800
    assert any("tek hamlede mat" in item.value for item in app.caption)


def test_board_colours_are_a_metadata_choice_outside_the_fingerprint() -> None:
    from puzzly.config import CHESS_BOARDS
    from puzzly.renderer import render_frame
    from puzzly.visuals.chess_mate import board_for
    spec = generate_spec("chess_mate", 4, "hard")
    assert board_for(spec) == "wood" and len(CHESS_BOARDS) >= 5
    green = replace(spec, metadata={"board": "green"})
    assert board_for(green) == "green" and green.fingerprint() == spec.fingerprint()
    a = np.asarray(render_frame(spec, 1.0, (270, 480)), dtype=int)
    b = np.asarray(render_frame(green, 1.0, (270, 480)), dtype=int)
    assert np.abs(a - b).mean() > 3
    assert board_for(replace(spec, metadata={"board": "unknown"})) == "wood"


def test_pieces_render_with_and_without_the_diagram_font(monkeypatch, tmp_path) -> None:
    from puzzly.visuals import chess_mate as visuals
    for white in (True, False):
        sprite = visuals.piece_sprite("b", white, 96)
        assert sprite.size == (96, 96) and sprite.getchannel("A").getbbox()
    black = np.asarray(visuals.piece_sprite("k", False, 96).convert("RGBA"), dtype=int)
    opaque = black[..., 3] > 250
    assert (black[opaque][:, :3].mean(axis=1) < 60).mean() > .5  # a black piece is mostly black
    monkeypatch.setattr(visuals, "DIAGRAM_FONT", tmp_path / "missing.ttf")
    visuals.piece_sprite.cache_clear()
    try:
        assert visuals.piece_sprite("q", False, 64).size == (64, 64)
    finally:
        visuals.piece_sprite.cache_clear()


def test_the_creator_sees_the_mating_move_in_the_ui(tmp_path) -> None:
    from streamlit.testing.v1 import AppTest
    assert cm.move_label({"uci": "c6d5", "san": "Bd5#"}) == "C6 > D5 (Bd5#)"
    assert cm.move_label({"uci": "e7e8q", "san": "e8=Q#"}) == "E7 > E8, vezir çıkar (e8=Q#)"
    spec = generate_spec("chess_mate", 3, "hard")
    video = tmp_path / "PZ_0001_chess_mate_hard.mp4"
    video.write_bytes(b"video")
    app = AppTest.from_file("app.py")
    app.session_state["videos"] = [str(video)]
    app.session_state["chess_answers"] = {str(video): spec.rounds[0].answer}
    app.run()
    assert not app.exception
    assert any(cm.move_label(spec.rounds[0].answer) in item.value for item in app.success)


def test_min_rating_draws_only_puzzles_at_or_above_it(tmp_path) -> None:
    from puzzly.generator import generate_unique_specs
    from puzzly.history import HistoryStore
    assert len(cm.rating_pool(1800)) >= 3000 and len(cm.rating_pool(2000)) >= 300
    specs = generate_unique_specs(12, "chess_mate", base_seed=5, history=HistoryStore(tmp_path / "h.sqlite"), min_rating=1800)
    for spec in specs:
        assert spec.rounds[0].data["rating"] >= 1800 and validation_errors(spec) == []
        assert spec.difficulty == cm.band_of(spec.rounds[0].data["rating"]) == "hard"
    assert generate_spec("chess_mate", 9, min_rating=1300).difficulty in ("medium", "hard")
    assert generate_spec("chess_mate", 9, min_rating=2000) == generate_spec("chess_mate", 9, min_rating=2000)
    with pytest.raises(ValueError, match="rated 3000"):
        generate_spec("chess_mate", 1, min_rating=3000)


def test_every_piece_is_centred_in_its_square() -> None:
    from puzzly.visuals.chess_mate import piece_sprite
    for kind in "kqrbnp":
        for white in (True, False):
            box = piece_sprite(kind, white, 120).getchannel("A").getbbox()
            assert abs((box[0] + box[2]) / 2 - 60) <= 1.5 and abs((box[1] + box[3]) / 2 - 60) <= 1.5
