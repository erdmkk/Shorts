from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from puzzly.config import RENDER_QUALITIES
from puzzly.models import VideoSpec
from puzzly.puzzles.missing_number import generate as missing_number
from puzzly.puzzles.puzzle_fit import generate as puzzle_fit
from puzzly.puzzles.quick_math import generate as quick_math
from puzzly.renderer import render_quality_frame, render_video
from puzzly.verify_video import inspect_video


def sample_specs() -> dict[str, VideoSpec]:
    return {
        "v4_quick_math_final": quick_math(6101, "hard", "mixed"),
        "v4_missing_number_final": missing_number(6201, "hard"),
        "v4_puzzle_fit_easy": puzzle_fit(6301, "easy"),
        "v4_puzzle_fit_hard": puzzle_fit(6302, "hard"),
    }


def moments(spec: VideoSpec) -> tuple[list[str], list[float]]:
    base = spec.intro_duration
    if spec.puzzle_type == "puzzle_fit":
        return (["COMPLETED", "REMOVING", "HOLE + CHOICES", "THINKING", "MOVING", "SOLVED"],
            [base + 0.15, base + 0.55, base + 0.90, base + 2.50, base + 5.40, base + 5.82])
    return (["INTRO", "PUZZLE", "THINKING", "REVEAL", "LATER ROUND", "OUTRO"],
        [0.72, base + 0.2, base + 2.2, base + 4.7, base + spec.round_duration * 3 + 1.2, spec.total_duration - 0.35])


def create_contact_sheet(spec: VideoSpec, path: Path, quality: str) -> None:
    labels, times = moments(spec)
    thumbnails: list[Image.Image] = []
    for label, moment in zip(labels, times):
        frame = render_quality_frame(spec, moment, quality).resize((225, 400), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (225, 438), "#183943")
        canvas.paste(frame, (0, 38))
        ImageDraw.Draw(canvas).text((112, 19), label, fill="white", anchor="mm")
        thumbnails.append(canvas)
    sheet = Image.new("RGB", (225 * len(thumbnails), 438), "#183943")
    for index, thumbnail in enumerate(thumbnails):
        sheet.paste(thumbnail, (index * 225, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, optimize=True)


def quality_frame_time(spec: VideoSpec) -> float:
    return spec.intro_duration + (2.4 if spec.puzzle_type == "puzzle_fit" else 2.2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", choices=("draft", "final"), default="final")
    parser.add_argument("--only", choices=("quick_math", "missing_number", "puzzle_fit"))
    args = parser.parse_args()
    output = Path("output/samples" if args.quality == "final" else "output/v4_drafts")
    contacts = output / "contact_sheets"
    settings = RENDER_QUALITIES[args.quality]
    specs = sample_specs()
    if args.only:
        specs = {name: spec for name, spec in specs.items() if spec.puzzle_type == args.only}
    for name, spec in specs.items():
        path = output / f"{name}.mp4"
        render_video(spec, path, args.quality, logger=None)
        create_contact_sheet(spec, contacts / f"{name}.png", args.quality)
        if args.quality == "final":
            quality_path = Path("output/samples/quality_frames") / f"{name}.png"
            quality_path.parent.mkdir(parents=True, exist_ok=True)
            render_quality_frame(spec, quality_frame_time(spec), "final").save(quality_path, optimize=True)
        print(inspect_video(path, settings.output_size, spec.total_duration))
    print({"supersampling": settings.supersampling, "internal_visual_fps": settings.internal_visual_fps, "crf": settings.crf, "preset": settings.encoder_preset})


if __name__ == "__main__":
    main()
