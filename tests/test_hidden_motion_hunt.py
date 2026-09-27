from __future__ import annotations

from collections import Counter
from io import BytesIO
import json
import math
import random

import numpy as np
from PIL import Image
import pytest
from streamlit.testing.v1 import AppTest

from puzzly.config import (HIDDEN_MOTION_DURATION, HIDDEN_MOTION_MIN_GAP,
                           HIDDEN_MOTION_SAFE_BOUNDS, HIDDEN_MOTION_TIER_COUNTS)
from puzzly.generator import generate_spec, generate_unique_specs, mixed_types, render_batch
from puzzly.history import HistoryStore
from puzzly.puzzles import hidden_motion_hunt
from puzzly.puzzles.hidden_motion_hunt import motion_state
from puzzly.registry import ACTIVE_PUZZLE_TYPES, EXPERIMENTAL_PUZZLE_TYPES, MIXED_PUZZLE_TYPES
from puzzly.validation import validate_spec


@pytest.fixture
def background_bytes(tmp_path, monkeypatch) -> bytes:
    monkeypatch.setattr(hidden_motion_hunt, "HIDDEN_MOTION_BACKGROUNDS_DIR", tmp_path / "backgrounds")
    monkeypatch.setattr(hidden_motion_hunt, "HIDDEN_MOTION_LAYOUTS_DIR", tmp_path / "layouts")
    monkeypatch.setattr(hidden_motion_hunt, "HIDDEN_MOTION_OBJECTS_DIR", tmp_path / "objects")
    stream = BytesIO()
    Image.new("RGB", (900, 1200), "#789ABC").save(stream, format="PNG")
    return stream.getvalue()


def _envelope(item: dict) -> float:
    radius = item["diameter"] * (1 + item["scale_amplitude"]) / 2
    return radius + max(item["x_amplitude"], item["y_amplitude"])


def test_registry_standalone_status_and_ui_controls() -> None:
    assert "hidden_motion_hunt" in ACTIVE_PUZZLE_TYPES
    assert "hidden_motion_hunt" not in MIXED_PUZZLE_TYPES
    assert "line_follow" in ACTIVE_PUZZLE_TYPES and "line_follow" not in EXPERIMENTAL_PUZZLE_TYPES
    assert "hidden_motion_hunt" not in set(mixed_types(700, random.Random(17)))
    app = AppTest.from_file("app.py").run()
    app.selectbox[0].select("Hidden Motion Hunt").run()
    assert not app.exception
    labels = [box.label for box in app.selectbox]
    assert "Difficulty" not in labels and "Challenges per video" not in labels
    assert "Number of videos" in labels and "Quality" in labels
    uploaders = app.get("file_uploader")
    assert len(uploaders) == 1 and uploaders[0].label == "Background Image Upload"
    assert len(app.radio) == 1 and app.radio[0].options == ["Manual Placement", "Auto Placement"]
    assert "Upload a 9:16 background image" in " ".join(item.value for item in app.caption)


def test_upload_is_required_and_invalid_data_fails_clearly(background_bytes) -> None:
    with pytest.raises(ValueError, match="required"):
        generate_spec("hidden_motion_hunt", 1)
    with pytest.raises(ValueError, match="could not be decoded"):
        generate_spec("hidden_motion_hunt", 1, background_bytes=b"not an image")


def test_spec_geometry_tiers_motion_loop_and_determinism(background_bytes) -> None:
    first = generate_spec("hidden_motion_hunt", 4501, background_bytes=background_bytes)
    second = generate_spec("hidden_motion_hunt", 4501, background_bytes=background_bytes)
    assert first == second
    validate_spec(first)
    assert first.difficulty is None and first.round_count == 1
    assert first.intro_duration == first.outro_duration == 0
    assert first.round_duration == first.total_duration == HIDDEN_MOTION_DURATION
    data = first.rounds[0].data
    objects = data["objects"]
    assert len(objects) == 7 and Counter(item["tier"] for item in objects) == Counter(HIDDEN_MOTION_TIER_COUNTS)
    assert len({item["phase"] for item in objects}) == 7
    left, top, right, bottom = HIDDEN_MOTION_SAFE_BOUNDS
    for item in objects:
        envelope = _envelope(item)
        x, y = item["position"]
        assert left + envelope <= x <= right - envelope
        assert top + envelope <= y <= bottom - envelope
        assert motion_state(item, 0) == pytest.approx(motion_state(item, HIDDEN_MOTION_DURATION), abs=1e-9)
    for index, item in enumerate(objects):
        for other in objects[:index]:
            assert math.dist(item["position"], other["position"]) >= _envelope(item) + _envelope(other) + HIDDEN_MOTION_MIN_GAP
    assert np.max(np.abs(__import__("puzzly.audio", fromlist=["timeline_audio"]).timeline_audio(first))) == 0


def test_background_hash_and_fingerprint_track_source_content(background_bytes) -> None:
    same = generate_spec("hidden_motion_hunt", 808, background_bytes=background_bytes)
    stream = BytesIO()
    Image.new("RGB", (900, 1200), "#789ABD").save(stream, format="PNG")
    changed = generate_spec("hidden_motion_hunt", 808, background_bytes=stream.getvalue())
    assert same.rounds[0].data["background_hash"] == hidden_motion_hunt.prepare_background(background_bytes)
    assert same.rounds[0].data["background_hash"] != changed.rounds[0].data["background_hash"]
    assert same.fingerprint() != changed.fingerprint()


