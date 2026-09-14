from __future__ import annotations

import json
from pathlib import Path
import subprocess

import imageio_ffmpeg
from PIL import Image

from puzzly.config import (FLASH_APPEARANCE_DURATION, FLASH_HIDE_DURATION, FLASH_REVEAL_DURATION,
                           FLASH_THINKING_DURATION, RENDER_QUALITIES)
from puzzly.generator import generate_spec, render_batch
from puzzly.history import HistoryStore
from puzzly.renderer import render_quality_frame
from puzzly.verify_video import inspect_video

OUTPUT = Path("output/samples/v9")
QUALITY_FRAMES = OUTPUT / "quality_frames"


def _verify(path: Path, spec, quality: str) -> dict[str, object]:
    result = inspect_video(path, RENDER_QUALITIES[quality].output_size, spec.total_duration)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    decoded = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0",
                              "-f", "null", "-"], capture_output=True)
    if decoded.returncode or decoded.stderr:
        raise AssertionError(decoded.stderr.decode(errors="replace"))
    cover = path.with_suffix(".jpg")
    with Image.open(cover) as image:
        assert image.format == "JPEG" and image.size == (1080, 1920)
        image.verify()
    result.update({"quality": quality, "full_decode": "passed", "cover": str(cover)})
    return result


def _quality_frames(easy, hard) -> list[Path]:
    QUALITY_FRAMES.mkdir(parents=True, exist_ok=True)
    easy_hidden_at = FLASH_APPEARANCE_DURATION + float(easy.rounds[0].data["visible_seconds"]) + FLASH_HIDE_DURATION
    hard_hidden_at = FLASH_APPEARANCE_DURATION + float(hard.rounds[0].data["visible_seconds"]) + FLASH_HIDE_DURATION
    moments = (
        ("v9_flash_count_intro.png", hard, 1.15),
        ("v9_flash_count_easy_visible.png", easy, easy.intro_duration + FLASH_APPEARANCE_DURATION + .55),
        ("v9_flash_count_hard_visible.png", hard, hard.intro_duration + FLASH_APPEARANCE_DURATION + .55),
        ("v9_flash_count_hidden_thinking.png", hard, hard.intro_duration + hard_hidden_at + 1.0),
        ("v9_flash_count_answer_reveal.png", hard,
         hard.intro_duration + hard_hidden_at + FLASH_THINKING_DURATION + FLASH_REVEAL_DURATION + .25),
    )
    paths = []
    for filename, spec, moment in moments:
        path = QUALITY_FRAMES / filename
        render_quality_frame(spec, moment, "final").save(path)
        paths.append(path)
    return paths


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    history = HistoryStore()
    drafts = [generate_spec("flash_count", seed, difficulty)
              for seed, difficulty in ((9901, "easy"), (9902, "medium"), (9903, "hard"))]
    final = generate_spec("flash_count", 9913, "hard")
    _, draft_paths = render_batch(drafts, quality="draft", output_dir=OUTPUT, history=history)
    _, final_paths = render_batch([final], quality="final", output_dir=OUTPUT, history=history)
    reports = [_verify(path, spec, "draft") for path, spec in zip(draft_paths, drafts)]
    reports.extend(_verify(path, final, "final") for path in final_paths)
    frames = _quality_frames(drafts[0], final)
    report_path = OUTPUT / "v9_verification.json"
    report_path.write_text(json.dumps({"videos": reports, "quality_frames": [str(path) for path in frames]},
                                      indent=2), encoding="utf-8")
    print(json.dumps({"videos": reports, "quality_frames": [str(path) for path in frames]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
