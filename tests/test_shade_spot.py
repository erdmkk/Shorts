"""Shade Spot: two grids of nearly the same colours, one tile differs."""
from collections import Counter
from dataclasses import replace

import numpy as np

from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
from puzzly.config import SHADE_LEVELS, SHADE_TIERS, shade_average_round
from puzzly.generator import generate_spec
from puzzly.metadata import youtube_metadata
from puzzly.puzzles.shade_spot import DELTA_RANGE, distance, generate, label
from puzzly.registry import ACTIVE_PUZZLE_TYPES, MIXED_PUZZLE_TYPES, PAUSED_PUZZLE_TYPES, SUPPORTED_PUZZLE_TYPES
from puzzly.validation import round_errors, validation_errors


def test_every_video_is_valid_and_the_levels_get_harder() -> None:
    for seed in range(60):
        for count in (3, 4, 5):
            spec = generate(seed, round_count=count)
            assert validation_errors(spec) == [], (seed, count)
            assert spec.difficulty == "hard" and spec.intro_duration == 4.0 and spec.outro_duration == 3.6
            assert [item.data["tier"] for item in spec.rounds] == list(SHADE_TIERS[count])
            deltas = [item.data["delta"] for item in spec.rounds]
            grids = [item.data["grid"] for item in spec.rounds]
            assert deltas == sorted(deltas, reverse=True) and grids == sorted(grids)  # smaller differences, bigger grids
            assert spec.round_duration == shade_average_round([item.data for item in spec.rounds])
            assert all(a.answer != b.answer for a, b in zip(spec.rounds, spec.rounds[1:]))


def test_exactly_one_tile_differs_by_the_level_difference() -> None:
    for seed in range(40):
        for item in generate(seed).rounds:
            data = item.data
            tiles, odd = data["tiles"], data["odd"]
            assert len(tiles) == data["grid"] ** 2 and len(set(tiles)) == len(tiles)  # every tile its own colour
            assert item.answer == label(odd, data["grid"])
            assert abs(distance(tiles[odd], data["odd_color"]) - data["delta"]) <= data["delta"] * .2  # as far as the level says
            assert data["odd_color"] != tiles[odd]
            # It stays inside its palette's range, so it does not stand out within its own grid.
            others = tiles[:odd] + tiles[odd + 1:]
            assert min(distance(data["odd_color"], other) for other in others) <= .12


def test_answers_are_spread_over_the_grid() -> None:
    spots = Counter(item.data["odd"] for seed in range(200) for item in generate(seed, round_count=3).rounds[:1])
    assert len(spots) == 9 and max(spots.values()) < 200 * .3  # the first level's nine spots are all used
    assert label(0, 3) == "A1" and label(4, 3) == "B2" and label(8, 5) == "D2" and label(24, 5) == "E5"


def test_generation_is_deterministic_and_registered() -> None:
    assert generate(7) == generate(7) and generate(7) != generate(8)
    assert generate_spec("shade_spot", 5, "easy") == generate_spec("shade_spot", 5, "hard")  # always Hard
    assert "shade_spot" not in ACTIVE_PUZZLE_TYPES and "shade_spot" not in MIXED_PUZZLE_TYPES  # paused: it plays inside Mind Mix
    assert "shade_spot" in PAUSED_PUZZLE_TYPES and "shade_spot" in SUPPORTED_PUZZLE_TYPES
    meta = youtube_metadata(generate(9))
    assert "#shorts" in meta["youtube_title"] and "spot the difference" in meta["youtube_tags"]


def test_wrong_rounds_are_rejected() -> None:
    item = generate(4).rounds[1]
    assert round_errors(replace(item, answer="E5"), "hard")
    assert round_errors(replace(item, data={**item.data, "odd_color": item.data["tiles"][item.data["odd"]]}), "hard")  # no difference
    far = {**item.data, "odd_color": "#FFFFFF"}
    assert round_errors(replace(item, data=far), "hard")  # not the stored difference
    assert round_errors(replace(item, data={**item.data, "tiles": item.data["tiles"][:-1]}), "hard")
    twin = list(item.data["tiles"])
    twin[1] = twin[0]
    assert round_errors(replace(item, data={**item.data, "tiles": twin}), "hard")  # two identical tiles
    assert round_errors(replace(item, data={**item.data, "delta": DELTA_RANGE[1] + .1}), "hard")


def test_retuning_the_levels_never_invalidates_a_made_video(monkeypatch) -> None:
    import puzzly.config as config
    spec = generate(6)
    monkeypatch.setattr(config, "SHADE_LEVELS", ({"grid": 3, "delta": .5, "thinking": 99.0},) * 4)
    assert validation_errors(spec) == []  # it is judged by what it stored


