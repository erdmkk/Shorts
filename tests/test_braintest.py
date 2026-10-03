"""The ten-game Brain Test long-form: plan, timing, cards, frames, audio, episode numbering, and thumbnails."""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from PIL import Image, ImageChops

from puzzly import braintest as bt
from puzzly.braintest_cover import HEADLINES, LAYOUTS, PALETTES, render_braintest_thumbnail, variant
from puzzly.audio import MIX_PEAK_LIMIT
from puzzly.history import HistoryStore

PLAN = bt.build_plan(3, background="violet", episode=3)


def test_the_estimate_matches_the_plan_and_fits_nine_to_ten_minutes() -> None:
    assert bt.expected_points() == PLAN.total_points == 36
    assert 540 <= PLAN.total_duration <= 600
    assert abs(bt.estimated_duration() - PLAN.total_duration) < 20
    assert PLAN.block_points == [7, 8, 8, 13]


def test_the_order_puts_quick_math_last_in_its_block() -> None:
    keys = [slot.key for slot in PLAN.slots]
    assert keys == [key for key, _ in bt.SEQUENCE]
    assert {slot.game.kind for slot in PLAN.slots} == {"cup_shuffle", "puzzle_fit", "quick_math", "cube_count", "matchstick",
                                                       "chess_mate", "memory_challenge", "find_the_exit", "line_follow"}
    for block in range(len(bt.BLOCK_SIZES)):
        members = [slot for slot in PLAN.slots if slot.block == block]
        assert len(members) == bt.BLOCK_SIZES[block]
        for slot in members[:-1]:
            assert slot.key not in ("shapes", "signs")  # Quick Math is the hardest, so it closes its block
    assert PLAN.slots[2].key == "shapes" and PLAN.slots[9].key == "signs"
    assert len({fp for slot in PLAN.slots for fp in (round_.fingerprint() for round_ in slot.spec.rounds)}) == sum(len(s.spec.rounds) for s in PLAN.slots)


def test_flash_games_get_the_ready_card_with_a_countdown() -> None:
    ready = {slot.key for slot in PLAN.slots if slot.game.ready}
    assert ready == {"cup", "cube", "memory"}
    frame = bt.render_frame(PLAN, next(s for s in PLAN.segments if s.kind == "card" and PLAN.slots[s.slot].key == "cube").start + 4.6, (960, 540))
    assert frame.size == (960, 540)


def test_chess_gives_15_seconds_and_shows_the_answer() -> None:
    from puzzly.visuals.chess_mate import long_phases
    phases = long_phases()
    from puzzly.config import CHESS_LONG_ENTRANCE, CHESS_LONG_THINKING
    assert CHESS_LONG_THINKING == 15.0 and phases["think_end"] == pytest.approx(CHESS_LONG_ENTRANCE + 15.0)
    chess = next(slot for slot in PLAN.slots if slot.key == "chess")
    assert chess.answers and chess.duration == pytest.approx(phases["end"])
    before = bt.render_frame(PLAN, next(s for s in PLAN.segments if s.kind == "game" and s.slot == chess.index).start + phases["think_end"] - 1, (960, 540))
    after = bt.render_frame(PLAN, next(s for s in PLAN.segments if s.kind == "game" and s.slot == chess.index).start + phases["think_end"] + 2, (960, 540))
    assert ImageChops.difference(before, after).getbbox() is not None  # the answer appears


def test_chapters_are_youtube_ready() -> None:
    starts = [start for start, _ in PLAN.chapters]
    assert starts[0] == 0 and all(b - a >= 10 for a, b in zip(starts, starts[1:]))
    names = [name for _, name in PLAN.chapters]
    assert "3. Quick Math: Shape Equations" in names and "10. Quick Math: Missing Signs" in names and names[-1] == "Final Score"
    meta = PLAN.metadata()
    assert "#3" in meta["title"] or "Brain Test" in meta["title"]
    assert len(meta["title"]) <= 100 and "IQ" not in meta["title"] + meta["description"]


def test_frames_for_every_segment_kind_render() -> None:
    seen = set()
    for segment in PLAN.segments:
        key = (segment.kind, PLAN.slots[segment.slot].key if segment.slot >= 0 else "")
        if key in seen:
            continue
        seen.add(key)
        frame = bt.render_frame(PLAN, segment.start + min(segment.duration - .05, 2.0), (960, 540))
        assert frame.size == (960, 540) and frame.getbbox() is not None
    assert {kind for kind, _ in seen} == {"intro", "card", "game", "checkpoint", "final_score", "end"}


