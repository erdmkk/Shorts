from puzzly.config import READY_GAMES, READY_INTRO_DURATION
from collections import Counter
import pytest

from puzzly.config import LINE_THINKING, DEFAULT_ROUNDS, INTRO_DURATION, MEMORY_INTRO_DURATION, OUTRO_DURATION, PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION, round_duration, thinking_duration, THINKING_DURATION
from puzzly.generator import generate_spec, generate_unique_specs, mixed_types
from puzzly.history import HistoryStore
from puzzly.registry import MIXED_PUZZLE_TYPES


def test_active_mixed_distribution_and_unique_fingerprints(tmp_path) -> None:
    specs = generate_unique_specs(5 * len(MIXED_PUZZLE_TYPES), "mixed", base_seed=12345, history=HistoryStore(tmp_path / "history.sqlite"))
    assert Counter(spec.puzzle_type for spec in specs) == {kind: 5 for kind in MIXED_PUZZLE_TYPES}
    assert len({spec.fingerprint() for spec in specs}) == len(specs)


def test_auto_defaults_and_explicit_round_counts() -> None:
    for puzzle_type, default in DEFAULT_ROUNDS.items():
        assert default == (1 if puzzle_type in ("memory_challenge", "lucky_pick", "hidden_motion_hunt", "bounce_arena", "chess_mate", "puzzle_fit") else (4 if puzzle_type in ("find_the_exit", "flash_count", "cube_count", "shade_spot", "laser_maze") else (3 if puzzle_type in ("quick_math", "matchstick", "cup_shuffle", "mind_mix") else (1 if puzzle_type == "puzzle_fit" else 5))))
        if puzzle_type in ("hidden_motion_hunt", "bounce_arena", "chess_mate", "matchstick", "puzzle_fit", "cup_shuffle", "memory_challenge", "mind_mix"):  # fixed formats: see their own tests
            continue
        assert generate_spec(puzzle_type, 1).round_count == default
        if puzzle_type in ("memory_challenge", "lucky_pick"):
            continue
        for requested in (3, 4, 5):
            spec = generate_spec(puzzle_type, 1, challenges=requested)
            assert spec.round_count == requested
            intro = INTRO_DURATION
            outro = OUTRO_DURATION
            if puzzle_type in ("puzzle_fit", "cube_count", "flash_count", "quick_math"):
                intro, outro = (READY_INTRO_DURATION if puzzle_type in READY_GAMES else PUZZLE_FIT_INTRO_DURATION), PUZZLE_FIT_OUTRO_DURATION
            if puzzle_type in ("quick_math", "line_follow", "cube_count", "shade_spot", "laser_maze"):  # levels last different times; see their own tests
                continue
            assert spec.total_duration == pytest.approx(intro + requested * round_duration(puzzle_type, "easy") + outro)
    assert THINKING_DURATION == 4.0


def test_difficulty_timing_and_dynamic_durations() -> None:
    for kind in DEFAULT_ROUNDS:
        if kind in ("hidden_motion_hunt", "bounce_arena", "chess_mate", "matchstick", "puzzle_fit", "cup_shuffle", "shade_spot", "mind_mix", "laser_maze"):
            continue
        for difficulty, seconds in (("easy", 5), ("medium", 6), ("hard", 7)):
            expected = {"easy": 10, "medium": 9, "hard": 8}[difficulty] if kind == "quick_math" else 5 if kind == "lucky_pick" else LINE_THINKING[0] if kind == "line_follow" else (3 if kind in ("memory_challenge", "flash_count", "cube_count") else ((8 if kind == "find_the_exit" and difficulty == "hard" else seconds) if kind in ("find_the_exit", "line_follow") else (5 if kind == "puzzle_fit" else 4)))
            assert thinking_duration(kind, difficulty) == expected
            spec = generate_spec(kind, 93, difficulty)
            intro = (MEMORY_INTRO_DURATION if kind == "memory_challenge" else
                     (PUZZLE_FIT_INTRO_DURATION if kind in ("lucky_pick", "puzzle_fit") else INTRO_DURATION))
            adult_look = kind in ("puzzle_fit", "cube_count", "flash_count", "memory_challenge", "lucky_pick", "quick_math", "line_follow") or (kind == "find_the_exit" and difficulty == "hard")
            if adult_look:
                intro = (PUZZLE_FIT_INTRO_DURATION + 3.0 if kind in ("flash_count", "cube_count", "memory_challenge")
                         else PUZZLE_FIT_INTRO_DURATION)  # hook, plus the 3 s READY screen for the flash-type games
            outro = PUZZLE_FIT_OUTRO_DURATION if adult_look else OUTRO_DURATION
            expected_duration = (intro + spec.rounds[0].data["timeline_duration"] + outro
                                 if kind == "lucky_pick" else
                                 intro + DEFAULT_ROUNDS[kind] * round_duration(kind, difficulty) + outro)
            if kind == "cube_count":  # every level is its own format with its own length
                from puzzly.config import cube_round
                expected_duration = intro + sum(cube_round(item.data) for item in spec.rounds) + outro
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
