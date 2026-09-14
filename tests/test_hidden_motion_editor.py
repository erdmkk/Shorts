from __future__ import annotations

import json
from io import BytesIO

from PIL import Image

from puzzly.puzzles import hidden_motion_hunt as hunt


def test_selection_and_editing_are_isolated_by_stable_id() -> None:
    objects = hunt.default_manual_layout()[:3]
    first_before = dict(hunt.manual_object_by_id(objects, 1))
    second_before = dict(hunt.manual_object_by_id(objects, 2))

    assert hunt.resolve_selected_object_id(objects, 2) == 2
    assert hunt.manual_object_by_id(objects, 2) == second_before
    edited = hunt.update_manual_object(objects, 2, shape="star", color="#123ABC", x_pct=.6,
                                       y_pct=.5, size_px=24, jump_height_px=12)

    assert hunt.manual_object_by_id(edited, 1) == first_before
    assert hunt.manual_object_by_id(edited, 2)["shape"] == "star"
    assert hunt.manual_object_by_id(edited, 2)["size_px"] == 24
    assert hunt.manual_object_by_id(objects, 2) == second_before
    assert hunt.manual_object_by_id(edited, 1) == first_before


def test_add_delete_clear_selection_and_ids() -> None:
    objects = hunt.default_manual_layout()[:3]
    stable_ids = [item["object_id"] for item in objects]
    objects, selected_id = hunt.add_manual_object(objects)
    assert selected_id == 4
    assert [item["object_id"] for item in objects[:3]] == stable_ids
    assert hunt.manual_object_by_id(objects, selected_id)["object_id"] == selected_id

    objects, selected_id = hunt.delete_manual_object(objects, selected_id)
    assert selected_id == 3
    assert [item["object_id"] for item in objects] == stable_ids

    objects.clear()
    selected_id = hunt.resolve_selected_object_id(objects, selected_id)
    assert objects == [] and selected_id is None


def test_serialization_preserves_every_editor_property(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(hunt, "HIDDEN_MOTION_LAYOUTS_DIR", tmp_path)
    monkeypatch.setattr(hunt, "HIDDEN_MOTION_OBJECTS_DIR", tmp_path / "objects")
    background_hash = "a" * 64
    objects = hunt.default_manual_layout()[:2]
    stream = BytesIO()
    Image.new("RGBA", (24, 16), (255, 80, 30, 0)).save(stream, format="PNG")
    png_hash = hunt.prepare_object_png(stream.getvalue())
    objects = hunt.update_manual_object(
        objects, 2, source_type="png", png_asset_hash=png_hash, shape="pentagon",
        color="#ABCDEF", x_pct=.61, y_pct=.42, size_px=1, jump_height_px=17,
        bounce_speed=1.75)
    path = hunt.save_manual_layout(background_hash, objects)
    payload = json.loads(path.read_text(encoding="utf-8"))
    restored = hunt.load_manual_layout(background_hash)

    assert payload["objects"] == restored
    assert restored == hunt.normalize_manual_layout(objects)
    assert {item["object_id"] for item in restored} == {1, 2}
    custom = hunt.manual_object_by_id(restored, 2)
    assert custom["source_type"] == "png" and custom["png_asset_hash"] == png_hash
    assert custom["size_px"] == 1 and custom["bounce_speed"] == 1.75


def test_shape_png_switch_and_bounce_speed_motion(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(hunt, "HIDDEN_MOTION_OBJECTS_DIR", tmp_path)
    stream = BytesIO()
    image = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    image.putpixel((4, 4), (20, 180, 90, 255))
    image.save(stream, format="PNG")
    png_hash = hunt.prepare_object_png(stream.getvalue())
    objects = hunt.default_manual_layout()[:1]
    png_objects = hunt.update_manual_object(objects, 1, source_type="png", png_asset_hash=png_hash,
                                             bounce_speed=.25, size_px=1)
    assert hunt.manual_object_by_id(objects, 1)["source_type"] == "shape"
    assert hunt.manual_object_by_id(png_objects, 1)["source_type"] == "png"
    assert hunt.manual_layout_errors(png_objects) == []
    shape_objects = hunt.update_manual_object(png_objects, 1, source_type="shape")
    assert hunt.manual_object_by_id(shape_objects, 1)["source_type"] == "shape"
    assert hunt.manual_object_by_id(shape_objects, 1)["png_asset_hash"] == png_hash


def test_png_object_reaches_in_memory_renderer(tmp_path, monkeypatch) -> None:
    from puzzly.renderer import render_frame

    monkeypatch.setattr(hunt, "HIDDEN_MOTION_BACKGROUNDS_DIR", tmp_path / "backgrounds")
    monkeypatch.setattr(hunt, "HIDDEN_MOTION_OBJECTS_DIR", tmp_path / "objects")
    background = BytesIO()
    Image.new("RGB", (540, 960), "#8899AA").save(background, format="PNG")
    background_hash = hunt.prepare_background(background.getvalue())
    custom = BytesIO()
    icon = Image.new("RGBA", (20, 12), (0, 0, 0, 0))
    for x in range(4, 16):
        for y in range(2, 10):
            icon.putpixel((x, y), (255, 180, 25, 255))
    icon.save(custom, format="PNG")
    png_hash = hunt.prepare_object_png(custom.getvalue())
    layout = [hunt.new_manual_object(0)]
    layout = hunt.update_manual_object(layout, 1, source_type="png", png_asset_hash=png_hash,
                                       x_pct=.5, y_pct=.5, size_px=40, jump_height_px=20,
                                       bounce_speed=2.0)
    spec = hunt.generate(55, background_hash, "manual", layout)
    first = render_frame(spec, 0.0, (270, 480))
    moved = render_frame(spec, .125, (270, 480))
    assert first.size == moved.size == (270, 480)
    assert first.tobytes() != moved.tobytes()


def test_editor_source_uses_two_columns_and_explicit_selected_id() -> None:
    source = (__import__("pathlib").Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    assert "st.columns([0.38, 0.62]" in source
    assert 'st.session_state["hidden_object_selected_id"]' in source
    assert "live_motion_controls(" in source
    assert "live_motion_preview(" in source
    assert "editor_preview_payload(" in source
    assert "Very small objects may disappear after video compression." in source
