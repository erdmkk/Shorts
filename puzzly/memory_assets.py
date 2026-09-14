from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .config import MEMORY_OBJECTS_DIR

CANVAS = 512
MIN_SOURCE_SIZE = 512
OUTLINE = "#244653"
COLORS = {"red": "#F36F62", "yellow": "#FFD05A", "blue": "#4D8FE8", "teal": "#19AAA0",
          "purple": "#9C8ADE", "pink": "#F59BC2", "orange": "#EF9B43", "green": "#63C77D", "white": "#FFFDF7"}


def _line(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], width: int = 24, fill: str = OUTLINE) -> None:
    draw.line(points, fill=fill, width=width, joint="curve")


def _star(cx: int, cy: int, outer: int, inner: int) -> list[tuple[float, float]]:
    import math
    return [(cx + (outer if i % 2 == 0 else inner) * math.cos(-math.pi / 2 + i * math.pi / 5),
             cy + (outer if i % 2 == 0 else inner) * math.sin(-math.pi / 2 + i * math.pi / 5)) for i in range(10)]


def _draw_icon(object_id: str) -> Image.Image:
    im = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    c = COLORS
    if object_id == "apple":
        d.ellipse((105, 145, 285, 380), fill=c["red"], outline=OUTLINE, width=18); d.ellipse((225, 145, 405, 380), fill=c["red"], outline=OUTLINE, width=18); _line(d, [(256, 160), (270, 95)], 20); d.ellipse((268, 85, 355, 145), fill=c["green"], outline=OUTLINE, width=14)
    elif object_id == "banana":
        d.arc((85, 70, 425, 405), 20, 145, fill=OUTLINE, width=95); d.arc((85, 70, 425, 405), 20, 145, fill=c["yellow"], width=60)
    elif object_id == "fish":
        d.ellipse((95, 145, 365, 365), fill=c["blue"], outline=OUTLINE, width=18); d.polygon([(345, 255), (445, 155), (445, 355)], fill=c["teal"], outline=OUTLINE); d.ellipse((150, 205, 178, 233), fill=OUTLINE)
    elif object_id == "star":
        d.polygon(_star(256, 255, 185, 78), fill=c["yellow"], outline=OUTLINE, width=18)
    elif object_id == "moon":
        d.ellipse((105, 75, 405, 420), fill=c["yellow"], outline=OUTLINE, width=18); d.ellipse((220, 45, 440, 330), fill=(0, 0, 0, 0)); d.arc((105, 75, 405, 420), 75, 285, fill=OUTLINE, width=18)
    elif object_id == "car":
        d.rounded_rectangle((75, 205, 435, 365), radius=48, fill=c["red"], outline=OUTLINE, width=18); d.polygon([(155, 205), (210, 125), (335, 125), (385, 205)], fill=c["blue"], outline=OUTLINE); d.ellipse((125, 325, 205, 405), fill=OUTLINE); d.ellipse((315, 325, 395, 405), fill=OUTLINE)
    elif object_id == "airplane":
        d.polygon([(65, 275), (225, 225), (260, 75), (300, 75), (315, 220), (450, 255), (450, 300), (310, 290), (270, 430), (230, 430), (225, 292), (65, 320)], fill=c["blue"], outline=OUTLINE)
    elif object_id == "boat":
        d.polygon([(75, 285), (440, 285), (375, 400), (145, 400)], fill=c["teal"], outline=OUTLINE); _line(d, [(255, 285), (255, 90)], 18); d.polygon([(270, 105), (270, 270), (405, 270)], fill=c["yellow"], outline=OUTLINE)
    elif object_id == "key":
        d.ellipse((75, 115, 255, 295), fill=c["yellow"], outline=OUTLINE, width=22); d.ellipse((128, 168, 202, 242), fill=(0, 0, 0, 0), outline=OUTLINE, width=18); _line(d, [(225, 270), (410, 420)], 48, c["yellow"]); _line(d, [(225, 270), (410, 420)], 18); _line(d, [(350, 365), (400, 315)], 28)
    elif object_id == "clock":
        d.ellipse((80, 80, 430, 430), fill=c["white"], outline=OUTLINE, width=22); _line(d, [(255, 255), (255, 145)], 22); _line(d, [(255, 255), (345, 305)], 22); d.ellipse((238, 238, 272, 272), fill=c["red"])
    elif object_id == "guitar":
        d.ellipse((100, 230, 315, 445), fill=c["orange"], outline=OUTLINE, width=20); d.ellipse((185, 115, 350, 310), fill=c["orange"], outline=OUTLINE, width=20); d.ellipse((208, 238, 262, 292), fill=OUTLINE); d.polygon([(295, 165), (355, 80), (395, 105), (335, 200)], fill=c["orange"], outline=OUTLINE)
    elif object_id == "flower":
        for x, y in ((256, 115), (375, 205), (330, 350), (182, 350), (137, 205)): d.ellipse((x-75, y-75, x+75, y+75), fill=c["pink"], outline=OUTLINE, width=14)
        d.ellipse((178, 178, 334, 334), fill=c["yellow"], outline=OUTLINE, width=18)
    elif object_id == "pencil":
        d.polygon([(90, 370), (340, 120), (410, 190), (160, 440)], fill=c["yellow"], outline=OUTLINE); d.polygon([(90, 370), (160, 440), (65, 465)], fill=c["white"], outline=OUTLINE); d.polygon([(65, 465), (95, 432), (105, 452)], fill=OUTLINE)
    elif object_id == "hat":
        d.ellipse((55, 315, 455, 410), fill=c["purple"], outline=OUTLINE, width=18); d.rounded_rectangle((135, 105, 375, 355), radius=65, fill=c["purple"], outline=OUTLINE, width=18); d.rectangle((135, 275, 375, 330), fill=c["yellow"])
    elif object_id == "ball":
        d.ellipse((80, 80, 432, 432), fill=c["blue"], outline=OUTLINE, width=20); d.arc((80, 175, 432, 510), 195, 345, fill=c["yellow"], width=38); d.arc((150, 80, 470, 432), 105, 255, fill=c["white"], width=28)
    elif object_id == "kite":
        d.polygon([(255, 55), (425, 235), (255, 390), (85, 235)], fill=c["red"], outline=OUTLINE); _line(d, [(255, 390), (350, 475)], 10); d.polygon([(315, 435), (350, 465), (380, 425)], fill=c["yellow"], outline=OUTLINE)
    elif object_id == "cup":
        d.rounded_rectangle((95, 105, 350, 410), radius=42, fill=c["teal"], outline=OUTLINE, width=20); d.ellipse((315, 175, 450, 340), fill=(0,0,0,0), outline=OUTLINE, width=25); d.rectangle((335, 200, 370, 315), fill=c["teal"])
    elif object_id == "house":
        d.rectangle((115, 220, 400, 435), fill=c["yellow"], outline=OUTLINE, width=20); d.polygon([(70, 240), (255, 65), (445, 240)], fill=c["red"], outline=OUTLINE); d.rectangle((225, 315, 300, 435), fill=c["blue"], outline=OUTLINE, width=14)
    elif object_id == "duck":
        d.ellipse((105, 205, 380, 410), fill=c["yellow"], outline=OUTLINE, width=18); d.ellipse((265, 90, 430, 265), fill=c["yellow"], outline=OUTLINE, width=18); d.polygon([(405, 165), (485, 205), (405, 230)], fill=c["orange"], outline=OUTLINE); d.ellipse((350, 145, 370, 165), fill=OUTLINE)
    elif object_id == "butterfly":
        d.ellipse((45, 90, 245, 300), fill=c["purple"], outline=OUTLINE, width=16); d.ellipse((267, 90, 467, 300), fill=c["pink"], outline=OUTLINE, width=16); d.ellipse((100, 255, 245, 445), fill=c["blue"], outline=OUTLINE, width=16); d.ellipse((267, 255, 412, 445), fill=c["yellow"], outline=OUTLINE, width=16); d.rounded_rectangle((230, 100, 282, 430), radius=25, fill=OUTLINE)
    elif object_id == "umbrella":
        d.pieslice((55, 65, 457, 400), 180, 360, fill=c["blue"], outline=OUTLINE, width=20); _line(d, [(256, 230), (256, 415), (310, 455), (355, 415)], 20)
    elif object_id == "rocket":
        d.polygon([(255, 45), (350, 170), (330, 365), (180, 365), (160, 170)], fill=c["white"], outline=OUTLINE); d.ellipse((210, 145, 300, 235), fill=c["blue"], outline=OUTLINE, width=14); d.polygon([(180, 300), (90, 405), (185, 380)], fill=c["red"], outline=OUTLINE); d.polygon([(330, 300), (420, 405), (325, 380)], fill=c["red"], outline=OUTLINE); d.polygon([(220, 365), (255, 475), (290, 365)], fill=c["yellow"], outline=OUTLINE)
    elif object_id == "crown":
        d.polygon([(65, 155), (155, 245), (220, 105), (290, 245), (390, 110), (445, 390), (75, 390)], fill=c["yellow"], outline=OUTLINE); d.rectangle((75, 320, 445, 420), fill=c["yellow"], outline=OUTLINE, width=18)
    elif object_id == "ice_cream":
        d.polygon([(170, 245), (350, 245), (270, 455)], fill=c["orange"], outline=OUTLINE); d.ellipse((125, 75, 385, 305), fill=c["pink"], outline=OUTLINE, width=18); d.ellipse((210, 45, 320, 155), fill=c["white"], outline=OUTLINE, width=14)
    else:
        raise KeyError(object_id)
    return im


