"""Light background music, synthesized locally (no copyrighted assets), that reacts to the game.

Every Puzzly for You game shares one signature (a soft pad over a bass-and-hat groove on one global beat grid, so it
flows unbroken from the first second to the end card), but each game has its own melody and character (see STYLES):
tempo, key, progression, bass pattern, lead instrument, and a two-bar motif and answer that repeat as A B A and rest
for one bar, so the tune never tires the ear. The melody is built from chord tones, so it moves with the harmony.

Two moods: "fun" games (pick games) use major keys, bouncier motifs, and a soft clap on 2 and 4; "tense" games use minor
keys and, in the last seconds of every timer, swap the melody for a climbing arpeggio over a soft heartbeat pulse.
Thinking time lifts the groove a little and each answer lands with a major chord on top. The music ducks under every
sound effect so ticks and dings stay clear. It is off unless the video's metadata says `music: on`.
"""
from __future__ import annotations

import random

import numpy as np

from .config import AUDIO_RATE
from .models import VideoSpec

KEYS = {"A minor": 45, "D minor": 50, "E minor": 40, "C minor": 48,  # MIDI roots (bass octave)
        "C major": 48, "D major": 50, "F major": 41, "G major": 43}
PROGRESSION = ((0, 3, 7), (-4, 0, 3), (3, 7, 10), (-2, 2, 5))  # i, VI, III, VII of the minor key
DARK_PROGRESSION = ((0, 3, 7), (-4, 0, 3), (5, 8, 12), (-5, -1, 2))  # i, VI, iv, V: unresolved, mysterious
FOCUS_PROGRESSION = ((0, 3, 7), (5, 8, 12), (-4, 0, 3), (-5, -2, 2))  # i, iv, VI, v: calm but serious
DRIVE_PROGRESSION = ((0, 3, 7), (-2, 2, 5), (-4, 0, 3), (-2, 2, 5))  # i, VII, VI, VII: driving, competitive
MEMORY_PROGRESSION = ((0, 3, 7), (3, 7, 10), (-2, 2, 5), (5, 8, 12))  # i, III, VII, iv: gentle, wistful
POP_PROGRESSION = ((0, 4, 7), (-5, -1, 2), (-3, 0, 4), (-7, -3, 0))  # I, V, vi, IV of the major key: playful
ARENA_PROGRESSION = ((-3, 0, 4), (-7, -3, 0), (0, 4, 7), (-5, -1, 2))  # vi, IV, I, V: upbeat, anthemic
WINDING_PROGRESSION = ((0, 3, 7), (-2, 2, 5), (5, 8, 12), (-5, -2, 2))  # i, VII, iv, v: winding, searching
TENSION_SECONDS = 3.0
MUSIC_PEAK = 0.11  # well under the sound effects (about -19 dBFS at the loudest)
DUCK_DEPTH = 0.6
# Per-game character. mood: "fun" (major, clap on 2 and 4) or "tense" (minor, heartbeat under each timer's last
# seconds). bass: "root" (on the beat), "octave" (root / octave up), "root_fifth" (root / fifth), "eighths" (root on
# every eighth), "low" (an octave down, long). hat_div: 2 = off-beat eighths, 4 = sixteenths, 1 = only on beats 2
# and 4. bass/hat amps are (calm, thinking[, tension]). lead: the melody instrument (see _lead_note). motif: the two
# melody bars A and B as (beat, chord tone, beats); chord tone 0-2 are the current chord's notes, 3-5 the same an
# octave up, 6 two octaves up.
STYLES = {
    "quick_math": {"mood": "tense", "bpm": 96, "keys": ("A minor", "D minor", "E minor", "C minor"), "progression": PROGRESSION,
                   "pad": .010, "rolloff": 1.6, "bass": "root", "bass_amp": (.03, .04, .05), "bass_decay": 7.0,
                   "hat_amp": (.007, .010), "hat_div": 2, "arp_amp": .018, "arp_decay": 10.0,
                   "lead": "pluck", "lead_amp": .020,  # focused: ticking staccato eighths, like a clock
                   "motif": (((0, 2, .5), (.5, 1, .5), (1, 2, .5), (1.5, 3, .5), (2.5, 2, .5), (3, 1, 1)),
                             ((0, 3, 1), (1, 4, .5), (1.5, 3, .5), (2, 2, 2)))},
    "puzzle_fit": {"mood": "tense", "bpm": 88, "keys": ("D minor", "A minor"), "progression": FOCUS_PROGRESSION,
                   "pad": .012, "rolloff": 1.2, "bass": "root", "bass_amp": (.025, .032, .042), "bass_decay": 5.0,
                   "hat_amp": (.005, .007), "hat_div": 2, "arp_amp": .020, "arp_decay": 6.0,
                   "lead": "bell", "lead_amp": .017,  # dreamy: long bell tones that rise and settle
                   "motif": (((0, 3, 1.5), (1.5, 2, .5), (2, 4, 2)),
                             ((0, 2, 1), (1, 1, 1), (2, 0, 2)))},
    "find_the_exit": {"mood": "tense", "bpm": 80, "keys": ("E minor", "C minor"), "progression": DARK_PROGRESSION,
                      "pad": .011, "rolloff": 2.0, "bass": "low", "bass_amp": (.03, .038, .048), "bass_decay": 3.5,
                      "hat_amp": (.005, .007), "hat_div": 1, "arp_amp": .016, "arp_decay": 8.0,
                      "lead": "glass", "lead_amp": .018,  # mysterious: dotted glass steps that hang in the air
                      "motif": (((0, 0, .75), (.75, 1, .75), (1.5, 2, 2.5)),
                                ((0, 3, .75), (.75, 2, .75), (1.5, 1, 1), (3, 0, 1)))},
    "cube_count": {"mood": "tense", "bpm": 104, "keys": ("A minor", "C minor"), "progression": DRIVE_PROGRESSION,
                   "pad": .008, "rolloff": 2.2, "bass": "octave", "bass_amp": (.03, .04, .05), "bass_decay": 11.0,
                   "hat_amp": (.005, .008), "hat_div": 4, "arp_amp": .016, "arp_decay": 14.0,
                   "lead": "square", "lead_amp": .014,  # techy: syncopated sixteenth blips
                   "motif": (((0, 3, .25), (.75, 3, .25), (1.5, 2, .25), (2, 4, .5), (3, 3, .25), (3.5, 2, .25)),
                             ((0, 1, .25), (.5, 2, .25), (1, 3, .5), (2.5, 2, .25), (3, 0, .5)))},
    "flash_count": {"mood": "tense", "bpm": 108, "keys": ("E minor", "D minor"), "progression": DARK_PROGRESSION,
                    "pad": .009, "rolloff": 2.0, "bass": "octave", "bass_amp": (.03, .04, .05), "bass_decay": 10.0,
                    "hat_amp": (.006, .009), "hat_div": 4, "arp_amp": .015, "arp_decay": 12.0,
                    "lead": "vibes", "lead_amp": .017,  # alert: shimmering vibraphone blips, like a camera flash
                    "motif": (((0, 4, .25), (.5, 4, .25), (1, 2, .5), (2, 3, .25), (2.5, 1, .25), (3, 2, 1)),
                              ((0, 2, .25), (.25, 3, .25), (.5, 4, .5), (1.5, 3, .5), (2, 0, 2)))},
    "line_follow": {"mood": "tense", "bpm": 100, "keys": ("A minor", "E minor"), "progression": WINDING_PROGRESSION,
                    "pad": .010, "rolloff": 1.8, "bass": "root", "bass_amp": (.028, .036, .046), "bass_decay": 6.5,
                    "hat_amp": (.006, .009), "hat_div": 2, "arp_amp": .017, "arp_decay": 10.0,
                    "lead": "harp", "lead_amp": .017,  # searching: harp arpeggios that zig-zag upward like a winding line
                    "motif": (((0, 0, .5), (.5, 2, .5), (1, 1, .5), (1.5, 3, .5), (2, 2, .5), (2.5, 4, .5), (3, 3, 1)),
                              ((0, 5, .75), (.75, 4, .25), (1, 3, .5), (1.5, 1, .5), (2, 2, 2)))},
    "memory_challenge": {"mood": "tense", "bpm": 84, "keys": ("D minor", "E minor"), "progression": MEMORY_PROGRESSION,
                         "pad": .012, "rolloff": 1.4, "bass": "root", "bass_amp": (.022, .03, .04), "bass_decay": 5.0,
                         "hat_amp": (.004, .006), "hat_div": 2, "arp_amp": .018, "arp_decay": 6.0,
                         "lead": "music_box", "lead_amp": .016,  # calm: a music-box arpeggio climbing and falling
                         "motif": (((0, 0, .5), (.5, 1, .5), (1, 2, .5), (1.5, 3, .5), (2, 4, 1), (3, 3, 1)),
                                   ((0, 5, 1), (1, 4, .5), (1.5, 3, .5), (2, 2, 2)))},
    "lucky_pick": {"mood": "fun", "bpm": 112, "keys": ("C major", "G major"), "progression": POP_PROGRESSION,
                   "pad": .009, "rolloff": 1.8, "bass": "root_fifth", "bass_amp": (.035, .042, .052), "bass_decay": 9.0,
                   "hat_amp": (.008, .011), "hat_div": 2, "arp_amp": .018, "arp_decay": 11.0,
                   "lead": "marimba", "lead_amp": .020,  # playful: a bouncing marimba hook
                   "motif": (((0, 0, .5), (.5, 1, .5), (1, 2, .5), (2, 4, .5), (2.5, 3, .5), (3, 2, 1)),
                             ((0, 3, .5), (.75, 2, .25), (1, 1, .5), (2, 2, .5), (2.5, 0, 1.5)))},
    "bounce_arena": {"mood": "fun", "bpm": 120, "keys": ("D major", "F major"), "progression": ARENA_PROGRESSION,
                     "pad": .008, "rolloff": 2.0, "bass": "eighths", "bass_amp": (.03, .038, .048), "bass_decay": 12.0,
                     "hat_amp": (.009, .012), "hat_div": 2, "arp_amp": .016, "arp_decay": 12.0,
                     "lead": "synth", "lead_amp": .015,  # energetic: octave-jumping synth riff
                     "motif": (((0, 0, .5), (.5, 3, .5), (1, 2, .5), (1.5, 3, .5), (2, 4, .5), (3, 3, .5), (3.5, 2, .5)),
                               ((0, 5, .5), (1, 4, .5), (1.5, 3, .5), (2, 2, 1), (3.5, 1, .5)))},
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


def _clap(rng: np.random.Generator, amplitude: float) -> np.ndarray:
    """A soft, short clap: a few smeared noise bursts, band-limited so it never gets harsh."""
    t = _time(.12)
    noise = np.convolve(rng.normal(0, 1, len(t)), np.ones(6) / 6, mode="same")  # take off the harsh top
    noise = np.diff(noise, prepend=0.0) * 3  # and the low rumble
    envelope = np.exp(-t * 38) + .5 * np.exp(-np.maximum(0, t - .012) * 60) * (t > .012)
    return amplitude * noise * envelope


def _lead_note(voice: str, midi: float, seconds: float, amplitude: float) -> np.ndarray:
    """One melody note. Every voice has few, soft harmonics and a clean fade so long listening stays easy."""
    t = _time(seconds)
    f = _freq(midi)
    tau = 2 * np.pi * f * t
    if voice == "bell":  # soft FM bell
        wave = np.sin(tau + 1.1 * np.exp(-t * 3) * np.sin(2 * tau))
        envelope = np.exp(-t * 2.4) * np.minimum(t / .004, 1.0)
    elif voice == "marimba":  # woody: a fast-fading fourth partial over a warm fundamental
        wave = np.sin(tau) + .35 * np.sin(4 * tau) * np.exp(-t * 18)
        envelope = np.exp(-t * 7) * np.minimum(t / .003, 1.0)
    elif voice == "glass":  # airy: slow attack, long ring
        wave = np.sin(tau) + .2 * np.sin(2 * tau) + .08 * np.sin(3 * tau)
        envelope = np.exp(-t * 1.8) * np.minimum(t / .03, 1.0)
    elif voice == "square":  # rounded square: odd harmonics that fall off fast
        wave = sum(np.sin(n * tau) / n ** 1.6 for n in (1, 3, 5, 7))
        envelope = np.exp(-t * 9) * np.minimum(t / .005, 1.0)
    elif voice == "music_box":  # a tine: bright strike that settles into a pure tone
        wave = np.sin(tau) + .3 * np.sin(2 * tau) + .12 * np.sin(5.4 * tau) * np.exp(-t * 10)
        envelope = np.exp(-t * 4) * np.minimum(t / .003, 1.0)
    elif voice == "harp":  # plucked string: rich harmonics that fade faster than the fundamental
        wave = sum(np.sin(n * tau) * np.exp(-t * 2.5 * n) / n ** 1.8 for n in range(1, 6))
        envelope = np.exp(-t * 3.2) * np.minimum(t / .004, 1.0)
    elif voice == "vibes":  # vibraphone: pure bar tone with a gentle motor tremolo
        wave = (np.sin(tau) + .25 * np.sin(4 * tau) * np.exp(-t * 12)) * (1 + .18 * np.sin(2 * np.pi * 5.5 * t))
        envelope = np.exp(-t * 3.6) * np.minimum(t / .003, 1.0)
    elif voice == "synth":  # soft saw-like pluck
        wave = sum(np.sin(n * tau) / n ** 1.3 for n in range(1, 5))
        envelope = np.exp(-t * 6) * np.minimum(t / .006, 1.0)
    else:  # "pluck"
        wave = np.sin(tau) + .25 * np.sin(2 * tau) + .12 * np.sin(3 * tau)
        envelope = np.exp(-t * 8) * np.minimum(t / .005, 1.0)
    release = np.clip((seconds - t) / .04, 0, 1)  # never cut a note off with a click
    return amplitude * wave * envelope * release


def _chord_tone(root: int, chord: tuple[int, ...], index: int) -> int:
    """Chord tone `index` of the melody register: 0-2 the chord's notes, 3-5 an octave up, 6 two octaves up."""
    tones = sorted(chord)
    octave, step = divmod(index, len(tones))
    return root + 24 + tones[step] + 12 * octave


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
        from .config import EXIT_HARD_ENTRANCE, EXIT_HARD_TRACE
        from .puzzles.find_the_exit import round_thinking
        from .visuals.find_the_exit import schedule
        windows = []
        for item, (start, _) in zip(spec.rounds, schedule(spec)):  # levels last different times
            think_end = start + EXIT_HARD_ENTRANCE + round_thinking(item.data)
            windows.append({"think_start": start + EXIT_HARD_ENTRANCE, "think_end": think_end, "answer": think_end + EXIT_HARD_TRACE})
        return windows
    if kind == "line_follow":
        from .visuals.line_follow import phases as line_phases, schedule as line_schedule
        windows = []
        for item, (start, _) in zip(spec.rounds, line_schedule(spec)):  # levels last different times
            times = line_phases(item)
            windows.append({"think_start": start + .35, "think_end": start + times["think_end"], "answer": start + times["arrival"]})
        return windows
    if kind == "flash_count":
        from .visuals.flash_count import phases as flash_phases
        return [{"think_start": s + flash_phases(item.data)["flash_end"], "think_end": s + flash_phases(item.data)["think_end"],
                 "answer": s + flash_phases(item.data)["reveal_end"]} for item, s in zip(spec.rounds, starts)]
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
    key = rng.choice(sorted(style["keys"]))
    root = KEYS[key]
    major = key.endswith("major")
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
        if style["mood"] == "fun" and index % 2:  # a soft clap on beats 2 and 4
            _add(track, at, _clap(noise, style["hat_amp"][0] * 1.4), -.1)
        if climbing:  # the last seconds of a timer climb: arpeggio and sixteenth hats, on the same grid
            for step in range(2):
                sub = at + step * beat / 2
                arp = root + 24 + chord[(index * 2 + step) % 3] + (12 if step else 0)
                _add(track, sub, _pluck(arp, beat / 2, style["arp_amp"], style["arp_decay"]), .3 if step else -.3)
                _add(track, sub + beat / 4, _hat(noise, .014), -.25 if step else .25)
            if style["mood"] == "tense":  # a soft heartbeat (lub-dub) under the countdown
                _add(track, at, _thump(.05))
                _add(track, at + beat * .28, _thump(.03))
    # Melody: motif A, answer B, A again, then a bar of rest, on the same beat grid. It steps aside for the arpeggio
    # in the last seconds of each timer and for the final chord under the end card.
    motif_a, motif_b = style["motif"]
    velocity = random.Random(f"melody:{spec.puzzle_type}:{spec.seed}")
    bar = 0
    while bar * bar_length < ending:
        phrase = bar % 4
        if phrase != 3:
            chord = progression[bar % len(progression)]
            notes = motif_a if phrase != 1 else motif_b
            for position, (beat_at, tone, beats) in enumerate(notes):
                at = bar * bar_length + beat_at * beat
                if at >= ending or tense(at):
                    continue
                if phrase == 2 and position == len(notes) - 1:
                    tone += 1  # the repeat of A ends one step higher, so it feels like a question
                amp = style["lead_amp"] * velocity.uniform(.85, 1.0) * (1.1 if beat_at == 0 else 1.0)
                note = _lead_note(style["lead"], _chord_tone(root, chord, tone), beats * beat + .3, amp)
                _add(track, at, note, .15 if position % 2 else -.15)
        bar += 1
    # Accents that sit on top of the groove without interrupting it: a major chord as each answer lands.
    lift = root + 12 if major else root + 15  # the tonic chord in a major key, the relative major in a minor key
    for window in windows:
        if window["answer"] is not None:
            for offset in (0, 4, 7, 12):
                _add(track, window["answer"], _pad_note(lift + offset, 1.3, .014, 0.0))
    # Final chord under the end card.
    for offset in ((0, 4, 7, 14) if major else (0, 3, 7, 14)):
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
