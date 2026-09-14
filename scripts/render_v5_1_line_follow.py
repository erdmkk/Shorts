from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time

import imageio_ffmpeg
import numpy as np
from moviepy import VideoFileClip
from PIL import Image

from puzzly.config import AUDIO_RATE, LINE_FOLLOW_FINAL_PATH_SCALE, RENDER_QUALITIES
from puzzly.puzzles.line_follow import generate
from puzzly.renderer import render_video
from puzzly.verify_video import inspect_video


def sample_specs():
    return {
        "v5_1_line_follow_medium": generate(8511, "medium"),
        "v5_1_line_follow_hard": generate(8512, "hard"),
    }


def verify_and_extract(path: Path, spec, quality: str, render_seconds: float) -> dict[str, object]:
    settings = RENDER_QUALITIES[quality]
    details = inspect_video(path, settings.output_size, spec.total_duration)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    decoded = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
        capture_output=True, check=True,
    )
    if decoded.stderr:
        raise AssertionError(decoded.stderr.decode(errors="replace"))
    probe = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True).stderr.decode(errors="replace")
    required = ("h264 (High)", "yuv420p", "aac (LC)", "48000 Hz", "stereo") if quality == "final" else ("yuv420p", "aac (LC)", "48000 Hz", "stereo")
    for value in required:
        assert value in probe, probe
    frames = Path("output/samples/quality_frames") if quality == "final" else path.parent / "quality_frames"
    frames.mkdir(parents=True, exist_ok=True)
    frame_path = frames / f"{path.stem}.png"
    with VideoFileClip(str(path)) as clip:
        # First round, safely inside the unrevealed thinking period.
        thinking_time = spec.intro_duration + 3.0
        Image.fromarray(clip.get_frame(thinking_time)).save(frame_path)
        audio = clip.audio.to_soundarray(fps=AUDIO_RATE)
        peak = float(np.max(np.abs(audio)))
        assert 0.001 < peak < 0.95
    details.update({
        "full_decode": "passed", "video_codec": "H.264", "pixel_format": "yuv420p",
        "audio_codec": "AAC-LC", "audio_rate": AUDIO_RATE, "audio_channels": 2,
        "crf": settings.crf, "preset": settings.encoder_preset,
        "global_supersampling": settings.supersampling,
        "line_path_raster_scale": LINE_FOLLOW_FINAL_PATH_SCALE if quality == "final" else 1,
        "render_seconds": round(render_seconds, 3), "quality_frame": str(frame_path),
        "quality_frame_time": thinking_time,
    })
    report = path.parent / f"{path.stem}.verification.json"
    report.write_text(json.dumps(details, indent=2), encoding="utf-8")
    return details


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quality", choices=("draft", "final"), default="final")
    args = parser.parse_args()
    output = Path("output/samples" if args.quality == "final" else "output/v5_1_drafts")
    output.mkdir(parents=True, exist_ok=True)
    for name, spec in sample_specs().items():
        path = output / f"{name}.mp4"
        print(f"Starting {name}: {spec.round_count} rounds, {spec.total_duration:.2f}s", flush=True)
        started = time.perf_counter()
        render_video(spec, path, args.quality, logger=None)
        elapsed = time.perf_counter() - started
        print(json.dumps(verify_and_extract(path, spec, args.quality, elapsed)), flush=True)


if __name__ == "__main__":
    main()
