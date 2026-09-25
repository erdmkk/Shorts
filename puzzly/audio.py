from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

from .config import (AUDIO_DIR, AUDIO_RATE, PATH_TYPES, MEMORY_ANSWER_HIGHLIGHT, MEMORY_QUESTION_DURATION,
                     MEMORY_TARGET_ENTRANCE, MEMORY_THINKING_DURATION, thinking_duration, ensure_directories)
from .config import (FLASH_APPEARANCE_DURATION, FLASH_HIDE_DURATION, FLASH_REVEAL_DURATION,
                     FLASH_THINKING_DURATION)
from .config import LUCKY_APPEARANCE_DURATION, LUCKY_SELECTION_DURATION, LUCKY_WINNER_HOLD
from .puzzles.lucky_pick import CHOMP_AT, EAT_ANTICIPATION, EAT_BITE
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

    if spec.puzzle_type == "bounce_arena":
        data = spec.rounds[0].data
        for ball_id in range(6):
            place(.12 + ball_id * .07, sounds["object_pop"], (ball_id % 3 - 1) * .35)
        for remaining in (3.0, 2.0, 1.0):  # clock ticks at the end of the pick window
            place(5.0 - remaining, sounds["pulse"])
        place(5.0, sounds["transition_whoosh"])
        # Every bounce plays a soft, low pentatonic "tock"; each ball has its own pitch, a little louder for harder hits.
        notes = [prepare_effect(_tone(frequency, .12, .018, 30, .04)) for frequency in (196.0, 220.0, 246.9, 293.7, 329.6, 392.0)]
        last_note = -1.0
        center_x = float(data["arena"]["center"][0])
        for impact in data.get("impacts", []):
            at = 5.0 + float(impact[0])
            if at - last_note < .08:
                continue
            last_note = at
            strength = min(1.0, float(impact[6]) / 900)
            place(at, notes[int(impact[2]) % len(notes)] * (.5 + .5 * strength), (float(impact[4]) - center_x) / 400 * .4)
        for event in data["eliminations"]:
            place(5.0 + float(event["time"]), sounds["puzzle_snap"], (int(event["ball_id"]) % 3 - 1) * .30)
            place(5.0 + float(event["time"]) + .05, sounds["transition_whoosh"])
        winner_at = 5.0 + float(data["simulation_duration"])
        place(winner_at, sounds["answer_ding"])
        place(winner_at + .18, sounds["sparkle"])
        return finalize_mix(audio)

    place(0.08, sounds["intro_pop"])
    intro_icons = 1 if spec.puzzle_type in ("flash_count", "lucky_pick") else (4 if spec.puzzle_type == "memory_challenge" else min(spec.round_count, 5))
    for icon in range(intro_icons):
        place(0.28 + icon * 0.08, sounds["object_pop"], (icon % 3 - 1) * 0.4)
    for index in range(spec.round_count):
        start = spec.intro_duration + index * spec.round_duration
        place(start + 0.08, sounds["object_pop"])
        if spec.puzzle_type == "memory_challenge":
            from .visuals.memory import grid_phases
            item = spec.rounds[index]
            times = grid_phases(item)
            for token_index in range(5):
                place(start + 0.04 + token_index * .05, sounds["object_pop"], (token_index % 3 - 1) * 0.22)
            for remaining in (3.0, 2.0, 1.0):  # clock ticks at the end of the memorize window
                if times["cover"] - remaining > times["memorize_start"]:
                    place(start + times["cover"] - remaining, sounds["pulse"])
            place(start + times["cover"], sounds["transition_whoosh"])
            for question in range(len(item.data["question_order"])):
                question_start = start + times["questions"] + question * MEMORY_QUESTION_DURATION
                place(question_start + 0.05, sounds["object_pop"])
                place(question_start + MEMORY_TARGET_ENTRANCE + MEMORY_THINKING_DURATION - 1.0, sounds["pulse"])
                reveal = question_start + MEMORY_TARGET_ENTRANCE + MEMORY_THINKING_DURATION + MEMORY_ANSWER_HIGHLIGHT
                place(reveal, sounds["puzzle_snap"]); place(reveal + .28, sounds["answer_ding"])
            place(start + times["final_flip"], sounds["puzzle_snap"])
            place(start + times["completed"], sounds["sparkle"])
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
            for remaining in (3.0, 2.0, 1.0):  # clock ticks at the end of the pick window
                place(start + selection_end - remaining, sounds["pulse"])
            place(start + selection_end, sounds["transition_whoosh"])
            for elimination, step in enumerate(spec.rounds[index].data["movement_steps"]):
                eat_start = start + float(step["end_time"]) - float(step["eat_duration"])
                if elimination >= 4:
                    place(eat_start - float(step["travel_duration"]) - .04, sounds["pulse"])
                chomp = eat_start + EAT_ANTICIPATION + EAT_BITE * CHOMP_AT  # the jaws close
                place(chomp, sounds["puzzle_snap"])
                place(chomp + .12, sounds["object_pop"])
            winner = start + float(spec.rounds[index].data["timeline_duration"]) - LUCKY_WINNER_HOLD
            place(winner, sounds["answer_ding"]); place(winner + .18, sounds["sparkle"])
            continue
        if spec.puzzle_type == "puzzle_fit":
            from .puzzles.puzzle_fit import phase_times
            times = phase_times(spec.difficulty)
            for remaining in (3.0, 2.0, 1.0):  # clock ticks over the final seconds
                place(start + times["think_end"] - remaining, sounds["pulse"])
            place(start + times["think_end"], sounds["transition_whoosh"])
            place(start + times["snap"], sounds["puzzle_snap"])
            place(start + times["snap"] + .15, sounds["answer_ding"])
            place(start + spec.round_duration - 0.15, sounds["transition_whoosh"])
            continue
        if spec.puzzle_type == "quick_math" and "format" in spec.rounds[index].data:
            from .visuals.quick_math import phases as math_phases, schedule as math_schedule
            start, level_duration = math_schedule(spec)[index]
            times = math_phases(spec.rounds[index])
            level = spec.rounds[index].data
            for row in range(len(level["clues"]) + 1 if "clues" in level else 2):
                place(start + .05 + row * .08, sounds["object_pop"], (row % 3 - 1) * .25)
            if level.get("hint_shape") or level.get("hint_slot") is not None:
                place(start + times["hint"], sounds["puzzle_snap"])  # the halfway hint
            for remaining in (3.0, 2.0, 1.0):  # clock ticks over the final seconds
                place(start + times["think_end"] - remaining, sounds["pulse"])
            place(start + times["think_end"], sounds["transition_whoosh"])
            chips = len(level["shapes"]) if "shapes" in level else len(level["operators"])
            for chip in range(chips):
                place(start + times["think_end"] + chip * 1.05 / chips, sounds["object_pop"], (chip % 3 - 1) * .3)
            place(start + times["answer"], sounds["answer_ding"])
            place(start + times["answer"] + .12, sounds["sparkle"])
            place(start + level_duration - 0.15, sounds["transition_whoosh"])
            continue
        if spec.puzzle_type == "cube_count":
            from .visuals.cube_count import phases
            times = phases(spec)
            stack_count = len(spec.rounds[index].data["stacks"])
            for drop in range(min(stack_count, 8)):
                place(start + .05 + drop * .06, sounds["object_pop"], (drop % 3 - 1) * .3)
            place(start + times["visible_end"], sounds["transition_whoosh"])
            for remaining in (3.0, 2.0, 1.0):  # clock ticks over the final seconds
                place(start + times["think_end"] - remaining, sounds["pulse"])
            slot = (times["count_end"] - times["count_start"]) / max(1, stack_count)
            for stack in range(stack_count):
                place(start + times["count_start"] + stack * slot, sounds["object_pop"], (stack % 3 - 1) * .25)
            place(start + times["count_end"], sounds["answer_ding"])
            place(start + times["count_end"] + .12, sounds["sparkle"])
            place(start + spec.round_duration - 0.15, sounds["transition_whoosh"])
            continue
        if spec.puzzle_type == "find_the_exit" and spec.rounds[index].data.get("layout") == "deceptive_v2":
            from .config import EXIT_HARD_TRACE
            think_end = 0.35 + thinking_duration(spec.puzzle_type, spec.difficulty)
            for remaining in (3.0, 2.0, 1.0):  # clock ticks over the final seconds
                place(start + think_end - remaining, sounds["pulse"])
            place(start + think_end, sounds["transition_whoosh"])
            place(start + think_end + EXIT_HARD_TRACE, sounds["answer_ding"])
            place(start + think_end + EXIT_HARD_TRACE + .12, sounds["sparkle"])
            place(start + spec.round_duration - 0.15, sounds["transition_whoosh"])
            continue
        if spec.puzzle_type in PATH_TYPES:
            think_start = 0.35
            think_end = think_start + thinking_duration(spec.puzzle_type, spec.difficulty)
            reveal = think_end + 1.25
        else:
            reveal, think_start, think_end = 4.35, 0.35, 4.35
        place(start + think_start + (think_end - think_start) * 0.5, sounds["pulse"])
        place(start + think_end - 0.35, sounds["pulse"])
        place(start + reveal, sounds["answer_ding"])
        transition_at = spec.round_duration - 0.38
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
