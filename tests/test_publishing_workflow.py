import csv
from pathlib import Path

from PIL import Image
import pytest

from puzzly.generator import (generate_spec, generate_unique_specs, render_batch,
                              render_draft_previews, rerender_record_final,
                              save_draft_preview, spec_for_record)
from puzzly.history import HistoryStore
from puzzly.renderer import save_cover


def _fake_render(spec, path: Path, **kwargs) -> float:
    path.write_bytes(b"local-video")
    return 0.01


def _fake_cover(spec, path: Path) -> None:
    Image.new("RGB", (1080, 1920), "white").save(path, quality=94)


def _render_one(tmp_path, monkeypatch, history, spec, folder="output"):
    monkeypatch.setattr("puzzly.generator.render_video", _fake_render)
    monkeypatch.setattr("puzzly.generator.save_cover", _fake_cover)
    directory, videos = render_batch([spec], output_dir=tmp_path / folder, history=history)
    return directory, videos[0]


def test_sequence_and_names_survive_empty_output_and_new_store(tmp_path, monkeypatch) -> None:
    database = tmp_path / "data" / "generation_history.sqlite"
    history = HistoryStore(database)
    output, first = _render_one(tmp_path, monkeypatch, history, generate_spec("memory_challenge", 610, "hard"))
    assert first.name == "PZ_0001_memory_challenge_hard.mp4"
    assert first.with_suffix(".jpg").exists()
    for path in output.iterdir():
        path.unlink()
    reopened = HistoryStore(database)
    _, second = _render_one(tmp_path, monkeypatch, reopened, generate_spec("find_the_exit", 611, "medium"))
    assert second.name == "PZ_0002_find_the_exit_medium.mp4"
    assert reopened.last_sequence() == 2


def test_sqlite_fingerprint_duplicate_rejection_and_metadata_independence(tmp_path, monkeypatch) -> None:
    database = tmp_path / "generation_history.sqlite"
    history = HistoryStore(database)
    spec = generate_spec("missing_number", 812, "easy")
    output, video = _render_one(tmp_path, monkeypatch, history, spec)
    fingerprint = spec.fingerprint()
    assert HistoryStore(database).contains(fingerprint)
    (output / "metadata.csv").unlink()
    assert HistoryStore(database).contains(fingerprint)
    with pytest.raises(ValueError, match="already exists"):
        _render_one(tmp_path, monkeypatch, HistoryStore(database), spec, "other-output")
    assert video.exists() and history.last_sequence() == 1


def test_generate_unique_specs_queries_sqlite_history(tmp_path) -> None:
    history = HistoryStore(tmp_path / "generation_history.sqlite")
    first = generate_unique_specs(1, "quick_math", "easy", base_seed=88, history=history)[0]
    history.commit_success(puzzle_type=first.puzzle_type, difficulty=first.difficulty, seed=first.seed,
                           fingerprint=first.fingerprint(), finalize_files=lambda number: ("old.mp4", "old.jpg"))
    second = generate_unique_specs(1, "quick_math", "easy", base_seed=88, history=HistoryStore(history.path))[0]
    assert second.fingerprint() != first.fingerprint()


def test_cover_is_direct_full_resolution_jpeg(tmp_path) -> None:
    path = tmp_path / "PZ_0001_missing_number_easy.jpg"
    save_cover(generate_spec("missing_number", 52, "easy"), path)
    with Image.open(path) as image:
        assert image.format == "JPEG"
        assert image.size == (1080, 1920)
        image.verify()


def test_cover_failure_does_not_commit_or_consume_sequence(tmp_path, monkeypatch) -> None:
    history = HistoryStore(tmp_path / "generation_history.sqlite")
    monkeypatch.setattr("puzzly.generator.render_video", _fake_render)
    monkeypatch.setattr("puzzly.generator.save_cover", lambda *args: (_ for _ in ()).throw(OSError("cover failed")))
    with pytest.raises(OSError, match="cover failed"):
        render_batch([generate_spec("quick_math", 101)], output_dir=tmp_path / "output", history=history)
    assert history.last_sequence() == 0
    assert history.records() == []
    assert not list((tmp_path / "output").glob("*"))


