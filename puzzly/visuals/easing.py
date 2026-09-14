from __future__ import annotations


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def ease_out_cubic(value: float) -> float:
    x = clamp01(value)
    return 1 - (1 - x) ** 3


def ease_in_out(value: float) -> float:
    x = clamp01(value)
    return 4 * x**3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out_back(value: float) -> float:
    x = clamp01(value)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2