def _normalize(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A"); box = alpha.getbbox()
    if box is None:
        raise ValueError("object artwork is empty")
    cropped = image.crop(box)
    scale = min(390 / cropped.width, 390 / cropped.height)
    resized = cropped.resize((round(cropped.width * scale), round(cropped.height * scale)), Image.Resampling.LANCZOS)
    result = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    result.alpha_composite(resized, ((CANVAS - resized.width) // 2, (CANVAS - resized.height) // 2))
    return result


def ensure_memory_assets() -> None:
    MEMORY_OBJECTS_DIR.mkdir(parents=True, exist_ok=True)
    for item in load_metadata(validate_files=False):
        path = MEMORY_OBJECTS_DIR / item["asset_path"]
        if not path.exists():
            _normalize(_draw_icon(item["id"])).save(path, "PNG")


@lru_cache(maxsize=2)
def load_metadata(validate_files: bool = True) -> tuple[dict[str, Any], ...]:
    path = MEMORY_OBJECTS_DIR / "objects.json"
    if not path.exists():
        raise ValueError(f"Memory asset metadata is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"id", "name", "category", "similarity_group", "dominant_color", "asset_path"}
    if len(data) != 24 or len({item.get("id") for item in data}) != len(data):
        raise ValueError("Memory asset metadata must contain 24 unique IDs")
    for item in data:
        if not required <= item.keys():
            raise ValueError(f"Memory asset metadata is incomplete: {item.get('id', '?')}")
        if validate_files:
            asset = MEMORY_OBJECTS_DIR / item["asset_path"]
            try:
                with Image.open(asset) as image:
                    if image.format != "PNG" or image.mode != "RGBA" or min(image.size) < MIN_SOURCE_SIZE or image.getchannel("A").getextrema() != (0, 255):
                        raise ValueError(f"Memory asset is invalid: {asset}")
            except OSError as exc:
                raise ValueError(f"Memory asset cannot be opened: {asset}") from exc
    return tuple(data)


@lru_cache(maxsize=48)
def object_image(object_id: str) -> Image.Image:
    ensure_memory_assets()
    item = next((entry for entry in load_metadata() if entry["id"] == object_id), None)
    if item is None:
        raise KeyError(object_id)
    with Image.open(MEMORY_OBJECTS_DIR / item["asset_path"]) as image:
        return image.convert("RGBA")
