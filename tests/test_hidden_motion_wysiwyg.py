from __future__ import annotations

from io import BytesIO
import math

from PIL import Image
import pytest

from puzzly.config import HIDDEN_MOTION_DURATION
from puzzly.puzzles import hidden_motion_hunt as hunt
from puzzly.visuals import hidden_motion as visuals


@pytest.fixture
def cached_assets(tmp_path, monkeypatch) -> tuple[str, str]:
    monkeypatch.setattr(hunt, "HIDDEN_MOTION_BACKGROUNDS_DIR", tmp_path / "backgrounds")
    monkeypatch.setattr(hunt, "HIDDEN_MOTION_OBJECTS_DIR", tmp_path / "objects")
    background = BytesIO()
    Image.new("RGB", (720, 1280), "#778899").save(background, format="PNG")
    background_hash = hunt.prepare_background(background.getvalue())
    source = Image.new("RGBA", (13, 9), (0, 0, 0, 0))
    for x in range(3, 10):
        for y in range(2, 7):
            source.putpixel((x, y), (40, 210, 120, 255))
    png = BytesIO(); source.save(png, format="PNG")
    return background_hash, hunt.prepare_object_png(png.getvalue())


def test_preview_payload_and_renderer_share_motion_math(cached_assets) -> None:
    background_hash, _ = cached_assets
    obj = hunt.new_manual_object(0)
    obj.update({"x_pct": .317, "y_pct": .614, "jump_height_px": 27,
                "bounce_speed": 1.75, "phase_offset": .73, "size_px": 8})
    runtime = hunt.runtime_object(obj, 0)
    payload = visuals.editor_preview_payload(background_hash, [obj], 1)["objects"][0]
    for timestamp in (0.0, .137, 1.125, 7.9, 17.99):
        renderer_y = hunt.motion_state(runtime, timestamp)[1]
        renderer_normalized = (renderer_y - runtime["position"][1]) / runtime["y_amplitude"]
        preview_normalized = hunt.normalized_offset_from_cycles(
            timestamp, payload["cycles"], payload["phase"], HIDDEN_MOTION_DURATION)
        assert preview_normalized == pytest.approx(renderer_normalized, abs=1e-12)
    assert (payload["x"], payload["y"], payload["jump"], payload["size"]) == (
        runtime["position"][0], runtime["position"][1], runtime["y_amplitude"], runtime["diameter"])


def test_frequency_mapping_determinism_and_exact_loop(cached_assets) -> None:
    background_hash, _ = cached_assets
    assert hunt.bounce_cycle_count(1.0) == 18
    assert hunt.effective_bounce_hz(1.0) == pytest.approx(1.0)
    assert hunt.effective_bounce_hz(.25) == pytest.approx(5 / 18)
    layout = [hunt.update_manual_object([hunt.new_manual_object(0)], 1,
                                        bounce_speed=2.25)[0]]
    first = hunt.generate(44, background_hash, "manual", layout)
    second = hunt.generate(44, background_hash, "manual", layout)
    assert first == second
    obj = first.rounds[0].data["objects"][0]
    assert obj["phase"] == layout[0]["phase_offset"]
    assert hunt.motion_state(obj, 0) == pytest.approx(
        hunt.motion_state(obj, HIDDEN_MOTION_DURATION), abs=1e-9)


def test_final_pixel_scaling_never_collapses_to_zero() -> None:
    assert hunt.scale_final_pixels(1, 1080) == 1
    assert hunt.raster_dimension(1, 1080) == 1
    assert hunt.raster_dimension(1, 540) == 1
    assert hunt.raster_dimension(1, 2160) == 2
    assert hunt.scale_final_pixels(8, 540) == 4
    assert hunt.scale_final_pixels(8, 360) == pytest.approx(8 / 3)
    assert hunt.raster_dimension(8, 540) == 4


def test_png_resize_keeps_dimensions_alpha_and_anchor(cached_assets) -> None:
    background_hash, png_hash = cached_assets
    tiny = visuals._custom_asset(png_hash, hunt.raster_dimension(1, 1080))
    draft = visuals._custom_asset(png_hash, hunt.raster_dimension(8, 540))
    assert tiny.size == (1, 1) and max(tiny.getchannel("A").getdata()) > 0
    assert draft.size == (4, 4) and max(draft.getchannel("A").getdata()) > 0
    obj = hunt.new_manual_object(0)
    obj.update({"source_type": "png", "png_asset_hash": png_hash,
                "x_pct": .123456, "y_pct": .654321, "size_px": 1})
    runtime = hunt.runtime_object(obj, 0)
    payload = visuals.editor_preview_payload(background_hash, [obj], 1)["objects"][0]
    assert payload["x"] == pytest.approx(.123456 * 1080)
    assert payload["y"] == pytest.approx(.654321 * 1920)
    assert payload["x"] == runtime["position"][0] and payload["y"] == runtime["position"][1]
