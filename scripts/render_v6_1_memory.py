from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

import imageio_ffmpeg
import numpy as np
from moviepy import VideoFileClip
from PIL import Image, ImageDraw

from puzzly.config import (MEMORY_BOARD_ENTRANCE, MEMORY_COVER_DURATION, MEMORY_MEMORIZATION_DURATION,
                           MEMORY_QUESTION_DURATION, RENDER_QUALITIES)
from puzzly.generator import generate_spec
from puzzly.models import VideoSpec
from puzzly.renderer import render_quality_frame, render_video
from puzzly.verify_video import inspect_video


def sample_specs() -> dict[str, VideoSpec]:
    return {
        "v6_1_memory_easy": generate_spec("memory_challenge", 9611, "easy"),
        "v6_1_memory_medium": generate_spec("memory_challenge", 9612, "medium"),
        "v6_1_memory_hard": generate_spec("memory_challenge", 9613, "hard"),
    }


def moments(spec: VideoSpec) -> tuple[list[str], list[float]]:
    start = spec.intro_duration
    questions = MEMORY_BOARD_ENTRANCE + MEMORY_MEMORIZATION_DURATION + MEMORY_COVER_DURATION
    return (["NEW INTRO", "MEMORIZE", "COVERED", "TARGET 1", "ANSWER 1", "LATER QUESTION", "ANSWER 4", "AUTO / COMPLETE"],
            [1.43, start+.9, start+questions-.08, start+questions+.8,
             start+questions+MEMORY_QUESTION_DURATION-.08,
             start+questions+2*MEMORY_QUESTION_DURATION+.8,
             start+questions+4*MEMORY_QUESTION_DURATION-.08,
             start+questions+4*MEMORY_QUESTION_DURATION+1.35])


def acceptance_artifacts(path: Path, spec: VideoSpec, quality: str) -> dict[str, object]:
    settings = RENDER_QUALITIES[quality]; result = inspect_video(path, settings.output_size, spec.total_duration)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    decoded = subprocess.run([ffmpeg,"-v","error","-i",str(path),"-map","0:v:0","-map","0:a:0","-f","null","-"],capture_output=True,check=True)
    if decoded.stderr: raise AssertionError(decoded.stderr.decode(errors="replace"))
    probe = subprocess.run([ffmpeg,"-hide_banner","-i",str(path)],capture_output=True).stderr.decode(errors="replace")
    required=("h264 (High)","yuv420p","aac (LC)","48000 Hz","stereo") if quality=="final" else ("yuv420p","aac (LC)","48000 Hz","stereo")
    for value in required: assert value in probe, probe
    contacts=path.parent/"contact_sheets"; contacts.mkdir(parents=True,exist_ok=True)
    labels,times=moments(spec); sheet=Image.new("RGB",(225*len(times),438),"#183943")
    with VideoFileClip(str(path)) as clip:
        for index,(label,moment) in enumerate(zip(labels,times)):
            frame=Image.fromarray(clip.get_frame(moment)); sheet.paste(frame.resize((225,400),Image.Resampling.LANCZOS),(225*index,38))
            ImageDraw.Draw(sheet).text((225*index+112,19),label,anchor="mm",fill="white")
        audio=clip.audio.to_soundarray(fps=48000); peak=float(np.max(np.abs(audio))); assert .001<peak<.95
    contact=contacts/f"{path.stem}.png"; sheet.save(contact)
    result.update({"full_decode":"passed","video_codec":"H.264","pixel_format":"yuv420p","audio_codec":"AAC-LC","audio_rate":48000,
                   "audio_channels":2,"audio_peak":peak,"crf":settings.crf,"preset":settings.encoder_preset,
                   "supersampling":settings.supersampling,"contact_sheet":str(contact)})
    (path.parent/f"{path.stem}.verification.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


def quality_frames(specs: dict[str, VideoSpec]) -> list[Path]:
    output=Path("output/samples/quality_frames"); output.mkdir(parents=True,exist_ok=True); paths=[]
    for difficulty in ("easy","medium","hard"):
        spec=specs[f"v6_1_memory_{difficulty}"]; path=output/f"v6_1_memory_{difficulty}_memorization.png"
        render_quality_frame(spec,spec.intro_duration+.9,"final").save(path); paths.append(path)
    hard=specs["v6_1_memory_hard"]
    question=MEMORY_BOARD_ENTRANCE+MEMORY_MEMORIZATION_DURATION+MEMORY_COVER_DURATION+.8
    for name,moment in (("v6_1_memory_hard_question.png",hard.intro_duration+question),("v6_1_memory_intro.png",1.43)):
        path=output/name; render_quality_frame(hard,moment,"final").save(path); paths.append(path)
    return paths


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--quality",choices=("draft","final"),default="draft"); parser.add_argument("--artifacts-only",action="store_true"); args=parser.parse_args()
    specs=sample_specs(); output=Path("output/samples" if args.quality=="final" else "output/v6_1_drafts"); output.mkdir(parents=True,exist_ok=True)
    for name,spec in specs.items():
        path=output/f"{name}.mp4"; print(f"Starting {name}: {spec.total_duration:.2f}s",flush=True)
        if not args.artifacts_only:
            elapsed=render_video(spec,path,args.quality,logger=None); print(f"Rendered {name} in {elapsed:.1f}s",flush=True)
        print(json.dumps(acceptance_artifacts(path,spec,args.quality)),flush=True)
    if args.quality=="final":
        print("Quality frames:",*[str(path) for path in quality_frames(specs)],sep="\n",flush=True)


if __name__=="__main__": main()
