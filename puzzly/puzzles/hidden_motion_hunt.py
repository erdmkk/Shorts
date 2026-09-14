from __future__ import annotations

from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import random
import re

from PIL import Image, ImageOps, UnidentifiedImageError

from ..config import (HIDDEN_MOTION_BACKGROUNDS_DIR, HIDDEN_MOTION_DIAMETER_RANGES,
                      HIDDEN_MOTION_DURATION, HIDDEN_MOTION_JUMP_RANGE, HIDDEN_MOTION_LAYOUTS_DIR,
                      HIDDEN_MOTION_MANUAL_SIZE_RANGE, HIDDEN_MOTION_MAX_OBJECTS,
                      HIDDEN_MOTION_MIN_GAP, HIDDEN_MOTION_OBJECT_COUNT,
                      HIDDEN_MOTION_OBJECTS_DIR, HIDDEN_MOTION_SAFE_BOUNDS,
                      HIDDEN_MOTION_SPEED_RANGE, HIDDEN_MOTION_TIER_COUNTS)
from ..models import RoundSpec, VideoSpec


SHAPES = ("circle", "square", "triangle", "star", "diamond", "hexagon", "pentagon")
COLORS = ("#38B9C7", "#F27C70", "#F3BD43", "#6CC58A", "#7770D8", "#DD72AE", "#4D91E2")
PLACEMENT_MODES = ("manual", "auto")
OBJECT_SOURCES = ("shape", "png")
PLACEMENT_ZONES = (
    (130, 390, 150, 570), (410, 680, 180, 620), (700, 950, 140, 590),
    (120, 440, 650, 1190), (600, 960, 650, 1180),
    (170, 530, 1230, 1780), (570, 940, 1210, 1780),
)
COLOR_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}")
FINAL_FRAME_WIDTH = 1080
FINAL_FRAME_HEIGHT = 1920
BASE_BOUNCE_HZ = 1.0


def background_path(background_hash: str) -> Path:
    return HIDDEN_MOTION_BACKGROUNDS_DIR / f"{background_hash}.png"


def layout_path(background_hash: str) -> Path:
    return HIDDEN_MOTION_LAYOUTS_DIR / f"{background_hash}.json"


def object_asset_path(asset_hash: str) -> Path:
    return HIDDEN_MOTION_OBJECTS_DIR / f"{asset_hash}.png"


def prepare_background(source: bytes) -> str:
    if not source:
        raise ValueError("Background image upload is required")
    digest = sha256(source).hexdigest()
    try:
        with Image.open(BytesIO(source)) as opened:
            opened.load()
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("Background image could not be decoded") from exc
    if image.width < 1 or image.height < 1:
        raise ValueError("Background image has invalid dimensions")
    HIDDEN_MOTION_BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
    path = background_path(digest)
    if not path.exists():
        temporary = path.with_name(f".{digest}.tmp.png")
        image.save(temporary, format="PNG", optimize=True)
        temporary.replace(path)
    return digest


def prepare_object_png(source: bytes) -> str:
    if not source:
        raise ValueError("Object PNG upload is required")
    digest = sha256(source).hexdigest()
    try:
        with Image.open(BytesIO(source)) as opened:
            opened.load()
            if opened.format != "PNG":
                raise ValueError("Custom object must be a PNG image")
            has_alpha = opened.mode in ("RGBA", "LA") or "transparency" in opened.info
            if not has_alpha:
                raise ValueError("Custom object PNG must contain transparency")
            image = ImageOps.exif_transpose(opened).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("Object PNG could not be decoded") from exc
    if image.width < 1 or image.height < 1:
        raise ValueError("Object PNG has invalid dimensions")
    HIDDEN_MOTION_OBJECTS_DIR.mkdir(parents=True, exist_ok=True)
    path = object_asset_path(digest)
    if not path.exists():
        temporary = path.with_name(f".{digest}.tmp.png")
        image.save(temporary, format="PNG", optimize=True)
        temporary.replace(path)
    return digest


