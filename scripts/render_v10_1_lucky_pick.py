from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import imageio_ffmpeg
from PIL import Image

from puzzly.config import LUCKY_PALETTE, LUCKY_WINNER_HOLD
from puzzly.generator import generate_spec, render_batch
from puzzly.history import HistoryStore
from puzzly.puzzles.lucky_pick import EAT_ANTICIPATION, EAT_BITE, EAT_DURATION
from puzzly.renderer import render_cover, render_quality_frame
from puzzly.verify_video import inspect_video
from puzzly.visuals.backgrounds import create_background
from puzzly.visuals.lucky_pick import chomper_image

OUTPUT = PROJECT_ROOT / "output/samples/v10_1"
QUALITY_FRAMES = OUTPUT / "quality_frames"


def verify(path: Path, spec, quality: str) -> dict[str, object]:
    expected_size = (540, 960) if quality == "draft" else (1080, 1920)
    result = inspect_video(path, expected_size, spec.total_duration)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    decoded = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-map", "0:v:0", "-map", "0:a:0",
                              "-f", "null", "-"], capture_output=True)
    if decoded.returncode or decoded.stderr:
        raise AssertionError(decoded.stderr.decode(errors="replace"))
    cover = path.with_suffix(".jpg")
    with Image.open(cover) as image:
        assert image.format == "JPEG" and image.size == (1080, 1920); image.verify()
    data = spec.rounds[0].data
    result.update({"quality": quality, "full_decode": "passed", "cover": str(cover),
                   "shape_id": data["shape_id"], "corridor_template_id": data["corridor_template_id"],
                   "mirrored": data["mirrored"], "winner_index": data["winner_index"],
                   "winner_color": data["winner_color"], "elimination_order": data["elimination_order"],
                   "selection_seconds": data["selection_seconds"], "eat_seconds": data["eat_seconds"]})
    return result


def quality_frames(spec) -> list[Path]:
    QUALITY_FRAMES.mkdir(parents=True, exist_ok=True); data=spec.rounds[0].data; first=data["movement_steps"][0]; sixth=data["movement_steps"][5]
    start=spec.intro_duration
    eat_time=start+float(first["end_time"])-EAT_DURATION+EAT_ANTICIPATION+EAT_BITE/2
    frames=(
        ("v10_1_complete_corridor_board.png",start+.65),
        ("v10_1_travel_mouth_closed.png",start+float(first["start_time"])+float(first["outward_duration"])/2),
        ("v10_1_eat_mouth_open.png",eat_time),
        ("v10_1_seven_same_shape_targets.png",.92),
        ("v10_1_late_two_targets.png",start+float(sixth["start_time"])+.05),
        ("v10_1_final_winner.png",start+float(data["timeline_duration"])-LUCKY_WINNER_HOLD+.45),
    )
    paths=[]
    for filename,moment in frames:
        path=QUALITY_FRAMES/filename; render_quality_frame(spec,moment,"final").save(path); paths.append(path)
    character=create_background((1080,1920),dict(LUCKY_PALETTE),0); asset=chomper_image(520,0,False,"right")
    character.paste(asset,(280,700),asset); character_path=QUALITY_FRAMES/"v10_1_side_profile_character.png"; character.save(character_path); paths.append(character_path)
    cover_path=QUALITY_FRAMES/"v10_1_updated_cover.png"; render_cover(spec).save(cover_path); paths.append(cover_path)
    return paths


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("stage",choices=("drafts","final")); args=parser.parse_args()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    seeds=(12002,12012) if args.stage=="drafts" else (12010,)
    quality="draft" if args.stage=="drafts" else "final"
    specs=[generate_spec("lucky_pick",seed) for seed in seeds]
    _,paths=render_batch(specs,quality=quality,output_dir=OUTPUT,history=HistoryStore())
    reports=[verify(path,spec,quality) for path,spec in zip(paths,specs)]
    frames=quality_frames(specs[0]) if args.stage=="final" else []
    payload={"videos":reports,"quality_frames":[str(path) for path in frames]}
    (OUTPUT/f"v10_1_{args.stage}_verification.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
    print(json.dumps(payload,indent=2),flush=True)


if __name__=="__main__": main()
