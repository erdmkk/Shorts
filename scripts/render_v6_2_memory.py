from __future__ import annotations

import argparse
import json
from pathlib import Path

from puzzly.config import MEMORY_BOARD_ENTRANCE, MEMORY_COVER_DURATION, MEMORY_MEMORIZATION_DURATION
from puzzly.generator import generate_spec
from puzzly.renderer import render_quality_frame, render_video
from scripts.render_v6_1_memory import acceptance_artifacts


def sample_specs():
    return {
        "easy": generate_spec("memory_challenge", 9621, "easy"),
        # Deliberately contains triangle, star, diamond, pentagon, and heart.
        "hard": generate_spec("memory_challenge", 35, "hard"),
    }


def quality_frames(specs) -> list[Path]:
    output = Path("output/samples/quality_frames"); output.mkdir(parents=True, exist_ok=True)
    questions = MEMORY_BOARD_ENTRANCE + MEMORY_MEMORIZATION_DURATION + MEMORY_COVER_DURATION
    settings = (
        ("v6_2_memory_intro.png", specs["hard"], 1.28),
        ("v6_2_memory_easy_memorization.png", specs["easy"], specs["easy"].intro_duration + .9),
        ("v6_2_memory_hard_question.png", specs["hard"], specs["hard"].intro_duration + questions + .8),
        ("v6_2_token_centering.png", specs["hard"], specs["hard"].intro_duration + .9),
    )
    paths = []
    for filename, spec, moment in settings:
        path = output / filename; render_quality_frame(spec, moment, "final").save(path); paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--quality", choices=("draft", "final"), default="draft")
    parser.add_argument("--only", choices=("easy", "hard"), nargs="+"); parser.add_argument("--artifacts-only", action="store_true"); args = parser.parse_args()
    specs = sample_specs(); selected = args.only or (["hard"] if args.quality == "draft" else ["easy", "hard"])
    output = Path("output/samples" if args.quality == "final" else "output/v6_2_drafts"); output.mkdir(parents=True, exist_ok=True)
    for difficulty in selected:
        spec = specs[difficulty]; path = output / f"v6_2_memory_{difficulty}.mp4"
        print(f"Starting {path.stem}: {spec.total_duration:.2f}s", flush=True)
        if not args.artifacts_only:
            elapsed = render_video(spec, path, args.quality, logger=None); print(f"Rendered in {elapsed:.1f}s", flush=True)
        print(json.dumps(acceptance_artifacts(path, spec, args.quality)), flush=True)
    if args.quality == "final" and set(selected) == {"easy", "hard"}:
        print("Quality frames:", *[str(path) for path in quality_frames(specs)], sep="\n", flush=True)


if __name__ == "__main__": main()
