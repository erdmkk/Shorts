"""Creator-chosen background tone and object palette."""
from __future__ import annotations

import colorsys

from puzzly.config import DARK_THEMES, dark_theme_for
from puzzly.generator import generate_spec, generate_unique_specs
from puzzly.history import HistoryStore
from puzzly.models import VideoSpec
from puzzly.palette import BACKGROUND_LABELS, PALETTE_LABELS, PALETTES, background_for, palette_for, recolor
from puzzly.puzzles.lucky_pick import COLORS


def _hue(value: str) -> float:
    return colorsys.rgb_to_hsv(*(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5)))[0]


def test_every_tone_and_palette_is_offered() -> None:
    assert set(BACKGROUND_LABELS) == {"random", *DARK_THEMES}
    assert set(PALETTE_LABELS) == set(PALETTES) == {"classic", "neon", "pastel", "jewel"}


def test_palettes_keep_hue_so_colour_names_stay_true() -> None:
    for palette in PALETTES:
        for value in COLORS.values():
            shifted = recolor(value, palette)
            difference = abs(_hue(shifted) - _hue(value))
            assert min(difference, 1 - difference) < .02, (palette, value, shifted)
        # All seven Lucky Pick colours stay different from each other.
        assert len({recolor(value, palette) for value in COLORS.values()}) == len(COLORS)
    assert recolor("#FF5A5F", "classic") == "#FF5A5F" and recolor("#FF5A5F", None) == "#FF5A5F"


def test_choices_live_in_metadata_outside_the_fingerprint() -> None:
    plain = generate_spec("lucky_pick", 44)
    chosen = generate_spec("lucky_pick", 44, background="ember", palette="neon")
    assert chosen.metadata == {"background": "ember", "palette": "neon"} and plain.metadata == {}
    assert chosen.fingerprint() == plain.fingerprint()  # colours never change duplicate detection
    assert background_for(chosen) == "ember" and palette_for(chosen) == "neon"
    assert background_for(plain) == dark_theme_for("lucky_pick", 44) and palette_for(plain) is None
    # "random" and "classic" are the defaults and are not stored.
    assert generate_spec("lucky_pick", 44, background="random", palette="classic").metadata == {}
    # A saved spec keeps the choices, so a Final re-render matches the Draft.
    assert VideoSpec.from_json(chosen.to_json()).metadata == chosen.metadata


def test_memory_keeps_its_own_colours_and_cubes_avoid_the_chosen_background(tmp_path) -> None:
    memory = generate_spec("memory_challenge", 5, "hard", background="ocean", palette="pastel")
    assert background_for(memory) == "ocean" and palette_for(memory) is None
    for tone in DARK_THEMES:
        from puzzly.config import CUBE_COLORS, THEME_CLASHING_CUBES
        spec = generate_spec("cube_count", 9, "hard", background=tone)
        assert not {item.data["color_id"] for item in spec.rounds} & set(THEME_CLASHING_CUBES[tone])
    specs = generate_unique_specs(2, "bounce_arena", base_seed=3, history=HistoryStore(tmp_path / "h.sqlite"),
                                  background="plum", palette="jewel")
    assert all(spec.metadata == {"background": "plum", "palette": "jewel"} for spec in specs)


def test_frames_and_covers_render_in_the_chosen_colours() -> None:
    from puzzly.covers import render_game_cover
    from puzzly.renderer import render_frame
    spec = generate_spec("lucky_pick", 12, background="crimson", palette="pastel")
    assert render_frame(spec, 3.0, (270, 480)).size == (270, 480)
    assert render_game_cover(spec).size == (1080, 1920)
