from __future__ import annotations

import logging

from .config import LOG_DIR, ensure_directories


def configure_logging() -> None:
    ensure_directories()
    root = logging.getLogger()
    if any(isinstance(handler, logging.FileHandler) for handler in root.handlers):
        return
    handler = logging.FileHandler(LOG_DIR / "puzzly.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)

