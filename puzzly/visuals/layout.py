from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920
TARGET_CENTER_X = 540


@dataclass(frozen=True)
class Bounds:
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2


def scale_point(point: tuple[float, float], size: tuple[int, int]) -> tuple[int, int]:
    return round(point[0] * size[0] / FRAME_WIDTH), round(point[1] * size[1] / FRAME_HEIGHT)


def scale_bounds(bounds: Bounds, size: tuple[int, int]) -> tuple[int, int, int, int]:
    left, top = scale_point((bounds.left, bounds.top), size)
    right, bottom = scale_point((bounds.right, bounds.bottom), size)
    return left, top, right, bottom


def union_bounds(bounds: Iterable[Bounds]) -> Bounds:
    values = list(bounds)
    if not values:
        raise ValueError("at least one bound is required")
    return Bounds(min(b.left for b in values), min(b.top for b in values), max(b.right for b in values), max(b.bottom for b in values))


def centered_x_positions(widths: list[float], gap: float, center_x: float = TARGET_CENTER_X) -> list[float]:
    total = sum(widths) + gap * max(0, len(widths) - 1)
    cursor = center_x - total / 2
    result: list[float] = []
    for width in widths:
        result.append(cursor + width / 2)
        cursor += width + gap
    return result


def center_offset(bounds: Bounds, target: float = TARGET_CENTER_X) -> float:
    return bounds.center_x - target


def bounds_inside(bounds: Bounds, frame: Bounds = Bounds(0, 0, FRAME_WIDTH, FRAME_HEIGHT)) -> bool:
    return frame.left <= bounds.left < bounds.right <= frame.right and frame.top <= bounds.top < bounds.bottom <= frame.bottom


def boxes_overlap(a: Bounds, b: Bounds, padding: float = 0) -> bool:
    return not (a.right + padding <= b.left or b.right + padding <= a.left or a.bottom + padding <= b.top or b.bottom + padding <= a.top)


def no_box_overlaps(bounds: Iterable[Bounds], padding: float = 0) -> bool:
    values = list(bounds)
    return all(not boxes_overlap(a, b, padding) for index, a in enumerate(values) for b in values[index + 1 :])


def no_overlaps(positions: Iterable[tuple[int, int]], minimum_distance: float = 190) -> bool:
    points = list(positions)
    return all((ax - bx) ** 2 + (ay - by) ** 2 >= minimum_distance**2 for i, (ax, ay) in enumerate(points) for bx, by in points[i + 1 :])
