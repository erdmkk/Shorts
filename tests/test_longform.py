"""YouTube long-form (16:9) Quick Math brain test: plan, frames, audio, history, and UI."""
from __future__ import annotations

import numpy as np
from PIL import Image

from puzzly import longform as lf
from puzzly.config import DARK_THEMES

PLAN = lf.build_plan(11)


def test_the_flow_guides_the_viewer_round_by_round() -> None:
    kinds = [segment.kind for segment in PLAN.segments]
    assert kinds == ["intro", "round_intro", "round", "round_end", "round_intro", "round", "round_end",
                     "luck_intro", "luck", "luck_end", "round_intro", "round", "round_end", "final_score", "end"]
    for first, second in zip(PLAN.segments, PLAN.segments[1:]):  # back to back, no gaps
        assert abs(first.end - second.start) < 1e-3
    assert PLAN.puzzle_count == 30 and lf.BEST_SCORE == 31
    assert [spec.round_count for spec in PLAN.rounds] == [10, 10, 10]
    assert {item.data["format"] for item in PLAN.rounds[0].rounds} == {"shapes"}
    assert {item.data["format"] for item in PLAN.rounds[1].rounds} == {"operators"}
    final = PLAN.rounds[2].rounds
    assert all(item.data["tier"] >= 2 for item in final)  # the final round is the hardest levels of both formats
    assert [item.data["format"] for item in final] == ["shapes", "operators"] * 5
    assert [item.index for item in final] == list(range(10))
    assert 8 * 60 <= PLAN.total_duration <= 11 * 60  # long enough for mid-roll ads
    # Levels keep their Shorts timing: each round lasts exactly its levels.
    from puzzly.visuals.quick_math import schedule
    for segment in PLAN.segments:
        if segment.kind == "round":
            assert abs(segment.duration - sum(duration for _, duration in schedule(segment.spec))) < 1e-3
        if segment.kind == "luck":
            assert segment.duration == segment.spec.round_duration


def test_every_puzzle_is_valid_unique_and_the_plan_is_deterministic() -> None:
    from puzzly.validation import round_errors
    fingerprints = [item.fingerprint() for spec in PLAN.rounds for item in spec.rounds]
    assert len(set(fingerprints)) == 30
    assert all(round_errors(item, "hard") == [] for spec in PLAN.rounds for item in spec.rounds)
    again = lf.build_plan(11)
    assert again.fingerprint == PLAN.fingerprint and again.total_duration == PLAN.total_duration
    assert lf.build_plan(12).fingerprint != PLAN.fingerprint
    chosen = lf.build_plan(11, background="gold")
    assert chosen.theme == "gold" and PLAN.theme in DARK_THEMES
    assert all(spec.metadata["background"] == chosen.theme for spec in chosen.rounds)
    assert chosen.fingerprint == PLAN.fingerprint  # picking a background never changes the puzzles


def test_chapters_title_and_description_are_youtube_ready() -> None:
    chapters = PLAN.chapters
    assert chapters[0] == (0.0, "Intro & how to play") and len(chapters) == 6
    assert all(b[0] - a[0] >= 10 for a, b in zip(chapters, chapters[1:]))  # YouTube needs 10 s chapters
    meta = PLAN.metadata()
    assert len(meta["title"]) <= 100 and "MATH" in meta["title"]
    assert "0:00 Intro & how to play" in meta["description"] and "Lucky Break" in meta["description"]
    assert "1%" not in meta["title"] and "IQ" not in meta["title"]


def test_frames_for_every_segment_kind_render() -> None:
    seen = set()
    for segment in PLAN.segments:
        if segment.kind in seen:
            continue
        seen.add(segment.kind)
        frame = lf.render_frame(PLAN, segment.start + min(2.0, segment.duration / 2), (480, 270))
        assert frame.size == (480, 270)
    assert len(seen) == 9


