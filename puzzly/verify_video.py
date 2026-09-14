from __future__ import annotations

from pathlib import Path
import sys

from moviepy import VideoFileClip


def inspect_video(path: Path, expected_size: tuple[int, int] = (1080, 1920), expected_duration: float | None = None) -> dict[str, object]:
    if not path.exists() or path.stat().st_size < 10_000:
        raise AssertionError(f"Missing or unexpectedly small video: {path}")
    clip = VideoFileClip(str(path))
    try:
        details = {"path": str(path), "width": clip.w, "height": clip.h, "duration": float(clip.duration), "fps": float(clip.fps), "audio": clip.audio is not None, "bytes": path.stat().st_size}
        assert (clip.w, clip.h) == expected_size, details
        if expected_duration is not None:
            assert abs(float(clip.duration) - expected_duration) <= 0.1, details
        assert abs(float(clip.fps) - 30.0) <= 0.01, details
        assert clip.audio is not None, details
        clip.get_frame(0.2); clip.get_frame(max(0.2, float(clip.duration) - 0.2))
        return details
    finally:
        clip.close()


def main(arguments: list[str]) -> int:
    if not arguments:
        print("Usage: python -m puzzly.verify_video VIDEO [VIDEO ...]"); return 2
    for argument in arguments:
        print(inspect_video(Path(argument)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
