import wave

import numpy as np

from puzzly.audio import (BOUNDARY_FADE_SECONDS, MIX_PEAK_LIMIT, finalize_mix,
                          sound_library, timeline_audio, write_audio_diagnostic)
from puzzly.config import AUDIO_RATE
from puzzly.generator import generate_spec


def test_effects_are_deterministic_faded_and_dc_safe() -> None:
    first, second = sound_library(), sound_library()
    fade_samples = round(BOUNDARY_FADE_SECONDS * AUDIO_RATE)
    assert first.keys() == second.keys()
    for name in first:
        samples = first[name]
        assert np.array_equal(samples, second[name])
        assert np.isfinite(samples).all()
        assert samples[0] == 0 and abs(samples[-1]) < 1e-12
        assert abs(float(np.mean(samples))) < 2e-4
        assert np.max(np.abs(samples[:fade_samples])) < np.max(np.abs(samples))


def test_overlapping_mix_has_safe_float_headroom_without_clipping() -> None:
    sound = sound_library()["answer_ding"]
    mixed = np.column_stack((sound * 8, sound * 8))
    safe = finalize_mix(mixed)
    assert safe.dtype == np.float64
    assert np.isfinite(safe).all()
    assert np.max(np.abs(safe)) <= MIX_PEAK_LIMIT + 1e-12
    assert len(np.unique(safe)) > 100


def test_representative_timeline_is_48khz_safe() -> None:
    spec = generate_spec("memory_challenge", 707, "hard")
    audio = timeline_audio(spec)
    assert len(audio) == round(spec.total_duration * AUDIO_RATE)
    assert audio.shape[1] == 2 and audio.dtype == np.float64
    assert np.isfinite(audio).all()
    assert np.max(np.abs(audio)) <= MIX_PEAK_LIMIT
    assert np.max(np.abs(np.mean(audio, axis=0))) < 1e-4
    assert np.max(np.abs(np.diff(audio, axis=0))) < 0.2


def test_diagnostic_wav_is_stereo_48khz(tmp_path) -> None:
    path = write_audio_diagnostic(tmp_path / "audio.wav")
    with wave.open(str(path), "rb") as wav:
        assert wav.getframerate() == AUDIO_RATE
        assert wav.getnchannels() == 2
        assert wav.getsampwidth() == 2
        assert wav.getnframes() == AUDIO_RATE * 5


def test_music_is_opt_in_quick_math_only_and_ducks_under_effects() -> None:
    from dataclasses import replace
    import numpy as np
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.generator import generate_spec
    from puzzly.music import music_enabled, music_track
    spec = generate_spec("quick_math", 7, "hard")
    with_music = replace(spec, metadata={"music": "on"})
    assert not music_enabled(spec) and music_enabled(with_music)
    assert spec.fingerprint() == with_music.fingerprint()  # music never changes duplicate detection
    silent, scored = timeline_audio(spec), timeline_audio(with_music)
    assert silent.shape == scored.shape and not np.allclose(silent, scored)
    assert float(np.abs(scored).max()) <= MIX_PEAK_LIMIT + 1e-9
    assert np.array_equal(music_track(with_music, 48000), music_track(with_music, 48000))  # deterministic
    from puzzly.music import STYLES
    for kind in STYLES:  # every Puzzly for You game has its own character and a valid, peak-safe mix
        item = replace(generate_spec(kind, 3, "hard"), metadata={"music": "on"})
        assert music_enabled(item)
        mixed = timeline_audio(item)
        assert float(np.abs(mixed).max()) <= MIX_PEAK_LIMIT + 1e-9 and not np.allclose(mixed, timeline_audio(replace(item, metadata={})))
    assert len({style["bpm"] for style in STYLES.values()}) >= 6
    legacy = replace(generate_spec("flash_count", 3, "hard"), metadata={"music": "on"})
    assert not music_enabled(legacy)  # light-theme games stay music-free
