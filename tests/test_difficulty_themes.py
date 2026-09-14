from puzzly.config import DIFFICULTY_THEMES, palette_for
from puzzly.puzzles.memory_challenge import generate
from puzzly.validation import validation_errors


def test_difficulty_backgrounds_are_centralized_distinct_and_light() -> None:
    assert set(DIFFICULTY_THEMES) == {"easy", "medium", "hard"}
    assert len({palette_for(level)["background"] for level in DIFFICULTY_THEMES}) == 3
    for level in DIFFICULTY_THEMES:
        palette = palette_for(level, 2)
        for key in ("background", "background_2"):
            rgb = tuple(int(palette[key][index:index + 2], 16) for index in (1, 3, 5))
            assert min(rgb) >= 216
        assert palette["surface"].startswith("#")


def test_memory_tokens_remain_valid_against_all_difficulty_backgrounds() -> None:
    for difficulty in DIFFICULTY_THEMES:
        for seed in range(30):
            assert validation_errors(generate(seed, difficulty)) == []