def test_frames_show_both_grids_then_reveal_the_odd_tile_and_the_cover_renders() -> None:
    from puzzly.renderer import render_cover, render_frame
    from puzzly.covers import has_template
    from puzzly.visuals.shade_spot import phases, schedule
    spec = generate_spec("shade_spot", 3, "hard")
    assert has_template(spec) and render_cover(spec).size == (1080, 1920)
    (start, duration), item = schedule(spec)[0], spec.rounds[0]
    times = phases(item)
    assert duration == times["duration"] == SHADE_LEVELS[0]["thinking"] + .5 + 2.0 + .8
    thinking = np.asarray(render_frame(spec, start + 2.0, (540, 960))).astype(int)
    reveal = np.asarray(render_frame(spec, start + times["answer"] + 1.0, (540, 960))).astype(int)
    grids = (slice(210, 790), slice(130, 410))
    assert np.abs(thinking[grids] - reveal[grids]).mean() > 8  # the other tiles dim, the odd pair stands out
    hook = np.asarray(render_frame(spec, .5, (540, 960)))
    assert hook.shape == (960, 540, 3)
    assert np.asarray(render_frame(spec, spec.total_duration - 1.0, (540, 960))).shape == (960, 540, 3)  # the end card


def test_the_tiles_are_drawn_in_their_exact_colours() -> None:
    from puzzly.renderer import render_frame
    from puzzly.visuals.shade_spot import phases, schedule, tile_box
    spec = generate_spec("shade_spot", 2, "hard", palette="neon")  # a creator palette must never recolour the puzzle
    start, _ = schedule(spec)[0]
    frame = render_frame(spec, start + 2.0, (1080, 1920)).convert("RGB")
    data = spec.rounds[0].data
    for card in (0, 1):
        for index, expected in enumerate(data["tiles"] if card == 0 else [*data["tiles"][:data["odd"]], data["odd_color"], *data["tiles"][data["odd"] + 1:]]):
            x1, y1, x2, y2 = tile_box(card, data["grid"], index)
            pixel = frame.getpixel((round((x1 + x2) / 2), round((y1 + y2) / 2)))
            assert max(abs(a - int(expected[1 + 2 * i:3 + 2 * i], 16)) for i, a in enumerate(pixel)) <= 2, (card, index)


def test_audio_and_music_cover_the_video() -> None:
    from puzzly.music import music_enabled
    spec = replace(generate_spec("shade_spot", 4, "hard"), metadata={"music": "on"})
    assert music_enabled(spec)
    audio = timeline_audio(spec)
    assert audio.shape[0] == round(spec.total_duration * 48000) and 0.05 < np.abs(audio).max() <= MIX_PEAK_LIMIT + 1e-9


def test_the_portal_no_longer_offers_shade_spot_on_its_own() -> None:
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file("app.py").run()
    assert "Shade Spot" not in app.selectbox[0].options and "Mind Mix" in app.selectbox[0].options
    from puzzly.generator import generate_unique_specs
    import pytest
    with pytest.raises(ValueError):
        generate_unique_specs(1, "shade_spot")  # not producible as its own video; older records still render


def test_a_ready_screen_prepares_the_viewer_before_the_first_board() -> None:
    from puzzly.config import READY_GAMES, READY_INTRO_DURATION
    from puzzly.renderer import render_frame
    from puzzly.visuals.ready import HOOK_SECONDS, has_ready, ready_text
    spec = generate(5)
    assert "shade_spot" in READY_GAMES and spec.intro_duration == READY_INTRO_DURATION == 4.0 and has_ready(spec)
    assert ready_text(spec) == "You will find the odd tile." and validation_errors(spec) == []
    hook = np.asarray(render_frame(spec, .5, (540, 960))).astype(int)
    ready = np.asarray(render_frame(spec, HOOK_SECONDS + 1.0, (540, 960))).astype(int)
    first_board = np.asarray(render_frame(spec, spec.intro_duration + 1.5, (540, 960))).astype(int)
    assert np.abs(hook - ready).mean() > 3 and np.abs(ready - first_board).mean() > 3
    # The videos made before it keep their short hook and no ready screen.
    old = replace(spec, intro_duration=1.0)
    assert not has_ready(old) and validation_errors(old) == []


def test_the_cover_card_is_large_and_in_the_standard_template() -> None:
    from puzzly.renderer import render_cover
    from puzzly.visuals.shade_spot import COVER_SIZE, cover_card
    spec = generate(5)
    card = cover_card(spec)
    assert card.size == (COVER_SIZE[0] * 2, COVER_SIZE[1] * 2) and card.width > card.height  # two grids side by side
    array = np.asarray(card.convert("RGB")).astype(int)
    assert array.std() > 25  # real colour content, not a dull panel
    assert render_cover(spec).size == (1080, 1920)
