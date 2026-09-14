from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components


_COMPONENT = components.declare_component(
    "puzzly_live_motion_preview",
    path=str(Path(__file__).with_name("live_motion_preview_frontend")),
)


def live_motion_preview(payload: dict[str, Any], *, key: str) -> None:
    """Display a Final-coordinate animated canvas driven by the renderer motion spec."""
    _COMPONENT(payload=payload, key=key, default=0)
