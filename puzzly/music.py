"""Light background music, synthesized locally (no copyrighted assets), that reacts to the game.

Every Puzzly for You game shares one signature (a soft minor pad over a bass-and-hat groove on one global beat grid,
so it flows unbroken from the first second to the end card), but each game has its own character: tempo, keys,
progression, bass pattern, and brightness (see STYLES). Thinking time lifts the groove a little, the last seconds of
each timer add an arpeggio and denser hats, and each answer lands with a major chord on top. The music ducks under
every sound effect so ticks and dings stay clear. It is off unless the video's metadata says `music: on`.
"""
from __future__ import annotations

import random

import numpy as np

from .config import AUDIO_RATE
from .models import VideoSpec

KEYS = {"A minor": 45, "D minor": 50, "E minor": 40, "C minor": 48}  # MIDI roots (bass octave)
PROGRESSION = ((0, 3, 7), (-4, 0, 3), (3, 7, 10), (-2, 2, 5))  # i, VI, III, VII of the minor key
DARK_PROGRESSION = ((0, 3, 7), (-4, 0, 3), (5, 8, 12), (-5, -1, 2))  # i, VI, iv, v
TENSION_SECONDS = 3.0
MUSIC_PEAK = 0.11  # well under the sound effects (about -19 dBFS at the loudest)
DUCK_DEPTH = 0.6
# Per-game character. bass: "root" (on the beat), "octave" (root / octave up), "root_fifth" (root / fifth),
# "eighths" (root on every eighth), "low" (an octave down, long). hat_div: 2 = off-beat eighths, 4 = sixteenths,
# 1 = only on beats 2 and 4. bass/hat amps are (calm, thinking[, tension]).
STYLES = {
    "quick_math": {"bpm": 96, "keys": ("A minor", "D minor", "E minor", "C minor"), "progression": PROGRESSION,
                   "pad": .010, "rolloff": 1.6, "bass": "root", "bass_amp": (.03, .04, .05), "bass_decay": 7.0,
                   "hat_amp": (.007, .010), "hat_div": 2, "arp_amp": .018, "arp_decay": 10.0},  # focused
    "puzzle_fit": {"bpm": 88, "keys": ("D minor", "A minor"), "progression": PROGRESSION,
                   "pad": .012, "rolloff": 1.2, "bass": "root", "bass_amp": (.025, .032, .042), "bass_decay": 5.0,
                   "hat_amp": (.005, .007), "hat_div": 2, "arp_amp": .020, "arp_decay": 6.0},  # dreamy, bell-like
    "find_the_exit": {"bpm": 80, "keys": ("E minor", "C minor"), "progression": DARK_PROGRESSION,
                      "pad": .011, "rolloff": 2.0, "bass": "low", "bass_amp": (.03, .038, .048), "bass_decay": 3.5,
                      "hat_amp": (.005, .007), "hat_div": 1, "arp_amp": .016, "arp_decay": 8.0},  # mysterious
    "cube_count": {"bpm": 104, "keys": ("A minor", "C minor"), "progression": PROGRESSION,
                   "pad": .008, "rolloff": 2.2, "bass": "octave", "bass_amp": (.03, .04, .05), "bass_decay": 11.0,
                   "hat_amp": (.005, .008), "hat_div": 4, "arp_amp": .016, "arp_decay": 14.0},  # techy, staccato
    "memory_challenge": {"bpm": 84, "keys": ("D minor", "E minor"), "progression": PROGRESSION,
                         "pad": .012, "rolloff": 1.4, "bass": "root", "bass_amp": (.022, .03, .04), "bass_decay": 5.0,
                         "hat_amp": (.004, .006), "hat_div": 2, "arp_amp": .018, "arp_decay": 6.0},  # calm
    "lucky_pick": {"bpm": 112, "keys": ("C minor", "A minor"), "progression": PROGRESSION,
                   "pad": .009, "rolloff": 1.8, "bass": "root_fifth", "bass_amp": (.035, .042, .052), "bass_decay": 9.0,
                   "hat_amp": (.008, .011), "hat_div": 2, "arp_amp": .018, "arp_decay": 11.0},  # playful
    "bounce_arena": {"bpm": 120, "keys": ("E minor", "A minor"), "progression": PROGRESSION,
                     "pad": .008, "rolloff": 2.0, "bass": "eighths", "bass_amp": (.03, .038, .048), "bass_decay": 12.0,
                     "hat_amp": (.009, .012), "hat_div": 2, "arp_amp": .016, "arp_decay": 12.0},  # energetic
}


def supports_music(spec: VideoSpec) -> bool:
    """Every Puzzly for You game (the ones with a 3D cover template) can play music."""
    from .covers import has_template
    return spec.puzzle_type in STYLES and has_template(spec)


def music_enabled(spec: VideoSpec) -> bool:
    return spec.metadata.get("music") == "on" and supports_music(spec)