def new_manual_object(index: int) -> dict:
    if index < len(PLACEMENT_ZONES):
        zone = PLACEMENT_ZONES[index]
        x, y = (zone[0] + zone[1]) / 2, (zone[2] + zone[3]) / 2
    else:
        x = 160 + (index * 271) % 760
        y = 180 + (index * 389) % 1540
    return {
        "object_id": index + 1,
        "source_type": "shape",
        "png_asset_hash": "",
        "shape": SHAPES[index % len(SHAPES)],
        "color": COLORS[index % len(COLORS)],
        "x_pct": round(x / 1080, 6),
        "y_pct": round(y / 1920, 6),
        "size_px": (56, 52, 42, 38, 27, 24, 21)[index % 7],
        "jump_height_px": 8,
        "bounce_speed": 1.0,
        "phase_offset": round((index * 2.399963) % math.tau, 6),
    }


def default_manual_layout() -> list[dict]:
    return [new_manual_object(index) for index in range(HIDDEN_MOTION_OBJECT_COUNT)]


def resolve_selected_object_id(objects: list[dict], selected_id: int | None) -> int | None:
    """Return a valid stable object ID, falling back to the first layer."""
    object_ids = [int(item["object_id"]) for item in objects]
    return selected_id if selected_id in object_ids else (object_ids[0] if object_ids else None)


def manual_object_by_id(objects: list[dict], object_id: int) -> dict:
    for item in objects:
        if int(item["object_id"]) == object_id:
            return item
    raise ValueError(f"Manual object {object_id} does not exist")


def update_manual_object(objects: list[dict], object_id: int, **changes: object) -> list[dict]:
    """Update exactly one layer without mutating any of the input dictionaries."""
    if not any(int(item["object_id"]) == object_id for item in objects):
        raise ValueError(f"Manual object {object_id} does not exist")
    return [{**item, **changes} if int(item["object_id"]) == object_id else dict(item) for item in objects]


def add_manual_object(objects: list[dict]) -> tuple[list[dict], int]:
    if len(objects) >= HIDDEN_MOTION_MAX_OBJECTS:
        raise ValueError(f"Manual layout supports at most {HIDDEN_MOTION_MAX_OBJECTS} objects")
    next_id = max((int(item["object_id"]) for item in objects), default=0) + 1
    return [*(dict(item) for item in objects), new_manual_object(next_id - 1)], next_id


def delete_manual_object(objects: list[dict], selected_id: int) -> tuple[list[dict], int | None]:
    selected_index = next((index for index, item in enumerate(objects)
                           if int(item["object_id"]) == selected_id), None)
    if selected_index is None:
        raise ValueError(f"Manual object {selected_id} does not exist")
    remaining = [dict(item) for index, item in enumerate(objects) if index != selected_index]
    next_selection = int(remaining[max(0, selected_index - 1)]["object_id"]) if remaining else None
    return remaining, next_selection


def _normalize_manual_object(item: dict, index: int) -> dict:
    try:
        return {
            "object_id": int(item.get("object_id", index + 1)),
            "source_type": str(item.get("source_type", "shape")),
            "png_asset_hash": str(item.get("png_asset_hash", "")),
            "shape": str(item.get("shape", "circle")),
            "color": str(item.get("color", COLORS[index % len(COLORS)])).upper(),
            "x_pct": round(float(item.get("x_pct", .5)), 6),
            "y_pct": round(float(item.get("y_pct", .5)), 6),
            "size_px": int(item.get("size_px", 24)),
            "jump_height_px": int(item.get("jump_height_px", 8)),
            "bounce_speed": round(float(item.get("bounce_speed", 1.0)), 2),
            "phase_offset": round(float(item.get("phase_offset", index * math.tau / 7)), 6),
        }
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Manual object {index + 1} has invalid values") from exc


def normalize_manual_layout(objects: list[dict]) -> list[dict]:
    if not isinstance(objects, list):
        raise ValueError("Manual layout objects must be a list")
    return [_normalize_manual_object(item, index) for index, item in enumerate(objects)]