def test_legacy_json_migration_is_backed_up_once(tmp_path) -> None:
    legacy = tmp_path / "history.json"
    legacy.write_text('{"fingerprints": ["bbb", "aaa", "aaa"]}', encoding="utf-8")
    old_output = tmp_path / "old-output"
    old_output.mkdir()
    (old_output / "PZ_0007_old_easy.mp4").write_bytes(b"old")
    store = HistoryStore(tmp_path / "generation_history.sqlite", legacy_path=legacy, legacy_output_dir=old_output)
    assert store.load() == {"aaa", "bbb"}
    assert store.last_sequence() == 7
    assert legacy.with_name("history.json.backup-before-sqlite").read_bytes() == legacy.read_bytes()
    assert HistoryStore(store.path, legacy_path=legacy, legacy_output_dir=old_output).last_sequence() == 7


def test_draft_preview_is_not_published_until_save(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("puzzly.generator.render_video", _fake_render)
    monkeypatch.setattr("puzzly.generator.save_cover", _fake_cover)
    history = HistoryStore(tmp_path / "generation_history.sqlite")
    spec = generate_spec("quick_math", 404, "easy", challenges=3)

    preview_dir, previews = render_draft_previews([spec], preview_root=tmp_path / "previews")
    assert preview_dir.is_dir() and previews[0].video_path.is_file()
    assert history.records() == []
    assert not (tmp_path / "output").exists()

    record, saved_path = save_draft_preview(
        previews[0], output_dir=tmp_path / "output", history=history)
    assert saved_path.is_file() and saved_path.with_suffix(".jpg").is_file()
    assert record.quality == "draft"
    assert spec_for_record(record, tmp_path / "output") == spec
    assert len(history.records()) == 1


def test_saved_draft_rerenders_final_in_place_with_same_spec(tmp_path, monkeypatch) -> None:
    qualities: list[tuple[str, str]] = []

    def tracked_render(spec, path: Path, **kwargs) -> float:
        quality = kwargs["quality"]
        qualities.append((quality, spec.fingerprint()))
        path.write_bytes(quality.encode())
        return 0.02

    monkeypatch.setattr("puzzly.generator.render_video", tracked_render)
    monkeypatch.setattr("puzzly.generator.save_cover", _fake_cover)
    history = HistoryStore(tmp_path / "generation_history.sqlite")
    spec = generate_spec("missing_number", 505, "medium", challenges=3)
    _, previews = render_draft_previews([spec], preview_root=tmp_path / "previews")
    record, draft_path = save_draft_preview(
        previews[0], output_dir=tmp_path / "output", history=history)

    final_path = rerender_record_final(record, output_root=tmp_path / "output", history=history)
    updated = history.record(record.sequence_no)
    assert final_path == draft_path and final_path.read_bytes() == b"final"
    assert updated is not None and updated.quality == "final"
    assert updated.sequence_no == record.sequence_no and len(history.records()) == 1
    assert spec_for_record(updated, tmp_path / "output") == spec
    assert qualities == [("draft", spec.fingerprint()), ("final", spec.fingerprint())]


def test_old_history_record_recovers_exact_content_from_manifest(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("puzzly.generator.render_video", _fake_render)
    monkeypatch.setattr("puzzly.generator.save_cover", _fake_cover)
    history = HistoryStore(tmp_path / "generation_history.sqlite")
    spec = generate_spec("quick_math", 606, "hard", operation="multiplication", challenges=3)
    render_batch([spec], output_dir=tmp_path / "output", history=history)
    record = history.records()[0]
    with history._connect() as connection:
        connection.execute(
            "UPDATE generations SET spec_json='', quality='' WHERE sequence_no=?",
            (record.sequence_no,),
        )
    old_record = history.record(record.sequence_no)
    assert old_record is not None and old_record.spec_json == ""
    recovered = spec_for_record(old_record, tmp_path / "output")
    assert recovered.seed == spec.seed
    assert recovered.rounds == spec.rounds
    assert recovered.fingerprint() == spec.fingerprint()
