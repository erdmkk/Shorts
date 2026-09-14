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
        "v3_quick_math_easy": quick_math(5101, "easy", "addition"),
        "v3_quick_math_hard": quick_math(5102, "hard", "mixed"),
        "v3_missing_number_medium": missing_number(5201, "medium"),
        "v3_puzzle_fit_easy": puzzle_fit(5301, "easy"),
        "v3_puzzle_fit_hard": puzzle_fit(5302, "hard"),
    }


def representative_times(spec: VideoSpec) -> list[float]:
    reveal = 5.4 if spec.puzzle_type == "puzzle_fit" else 4.7
    later_round = spec.intro_duration + spec.round_duration * 3 + 1.2
    return [0.72, spec.intro_duration + 0.2, spec.intro_duration + 2.2, spec.intro_duration + reveal, later_round, spec.total_duration - 0.35]


def create_contact_sheet(spec: VideoSpec, path: Path) -> None:
    labels = ("INTRO", "PUZZLE", "THINK", "REVEAL", "LATER ROUND", "OUTRO")
    thumbnails: list[Image.Image] = []
    for label, moment in zip(labels, representative_times(spec)):
        frame = render_frame(spec, moment, (540, 960)).resize((225, 400), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (225, 438), "#183943")
        canvas.paste(frame, (0, 38))
        ImageDraw.Draw(canvas).text((112, 19), label, fill="white", anchor="mm")
        thumbnails.append(canvas)
    sheet = Image.new("RGB", (225 * len(thumbnails), 438), "#183943")
    for index, thumbnail in enumerate(thumbnails):
        sheet.paste(thumbnail, (index * 225, 0))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", choices=("draft", "final"), default="final")
    args = parser.parse_args()
    output = Path("output/samples" if args.quality == "final" else "output/v3_drafts")
    contacts = output / "contact_sheets"
    expected_size = (1080, 1920) if args.quality == "final" else (540, 960)
    for name, spec in sample_specs().items():
        path = output / f"{name}.mp4"
        render_video(spec, path, args.quality, logger=None)
        create_contact_sheet(spec, contacts / f"{name}.png")
        print(inspect_video(path, expected_size, spec.total_duration))


if __name__ == "__main__":
    main()
