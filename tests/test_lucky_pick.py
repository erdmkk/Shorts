from __future__ import annotations

from collections import Counter
from dataclasses import replace
import random

from PIL import Image

from puzzly.config import (LUCKY_APPEARANCE_DURATION, LUCKY_SELECTION_DURATION, LUCKY_WINNER_HOLD,
                           PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION)
from puzzly.generator import generate_spec, mixed_types
from puzzly.puzzles.lucky_pick import (CHOMP_AT, COLORS, CORRIDOR_WIDTH, EAT_ANTICIPATION, EAT_BITE, EAT_DURATION,
                                       MAP_VERSION, MAZE_MIN_POCKETS, POST_EAT, SHAPES, STOP_GAP, TARGET_COUNT,
                                       TARGET_SIZE, TRAVEL_RAMP, TRAVEL_SPEED, build_maze, errors, generate,
                                       maze_errors, path_length, point_on_path, travel_distance)
from puzzly.registry import ACTIVE_PUZZLE_TYPES, EXPERIMENTAL_PUZZLE_TYPES, MIXED_PUZZLE_TYPES
from puzzly.renderer import render_cover, render_frame, save_cover
from puzzly.validation import validate_spec
from puzzly.visuals.lucky_pick import CHARACTER_RADIUS, creature, lucky_state


def _on_axis_segment(point: tuple[float, float], path: list[list[int]]) -> bool:
    x, y = point
    return any((a[0] == b[0] and abs(x - a[0]) < 1e-6 and min(a[1], b[1]) - 1e-6 <= y <= max(a[1], b[1]) + 1e-6) or
               (a[1] == b[1] and abs(y - a[1]) < 1e-6 and min(a[0], b[0]) - 1e-6 <= x <= max(a[0], b[0]) + 1e-6)
               for a, b in zip(path, path[1:]))


def test_seeded_mazes_are_connected_with_dead_end_pockets() -> None:
    layouts = set()
    for map_seed in range(150):
        geometry = build_maze(map_seed)
        assert maze_errors(geometry) == [] and geometry == build_maze(map_seed)
        assert len(geometry["target_nodes"]) >= MAZE_MIN_POCKETS
        layouts.add(tuple(map(tuple, map(lambda edge: tuple(map(tuple, edge)), geometry["corridors"]))))
        degree = Counter(tuple(point) for edge in geometry["corridors"] for point in edge)
        assert all(degree[tuple(point)] == 1 for point in geometry["target_nodes"])
        # A spanning tree of 30 nodes plus the entrance corridor plus two shortcut loops.
        assert len(geometry["corridors"]) == 30 - 1 + 1 + 2
    assert len(layouts) == 150


def test_lucky_pick_700_specs_are_valid_deterministic_and_fair() -> None:
    winners: Counter[int] = Counter(); orders = set(); shapes = set()
    for seed in range(700):
        spec = generate(seed); validate_spec(spec)
        assert spec == generate(seed) and spec.fingerprint() == generate(seed).fingerprint()
        assert spec.difficulty is None and spec.round_count == 1 and 19 <= spec.total_duration <= 30
        assert spec.intro_duration == PUZZLE_FIT_INTRO_DURATION and spec.outro_duration == PUZZLE_FIT_OUTRO_DURATION
        game = spec.rounds[0]; data = game.data; targets = data["targets"]
        assert data["map_version"] == MAP_VERSION
        assert data["target_count"] == TARGET_COUNT == len(targets) == 7
        assert len({target["shape_id"] for target in targets}) == 1 and data["shape_id"] in SHAPES
        assert {target["color_id"] for target in targets} == set(COLORS)
        assert len({tuple(target["position"]) for target in targets}) == 7
        assert all(target["position"] in data["valid_target_positions"] for target in targets)
        assert data["selection_seconds"] == LUCKY_SELECTION_DURATION == 5.0 and data["eat_seconds"] == EAT_DURATION
        assert game.answer == data["winner_index"] and data["winner_index"] not in data["elimination_order"]
        assert sorted(data["elimination_order"]) == sorted(set(range(7)) - {data["winner_index"]})
        assert not errors(data, game.answer)
        winners[data["winner_index"]] += 1; orders.add(tuple(data["elimination_order"])); shapes.add(data["shape_id"])
    expected = 700 / 7
    assert all(abs(count - expected) <= expected * .30 for count in winners.values())
    assert len(orders) > 300 and shapes == set(SHAPES)


def test_travel_enters_from_the_portal_and_follows_corridors() -> None:
    for seed in range(100):
        data = generate(seed).rounds[0].data; previous = None
        route_edges = {tuple(sorted((tuple(a), tuple(b)))) for a, b in data["corridors"]}
        pockets = {tuple(target["position"]) for target in data["targets"]}
        for step, target_index in zip(data["movement_steps"], data["elimination_order"]):
            path = step["travel_path"]
            assert path[-1] == data["targets"][target_index]["position"]
            assert path[0] == (data["entrance"] if previous is None else data["targets"][previous]["position"])
            assert all(tuple(sorted((tuple(a), tuple(b)))) in route_edges for a, b in zip(path, path[1:]))
            assert not pockets & {tuple(point) for point in path[1:-1]}  # never walks over another target
            for sample in range(51):
                point, _ = point_on_path(path, sample / 50); assert _on_axis_segment(point, path)
            previous = target_index


