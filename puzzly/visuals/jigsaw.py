"""Shared rounded jigsaw geometry for boards, holes, and candidates."""
from __future__ import annotations

import math


def piece_points(bounds: tuple[float, float, float, float], edges: list[int], tab: float) -> list[tuple[float, float]]:
    x1, y1, x2, y2 = bounds
    corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    points = []
    for index, sign in enumerate(edges):
        ax, ay = corners[index]
        bx, by = corners[(index + 1) % 4]
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        profile = [(0.0, 0.0), (0.38, 0.0)]
        # Symmetric cubic curves form a narrow neck and a rounded bulb.
        curves = [
            ((0.38, 0), (0.47, 0), (0.47, 0.08), (0.44, 0.32)),
            ((0.44, 0.32), (0.35, 0.90), (0.41, 1.0), (0.5, 1.0)),
            ((0.5, 1.0), (0.59, 1.0), (0.65, 0.90), (0.56, 0.32)),
            ((0.56, 0.32), (0.53, 0.08), (0.53, 0), (0.62, 0)),
        ]
        if sign:
            for control in curves:
                for step in range(1, 17):
                    t = step / 16
                    weights = ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t, t ** 3)
                    profile.append(tuple(sum(weight * p[axis] for weight, p in zip(weights, control)) for axis in (0, 1)))
        profile.append((1.0, 0.0))
        for u, bump in profile:
            points.append((ax + dx * u + dy / length * tab * sign * bump,
                           ay + dy * u - dx / length * tab * sign * bump))
    return points