def test_manual_layout_round_trip_exact_values_and_vertical_only_motion(background_bytes) -> None:
    background_hash = hidden_motion_hunt.prepare_background(background_bytes)
    layout = hidden_motion_hunt.default_manual_layout()
    layout[0].update({"shape": "star", "color": "#123ABC", "x_pct": .31, "y_pct": .57,
                      "size_px": 11, "jump_height_px": 23})
    saved = hidden_motion_hunt.save_manual_layout(background_hash, layout)
    assert saved.exists()
    restored = hidden_motion_hunt.load_manual_layout(background_hash)
    assert restored == hidden_motion_hunt.normalize_manual_layout(layout)
    first = generate_spec("hidden_motion_hunt", 321, background_bytes=background_bytes,
                          placement_mode="manual", manual_objects=restored)
    second = generate_spec("hidden_motion_hunt", 321, background_bytes=background_bytes,
                           placement_mode="manual", manual_objects=restored)
    assert first == second and first.rounds[0].data["placement_mode"] == "manual"
    obj = first.rounds[0].data["objects"][0]
    assert (obj["shape"], obj["color"], obj["x_pct"], obj["y_pct"], obj["diameter"], obj["y_amplitude"]) == (
        "star", "#123ABC", .31, .57, 11, 23)
    samples = [motion_state(obj, moment) for moment in (0, .125, .375, .625)]
    assert all(state[0] == pytest.approx(.31 * 1080) for state in samples)
    assert {state[2] for state in samples} == {1.0}
    assert len({round(state[1], 5) for state in samples}) > 1
    assert motion_state(obj, 0) == pytest.approx(motion_state(obj, HIDDEN_MOTION_DURATION), abs=1e-9)


def test_manual_seed_preserves_wysiwyg_phase_and_layout_changes_fingerprint(background_bytes) -> None:
    layout = hidden_motion_hunt.default_manual_layout()
    first = generate_spec("hidden_motion_hunt", 901, background_bytes=background_bytes,
                          placement_mode="manual", manual_objects=layout)
    other_seed = generate_spec("hidden_motion_hunt", 902, background_bytes=background_bytes,
                               placement_mode="manual", manual_objects=layout)
    stable_fields = ("shape", "color", "x_pct", "y_pct", "diameter", "jump_height_px")
    assert [[item[field] for field in stable_fields] for item in first.rounds[0].data["objects"]] == [
        [item[field] for field in stable_fields] for item in other_seed.rounds[0].data["objects"]]
    assert [item["phase"] for item in first.rounds[0].data["objects"]] == [
        item["phase"] for item in other_seed.rounds[0].data["objects"]]
    changed = [dict(item) for item in layout]
    changed[0]["jump_height_px"] += 1
    changed_spec = generate_spec("hidden_motion_hunt", 901, background_bytes=background_bytes,
                                 placement_mode="manual", manual_objects=changed)
    assert first.fingerprint() != changed_spec.fingerprint()


def test_new_layer_id_stays_unique_after_delete() -> None:
    objects = hidden_motion_hunt.default_manual_layout()
    objects.pop(2)
    next_index = max(item["object_id"] for item in objects)
    objects.append(hidden_motion_hunt.new_manual_object(next_index))
    assert len({item["object_id"] for item in objects}) == len(objects)


def test_manual_config_reaches_renderer_without_media_export(background_bytes) -> None:
    from puzzly.renderer import render_frame
    layout = hidden_motion_hunt.default_manual_layout()
    layout[0].update({"shape": "hexagon", "size_px": 15, "jump_height_px": 18})
    spec = generate_spec("hidden_motion_hunt", 707, background_bytes=background_bytes,
                         placement_mode="manual", manual_objects=layout)
    first = render_frame(spec, 0.0, (270, 480))
    moved = render_frame(spec, .25, (270, 480))
    assert first.size == moved.size == (270, 480)
    assert not np.array_equal(np.asarray(first), np.asarray(moved))


def test_unique_generation_filename_history_and_manifest_fields(tmp_path, monkeypatch, background_bytes) -> None:
    history = HistoryStore(tmp_path / "history.sqlite")
    specs = generate_unique_specs(2, "hidden_motion_hunt", base_seed=71, history=history,
                                  background_bytes=background_bytes)
    assert len({spec.fingerprint() for spec in specs}) == 2
    monkeypatch.setattr("puzzly.generator.render_video", lambda spec, path, **kwargs: path.write_bytes(b"video") or .01)
    monkeypatch.setattr("puzzly.generator.save_cover", lambda spec, path: Image.new("RGB", (1080, 1920)).save(path))
    output, paths = render_batch(specs, output_dir=tmp_path / "output", history=history)
    assert [path.name for path in paths] == ["PZ_0001_hidden_motion_hunt.mp4", "PZ_0002_hidden_motion_hunt.mp4"]
    assert all(record.difficulty == "" for record in history.records())
    rows = list(__import__("csv").DictReader((output / "metadata.csv").open(encoding="utf-8-sig", newline="")))
    for row in rows:
        assert row["difficulty"] == "" and row["background_hash"]
        assert row["placement_mode"] == "auto"
        assert row["object_count"] == "7"
        assert Counter(json.loads(row["hidden_object_tiers"])) == Counter(HIDDEN_MOTION_TIER_COUNTS)
        assert len(json.loads(row["hidden_object_positions"])) == 7
        assert len(json.loads(row["hidden_object_diameters"])) == 7
        assert json.loads(row["hidden_object_bounce_speeds"]) == [1.0] * 7
        assert json.loads(row["hidden_object_sources"]) == ["shape"] * 7
        assert len(json.loads(row["motion_parameters"])) == 7
