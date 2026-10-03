"""The shared end card: score ring, YouTube and Instagram accounts, FOLLOW FOR MORE, 2 s longer than before."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from puzzly.config import BOUNCE_CTA_DURATION, PUZZLE_FIT_OUTRO_DURATION, SOCIAL_HANDLES
from puzzly.generator import generate_spec
from puzzly.validation import validation_errors
from puzzly.visuals import end_card


def test_the_end_card_lasts_two_seconds_longer_and_every_game_uses_it() -> None:
    assert PUZZLE_FIT_OUTRO_DURATION == 3.6 and BOUNCE_CTA_DURATION == 3.7
    for kind in ("quick_math", "puzzle_fit", "find_the_exit", "cube_count", "memory_challenge", "flash_count", "lucky_pick",
                 "line_follow", "matchstick", "cup_shuffle", "shade_spot", "bounce_arena"):
        spec = generate_spec(kind, 3, "hard")
        assert spec.outro_duration == (BOUNCE_CTA_DURATION if kind == "bounce_arena" else PUZZLE_FIT_OUTRO_DURATION), kind
        assert validation_errors(spec) == []


def test_older_videos_with_the_short_end_card_still_validate() -> None:
    spec = generate_spec("cube_count", 3, "hard")
    assert validation_errors(replace(spec, outro_duration=1.6)) == []
    bounce = generate_spec("bounce_arena", 3)
    old = replace(bounce, rounds=(replace(bounce.rounds[0], data={**bounce.rounds[0].data, "cta_duration": 1.7}),), outro_duration=1.7)
    assert validation_errors(old) == []


def test_the_handles_and_icons() -> None:
    assert dict(SOCIAL_HANDLES) == {"youtube": "@puzzlyforyou", "instagram": "@puzzlyforyou"}
    youtube, instagram = end_card.youtube_icon(80), end_card.instagram_icon(80)
    assert youtube.size[1] == 80 and youtube.size[0] > 100 and instagram.size == (80, 80)
    red = np.asarray(youtube, dtype=int)
    centre = red[40, 8]  # the red body left of the play triangle
    assert centre[0] > 180 and centre[1] < 90 and centre[3] == 255
    rgba = np.asarray(instagram, dtype=int)
    assert rgba[2, 2, 3] < 255 and rgba[40, 40, 3] == 255  # rounded corners
    assert len({tuple(rgba[y, x, :3]) for y, x in ((70, 8), (40, 40), (8, 70))}) == 3  # a real gradient


def test_the_card_builds_up_over_the_whole_time() -> None:
    spec = generate_spec("cup_shuffle", 5, "hard")
    size = (270, 480)
    frames = {t: np.asarray(end_card.draw_end_card(spec, t, size), dtype=int) for t in (.2, .7, 1.2, 1.8, 2.3, 3.4)}
    assert all(frame.shape == (480, 270, 3) for frame in frames.values())
    panel = (slice(190, 285), slice(25, 245))  # the social panel area
    button = (slice(300, 350), slice(35, 235))  # the FOLLOW FOR MORE button area
    assert np.abs(frames[1.2][panel] - frames[.2][panel]).mean() > 4  # the rows have popped in
    assert np.abs(frames[1.8][button] - frames[1.2][button]).mean() > 4  # the button has risen
    assert np.abs(frames[3.4] - frames[2.3]).mean() > .3  # it keeps moving to the very end (confetti, light, shine)


def test_it_is_the_card_every_game_draws() -> None:
    from puzzly.renderer import render_frame
    spec = generate_spec("matchstick", 5, "hard")
    last = render_frame(spec, spec.total_duration - .4, (270, 480))
    direct = end_card.draw_end_card(spec, spec.outro_duration - .4, (270, 480)).convert("RGB")
    assert np.abs(np.asarray(last, dtype=int) - np.asarray(direct, dtype=int)).mean() < 1


def test_the_end_card_sounds_are_in_every_mix() -> None:
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    spec = generate_spec("cube_count", 5, "hard")
    audio = timeline_audio(spec)
    tail = audio[round((spec.total_duration - spec.outro_duration) * 48000):]
    assert np.abs(tail[round(1.95 * 48000):round(2.6 * 48000)]).max() > .02  # the tap and its ding
    assert float(np.abs(audio).max()) <= MIX_PEAK_LIMIT + 1e-9


def test_ready_screen_for_the_flash_type_games() -> None:
    from puzzly.config import READY_GAMES, READY_INTRO_DURATION
    from puzzly.renderer import render_frame
    from puzzly.visuals.ready import HOOK_SECONDS, has_ready, hook_end
    assert READY_GAMES == ("cube_count", "cup_shuffle", "memory_challenge", "flash_count", "shade_spot") and READY_INTRO_DURATION == 4.0
    for kind in READY_GAMES:
        spec = generate_spec(kind, 3, "hard")
        assert spec.intro_duration == 4.0 and has_ready(spec) and hook_end(spec) == HOOK_SECONDS
        assert validation_errors(spec) == []
        numbers = [np.asarray(render_frame(spec, HOOK_SECONDS + second + .5, (270, 480)), dtype=int) for second in range(3)]
        assert all(np.abs(numbers[0] - other).mean() > .3 for other in numbers[1:])  # 3, 2, 1 differ
        assert np.array_equal(np.asarray(render_frame(spec, .5, (270, 480))), np.asarray(render_frame(spec, .5, (270, 480))))
    older = replace(generate_spec("cube_count", 3, "hard"), intro_duration=1.0)  # made before the READY screen
    assert not has_ready(older) and hook_end(older) == 1.0 and validation_errors(older) == []


def test_ready_screen_sounds_and_the_games_that_never_get_one() -> None:
    from puzzly.audio import timeline_audio
    from puzzly.visuals.ready import has_ready
    spec = generate_spec("cup_shuffle", 5, "hard")
    audio = timeline_audio(spec)
    for second in (1.0, 2.0, 3.0):  # a tick on every number
        assert np.abs(audio[round(second * 48000):round((second + .12) * 48000)]).max() > .02
    for kind in ("quick_math", "puzzle_fit", "matchstick", "find_the_exit"):
        assert not has_ready(generate_spec(kind, 3, "hard")), kind


def test_the_end_card_shows_the_round_profile_photo_next_to_the_brand_name() -> None:
    from PIL import Image
    from puzzly import branding
    disc = branding._profile_disc(120)
    assert branding.PROFILE_PHOTO.exists() and disc is not None and disc.size == (120, 120)
    alpha = disc.getchannel("A")
    assert alpha.getpixel((60, 60)) == 255 and alpha.getpixel((2, 2)) == 0 and alpha.getpixel((117, 117)) == 0  # round, corners clear
    canvas = Image.new("RGB", (300, 200), (10, 10, 10))
    branding.draw_profile_mark(canvas, (150, 100), 120)
    assert canvas.getpixel((150, 100)) != (10, 10, 10) and canvas.getpixel((92, 42)) == (10, 10, 10)