def save_manual_layout(background_hash: str, objects: list[dict]) -> Path:
    normalized = normalize_manual_layout(objects)
    issues = manual_layout_errors(normalized)
    if issues:
        raise ValueError("; ".join(issues))
    HIDDEN_MOTION_LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)
    path = layout_path(background_hash)
    temporary = path.with_name(f".{background_hash}.tmp.json")
    temporary.write_text(json.dumps({"version": 1, "background_hash": background_hash, "objects": normalized},
                                    indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def load_manual_layout(background_hash: str) -> list[dict] | None:
    path = layout_path(background_hash)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Saved manual layout could not be read") from exc
    if payload.get("background_hash") != background_hash:
        raise ValueError("Saved manual layout does not match this background")
    normalized = normalize_manual_layout(payload.get("objects"))
    issues = manual_layout_errors(normalized)
    if issues:
        raise ValueError("Saved manual layout is invalid: " + "; ".join(issues))
    return normalized


def bounce_cycle_count(speed: float, duration: float = HIDDEN_MOTION_DURATION) -> int:
    """Convert the requested speed multiplier to the nearest loop-safe whole cycle count."""
    return max(1, math.floor(float(speed) * BASE_BOUNCE_HZ * duration + .5))


def effective_bounce_hz(speed: float, duration: float = HIDDEN_MOTION_DURATION) -> float:
    return bounce_cycle_count(speed, duration) / duration


def normalized_offset_from_cycles(t: float, cycles: int, phase: float,
                                  duration: float = HIDDEN_MOTION_DURATION) -> float:
    return math.sin(math.tau * cycles * t / duration + phase)


def normalized_bounce_offset(t: float, speed: float, phase: float,
                             duration: float = HIDDEN_MOTION_DURATION) -> float:
    return normalized_offset_from_cycles(t, bounce_cycle_count(speed, duration), phase, duration)


def final_anchor(item: dict) -> tuple[float, float]:
    if "x_pct" in item and "y_pct" in item:
        return float(item["x_pct"]) * FINAL_FRAME_WIDTH, float(item["y_pct"]) * FINAL_FRAME_HEIGHT
    return float(item["position"][0]), float(item["position"][1])


def scale_final_pixels(value: float, frame_width: int) -> float:
    """Scale a Final-resolution pixel measurement without premature rounding."""
    return float(value) * frame_width / FINAL_FRAME_WIDTH


def raster_dimension(value: float, frame_width: int) -> int:
    """Resolve a positive Final-pixel size at the final raster boundary."""
    return max(1, round(scale_final_pixels(value, frame_width)))


def runtime_object(item: dict, index: int, phase_shift: float = 0.0, tier: str = "manual") -> dict:
    x_pct, y_pct = float(item["x_pct"]), float(item["y_pct"])
    speed = float(item.get("bounce_speed", 1.0))
    cycles = bounce_cycle_count(speed)
    return {
        "index": index, "object_id": int(item.get("object_id", index + 1)), "tier": tier,
        "source_type": item.get("source_type", "shape"),
        "png_asset_hash": item.get("png_asset_hash", ""),
        "shape": item["shape"], "color": item["color"],
        "x_pct": x_pct, "y_pct": y_pct,
        "position": [x_pct * FINAL_FRAME_WIDTH, y_pct * FINAL_FRAME_HEIGHT],
        "diameter": int(item["size_px"]), "size_px": int(item["size_px"]),
        "jump_height_px": int(item["jump_height_px"]),
        "bounce_speed": float(item.get("bounce_speed", 1.0)),
        "x_amplitude": 0, "y_amplitude": int(item["jump_height_px"]), "scale_amplitude": 0.0,
        "requested_bounce_hz": speed * BASE_BOUNCE_HZ,
        "bounce_hz": cycles / HIDDEN_MOTION_DURATION,
        "cycles": cycles,
        "phase": round((float(item["phase_offset"]) + phase_shift) % math.tau, 6),
        "phase_offset": float(item["phase_offset"]),
    }


def _motion_envelope(item: dict) -> float:
    return float(item["diameter"]) / 2 + abs(float(item["y_amplitude"]))


def _separated(candidate: dict, existing: list[dict]) -> bool:
    return all(math.dist(candidate["position"], other["position"])
               >= _motion_envelope(candidate) + _motion_envelope(other) + HIDDEN_MOTION_MIN_GAP
               for other in existing)


def _auto_object(index: int, tier: str, zone: tuple[int, int, int, int], rng: random.Random,
                 existing: list[dict]) -> dict:
    diameter = rng.randint(*HIDDEN_MOTION_DIAMETER_RANGES[tier])
    jump = {"easy": rng.randint(7, 11), "medium": rng.randint(6, 9), "hard": rng.randint(4, 7)}[tier]
    phase = round(rng.uniform(0, math.tau), 6)
    base = {
        "index": index, "object_id": index + 1, "tier": tier, "source_type": "shape",
        "png_asset_hash": "", "shape": "circle", "color": COLORS[index],
        "diameter": diameter, "size_px": diameter, "jump_height_px": jump,
        "bounce_speed": 1.0,
        "x_amplitude": 0, "y_amplitude": jump, "scale_amplitude": 0.0,
        "requested_bounce_hz": BASE_BOUNCE_HZ, "bounce_hz": BASE_BOUNCE_HZ,
        "cycles": bounce_cycle_count(1.0), "phase": phase, "phase_offset": phase,
    }
    envelope = _motion_envelope({**base, "position": [0, 0]})
    safe_left, safe_top, safe_right, safe_bottom = HIDDEN_MOTION_SAFE_BOUNDS
    zone_left, zone_right, zone_top, zone_bottom = zone
    left, right = math.ceil(max(zone_left, safe_left + envelope)), math.floor(min(zone_right, safe_right - envelope))
    top, bottom = math.ceil(max(zone_top, safe_top + envelope)), math.floor(min(zone_bottom, safe_bottom - envelope))
    for _ in range(200):
        position = [rng.randint(left, right), rng.randint(top, bottom)]
        candidate = {**base, "position": position,
                     "x_pct": round(position[0] / 1080, 6), "y_pct": round(position[1] / 1920, 6)}
        if _separated(candidate, existing):
            return candidate
    raise RuntimeError("Could not place hidden motion object with safe spacing")


def manual_layout_errors(objects: list[dict]) -> list[str]:
    result: list[str] = []
    if not 1 <= len(objects) <= HIDDEN_MOTION_MAX_OBJECTS:
        return [f"Manual layout requires 1 to {HIDDEN_MOTION_MAX_OBJECTS} objects"]
    object_ids = [item.get("object_id") for item in objects]
    if any(not isinstance(object_id, int) or object_id < 1 for object_id in object_ids):
        result.append("Manual object IDs must be positive integers")
    if len(set(object_ids)) != len(object_ids):
        result.append("Manual object IDs must be unique")
    runtime: list[dict] = []
    safe_left, safe_top, safe_right, safe_bottom = HIDDEN_MOTION_SAFE_BOUNDS
    for index, item in enumerate(objects):
        label = item.get("object_id", index + 1)
        source_type = item.get("source_type", "shape")
        if source_type not in OBJECT_SOURCES:
            result.append(f"Object {label} source is invalid")
        asset_hash = str(item.get("png_asset_hash", ""))
        if source_type == "png" and (not re.fullmatch(r"[0-9a-f]{64}", asset_hash)
                                     or not object_asset_path(asset_hash).exists()):
            result.append(f"Object {label} PNG asset is missing")
        if item.get("shape") not in SHAPES:
            result.append(f"Object {label} shape is invalid")
        if not COLOR_PATTERN.fullmatch(str(item.get("color", ""))):
            result.append(f"Object {label} color is invalid")
        size_px, jump = item.get("size_px"), item.get("jump_height_px")
        speed = item.get("bounce_speed", 1.0)
        if (not isinstance(speed, (int, float)) or
                not HIDDEN_MOTION_SPEED_RANGE[0] <= float(speed) <= HIDDEN_MOTION_SPEED_RANGE[1] or
                abs(float(speed) * 4 - round(float(speed) * 4)) > 1e-9):
            result.append(f"Object {label} bounce speed is invalid")
        if not isinstance(size_px, int) or not HIDDEN_MOTION_MANUAL_SIZE_RANGE[0] <= size_px <= HIDDEN_MOTION_MANUAL_SIZE_RANGE[1]:
            result.append(f"Object {label} size is invalid")
            continue
        if not isinstance(jump, int) or not HIDDEN_MOTION_JUMP_RANGE[0] <= jump <= HIDDEN_MOTION_JUMP_RANGE[1]:
            result.append(f"Object {label} jump height is invalid")
            continue
        x_pct, y_pct = item.get("x_pct"), item.get("y_pct")
        if not isinstance(x_pct, (int, float)) or not isinstance(y_pct, (int, float)):
            result.append(f"Object {label} position is invalid")
            continue
        current = runtime_object(item, index)
        x, y = current["position"]
        envelope = _motion_envelope(current)
        if not (safe_left + envelope <= x <= safe_right - envelope and
                safe_top + envelope <= y <= safe_bottom - envelope):
            result.append(f"Object {label} leaves safe bounds while bouncing")
        if not _separated(current, runtime):
            result.append(f"Object {label} overlaps another object")
        runtime.append(current)
    return result


def generate(seed: int, background_hash: str, placement_mode: str = "auto",
             manual_objects: list[dict] | None = None) -> VideoSpec:
    if not re.fullmatch(r"[0-9a-f]{64}", background_hash):
        raise ValueError("Background hash is invalid")
    if placement_mode not in PLACEMENT_MODES:
        raise ValueError("Placement mode must be manual or auto")
    rng = random.Random(f"hidden_motion_hunt_v3:{seed}:{background_hash}:{placement_mode}")
    if placement_mode == "manual":
        layout = normalize_manual_layout(manual_objects if manual_objects is not None else [])
        issues = manual_layout_errors(layout)
        if issues:
            raise ValueError("; ".join(issues))
        objects = [runtime_object(item, index) for index, item in enumerate(layout)]
    else:
        tiers = [tier for tier, count in HIDDEN_MOTION_TIER_COUNTS.items() for _ in range(count)]
        rng.shuffle(tiers)
        zones = list(PLACEMENT_ZONES)
        rng.shuffle(zones)
        objects = []
        for index, (tier, zone) in enumerate(zip(tiers, zones)):
            objects.append(_auto_object(index, tier, zone, rng, objects))
    data = {
        "seed": seed, "background_hash": background_hash, "placement_mode": placement_mode,
        "object_count": len(objects), "objects": objects, "duration": HIDDEN_MOTION_DURATION,
    }
    item = RoundSpec(0, "hidden_motion_hunt", data, None)
    stable_id = sha256(f"hidden_motion_hunt_v3:{seed}:{background_hash}:{placement_mode}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "hidden_motion_hunt", seed, None, "uploaded_background",
                     (item,), 0.0, HIDDEN_MOTION_DURATION, 0.0, operation="none")


def motion_state(item: dict, t: float) -> tuple[float, float, float]:
    speed = float(item.get("bounce_speed", float(item.get("cycles", 18)) / HIDDEN_MOTION_DURATION))
    offset = normalized_bounce_offset(t, speed, float(item["phase"]))
    x, anchor_y = final_anchor(item)
    return x, anchor_y + float(item["y_amplitude"]) * offset, 1.0


def errors(data: dict) -> list[str]:
    result: list[str] = []
    objects = data.get("objects", [])
    mode = data.get("placement_mode")
    if mode not in PLACEMENT_MODES or data.get("object_count") != len(objects):
        result.append("hidden motion placement mode or object count is invalid")
        return result
    if mode == "auto":
        if len(objects) != HIDDEN_MOTION_OBJECT_COUNT:
            result.append("auto hidden motion hunt requires exactly seven objects")
        if Counter(item.get("tier") for item in objects) != Counter(HIDDEN_MOTION_TIER_COUNTS):
            result.append("hidden motion object tier distribution is invalid")
    elif not 1 <= len(objects) <= HIDDEN_MOTION_MAX_OBJECTS:
        result.append("manual hidden motion object count is invalid")
    if data.get("duration") != HIDDEN_MOTION_DURATION:
        result.append("hidden motion duration is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(data.get("background_hash", ""))):
        result.append("hidden motion background hash is invalid")
    safe_left, safe_top, safe_right, safe_bottom = HIDDEN_MOTION_SAFE_BOUNDS
    valid_runtime: list[dict] = []
    for index, item in enumerate(objects):
        tier, diameter = item.get("tier"), item.get("diameter")
        source_type = item.get("source_type", "shape")
        asset_hash = str(item.get("png_asset_hash", ""))
        if source_type not in OBJECT_SOURCES:
            result.append("hidden motion object source is invalid")
        if source_type == "png" and (not re.fullmatch(r"[0-9a-f]{64}", asset_hash)
                                     or not object_asset_path(asset_hash).exists()):
            result.append("hidden motion PNG asset is missing")
        if item.get("shape") not in SHAPES or not COLOR_PATTERN.fullmatch(str(item.get("color", ""))):
            result.append("hidden motion shape or color is invalid")
            continue
        if not isinstance(diameter, int) or not HIDDEN_MOTION_MANUAL_SIZE_RANGE[0] <= diameter <= HIDDEN_MOTION_MANUAL_SIZE_RANGE[1]:
            result.append("hidden motion object diameter is invalid")
            continue
        if mode == "auto" and (tier not in HIDDEN_MOTION_DIAMETER_RANGES or not
                HIDDEN_MOTION_DIAMETER_RANGES[tier][0] <= diameter <= HIDDEN_MOTION_DIAMETER_RANGES[tier][1]):
            result.append("auto hidden motion tier diameter is invalid")
        if item.get("x_amplitude") != 0 or item.get("scale_amplitude") != 0.0:
            result.append("hidden motion objects may only move vertically")
        jump = item.get("y_amplitude")
        if not isinstance(jump, int) or not HIDDEN_MOTION_JUMP_RANGE[0] <= jump <= HIDDEN_MOTION_JUMP_RANGE[1]:
            result.append("hidden motion jump height is invalid")
            continue
        speed = item.get("bounce_speed")
        expected_cycles = bounce_cycle_count(float(speed)) if isinstance(speed, (int, float)) else None
        if (not isinstance(speed, (int, float)) or
                not HIDDEN_MOTION_SPEED_RANGE[0] <= float(speed) <= HIDDEN_MOTION_SPEED_RANGE[1] or
                abs(float(speed) * 4 - round(float(speed) * 4)) > 1e-9 or
                item.get("cycles") != expected_cycles or
                item.get("bounce_hz") != expected_cycles / HIDDEN_MOTION_DURATION or
                not isinstance(item.get("phase"), (int, float))):
            result.append("hidden motion cycle or phase is invalid")
        position = item.get("position")
        if (not isinstance(position, list) or len(position) != 2
                or not all(isinstance(value, (int, float)) for value in position)):
            result.append("hidden motion position is invalid")
            continue
        envelope = _motion_envelope(item)
        x, y = position
        if not (safe_left + envelope <= x <= safe_right - envelope and safe_top + envelope <= y <= safe_bottom - envelope):
            result.append("hidden motion object leaves safe bounds")
        if not _separated(item, valid_runtime):
            result.append("hidden motion objects overlap or violate spacing")
        valid_runtime.append(item)
    return result
