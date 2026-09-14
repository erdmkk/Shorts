from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from .config import (AUDIO_DIR, AUDIO_RATE, PATH_TYPES, MEMORY_ANSWER_HIGHLIGHT,
                     MEMORY_BOARD_ENTRANCE, MEMORY_COVER_DURATION, MEMORY_FINAL_DELAY,
                     MEMORY_MEMORIZATION_DURATION, MEMORY_QUESTION_DURATION,
                     MEMORY_TARGET_ENTRANCE, MEMORY_THINKING_DURATION, thinking_duration, ensure_directories)
from .config import (FLASH_APPEARANCE_DURATION, FLASH_HIDE_DURATION, FLASH_REVEAL_DURATION,
                     FLASH_THINKING_DURATION)
from .config import LUCKY_APPEARANCE_DURATION, LUCKY_SELECTION_DURATION, LUCKY_WINNER_HOLD
from .puzzles.lucky_pick import EAT_ANTICIPATION
from .models import VideoSpec

BOUNDARY_FADE_SECONDS = 0.008
SFX_PEAK_LIMIT = 10 ** (-7 / 20)
MIX_PEAK_LIMIT = 10 ** (-1 / 20)


def prepare_effect(samples: np.ndarray) -> np.ndarray:
    """Make a procedural effect safe to cut, overlap, and encode."""
    result = np.nan_to_num(np.asarray(samples, dtype=np.float64), copy=True)
    if result.size == 0:
        return result
    result -= np.mean(result, axis=0)
    fade_length = min(round(BOUNDARY_FADE_SECONDS * AUDIO_RATE), result.shape[0] // 2)
    if fade_length:
        curve = np.sin(np.linspace(0, np.pi / 2, fade_length)) ** 2
        result[:fade_length] *= curve
        result[-fade_length:] *= curve[::-1]
    peak = float(np.max(np.abs(result)))
    if peak > SFX_PEAK_LIMIT:
        result *= SFX_PEAK_LIMIT / peak
    return result


def finalize_mix(samples: np.ndarray) -> np.ndarray:
    """Apply a transparent peak gain stage before any PCM conversion."""
    result = np.nan_to_num(np.asarray(samples, dtype=np.float64), copy=True)
    peak = float(np.max(np.abs(result))) if result.size else 0.0
    if peak > MIX_PEAK_LIMIT:
        result *= MIX_PEAK_LIMIT / peak
    return result


def _tone(frequency: float, seconds: float, volume: float, decay: float = 5.0, harmonic: float = 0.12) -> np.ndarray:
    t = np.arange(int(AUDIO_RATE * seconds), dtype=np.float64) / AUDIO_RATE
    attack = np.minimum(t / 0.018, 1.0)
    envelope = attack * np.exp(-decay * t)
    signal = np.sin(2 * np.pi * frequency * t) + harmonic * np.sin(2 * np.pi * frequency * 2 * t)
    return volume * envelope * signal


def _whoosh(seconds: float = 0.32) -> np.ndarray:
    rng = np.random.default_rng(2026)
    length = int(AUDIO_RATE * seconds)
    noise = rng.normal(0, 1, length)
    smooth = np.convolve(noise, np.ones(80) / 80, mode="same")
    envelope = np.sin(np.linspace(0, np.pi, length)) ** 2
    return (smooth * envelope * 0.08).astype(np.float64)


def _write_wav(path: Path, samples: np.ndarray) -> None:
    safe = finalize_mix(samples)
    pcm = np.rint(safe * 32767).astype("<i2")
    channels = 1 if pcm.ndim == 1 else pcm.shape[1]
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels); wav.setsampwidth(2); wav.setframerate(AUDIO_RATE); wav.writeframes(pcm.tobytes())


def sound_library() -> dict[str, np.ndarray]:
    raw = {
        "intro_pop": _tone(390, 0.22, 0.15, 8),
        "object_pop": _tone(520, 0.16, 0.11, 11),
        "pulse": _tone(720, 0.09, 0.045, 18),
        "answer_ding": _tone(660, 0.58, 0.16, 4) + _tone(990, 0.58, 0.07, 5),
        "puzzle_snap": _tone(240, 0.30, 0.12, 12) + _tone(760, 0.30, 0.10, 7),
        "sparkle": _tone(1180, 0.48, 0.07, 6) + _tone(1540, 0.48, 0.04, 8),
        "transition_whoosh": _whoosh(),
    }
    return {name: prepare_effect(samples) for name, samples in raw.items()}


def ensure_sound_effects() -> dict[str, Path]:
    ensure_directories()
    paths: dict[str, Path] = {}
    for name, samples in sound_library().items():
        path = AUDIO_DIR / f"{name}.wav"
        _write_wav(path, samples)
        paths[name] = path
    return paths