def test_speed_profile_ramps_then_cruises() -> None:
    step = generate(77).rounds[0].data["movement_steps"][0]
    stop = path_length(step["travel_path"]) - STOP_GAP
    duration = step["travel_duration"]
    assert abs(duration - round(stop / TRAVEL_SPEED + TRAVEL_RAMP, 4)) < 1e-9
    assert travel_distance(0, duration, stop) == 0 and abs(travel_distance(duration, duration, stop) - stop) < 1e-6
    samples = [travel_distance(duration * k / 40, duration, stop) for k in range(41)]
    assert all(b >= a for a, b in zip(samples, samples[1:]))
    middle = (travel_distance(duration / 2 + .05, duration, stop) - travel_distance(duration / 2 - .05, duration, stop)) / .1
    assert abs(middle - TRAVEL_SPEED) < 1


def test_eating_states_crouch_lunge_chomp_and_chew() -> None:
    game = generate(9010).rounds[0]; first = game.data["movement_steps"][0]
    eat_start = float(first["end_time"]) - EAT_DURATION
    selection = lucky_state(LUCKY_APPEARANCE_DURATION + .2, game)
    entrance = lucky_state(float(first["start_time"]), game)
    anticipation = lucky_state(eat_start + EAT_ANTICIPATION / 2, game)
    wide = lucky_state(eat_start + EAT_ANTICIPATION + EAT_BITE * .5, game)
    chomp = lucky_state(eat_start + EAT_ANTICIPATION + EAT_BITE * (CHOMP_AT + .05), game)
    chew = lucky_state(eat_start + EAT_ANTICIPATION + EAT_BITE + POST_EAT * .3, game)
    winner = lucky_state(float(game.data["timeline_duration"]) - LUCKY_WINNER_HOLD + .2, game)
    assert selection["phase"] == "selection" and selection["character"] is None
    assert entrance["phase"] == "travel" and entrance["character"] == tuple(game.data["entrance"]) and entrance["emerge"] == 0
    assert anticipation["phase"] == "eat_anticipation" and 0 < anticipation["mouth"] < .4
    assert wide["phase"] == "eat" and wide["mouth"] == 1.0 and first["target_index"] not in wide["eliminated"]
    assert chomp["phase"] == "eat" and first["target_index"] in chomp["eliminated"] and chomp["chomp_age"] > 0
    assert chew["phase"] == "post_eat" and chew["cheeks"] > 0 and chew["happy"] == 1.0
    assert winner["phase"] == "winner" and game.data["winner_index"] not in winner["eliminated"]
    assert len(winner["eliminated"]) == 6


def test_creature_and_maze_scale() -> None:
    assert TARGET_SIZE < CHARACTER_RADIUS * 2 and CHARACTER_RADIUS * 2 < CORRIDOR_WIDTH * 1.2
    closed = creature(64); open_mouth = creature(64, mouth=1.0)
    assert closed.getbbox() and closed.tobytes() != open_mouth.tobytes()


def test_lucky_fingerprint_tracks_identity() -> None:
    spec = generate(88); game = spec.rounds[0]
    changed = dict(game.data); changed["shape_id"] = "circle" if changed["shape_id"] != "circle" else "star"
    assert spec.fingerprint() != replace(spec, rounds=(replace(game, data=changed),)).fingerprint()


def test_lucky_frames_and_cover(tmp_path) -> None:
    spec = generate(616); game = spec.rounds[0]
    first = game.data["movement_steps"][0]
    eat = float(first["end_time"]) - EAT_DURATION + EAT_ANTICIPATION + EAT_BITE / 2
    moments = (.5, spec.intro_duration + .5, spec.intro_duration + float(first["start_time"]) + .2,
               spec.intro_duration + eat, spec.total_duration - spec.outro_duration - .2, spec.total_duration - .2)
    for moment in moments:
        assert render_frame(spec, moment, (540, 960)).size == (540, 960)
    assert render_cover(spec).size == (1080, 1920)
    path = tmp_path / "lucky.jpg"; save_cover(spec, path)
    with Image.open(path) as image:
        assert image.format == "JPEG" and image.size == (1080, 1920); image.verify()


def test_lucky_is_active_and_line_follow_stays_disabled() -> None:
    assert "lucky_pick" in ACTIVE_PUZZLE_TYPES
    assert "line_follow" in EXPERIMENTAL_PUZZLE_TYPES and "line_follow" not in ACTIVE_PUZZLE_TYPES
    assert set(mixed_types(700, random.Random(10))) == set(MIXED_PUZZLE_TYPES)
    assert generate_spec("lucky_pick", 17).difficulty is None