def test_audio_covers_the_whole_video_safely() -> None:
    audio = bt.timeline_audio(PLAN)
    assert audio.shape == (round(PLAN.total_duration * 48000), 2)
    assert 0.05 < float(np.abs(audio).max()) <= MIX_PEAK_LIMIT + 1e-9


def _fake_render(monkeypatch) -> None:
    def fake_video(plan, path, quality="draft", progress=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")
        return 0.1

    monkeypatch.setattr(bt, "render_video", fake_video)
    monkeypatch.setattr(bt, "render_thumbnail", lambda plan: Image.new("RGB", (1920, 1080)))
    monkeypatch.setattr(bt, "build_plan", lambda seed, background="random", music=False, episode=1, progress=None:
                        dataclasses.replace(PLAN, episode=episode, seed=seed))


def test_a_draft_does_not_use_up_the_episode_number(tmp_path, monkeypatch) -> None:
    _fake_render(monkeypatch)
    history = HistoryStore(tmp_path / "history.sqlite")
    assert bt.episode_number(history) == 1
    first = bt.produce(seed=5, quality="draft", history=history, output_root=tmp_path)
    assert first["sequence"] is None and first["episode"] == 1 and bt.episode_number(history) == 1
    second = bt.produce(seed=6, quality="draft", history=history, output_root=tmp_path)  # an unsaved #1 is #1 again
    assert second["episode"] == 1
    saved = bt.produce(seed=7, quality="final", history=history, output_root=tmp_path)
    assert saved["episode"] == 1 and saved["video"].name == f"PZ_{saved['sequence']:04d}_longform_brain_test.mp4"
    assert bt.episode_number(history) == 2
    assert bt.produce(seed=8, quality="draft", history=history, output_root=tmp_path)["episode"] == 2
    assert "BRAIN TEST NUMBER\n#1" in saved["text"].read_text(encoding="utf-8")


def test_a_failed_final_keeps_the_number_and_leaves_no_files(tmp_path, monkeypatch) -> None:
    _fake_render(monkeypatch)

    def broken(plan, path, quality="draft", progress=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"half")
        raise RuntimeError("encoder died")

    monkeypatch.setattr(bt, "render_video", broken)
    history = HistoryStore(tmp_path / "history.sqlite")
    with pytest.raises(RuntimeError):
        bt.produce(seed=5, quality="final", history=history, output_root=tmp_path)
    assert bt.episode_number(history) == 1
    assert [path for path in tmp_path.rglob("*") if path.is_file() and "sqlite" not in path.name] == []


def test_neighbouring_episodes_differ_in_every_cover_dimension() -> None:
    combos = set()
    for episode in range(1, 61):
        now, after = variant(episode), variant(episode + 1)
        assert all(a != b for a, b in zip(now, after)), episode
        combos.add(now[:2])
    assert len(combos) == len(LAYOUTS) * len(PALETTES) // 2 or len(combos) >= 24
    assert len({variant(e)[2] for e in range(1, 9)}) == len(HEADLINES)
    heroes = [dataclasses.replace(PLAN, episode=e).hero_key for e in range(1, 12)]
    assert len(set(heroes[:10])) == 10 and heroes[0] == heroes[10] and all(a != b for a, b in zip(heroes, heroes[1:]))


def test_thumbnails_are_1080p_and_look_different() -> None:
    images = [render_braintest_thumbnail(dataclasses.replace(PLAN, episode=episode)) for episode in (1, 2, 3)]
    assert all(image.size == (1920, 1080) for image in images)
    for left, right in ((0, 1), (1, 2), (0, 2)):
        diff = np.abs(np.asarray(images[left], np.int16) - np.asarray(images[right], np.int16)).mean()
        assert diff > 12
    # The number that keeps uploads distinct is on the cover; the same episode draws the same cover.
    again = render_braintest_thumbnail(dataclasses.replace(PLAN, episode=2))
    assert ImageChops.difference(again, images[1]).getbbox() is None


def test_ui_offers_both_long_form_kinds() -> None:
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("app.py").run()
    app.radio[0].set_value("YouTube uzun video (16:9)").run()
    assert not app.exception
    assert app.radio[1].options[0].startswith("Brain Test") and "36 puan" in app.info[0].value
    app.radio[1].set_value(app.radio[1].options[1]).run()
    assert not app.exception and "30 bulmaca" in app.info[0].value
