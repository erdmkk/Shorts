from __future__ import annotations

from functools import lru_cache
from base64 import b64encode
from io import BytesIO

from PIL import Image, ImageDraw, ImageOps

from ..puzzles.hidden_motion_hunt import (background_path, final_anchor, motion_state,
                                          object_asset_path, raster_dimension,
                                          runtime_object, scale_final_pixels)
from .memory import token_image


@lru_cache(maxsize=4)
def _background(background_hash: str, size: tuple[int, int]) -> Image.Image:
    path = background_path(background_hash)
    if not path.exists():
        raise ValueError("Cached background image is missing; upload it again")
    with Image.open(path) as source:
        return ImageOps.fit(source.convert("RGB"), size, method=Image.Resampling.LANCZOS, centering=(.5, .5))


def _paste_object(image: Image.Image, obj: dict, x: float, y: float, logical_size: float) -> None:
    scale = image.width / 1080
    size = raster_dimension(logical_size, image.width)
    if (obj.get("source_type") == "png" and obj.get("png_asset_hash")
            and object_asset_path(str(obj["png_asset_hash"])).exists()):
        asset = _custom_asset(str(obj["png_asset_hash"]), size)
    else:
        asset = token_image(obj.get("shape", "circle"), obj["color"], size)
    center_x, center_y = round(x * scale), round(y * scale)
    image.paste(asset, (center_x - asset.width // 2, center_y - asset.height // 2), asset)


@lru_cache(maxsize=128)
def _custom_asset(asset_hash: str, size: int) -> Image.Image:
    path = object_asset_path(asset_hash)
    if not path.exists():
        raise ValueError("Cached custom object PNG is missing; upload it again")
    with Image.open(path) as opened:
        source = opened.convert("RGBA")
    source.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(source, ((size - source.width) // 2, (size - source.height) // 2), source)
    return canvas


def draw_hidden_motion(item, t: float, size: tuple[int, int]) -> Image.Image:
    data = item.data
    image = _background(data["background_hash"], size).copy()
    for obj in data["objects"]:
        x, y, _ = motion_state(obj, t)
        _paste_object(image, obj, x, y, float(obj["diameter"]))
    return image


def draw_editor_preview(background_hash: str, objects: list[dict], selected_index: int | None = None,
                        size: tuple[int, int] = (540, 960), t: float = 0.0) -> Image.Image:
    image = _background(background_hash, size).copy()
    scale = size[0] / 1080
    draw = ImageDraw.Draw(image)
    for index, obj in enumerate(objects):
        runtime = runtime_object(obj, index)
        x, y, _ = motion_state(runtime, t)
        _paste_object(image, obj, x, y, float(obj["size_px"]))
        if index == selected_index:
            radius = max(8, scale_final_pixels(float(obj["size_px"]) / 2 + 7, size[0]))
            cx, cy = x * scale, y * scale
            draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), outline="#FFFFFF", width=max(2, round(3*scale)))
            draw.line((cx-radius-4, cy, cx+radius+4, cy), fill="#183943", width=max(1, round(2*scale)))
            draw.line((cx, cy-radius-4, cx, cy+radius+4), fill="#183943", width=max(1, round(2*scale)))
    return image


def _data_uri(image: Image.Image) -> str:
    stream = BytesIO()
    image.save(stream, format="PNG", optimize=True)
    return "data:image/png;base64," + b64encode(stream.getvalue()).decode("ascii")


@lru_cache(maxsize=4)
def _background_data_uri(background_hash: str) -> str:
    return _data_uri(_background(background_hash, (1080, 1920)))


def editor_preview_payload(background_hash: str, objects: list[dict], selected_id: int | None) -> dict:
    payload_objects = []
    for index, obj in enumerate(objects):
        runtime = runtime_object(obj, index)
        asset = (_custom_asset(str(obj["png_asset_hash"]), max(2, int(obj["size_px"]) * 2))
                 if obj.get("source_type") == "png" and obj.get("png_asset_hash")
                 else token_image(obj.get("shape", "circle"), obj["color"], max(2, int(obj["size_px"]) * 2)))
        anchor_x, anchor_y = final_anchor(runtime)
        payload_objects.append({
            "object_id": int(runtime["object_id"]), "image": _data_uri(asset),
            "x": anchor_x, "y": anchor_y, "size": int(runtime["diameter"]),
            "jump": float(runtime["y_amplitude"]), "cycles": int(runtime["cycles"]),
            "phase": float(runtime["phase"]),
        })
    return {"background": _background_data_uri(background_hash), "objects": payload_objects,
            "selected_id": selected_id, "duration": 18.0, "width": 1080, "height": 1920}
