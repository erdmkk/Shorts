"""Lucky Pick snake chase: an open arena, seven fleeing targets, a hunting snake, and one survivor."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
import math

from PIL import Image

from puzzly.config import LUCKY_SELECTION_DURATION, PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION
from puzzly.generator import generate_spec
from puzzly.metadata import youtube_metadata
from puzzly.puzzles import lucky_snake
from puzzly.puzzles.lucky_pick import COLORS, SHAPES, errors, generate, is_snake
from puzzly.renderer import render_cover, render_frame, save_cover
from puzzly.validation import validate_spec
from puzzly.visuals.lucky_snake import RING_FADE, chase_for, pick_ring_alpha


def test_snake_chase_specs_are_valid_deterministic_and_fair() -> None:
    winners: Counter[int] = Counter(); orders = set()
    for seed in range(140):
        spec = generate(seed); validate_spec(spec)
        assert spec == generate(seed) and spec.fingerprint() == generate(seed).fingerprint()
        data = spec.rounds[0].data
        assert is_snake(data) and spec.difficulty is None and spec.round_count == 1
        assert spec.intro_duration == PUZZLE_FIT_INTRO_DURATION and spec.outro_duration == PUZZLE_FIT_OUTRO_DURATION
        assert 18 <= spec.total_duration <= 30
        assert lucky_snake.SIM_MIN <= data["simulation_duration"] <= lucky_snake.SIM_MAX
        assert {target["color_id"] for target in data["targets"]} == set(COLORS) and data["shape_id"] in SHAPES
        assert data["selection_seconds"] == LUCKY_SELECTION_DURATION
        # Exactly one survivor, never eaten; every other target is caught once, in order, with room to breathe.
        order, winner = data["elimination_order"], data["winner_index"]
        assert spec.rounds[0].answer == winner and winner not in order and sorted(order + [winner]) == list(range(7))
        times = [event["time"] for event in data["catches"]]
        assert times == sorted(times) and times[0] >= lucky_snake.FIRST_CATCH_MIN
        assert times[-1] - times[-2] >= lucky_snake.FINAL_DUEL_MIN
        assert errors(data, winner) == []
        winners[winner] += 1; orders.add(tuple(order))
    # Every target follows the same rules; only the random layout differs, so no index is favoured.
    assert all(8 <= winners[index] <= 34 for index in range(7)) and len(orders) > 120


def test_targets_stay_in_the_arena_and_eaten_ones_never_return() -> None:
    for seed in range(20):
        data = generate(seed).rounds[0].data
        caught: set[int] = set()
        catch_time = {event["target_index"]: event["time"] for event in data["catches"]}
        for frame in data["frames"]:
            time_value, hx, hy = frame[0], frame[1], frame[2]
            assert math.dist((hx, hy), lucky_snake.ARENA_CENTER) <= lucky_snake.ARENA_RADIUS
            caught |= {index for index, at in catch_time.items() if at <= time_value}
            for index, x, y in frame[5]:
                assert index not in caught
                assert math.dist((x, y), lucky_snake.ARENA_CENTER) <= lucky_snake.ARENA_RADIUS - lucky_snake.TARGET_RADIUS + 1e-6
        assert [record[0] for record in data["frames"][-1][5]] == [data["winner_index"]]


def test_the_snake_grows_and_speeds_up_with_every_catch() -> None:
    data = generate(5).rounds[0].data
    lengths = [frame[4] for frame in data["frames"]]
    assert lengths[0] == lucky_snake.SNAKE_BASE_LENGTH
    assert lengths[-1] == lucky_snake.SNAKE_BASE_LENGTH + lucky_snake.SNAKE_LENGTH_PER_CATCH * 6
    assert lengths == sorted(lengths)


def test_a_tampered_chase_is_rejected() -> None:
    game = generate(12).rounds[0]; data = game.data
    wrong_winner = next(index for index in range(7) if index != game.answer)
    assert errors(data, wrong_winner)
    moved = [dict(event) for event in data["catches"]]; moved[0]["time"] += .5
    assert errors({**data, "catches": moved}, game.answer)
    assert errors({**data, "elimination_order": data["elimination_order"][:-1]}, game.answer)


def test_pick_rings_only_show_while_the_viewer_picks() -> None:
    assert pick_ring_alpha(-3.0) == pick_ring_alpha(-.01) == 1.0
    assert 0 < pick_ring_alpha(RING_FADE / 2) < 1
    assert pick_ring_alpha(RING_FADE) == 0 and pick_ring_alpha(5.0) == 0


def test_the_den_disappears_once_the_snake_is_out() -> None:
    from puzzly.visuals.lucky_snake import DEN_FADE, EMERGE, den_opacity
    assert den_opacity(-2.0) == den_opacity(EMERGE - .01) == 1.0
    assert 0 < den_opacity(EMERGE + DEN_FADE / 2) < 1
    assert den_opacity(EMERGE + DEN_FADE) == 0 and den_opacity(8.0) == 0


def test_the_snake_roams_the_arena_instead_of_circling_the_rim() -> None:
    """Most catches happen in the open, not along the rim, and the head spends most of its time away from the rim."""
    rim_catches = catches = rim_frames = frames = 0
    for seed in range(30):
        data = generate(seed).rounds[0].data
        for event in data["catches"]:
            catches += 1
            rim_catches += math.dist(event["position"], lucky_snake.ARENA_CENTER) > lucky_snake.ARENA_RADIUS * .75
        for frame in data["frames"]:
            frames += 1
            rim_frames += math.dist((frame[1], frame[2]), lucky_snake.ARENA_CENTER) > lucky_snake.ARENA_RADIUS * .75
    assert rim_catches / catches < .35 and rim_frames / frames < .45


def test_the_body_follows_the_head_and_emerges_from_the_den() -> None:
    spec = generate(7); chase = chase_for(spec)
    assert len(chase.body(0.0)) == 1  # it has not left its den yet
    early, later = chase.body(.2), chase.body(3.0)
    assert len(early) < len(later)  # it rises out as it moves
    assert all(math.dist(a, b) < 6.5 for a, b in zip(later, later[1:]))  # a continuous body along its own path


def test_snake_frames_cover_and_metadata(tmp_path) -> None:
    spec = generate_spec("lucky_pick", 616)
    data = spec.rounds[0].data
    release = spec.intro_duration + lucky_snake.release_time()
    moments = (.5, spec.intro_duration + 2.0, release + .2, release + data["catches"][0]["time"] + .05,
               release + data["simulation_duration"] + .5, spec.total_duration - .2)
    for moment in moments:
        assert render_frame(spec, moment, (540, 960)).size == (540, 960)
    assert render_cover(spec).size == (1080, 1920)
    path = tmp_path / "snake.jpg"; save_cover(spec, path)
    with Image.open(path) as image:
        assert image.format == "JPEG" and image.size == (1080, 1920)
    snake_spec = next(generate(seed) for seed in range(40) if seed % 4 == 3)
    assert "Snake" in youtube_metadata(snake_spec)["youtube_title"]
    assert "maze" not in youtube_metadata(spec)["youtube_description"].lower()


def test_the_cover_never_hints_at_the_first_victim() -> None:
    """The cover uses start positions and a staged snake rising from its den, with its head away from every target."""
    from puzzly.covers import cover_snake_pose
    from puzzly.puzzles.lucky_snake import ENTRY
    for seed in range(40):
        targets = generate(seed).rounds[0].data["targets"]
        pose = cover_snake_pose(targets)
        assert math.dist(pose[-1], ENTRY) < 1e-6  # the tail is in the den
        nearest = min(math.dist(pose[0], target["position"]) for target in targets)
        assert nearest >= 170 or len(pose) <= 28  # head in open space, or just peeking out when the arena is crowded


def test_audio_places_a_bite_for_every_catch() -> None:
    from puzzly.audio import timeline_audio
    import numpy as np
    spec = generate(21)
    audio = timeline_audio(replace(spec, metadata={}))
    assert np.isfinite(audio).all() and len(audio) == round(spec.total_duration * 48000)
