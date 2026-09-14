from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from puzzly.generator import generate_spec, render_batch
from puzzly.history import HistoryStore
from puzzly.verify_video import inspect_video


def main() -> None:
    output = Path("output/samples/v9_1")
    specs = [generate_spec("flash_count", 10001, "easy"), generate_spec("flash_count", 10003, "hard")]
    _, paths = render_batch(specs, quality="draft", output_dir=output, history=HistoryStore())
    reports = []
    for spec, path in zip(specs, paths):
        report = inspect_video(path, (540, 960), spec.total_duration)
        cover = path.with_suffix(".jpg")
        with Image.open(cover) as image:
            assert image.format == "JPEG" and image.size == (1080, 1920)
            image.verify()
        report.update({"difficulty": spec.difficulty,
                       "visible_seconds": spec.rounds[0].data["visible_seconds"],
                       "counts": [item.answer for item in spec.rounds], "cover": str(cover)})
        reports.append(report)
    verification = output / "v9_1_verification.json"
    verification.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2), flush=True)


if __name__ == "__main__":
    main()