def timeline_audio(spec: VideoSpec) -> np.ndarray:
    audio = np.zeros((round(spec.total_duration * AUDIO_RATE), 2), dtype=np.float64)
    if spec.puzzle_type == "hidden_motion_hunt":
        return audio
    sounds = sound_library()

    def place(at: float, sound: np.ndarray, pan: float = 0.0) -> None:
        start = max(0, int(at * AUDIO_RATE)); end = min(start + len(sound), len(audio))
        if end <= start:
            return
        sample = sound[:end - start]
        audio[start:end, 0] += sample * (1 - max(0, pan) * 0.35)
        audio[start:end, 1] += sample * (1 + min(0, pan) * 0.35)

    place(0.08, sounds["intro_pop"])
    intro_icons = 1 if spec.puzzle_type in ("flash_count", "lucky_pick") else (4 if spec.puzzle_type == "memory_challenge" else min(spec.round_count, 5))
    for icon in range(intro_icons):
        place(0.28 + icon * 0.08, sounds["object_pop"], (icon % 3 - 1) * 0.4)
    for index in range(spec.round_count):
        start = spec.intro_duration + index * spec.round_duration
        place(start + 0.08, sounds["object_pop"])
        if spec.puzzle_type == "memory_challenge":
            for token_index in range(5):
                place(start + 0.08, sounds["object_pop"], (token_index % 3 - 1) * 0.22)
            questions_start = MEMORY_BOARD_ENTRANCE + MEMORY_MEMORIZATION_DURATION + MEMORY_COVER_DURATION
            place(start + MEMORY_BOARD_ENTRANCE + MEMORY_MEMORIZATION_DURATION, sounds["transition_whoosh"])
            for question in range(4):
                question_start = start + questions_start + question * MEMORY_QUESTION_DURATION
                place(question_start + 0.05, sounds["object_pop"])
                place(question_start + MEMORY_TARGET_ENTRANCE + MEMORY_THINKING_DURATION * .55, sounds["pulse"])
                place(question_start + MEMORY_TARGET_ENTRANCE + MEMORY_THINKING_DURATION - .32, sounds["pulse"])
                reveal = question_start + MEMORY_TARGET_ENTRANCE + MEMORY_THINKING_DURATION + MEMORY_ANSWER_HIGHLIGHT
                place(reveal, sounds["puzzle_snap"]); place(reveal + .28, sounds["answer_ding"])
            final_start = start + questions_start + 4 * MEMORY_QUESTION_DURATION
            place(final_start + MEMORY_FINAL_DELAY, sounds["puzzle_snap"])
            place(final_start + MEMORY_FINAL_DELAY + .30, sounds["sparkle"])
            place(start + spec.round_duration - 0.38, sounds["transition_whoosh"])
            continue
        if spec.puzzle_type == "flash_count":
            visible_end = FLASH_APPEARANCE_DURATION + float(spec.rounds[index].data["visible_seconds"])
            hidden_at = visible_end + FLASH_HIDE_DURATION
            reveal_at = hidden_at + FLASH_THINKING_DURATION + FLASH_REVEAL_DURATION
            place(start + visible_end, sounds["transition_whoosh"])
            place(start + hidden_at + FLASH_THINKING_DURATION * .55, sounds["pulse"])
            place(start + hidden_at + FLASH_THINKING_DURATION - .32, sounds["pulse"])
            place(start + reveal_at, sounds["answer_ding"])
            place(start + spec.round_duration - .38, sounds["transition_whoosh"])
            continue
        if spec.puzzle_type == "lucky_pick":
            selection_end = LUCKY_APPEARANCE_DURATION + LUCKY_SELECTION_DURATION
            place(start + LUCKY_APPEARANCE_DURATION + 2.5, sounds["pulse"])
            place(start + selection_end - .35, sounds["pulse"])
            place(start + selection_end, sounds["transition_whoosh"])
            for elimination, step in enumerate(spec.rounds[index].data["movement_steps"]):
                eat_start = start + float(step["end_time"]) - float(step["eat_duration"])
                if elimination >= 4:
                    place(eat_start - float(step["travel_duration"]) - .04, sounds["pulse"])
                chomp = eat_start + EAT_ANTICIPATION
                place(chomp, sounds["puzzle_snap"])
                place(chomp + .15, sounds["object_pop"])
            winner = start + float(spec.rounds[index].data["timeline_duration"]) - LUCKY_WINNER_HOLD
            place(winner, sounds["answer_ding"]); place(winner + .18, sounds["sparkle"])
            continue
        if spec.puzzle_type == "puzzle_fit":
            think_start = 0.35
            think_end = think_start + thinking_duration(spec.puzzle_type, spec.difficulty)
            reveal = think_end + 0.90
        elif spec.puzzle_type in PATH_TYPES:
            think_start = 0.35
            think_end = think_start + thinking_duration(spec.puzzle_type, spec.difficulty)
            reveal = think_end + 1.25
        else:
            reveal, think_start, think_end = 4.35, 0.35, 4.35
        place(start + think_start + (think_end - think_start) * 0.5, sounds["pulse"])
        place(start + think_end - 0.35, sounds["pulse"])
        place(start + reveal, sounds["puzzle_snap"] if spec.puzzle_type == "puzzle_fit" else sounds["answer_ding"])
        transition_at = spec.round_duration - (0.15 if spec.puzzle_type == "puzzle_fit" else 0.38)
        place(start + transition_at, sounds["transition_whoosh"])
    place(spec.total_duration - spec.outro_duration + 0.12, sounds["sparkle"])
    return finalize_mix(audio)


def write_audio_diagnostic(path: Path) -> Path:
    """Write isolated and deliberately overlapping representative effects."""
    sounds = sound_library()
    audio = np.zeros((AUDIO_RATE * 5, 2), dtype=np.float64)

    def place(at: float, name: str, gain: float = 1.0) -> None:
        sound = sounds[name] * gain
        start = round(at * AUDIO_RATE)
        end = min(start + len(sound), len(audio))
        audio[start:end] += sound[:end - start, None]

    for at, name in ((0.25, "intro_pop"), (0.75, "object_pop"), (1.15, "pulse"),
                     (1.50, "answer_ding"), (2.30, "puzzle_snap"), (2.85, "sparkle"),
                     (3.55, "transition_whoosh")):
        place(at, name)
    for offset in (0.0, 0.025, 0.050, 0.075):
        place(4.10 + offset, "object_pop")
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_wav(path, audio)
    return path
