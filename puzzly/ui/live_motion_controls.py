from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_COMPONENT = components.declare_component(
    "puzzly_live_motion_controls",
    path=str(Path(__file__).with_name("live_motion_controls_frontend")),
)


def live_motion_controls(*, x_pct: float, y_pct: float, size_px: int, jump_height_px: int,
                         bounce_speed: float, key: str) -> dict[str, float | int]:
    """Return continuously streamed range values from the local browser component."""
    defaults: dict[str, float | int] = {
        "x_pct": round(x_pct, 6), "y_pct": round(y_pct, 6), "size_px": int(size_px),
        "jump_height_px": int(jump_height_px), "bounce_speed": round(bounce_speed, 2),
    }
    value: Any = _COMPONENT(values=defaults, key=key, default=defaults)
    if not isinstance(value, dict):
        return defaults
    return {
        "x_pct": round(float(value.get("x_pct", x_pct)), 6),
        "y_pct": round(float(value.get("y_pct", y_pct)), 6),
        "size_px": int(value.get("size_px", size_px)),
        "jump_height_px": int(value.get("jump_height_px", jump_height_px)),
        "bounce_speed": round(float(value.get("bounce_speed", bounce_speed)), 2),
    }
