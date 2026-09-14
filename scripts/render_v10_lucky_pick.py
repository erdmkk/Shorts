from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import imageio_ffmpeg
from PIL import Image

from puzzly.generator import generate_spec, render_batch
from puzzly.history import HistoryStore
from puzzly.verify_video import inspect_video

OUTPUT = Path("output/samples/v10")


def verify(path: Path, spec, quality: str) -> dict[str, object]:
    expected_size = (540, 960) if quality == "draft" else (1080, 1920)
    result = inspect_video(path, expected_size, spec.total_duration)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    decoded = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0",
                              "-f", "null", "-"], capture_output=True)
    if decoded.returncode or decoded.stderr:
        raise AssertionError(decoded.stderr.decode(errors="replace"))
    cover = path.with_suffix(".jpg")
    with Image.open(cover) as image:
        assert image.format == "JPEG" and image.size == (1080, 1920)
        image.verify()
    game = spec.rounds[0].data
    result.update({"quality": quality, "full_decode": "passed", "cover": str(cover),
                   "winner_index": game["winner_index"], "winner_color": game["winner_color"],
                   "elimination_order": game["elimination_order"], "selection_seconds": game["selection_seconds"]})
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("drafts", "final"))
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    seeds = (11001, 11002) if args.stage == "drafts" else (11010,)
    quality = "draft" if args.stage == "drafts" else "final"
    specs = [generate_spec("lucky_pick", seed) for seed in seeds]
    _, paths = render_batch(specs, quality=quality, output_dir=OUTPUT, history=HistoryStore())
    reports = [verify(path, spec, quality) for path, spec in zip(paths, specs)]
    report_path = OUTPUT / f"v10_{args.stage}_verification.json"
    report_path.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    print(json.dumps(reports, indent=2), flush=True)


if __name__ == "__main__":
    main()
