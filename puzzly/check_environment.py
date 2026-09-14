from __future__ import annotations

import sys


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11 veya daha yenisi gerekli.")
        return 1
    import PIL  # noqa: F401
    import imageio_ffmpeg
    import moviepy  # noqa: F401
    import numpy  # noqa: F401
    import streamlit  # noqa: F401

    print(f"Python: {sys.version.split()[0]}")
    print(f"FFmpeg: {imageio_ffmpeg.get_ffmpeg_exe()}")
    print("Ortam kontrolu basarili.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

