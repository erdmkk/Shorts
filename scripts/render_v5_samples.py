from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import imageio_ffmpeg
import numpy as np
from moviepy import VideoFileClip
from PIL import Image, ImageDraw

from puzzly.config import RENDER_QUALITIES, PATH_TYPES, thinking_duration
from puzzly.generator import generate_spec, PUZZLE_TYPES
from puzzly.models import VideoSpec
from puzzly.renderer import render_video
from puzzly.verify_video import inspect_video


def sample_specs(include_hard: bool = False) -> dict[str, VideoSpec]:
    settings = [
        ("v5_quick_math_final", "quick_math", 7101, "hard"),
        ("v5_missing_number_final", "missing_number", 7201, "hard"),
        ("v5_puzzle_fit_final", "puzzle_fit", 7301, "medium"),
        ("v5_find_the_exit_medium", "find_the_exit", 7401, "medium"),
        ("v5_line_follow_medium", "line_follow", 7501, "medium"),
    ]
    if include_hard:
        settings += [
            ("v5_find_the_exit_hard", "find_the_exit", 7402, "hard"),
            ("v5_line_follow_hard", "line_follow", 7502, "hard"),
        ]
    return {name: generate_spec(kind, seed, difficulty) for name, kind, seed, difficulty in settings}


def moments(spec: VideoSpec) -> tuple[list[str], list[float]]:
    start = spec.intro_duration
    if spec.puzzle_type == "puzzle_fit":
        return (["INTRO", "MISSING PIECE", "CANDIDATES", "THINKING", "SNAPPING IN", "SOLVED"],
                [0.4, start + 0.1, start + 0.4, start + 2.4, start + 5.05, start + 5.6])
    reveal = 0.35 + thinking_duration(spec.puzzle_type, spec.difficulty)
    if spec.puzzle_type in PATH_TYPES:
        return (["INTRO", "PUZZLE", "THINKING", "PATH REVEAL", "SOLVED", "OUTRO"],
                [0.65, start + 0.4, start + 3, start + reveal + 0.65, start + reveal + 1.5, spec.total_duration - 0.3])
    return (["INTRO", "PUZZLE", "THINKING", "REVEAL", "LATER ROUND", "OUTRO"],
            [0.7, start + 0.4, start + 2.2, start + 4.7, start + 2 * spec.round_duration + 2, spec.total_duration - 0.3])


def acceptance_artifacts(path: Path, spec: VideoSpec, quality: str) -> dict:
    settings = RENDER_QUALITIES[quality]
    result = inspect_video(path, settings.output_size, spec.total_duration)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    decoded = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
                             capture_output=True, check=True)
    if decoded.stderr:
        raise AssertionError(decoded.stderr.decode(errors="replace"))
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True).stderr.decode(errors="replace")
    for required in ("h264 (High)", "yuv420p", "aac (LC)", "48000 Hz", "stereo"):
        if quality == "final" or required != "h264 (High)":
            assert required in probe, probe
    contacts, frames = path.parent / "contact_sheets", path.parent / "quality_frames"
    contacts.mkdir(parents=True, exist_ok=True)
    frames.mkdir(parents=True, exist_ok=True)
    labels, times = moments(spec)
    sheet = Image.new("RGB", (225 * len(times), 438), "#183943")
    with VideoFileClip(str(path)) as clip:
        for index, (label, moment) in enumerate(zip(labels, times)):
            frame = Image.fromarray(clip.get_frame(moment))
            sheet.paste(frame.resize((225, 400), Image.Resampling.LANCZOS), (225 * index, 38))
            ImageDraw.Draw(sheet).text((225 * index + 112, 19), label, anchor="mm", fill="white")
        Image.fromarray(clip.get_frame(spec.intro_duration + 2.2)).save(frames / f"{path.stem}.png")
        audio = clip.audio.to_soundarray(fps=48000)
        peak = float(np.max(np.abs(audio)))
        assert 0.001 < peak < 0.95, peak
        result["audio_peak"] = peak
    sheet.save(contacts / f"{path.stem}.png")
    result.update({"full_decode": "passed", "video_codec": "H.264", "pixel_format": "yuv420p",
                   "audio_codec": "AAC-LC", "audio_rate": 48000, "audio_channels": 2,
                   "supersampling": settings.supersampling, "visual_fps": settings.internal_visual_fps,
                   "crf": settings.crf, "preset": settings.encoder_preset,
                   "contact_sheet": str(contacts / f"{path.stem}.png"), "quality_frame": str(frames / f"{path.stem}.png")})
    (path.parent / f"{path.stem}.verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", choices=("draft", "final"), default="final")
    parser.add_argument("--only", choices=PUZZLE_TYPES, nargs="+")
    parser.add_argument("--include-hard", action="store_true")
    parser.add_argument("--artifacts-only", action="store_true")
    args = parser.parse_args()
    output = Path("output/samples" if args.quality == "final" else "output/v5_drafts")
    for name, spec in sample_specs(args.include_hard).items():
        if args.only and spec.puzzle_type not in args.only:
            continue
        path = output / f"{name}.mp4"
        print(f"Starting {name}: {spec.round_count} rounds, {spec.total_duration:.2f}s", flush=True)
        if not args.artifacts_only:
            elapsed = render_video(spec, path, args.quality, logger=None)
            print(f"Rendered {name} in {elapsed:.1f}s", flush=True)
        print(json.dumps(acceptance_artifacts(path, spec, args.quality)), flush=True)


if __name__ == "__main__":
    main()
