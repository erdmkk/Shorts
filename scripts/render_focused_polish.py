from __future__ import annotations

import json
from pathlib import Path
import subprocess

import imageio_ffmpeg
from moviepy import VideoFileClip
from PIL import Image, ImageDraw

from puzzly.config import RENDER_QUALITIES, thinking_duration
from puzzly.generator import generate_spec, render_batch
from puzzly.history import HistoryStore
from puzzly.renderer import render_quality_frame
from puzzly.verify_video import inspect_video


OUTPUT = Path("output/samples/focused_polish")
FRAMES = OUTPUT / "quality_frames"
SHEETS = OUTPUT / "contact_sheets"
SETTINGS = (
    ("flash_count", 18101, "medium"),
    ("quick_math", 18102, "hard"),
    ("puzzle_fit", 18103, "medium"),
    ("find_the_exit", 18104, "easy"),
    ("find_the_exit", 18105, "medium"),
    ("find_the_exit", 18106, "hard"),
)


def _verify(path: Path, spec) -> dict[str, object]:
    result = inspect_video(path, RENDER_QUALITIES["draft"].output_size, spec.total_duration)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    decoded = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
        capture_output=True,
    )
    if decoded.returncode or decoded.stderr:
        raise AssertionError(decoded.stderr.decode(errors="replace"))
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True).stderr.decode(errors="replace")
    for required in ("yuv420p", "aac (LC)", "48000 Hz", "30 fps"):
        assert required in probe, probe
    cover = path.with_suffix(".jpg")
    with Image.open(cover) as image:
        assert image.format == "JPEG" and image.size == (1080, 1920)
        image.verify()
    result.update({"quality": "draft", "full_decode": "passed", "cover": str(cover)})
    if spec.puzzle_type == "find_the_exit":
        result["difficulty_profile"] = [item.data["route_metrics"] for item in spec.rounds]
        result["route_branch_points"] = [item.data["route_branch_points"] for item in spec.rounds]
    return result


def _contact_sheet(path: Path, spec) -> Path:
    SHEETS.mkdir(parents=True, exist_ok=True)
    moments = (0.9, spec.intro_duration + .55,
               spec.intro_duration + min(spec.round_duration - .9, spec.round_duration * .55),
               spec.intro_duration + spec.round_duration - .55)
    labels = ("INTRO", "PLAY", "THINK", "REVEAL")
    sheet = Image.new("RGB", (216 * 4, 414), "#183943")
    with VideoFileClip(str(path)) as clip:
        for index, (label, moment) in enumerate(zip(labels, moments)):
            frame = Image.fromarray(clip.get_frame(moment)).resize((216, 384), Image.Resampling.LANCZOS)
            sheet.paste(frame, (216 * index, 30))
            ImageDraw.Draw(sheet).text((216 * index + 108, 15), label, anchor="mm", fill="white")
    destination = SHEETS / f"{path.stem}.jpg"
    sheet.save(destination, quality=88)
    return destination


def _quality_frames(specs) -> list[Path]:
    FRAMES.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for spec in specs:
        if spec.puzzle_type in ("flash_count", "quick_math", "puzzle_fit"):
            path = FRAMES / f"{spec.puzzle_type}_intro.png"
            render_quality_frame(spec, .9, "final").save(path)
            paths.append(path)
        elif spec.puzzle_type == "find_the_exit":
            path = FRAMES / f"find_the_exit_{spec.difficulty}_route.png"
            reveal = .35 + thinking_duration("find_the_exit", spec.difficulty) + 1.15
            render_quality_frame(spec, spec.intro_duration + reveal, "final").save(path)
            paths.append(path)
    return paths


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    specs = [generate_spec(kind, seed, difficulty) for kind, seed, difficulty in SETTINGS]
    _, paths = render_batch(specs, quality="draft", output_dir=OUTPUT, history=HistoryStore())
    reports = []
    for path, spec in zip(paths, specs):
        report = _verify(path, spec)
        report["contact_sheet"] = str(_contact_sheet(path, spec))
        reports.append(report)
    quality_frames = _quality_frames(specs)
    payload = {"videos": reports, "quality_frames": [str(path) for path in quality_frames]}
    (OUTPUT / "verification.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)


if __name__ == "__main__":
    main()
