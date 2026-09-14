from collections import Counter
import pytest

from puzzly.config import DEFAULT_ROUNDS, INTRO_DURATION, MEMORY_INTRO_DURATION, OUTRO_DURATION, round_duration, thinking_duration, THINKING_DURATION
from puzzly.generator import generate_spec, generate_unique_specs, mixed_types
from puzzly.history import HistoryStore
from puzzly.registry import MIXED_PUZZLE_TYPES


def test_active_mixed_distribution_and_unique_fingerprints(tmp_path) -> None:
    specs = generate_unique_specs(35, "mixed", base_seed=12345, history=HistoryStore(tmp_path / "history.sqlite"))
    assert Counter(spec.puzzle_type for spec in specs) == {kind: 5 for kind in MIXED_PUZZLE_TYPES}
    assert len({spec.fingerprint() for spec in specs}) == len(specs)


def test_auto_defaults_and_explicit_round_counts() -> None:
    for puzzle_type, default in DEFAULT_ROUNDS.items():
        assert default == (1 if puzzle_type in ("memory_challenge", "lucky_pick", "hidden_motion_hunt") else (4 if puzzle_type in ("find_the_exit", "line_follow", "flash_count") else 5))
        if puzzle_type == "hidden_motion_hunt":
            continue
        assert generate_spec(puzzle_type, 1).round_count == default
        if puzzle_type in ("memory_challenge", "lucky_pick"):
            continue
        for requested in (3, 4, 5):
            spec = generate_spec(puzzle_type, 1, challenges=requested)
            assert spec.round_count == requested
            from puzzly.config import FLASH_INTRO_DURATION
            intro = FLASH_INTRO_DURATION if puzzle_type == "flash_count" else INTRO_DURATION
            assert spec.total_duration == pytest.approx(intro + requested * round_duration(puzzle_type, "easy") + OUTRO_DURATION)
    assert THINKING_DURATION == 4.0


def test_difficulty_timing_and_dynamic_durations() -> None:
    for kind in DEFAULT_ROUNDS:
        if kind == "hidden_motion_hunt":
            continue
        for difficulty, seconds in (("easy", 5), ("medium", 6), ("hard", 7)):
            expected = 5 if kind == "lucky_pick" else (3 if kind in ("memory_challenge", "flash_count") else (seconds if kind in ("find_the_exit", "line_follow") else (5 if kind == "puzzle_fit" and difficulty == "hard" else 4)))
            assert thinking_duration(kind, difficulty) == expected
            spec = generate_spec(kind, 93, difficulty)
            from puzzly.config import FLASH_INTRO_DURATION, LUCKY_INTRO_DURATION
            intro = (MEMORY_INTRO_DURATION if kind == "memory_challenge" else
                     (FLASH_INTRO_DURATION if kind == "flash_count" else
                      (LUCKY_INTRO_DURATION if kind == "lucky_pick" else INTRO_DURATION)))
            expected_duration = (intro + spec.rounds[0].data["timeline_duration"] + OUTRO_DURATION
                                 if kind == "lucky_pick" else
                                 intro + DEFAULT_ROUNDS[kind] * round_duration(kind, difficulty) + OUTRO_DURATION)
            assert spec.total_duration == pytest.approx(round(expected_duration, 3))


def test_seed_repeatability_and_history(tmp_path) -> None:
    first = generate_unique_specs(8, base_seed=8080, history=HistoryStore(tmp_path / "a.sqlite"), challenges=5)
    second = generate_unique_specs(8, base_seed=8080, history=HistoryStore(tmp_path / "b.sqlite"), challenges=5)
    assert first == second
    history = HistoryStore(tmp_path / "history.sqlite")
    for spec in first:
        history.commit_success(puzzle_type=spec.puzzle_type, difficulty=spec.difficulty, seed=spec.seed,
                               fingerprint=spec.fingerprint(), finalize_files=lambda sequence: (f"{sequence}.mp4", f"{sequence}.jpg"))
    third = generate_unique_specs(8, base_seed=8080, history=history, challenges=5)
    assert {spec.fingerprint() for spec in first}.isdisjoint(spec.fingerprint() for spec in third)


def test_single_video_mixed_mode_can_select_every_type() -> None:
    import random
    assert {mixed_types(1, random.Random(seed))[0] for seed in range(50)} == set(MIXED_PUZZLE_TYPES)