def test_the_plus_one_toast_appears_when_the_answer_lands() -> None:
    from puzzly.visuals.quick_math import phases
    segment = next(item for item in PLAN.segments if item.kind == "round")
    answer = phases(segment.spec.rounds[0])["answer"]
    before = np.asarray(lf.render_frame(PLAN, segment.start + answer - .3, (960, 540)), dtype=int)
    after = np.asarray(lf.render_frame(PLAN, segment.start + answer + .5, (960, 540)), dtype=int)
    right_panel = (slice(290, 340), slice(690, 910))  # where the toast sits (960x540 frame)
    assert np.abs(after[right_panel] - before[right_panel]).mean() > 10


def test_audio_covers_the_whole_video_safely() -> None:
    from puzzly.audio import MIX_PEAK_LIMIT
    audio = lf.timeline_audio(PLAN)
    assert audio.shape == (round(PLAN.total_duration * 48000), 2)
    assert float(np.abs(audio).max()) <= MIX_PEAK_LIMIT + 1e-9 and float(np.abs(audio).max()) > .05


def test_final_is_saved_with_thumbnail_text_and_history(tmp_path, monkeypatch) -> None:
    from puzzly.history import HistoryStore

    def fake_video(plan, path, quality="draft", progress=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"video")
        return 0.1

    monkeypatch.setattr(lf, "render_video", fake_video)
    monkeypatch.setattr(lf, "render_thumbnail", lambda plan: Image.new("RGB", (1920, 1080)))
    history = HistoryStore(tmp_path / "history.sqlite")
    result = lf.produce(seed=11, quality="final", history=history, output_root=tmp_path)
    assert result["video"].name == f"PZ_{result['sequence']:04d}_longform_quick_math.mp4"
    assert result["thumbnail"].exists() and result["text"].read_text(encoding="utf-8").startswith("TITLE")
    assert history.contains(PLAN.fingerprint)
    import pytest
    with pytest.raises(ValueError):  # the same seed cannot be published twice
        lf.produce(seed=11, quality="final", history=history, output_root=tmp_path)
    draft = lf.produce(seed=11, quality="draft", history=history, output_root=tmp_path)
    assert draft["sequence"] is None and draft["video"].exists()


def test_ui_switches_to_the_long_form_panel() -> None:
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("app.py").run()
    assert not app.exception
    app.radio[0].set_value("YouTube uzun video (16:9)").run()
    assert not app.exception
    assert any(button.label == "Uzun Video Üret" for button in app.button)
    assert all(box.label != "Puzzle Type" for box in app.selectbox)


def test_a_failed_render_leaves_no_files_behind(tmp_path, monkeypatch) -> None:
    import pytest
    from puzzly.history import HistoryStore

    def broken_video(plan, path, quality="draft", progress=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"half")
        raise RuntimeError("encoder died")

    monkeypatch.setattr(lf, "render_video", broken_video)
    history = HistoryStore(tmp_path / "history.sqlite")
    for quality in ("draft", "final"):
        with pytest.raises(RuntimeError):
            lf.produce(seed=11, quality=quality, history=history, output_root=tmp_path)
    assert [path for path in tmp_path.rglob("*") if path.is_file() and path.suffix != ".sqlite"] == []
    assert not history.contains(PLAN.fingerprint)


def test_the_panel_offers_downloads_and_the_seed(tmp_path) -> None:
    from streamlit.testing.v1 import AppTest
    files = {"video": tmp_path / "v.mp4", "thumbnail": tmp_path / "t.jpg", "text": tmp_path / "t.txt"}
    files["video"].write_bytes(b"video")
    Image.new("RGB", (192, 108)).save(files["thumbnail"])
    files["text"].write_text("TITLE", encoding="utf-8")
    app = AppTest.from_file("app.py")
    app.session_state["longform_result"] = {key: str(value) for key, value in files.items()}
    app.session_state["longform_meta"] = {**PLAN.metadata(), "seed": 11, "theme": PLAN.theme, "music": False,
                                          "sequence": None}
    app.run()
    app.radio[0].set_value("YouTube uzun video (16:9)").run()
    assert not app.exception
    assert len(app.get("download_button")) == 3
    assert any("Seed: 11" in item.value for item in app.caption)
    assert any(button.label == "Bu videoyu Final olarak üret" for button in app.button)
