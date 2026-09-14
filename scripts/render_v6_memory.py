from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import imageio_ffmpeg
import numpy as np
from moviepy import VideoFileClip
from PIL import Image, ImageDraw

from puzzly.config import RENDER_QUALITIES
from puzzly.generator import generate_spec
from puzzly.models import VideoSpec
from puzzly.renderer import render_quality_frame, render_video
from puzzly.verify_video import inspect_video


def sample_specs() -> dict[str, VideoSpec]:
    return {
        "v6_memory_easy": generate_spec("memory_challenge", 9601, "easy"),
        "v6_memory_medium": generate_spec("memory_challenge", 9602, "medium"),
        "v6_memory_hard": generate_spec("memory_challenge", 9603, "hard"),
    }


def moments(spec: VideoSpec) -> tuple[list[str], list[float]]:
    start = spec.intro_duration
    return (["INTRO", "MEMORIZE", "COVERS", "TARGET", "THINKING", "REVEAL", "SOLVED"],
            [0.72, start + 1.35, start + 3.08, start + 3.52, start + 5.15, start + 7.68, start + 8.25])


def acceptance_artifacts(path: Path, spec: VideoSpec, quality: str) -> dict[str, object]:
    settings = RENDER_QUALITIES[quality]
    result = inspect_video(path, settings.output_size, spec.total_duration)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    decoded = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"], capture_output=True, check=True)
    if decoded.stderr:
        raise AssertionError(decoded.stderr.decode(errors="replace"))
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True).stderr.decode(errors="replace")
    required = ("h264 (High)", "yuv420p", "aac (LC)", "48000 Hz", "stereo") if quality == "final" else ("yuv420p", "aac (LC)", "48000 Hz", "stereo")
    for value in required:
        assert value in probe, probe
    contacts = path.parent / "contact_sheets"; contacts.mkdir(parents=True, exist_ok=True)
    labels, times = moments(spec); sheet = Image.new("RGB", (225 * len(times), 438), "#183943")
    with VideoFileClip(str(path)) as clip:
        for index, (label, moment) in enumerate(zip(labels, times)):
            frame = Image.fromarray(clip.get_frame(moment))
            sheet.paste(frame.resize((225, 400), Image.Resampling.LANCZOS), (225 * index, 38))
            ImageDraw.Draw(sheet).text((225 * index + 112, 19), label, anchor="mm", fill="white")
        audio = clip.audio.to_soundarray(fps=48000)
        peak = float(np.max(np.abs(audio))); assert 0.001 < peak < 0.95
    contact_path = contacts / f"{path.stem}.png"; sheet.save(contact_path)
    result.update({"full_decode": "passed", "video_codec": "H.264", "pixel_format": "yuv420p", "audio_codec": "AAC-LC",
                   "audio_rate": 48000, "audio_channels": 2, "audio_peak": peak, "crf": settings.crf,
                   "preset": settings.encoder_preset, "supersampling": settings.supersampling, "contact_sheet": str(contact_path)})
    (path.parent / f"{path.stem}.verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def radius_quality_frame() -> Path:
    spec = generate_spec("missing_number", 9610, "medium")
    frame = render_quality_frame(spec, spec.intro_duration + 2.0, "final")
    path = Path("output/samples/quality_frames/v6_radius_quality_check.png")
    path.parent.mkdir(parents=True, exist_ok=True); frame.save(path)
    render_quality_frame(spec, 0.72, "final").save(path.with_name("v6_radius_intro_check.png"))
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", choices=("draft", "final"), default="draft")
    parser.add_argument("--artifacts-only", action="store_true")
    args = parser.parse_args()
    output = Path("output/samples" if args.quality == "final" else "output/v6_drafts")
    output.mkdir(parents=True, exist_ok=True)
    for name, spec in sample_specs().items():
        path = output / f"{name}.mp4"
        print(f"Starting {name}: {spec.round_count} rounds, {spec.total_duration:.2f}s", flush=True)
        if not args.artifacts_only:
            elapsed = render_video(spec, path, args.quality, logger=None)
            print(f"Rendered {name} in {elapsed:.1f}s", flush=True)
        print(json.dumps(acceptance_artifacts(path, spec, args.quality)), flush=True)
    if args.quality == "final":
        print(f"Radius quality frame: {radius_quality_frame()}", flush=True)


if __name__ == "__main__":
    main()
