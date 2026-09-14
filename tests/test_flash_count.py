from __future__ import annotations

from dataclasses import replace
from collections import Counter
import inspect
import math

import pytest
from PIL import Image

from puzzly.config import (FLASH_APPEARANCE_DURATION, FLASH_HIDE_DURATION, FLASH_INTRO_DURATION,
                           FLASH_REVEAL_DURATION, FLASH_THINKING_DURATION, FLASH_VISIBLE_DURATIONS,
                           OUTRO_DURATION, round_duration)
from puzzly.generator import generate_spec, generate_unique_specs, mixed_types
from puzzly.history import HistoryStore
from puzzly.puzzles.flash_count import (ALIGNMENT_TOLERANCE, COLORS, COUNT_RANGE, COUNT_RANGES, EDGE_GAP,
                                        PLAY_FIELD, SHAPES, errors, generate, layout_errors,
                                        token_size_for_count)
from puzzly.registry import ACTIVE_PUZZLE_TYPES, EXPERIMENTAL_PUZZLE_TYPES
from puzzly.renderer import save_cover
from puzzly.validation import validate_spec
from puzzly.visuals.flash_count import INTRO_POSITIONS, draw_flash_intro, flash_state


@pytest.mark.parametrize("difficulty,volume", (("easy", 300), ("medium", 400), ("hard", 500)))
def test_flash_count_spec_volume_and_layout_quality(difficulty: str, volume: int) -> None:
    low, high = COUNT_RANGES[difficulty]
    for seed in range(volume):
        spec = generate(seed, difficulty)
        validate_spec(spec)
        assert spec == generate(seed, difficulty)
        assert spec.intro_duration == FLASH_INTRO_DURATION and spec.round_count == 4
        identities = {(item.data["shape_id"], item.data["color_id"]) for item in spec.rounds}
        assert len(identities) == 1
        assert next(iter(identities))[0] in SHAPES and next(iter(identities))[1] in COLORS
        counts = [item.data["displayed_count"] for item in spec.rounds]
        assert all(low <= count <= high for count in counts)
        assert all(first != second for first, second in zip(counts, counts[1:]))
        for item in spec.rounds:
            data = item.data
            assert item.answer == data["displayed_count"] == len(data["positions"])
            assert data["visible_seconds"] == FLASH_VISIBLE_DURATIONS[difficulty]
            assert data["thinking_seconds"] == FLASH_THINKING_DURATION
            assert data["token_size"] == token_size_for_count(data["displayed_count"])
            assert not errors(data, item.answer, difficulty) and not layout_errors(data["positions"], data["token_size"])
            radius = data["token_size"] / 2
            assert all(PLAY_FIELD[0] + radius <= x <= PLAY_FIELD[2] - radius and
                       PLAY_FIELD[1] + radius <= y <= PLAY_FIELD[3] - radius for x, y in data["positions"])
            assert all(math.dist(a, b) >= data["token_size"] + EDGE_GAP
                       for index, a in enumerate(data["positions"]) for b in data["positions"][index + 1:])
            pairs = [(a, b) for index, a in enumerate(data["positions"]) for b in data["positions"][index + 1:]]
            assert sum(abs(a[0] - b[0]) < ALIGNMENT_TOLERANCE for a, b in pairs) <= max(1, len(data["positions"]) // 3)
            assert sum(abs(a[1] - b[1]) < ALIGNMENT_TOLERANCE for a, b in pairs) <= max(1, len(data["positions"]) // 3)


def test_flash_fingerprint_tracks_identity_counts_order_and_layout(tmp_path) -> None:
    spec = generate(8128, "hard")
    changed_data = dict(spec.rounds[0].data)
    changed_data["positions"] = [list(point) for point in changed_data["positions"]]
    changed_data["positions"][0][0] += 1
    changed_round = replace(spec.rounds[0], data=changed_data)
    assert spec.fingerprint() != replace(spec, rounds=(changed_round, *spec.rounds[1:])).fingerprint()
    unique = generate_unique_specs(8, "flash_count", "medium", base_seed=44,
                                   history=HistoryStore(tmp_path / "history.sqlite"))
    assert len({item.fingerprint() for item in unique}) == 8


def test_flash_timeline_and_single_identity_intro() -> None:
    assert len(INTRO_POSITIONS) == 6 and len(set(INTRO_POSITIONS)) == 6
    assert '"How many?"' in inspect.getsource(draw_flash_intro)
    assert FLASH_VISIBLE_DURATIONS == {"easy": 1.20, "medium": 0.90, "hard": 0.65}
    for difficulty, visible in FLASH_VISIBLE_DURATIONS.items():
        assert flash_state(.1, visible) == "appearance"
        assert flash_state(FLASH_APPEARANCE_DURATION + visible / 2, visible) == "visible"
        assert flash_state(FLASH_APPEARANCE_DURATION + visible + .1, visible) == "hiding"
        hidden = FLASH_APPEARANCE_DURATION + visible + FLASH_HIDE_DURATION
        assert flash_state(hidden + 1, visible) == "thinking"
        assert flash_state(hidden + FLASH_THINKING_DURATION + .1, visible) == "revealing"
        assert flash_state(hidden + FLASH_THINKING_DURATION + FLASH_REVEAL_DURATION + .1, visible) == "solved"
        spec = generate(55, difficulty)
        assert spec.total_duration == pytest.approx(FLASH_INTRO_DURATION + 4 * round_duration("flash_count", difficulty) + OUTRO_DURATION)


def test_shared_count_pool_is_uniform_and_difficulty_unbiased() -> None:
    distributions: dict[str, Counter[int]] = {}
    means: dict[str, float] = {}
    for difficulty in FLASH_VISIBLE_DURATIONS:
        counts = [item.answer for seed in range(600) for item in generate(20_000 + seed, difficulty).rounds]
        distribution = Counter(counts)
        distributions[difficulty] = distribution
        expected = len(counts) / len(range(COUNT_RANGE[0], COUNT_RANGE[1] + 1))
        assert set(distribution) == set(range(5, 11))
        assert all(abs(frequency - expected) <= expected * .20 for frequency in distribution.values())
        means[difficulty] = sum(counts) / len(counts)
    assert max(means.values()) - min(means.values()) < .20


def test_nonconsecutive_count_reuse_is_allowed() -> None:
    examples = [[item.answer for item in generate(seed, "medium").rounds] for seed in range(100)]
    assert any(counts[0] == counts[2] or counts[1] == counts[3] for counts in examples)
    assert all(all(first != second for first, second in zip(counts, counts[1:])) for counts in examples)


def test_flash_cover_is_standard_full_resolution_jpeg(tmp_path) -> None:
    path = tmp_path / "flash.jpg"
    save_cover(generate_spec("flash_count", 930, "hard"), path)
    with Image.open(path) as image:
        assert image.format == "JPEG" and image.size == (1080, 1920)
        image.verify()


def test_line_follow_is_experimental_not_active(tmp_path) -> None:
    assert "line_follow" in EXPERIMENTAL_PUZZLE_TYPES
    assert "line_follow" not in ACTIVE_PUZZLE_TYPES
    assert "flash_count" in ACTIVE_PUZZLE_TYPES
    assert "line_follow" not in set(mixed_types(600, __import__("random").Random(9)))
    with pytest.raises(ValueError, match="not active"):
        generate_unique_specs(1, "line_follow", history=HistoryStore(tmp_path / "history.sqlite"))
    assert generate_spec("line_follow", 8).puzzle_type == "line_follow"
