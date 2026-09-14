from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

from puzzly.models import VideoSpec
from puzzly.puzzles.missing_number import generate as missing_number
from puzzly.puzzles.puzzle_fit import generate as puzzle_fit
from puzzly.puzzles.quick_math import generate as quick_math
from puzzly.renderer import render_frame, render_video
from puzzly.verify_video import inspect_video


def sample_specs() -> dict[str, VideoSpec]:
    return {
        "v2_quick_math_addition": quick_math(4101, "easy", "addition"),
        "v2_quick_math_mixed": quick_math(4102, "medium", "mixed"),
        "v2_missing_number": missing_number(4201, "medium"),
        "v2_puzzle_fit_easy": puzzle_fit(4301, "easy"),
        "v2_puzzle_fit_medium": puzzle_fit(4302, "medium"),
    }


def representative_times(spec: VideoSpec) -> list[float]:
    reveal = {"quick_math": 2.9, "missing_number": 3.9, "puzzle_fit": 5.4}[spec.puzzle_type]
    thinking = {"quick_math": 1.5, "missing_number": 2.0, "puzzle_fit": 2.7}[spec.puzzle_type]
    return [0.65, spec.intro_duration + 0.2, spec.intro_duration + thinking, spec.intro_duration + reveal, spec.total_duration - 0.35]


def create_contact_sheet(spec: VideoSpec, path: Path) -> None:
    labels = ("INTRO", "PUZZLE", "THINK", "REVEAL", "OUTRO")
    thumbnails: list[Image.Image] = []
    for label, moment in zip(labels, representative_times(spec)):
        frame = render_frame(spec, moment, (540, 960)).resize((270, 480), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (270, 520), "#183943")
        canvas.paste(frame, (0, 40))
        ImageDraw.Draw(canvas).text((135, 20), label, fill="white", anchor="mm")
        thumbnails.append(canvas)
    sheet = Image.new("RGB", (270 * len(thumbnails), 520), "#183943")
    for index, thumbnail in enumerate(thumbnails):
        sheet.paste(thumbnail, (index * 270, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", choices=("draft", "final"), default="final")
    args = parser.parse_args()
    output = Path("output/samples" if args.quality == "final" else "output/v2_drafts")
    contacts = output / "contact_sheets"
    expected_size = (1080, 1920) if args.quality == "final" else (540, 960)
    for name, spec in sample_specs().items():
        path = output / f"{name}.mp4"
        render_video(spec, path, args.quality, logger=None)
        create_contact_sheet(spec, contacts / f"{name}.png")
        print(inspect_video(path, expected_size, spec.total_duration))


if __name__ == "__main__":
    main()