def _freq(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _time(seconds: float) -> np.ndarray:
    return np.arange(max(1, int(seconds * AUDIO_RATE)), dtype=np.float64) / AUDIO_RATE


def _add(track: np.ndarray, at: float, sound: np.ndarray, pan: float = 0.0) -> None:
    start = int(at * AUDIO_RATE)
    if start >= len(track):
        return
    end = min(len(track), start + len(sound))
    piece = sound[:end - start]
    track[start:end, 0] += piece * (1 - max(0.0, pan) * .5)
    track[start:end, 1] += piece * (1 + min(0.0, pan) * .5)


def _pad_note(midi: float, seconds: float, amplitude: float, detune: float, rolloff: float = 1.6) -> np.ndarray:
    t = _time(seconds)
    frequency = _freq(midi) * (1 + detune)
    wave = sum(np.sin(2 * np.pi * frequency * n * t) / n ** rolloff for n in range(1, 6))  # soft, few harmonics
    attack = np.minimum(t / .35, 1.0)
    release = np.minimum((seconds - t) / .5, 1.0)
    return amplitude * wave * attack * np.clip(release, 0, 1)


def _pluck(midi: float, seconds: float, amplitude: float, decay: float = 7.0) -> np.ndarray:
    t = _time(seconds)
    frequency = _freq(midi)
    wave = np.sin(2 * np.pi * frequency * t) + .25 * np.sin(4 * np.pi * frequency * t)
    return amplitude * wave * np.exp(-decay * t) * np.minimum(t / .006, 1.0)


def _hat(rng: np.random.Generator, amplitude: float) -> np.ndarray:
    noise = rng.normal(0, 1, int(.035 * AUDIO_RATE))
    bright = np.diff(noise, prepend=0.0)  # crude high-pass
    return amplitude * bright * np.exp(-np.arange(len(bright)) / (AUDIO_RATE * .008))


def _thump(amplitude: float) -> np.ndarray:
    t = _time(.3)
    sweep = 120 * np.exp(-t * 18) + 48
    return amplitude * np.sin(2 * np.pi * np.cumsum(sweep) / AUDIO_RATE) * np.exp(-t * 9)


# ---------------------------------------------------------------- when each game thinks and answers

def _windows(spec: VideoSpec) -> list[dict[str, float | None]]:
    """Thinking windows and answer moments (absolute seconds) for the tension and resolve accents."""
    kind = spec.puzzle_type
    if kind == "quick_math":
        from .visuals.quick_math import phases, schedule
        return [{"think_start": start + .5, "think_end": start + phases(item)["think_end"], "answer": start + phases(item)["answer"]}
                for item, (start, _) in zip(spec.rounds, schedule(spec))]
    starts = [spec.intro_duration + index * spec.round_duration for index in range(spec.round_count)]
    if kind == "puzzle_fit":
        from .puzzles.puzzle_fit import phase_times
        times = phase_times(spec.difficulty)
        return [{"think_start": s + times["think_start"], "think_end": s + times["think_end"], "answer": s + times["snap"]} for s in starts]
    if kind == "find_the_exit":
        from .config import EXIT_HARD_THINKING, EXIT_HARD_TRACE
        return [{"think_start": s + .35, "think_end": s + .35 + EXIT_HARD_THINKING, "answer": s + .35 + EXIT_HARD_THINKING + EXIT_HARD_TRACE}
                for s in starts]
    if kind == "cube_count":
        from .visuals.cube_count import phases
        times = phases(spec)
        return [{"think_start": s + times["hide_end"], "think_end": s + times["think_end"], "answer": s + times["count_end"]} for s in starts]
    if kind == "memory_challenge":
        from .config import MEMORY_ANSWER_HIGHLIGHT, MEMORY_QUESTION_DURATION, MEMORY_TARGET_ENTRANCE, MEMORY_THINKING_DURATION
        from .visuals.memory import grid_phases
        start, item = spec.intro_duration, spec.rounds[0]
        times = grid_phases(item)
        windows = [{"think_start": start + times["memorize_start"], "think_end": start + times["cover"], "answer": None}]
        for question in range(len(item.data["question_order"])):
            think_start = start + times["questions"] + question * MEMORY_QUESTION_DURATION + MEMORY_TARGET_ENTRANCE
            windows.append({"think_start": think_start, "think_end": think_start + MEMORY_THINKING_DURATION,
                            "answer": think_start + MEMORY_THINKING_DURATION + MEMORY_ANSWER_HIGHLIGHT})
        return windows
    if kind == "lucky_pick":
        from .config import LUCKY_APPEARANCE_DURATION, LUCKY_SELECTION_DURATION, LUCKY_WINNER_HOLD
        start = spec.intro_duration
        return [{"think_start": start + LUCKY_APPEARANCE_DURATION, "think_end": start + LUCKY_APPEARANCE_DURATION + LUCKY_SELECTION_DURATION,
                 "answer": start + float(spec.rounds[0].data["timeline_duration"]) - LUCKY_WINNER_HOLD}]
    if kind == "bounce_arena":
        from .config import BOUNCE_SELECTION_DURATION
        return [{"think_start": 0.0, "think_end": BOUNCE_SELECTION_DURATION,
                 "answer": BOUNCE_SELECTION_DURATION + float(spec.rounds[0].data["simulation_duration"])}]
    return []


# ---------------------------------------------------------------- the track

def music_track(spec: VideoSpec, length: int) -> np.ndarray:
    style = STYLES[spec.puzzle_type]
    beat = 60.0 / style["bpm"]
    bar_length = beat * 4
    progression = style["progression"]
    rng = random.Random(f"music:{spec.puzzle_type}:{spec.seed}")
    root = KEYS[rng.choice(sorted(style["keys"]))]
    noise = np.random.default_rng(spec.seed % (2**32))
    track = np.zeros((length, 2), dtype=np.float64)
    duration = length / AUDIO_RATE
    windows = _windows(spec)
    # Pad: one chord per bar through the whole video, a little wider in stereo.
    bar_start, bar = 0.0, 0
    while bar_start < duration:
        chord = progression[bar % len(progression)]
        for offset in chord:
            midi = root + 12 + offset
            _add(track, bar_start, _pad_note(midi, bar_length + .4, style["pad"], -.002, style["rolloff"]), -.6)
            _add(track, bar_start, _pad_note(midi, bar_length + .4, style["pad"], .002, style["rolloff"]), .6)
        bar_start += bar_length
        bar += 1
    _add(track, 0.0, _thump(.12))

    # One global beat grid from the first second to the last: the groove never restarts between levels.
    def thinking(at: float) -> bool:
        return any(w["think_start"] <= at < w["think_end"] for w in windows)

    def tense(at: float) -> bool:
        return any(w["think_end"] - min(TENSION_SECONDS, (w["think_end"] - w["think_start"]) / 2) <= at < w["think_end"] for w in windows)

    calm, busy, peak = style["bass_amp"]
    ending = spec.total_duration - spec.outro_duration
    for index in range(int((duration - .2) / beat)):
        at = index * beat
        if at >= ending:  # under the end card the groove gives way to the final chord
            break
        chord = progression[int(at / bar_length) % len(progression)]
        climbing = tense(at)
        amp = peak if climbing else (busy if thinking(at) else calm)
        bass = style["bass"]
        if bass == "octave":
            note = root + chord[0] + (12 if index % 2 else 0)
        elif bass == "root_fifth":
            note = root + chord[0] + (7 if index % 2 else 0)
        elif bass == "low":
            note = root + chord[0] - 12 if root + chord[0] - 12 >= 28 else root + chord[0]
        else:
            note = root + chord[0]
        _add(track, at, _pluck(note, beat * .9, amp, style["bass_decay"]))
        if bass == "eighths":
            _add(track, at + beat / 2, _pluck(note, beat * .45, amp * .7, style["bass_decay"]))
        hat = style["hat_amp"][1] if thinking(at) else style["hat_amp"][0]
        if style["hat_div"] == 1:
            if index % 2:
                _add(track, at, _hat(noise, hat), .3)
        else:
            for tick in range(1, style["hat_div"], 2 if style["hat_div"] == 4 else 1):
                _add(track, at + beat * tick / style["hat_div"], _hat(noise, hat), .35 if (index + tick) % 2 else -.35)
        if climbing:  # the last seconds of a timer climb: arpeggio and sixteenth hats, on the same grid
            for step in range(2):
                sub = at + step * beat / 2
                arp = root + 24 + chord[(index * 2 + step) % 3] + (12 if step else 0)
                _add(track, sub, _pluck(arp, beat / 2, style["arp_amp"], style["arp_decay"]), .3 if step else -.3)
                _add(track, sub + beat / 4, _hat(noise, .014), -.25 if step else .25)
    # Accents that sit on top of the groove without interrupting it: a major chord as each answer lands.
    for window in windows:
        if window["answer"] is not None:
            for offset in (0, 4, 7, 12):
                _add(track, window["answer"], _pad_note(root + 15 + offset, 1.3, .014, 0.0))
    # Final chord under the end card.
    for offset in (0, 3, 7, 14):
        _add(track, ending, _pad_note(root + 12 + offset, spec.outro_duration + .3, .014, 0.0))
    gain = np.ones(length)
    fade_out = int(.4 * AUDIO_RATE)
    gain[-fade_out:] *= np.linspace(1, 0, fade_out)
    track *= gain[:, None]
    loudest = float(np.max(np.abs(track))) or 1.0
    return track * (MUSIC_PEAK / loudest)


def add_music(spec: VideoSpec, effects: np.ndarray) -> np.ndarray:
    """Mix the music under the effects, ducking it wherever an effect plays."""
    music = music_track(spec, len(effects))
    level = np.max(np.abs(effects), axis=1)
    window = int(.06 * AUDIO_RATE)
    kernel = np.ones(window) / window
    envelope = np.convolve(level, kernel, mode="same")
    envelope = np.convolve(np.maximum(envelope, np.roll(envelope, window)), kernel, mode="same")  # quick attack, soft release
    duck = 1 - DUCK_DEPTH * np.clip(envelope / .05, 0, 1)
    return effects + music * duck[:, None]
