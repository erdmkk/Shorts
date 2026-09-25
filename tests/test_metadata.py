import csv
from io import BytesIO

from PIL import Image

from puzzly.metadata import write_manifest, youtube_metadata
from puzzly.puzzles.quick_math import generate
from puzzly.generator import generate_spec, render_batch, PUZZLE_TYPES
from puzzly.history import HistoryStore


def test_v2_metadata_and_manifest_round_fields(tmp_path) -> None:
    spec = generate(1, round_count=4)  # the "N Levels of Shape Math" title variant
    metadata = youtube_metadata(spec)
    assert "4" in metadata["youtube_title"] and "#shorts" in metadata["youtube_title"]
    assert "99%" not in " ".join(metadata.values())
    path = tmp_path / "metadata.csv"
    write_manifest(path, [{"filename": "a.mp4", "round_count": spec.round_count, "duration_seconds": spec.total_duration, **metadata}])
    with path.open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["round_count"] == "4" and float(row["duration_seconds"]) == spec.total_duration


def test_batch_manifest_records_all_active_types(tmp_path, monkeypatch) -> None:
    def fake_video(spec, path, **kwargs):
        path.write_bytes(b"video")
        return 0.1
    def fake_cover(spec, path):
        Image.new("RGB", (1080, 1920)).save(path)
    monkeypatch.setattr("puzzly.generator.render_video", fake_video)
    monkeypatch.setattr("puzzly.generator.save_cover", fake_cover)
    stream = BytesIO()
    Image.new("RGB", (90, 160), "navy").save(stream, format="PNG")
    from puzzly.puzzles import hidden_motion_hunt
    monkeypatch.setattr(hidden_motion_hunt, "HIDDEN_MOTION_BACKGROUNDS_DIR", tmp_path / "backgrounds")
    specs = [generate_spec(kind, 82, "medium", background_bytes=stream.getvalue())
             if kind == "hidden_motion_hunt" else generate_spec(kind, 82, "medium") for kind in PUZZLE_TYPES]
    render_batch(specs, output_dir=tmp_path / "batch", history=HistoryStore(tmp_path / "history.sqlite"))
    with (tmp_path / "batch" / "metadata.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for spec, row in zip(specs, rows):
        assert row["puzzle_type"] == spec.puzzle_type
        assert row["difficulty"] == ("" if spec.puzzle_type in ("lucky_pick", "hidden_motion_hunt", "bounce_arena") else "medium")
        assert row["filename"] == row["cover_filename"].replace(".jpg", ".mp4")
        expected_suffix = (f"_{spec.puzzle_type}.mp4"
                           if spec.puzzle_type in ("lucky_pick", "hidden_motion_hunt", "bounce_arena")
                           else f"_{spec.puzzle_type}_medium.mp4")
        assert row["filename"].endswith(expected_suffix)
        assert int(row["round_count"]) == spec.round_count
        assert float(row["duration_seconds"]) == spec.total_duration
        assert row["validation_status"] == "valid"
        assert "#shorts" in row["youtube_title"]
        if spec.puzzle_type == "memory_challenge":
            assert "question_order" in row["question"]
            assert row["token_shapes"] != "[]"
            assert row["color_ids"] != "[]"
            assert row["token_positions"] == "[1, 2, 3, 4, 5, 6, 7, 8, 9]"
            assert row["question_order"] != "[]" and row["final_auto_reveal"]
        elif spec.puzzle_type == "quick_math":
            assert row["equation_templates"] != "[]" and row["operations"] != "[]"
        elif spec.puzzle_type == "missing_number":
            assert row["sequence_families"] != "[]" and row["steps_or_ratios"] != "[]"
        elif spec.puzzle_type == "lucky_pick":
            assert row["circle_count"] == "7"
            assert len(__import__("json").loads(row["lucky_color_ids"])) == 7
            assert len(__import__("json").loads(row["lucky_positions"])) == 7
            assert row["winner_color"] and len(__import__("json").loads(row["elimination_order"])) == 6
            assert row["corridor_template_id"].startswith("neon_maze_v1:") and row["mirrored"] == ""
            assert row["shape_id"] and len(__import__("json").loads(row["target_terminal_mapping"])) == 7
        elif spec.puzzle_type == "hidden_motion_hunt":
            assert row["background_hash"] and row["placement_mode"] == "auto" and row["object_count"] == "7"
            assert len(__import__("json").loads(row["motion_parameters"])) == 7
