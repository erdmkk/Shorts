from __future__ import annotations

from dataclasses import replace
import inspect
import math
import random

import pytest
from streamlit.testing.v1 import AppTest

from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
from puzzly.generator import generate_spec, output_stem
from puzzly.history import HistoryStore
from puzzly.puzzles import bounce_arena as arena
from puzzly.visuals import bounce_arena as bounce_visual
from puzzly.validation import validation_errors


def test_initial_conditions_contain_no_predetermined_result() -> None:
    balls, arena_data = arena._initial_state(random.Random("initial-only"))
    assert len(balls) == arena.BALL_COUNT == 6
    assert math.isfinite(arena_data["opening_start_angle"])
    assert all(set(ball) == {"id", "color", "position", "velocity"} for ball in balls)
    safe_radius = arena.ARENA_RADIUS - arena.BALL_RADIUS
    assert all(
        math.hypot(ball["position"][0] - arena.ARENA_CENTER[0],
                   ball["position"][1] - arena.ARENA_CENTER[1])
        <= safe_radius - 2 * arena.BALL_RADIUS
        for ball in balls
    )
    source = inspect.getsource(arena._run_attempt)
    assert "elimination_priority" not in source
    assert "protected_winner" not in source
    assert "target_id" not in source
    assert "steer" not in source


def test_same_seed_repeats_natural_result() -> None:
    first = arena.simulate(31)
    second = arena.simulate(31)
    assert first == second
    assert first["elimination_order"] == [event["ball_id"] for event in first["eliminations"]]
    assert first["winner"] not in first["elimination_order"]
    assert first["simulation_duration"] <= arena.ACCEPTANCE_MAX_SECONDS
    assert arena.SAFETY_CAP_SECONDS == arena.ACCEPTANCE_MAX_SECONDS == pytest.approx(21.8)
    assert first["timeline_duration"] + first["cta_duration"] <= arena.MAX_VIDEO_DURATION


def test_different_seeds_produce_different_natural_results() -> None:
    results = [arena.simulate(seed) for seed in range(8)]
    outcomes = {(item["winner"], tuple(item["elimination_order"])) for item in results}
    assert len(outcomes) > 1
    assert len({item["winner"] for item in results}) > 1


def test_gap_angle_rotates_at_constant_seeded_rate() -> None:
    _, first = arena._initial_state(random.Random("gap-motion"))
    _, second = arena._initial_state(random.Random("gap-motion"))
    assert first == second
    start = arena.gap_angle(first, 0.0)
    quarter = arena.gap_angle(first, first["revolution_seconds"] / 4)
    expected = math.copysign(math.pi / 2, first["angular_velocity"])
    assert arena._angle_delta(quarter, start) == pytest.approx(expected)
    assert abs(first["angular_velocity"]) == pytest.approx(2 * math.pi / first["revolution_seconds"])


def _ball_at(arena_data: dict, angle: float, distance: float, speed: tuple[float, float]) -> dict:
    return {"id": 0, "position": [arena.ARENA_CENTER[0] + math.cos(angle) * distance,
                                  arena.ARENA_CENTER[1] + math.sin(angle) * distance], "velocity": list(speed)}


def test_visual_and_physics_gap_share_source_of_truth() -> None:
    assert bounce_visual.gap_geometry is arena.gap_geometry
    assert "gap_geometry" in inspect.getsource(bounce_visual._draw_ring)
    assert "gap_angle" in inspect.getsource(arena.resolve_circular_wall)
    _, arena_data = arena._initial_state(random.Random("shared-gap"))
    widths = [arena.gap_geometry(arena_data, time)["wall_half_angle"] for time in (0.0, 1.25, 5.0, 11.75)]
    assert widths == pytest.approx([arena.OPENING_HALF_ANGLE] * 4)
    # The clear window between the two round caps is wider than a ball.
    clear = 2 * arena.ARENA_RADIUS * math.sin(arena.OPENING_HALF_ANGLE) - arena.WALL_STROKE_WIDTH
    assert clear > 2 * arena.BALL_RADIUS * 2


def test_ball_centred_in_the_gap_passes_through() -> None:
    _, arena_data = arena._initial_state(random.Random("inside-gap"))
    time_value = 2.75
    angle = arena.gap_angle(arena_data, time_value)
    ball = _ball_at(arena_data, angle, arena.ARENA_RADIUS, (math.cos(angle) * 200, math.sin(angle) * 200))
    before = tuple(ball["velocity"])
    assert arena.resolve_circular_wall(ball, arena_data, time_value) is False
    assert tuple(ball["velocity"]) == pytest.approx(before)
    assert arena.outside_ring({"position": [arena.ARENA_CENTER[0] + math.cos(angle) * 401,
                                            arena.ARENA_CENTER[1] + math.sin(angle) * 401]}, arena_data)


def test_ball_never_overlaps_the_band_outside_the_gap() -> None:
    _, arena_data = arena._initial_state(random.Random("outside-gap"))
    time_value = 1.25
    angle = arena.gap_angle(arena_data, time_value) + arena.OPENING_HALF_ANGLE + .3
    nx, ny = math.cos(angle), math.sin(angle)
    ball = _ball_at(arena_data, angle, arena.ARENA_RADIUS - 20, (nx * 200, ny * 200))
    assert arena.resolve_circular_wall(ball, arena_data, time_value) is True
    distance = math.hypot(ball["position"][0] - arena.ARENA_CENTER[0], ball["position"][1] - arena.ARENA_CENTER[1])
    assert distance == pytest.approx(arena.ARENA_RADIUS - arena.WALL_STROKE_WIDTH / 2 - arena.BALL_RADIUS)
    assert ball["velocity"][0] * nx + ball["velocity"][1] * ny < 0


def test_gap_caps_are_solid() -> None:
    _, arena_data = arena._initial_state(random.Random("solid-lips"))
    time_value = 4.5
    gap = arena.gap_angle(arena_data, time_value)
    for sign in (-1, 1):
        edge = gap + sign * arena.OPENING_HALF_ANGLE
        cap = (arena.ARENA_CENTER[0] + math.cos(edge) * arena.ARENA_RADIUS,
               arena.ARENA_CENTER[1] + math.sin(edge) * arena.ARENA_RADIUS)
        inward = (edge - sign * .05)
        ball = _ball_at(arena_data, inward, arena.ARENA_RADIUS - 5, (math.cos(edge) * 190, math.sin(edge) * 190))
        arena.resolve_circular_wall(ball, arena_data, time_value)
        assert math.dist(ball["position"], cap) >= arena.BALL_RADIUS + arena.WALL_STROKE_WIDTH / 2 - 1e-6


def test_simulated_balls_stay_off_the_band() -> None:
    data = arena.simulate(4402)
    arena_data = data["arena"]
    for frame in data["frames"]:
        gap = arena.gap_angle(arena_data, frame["time"])
        for _, x, y in frame["balls"]:
            dx, dy = x - arena.ARENA_CENTER[0], y - arena.ARENA_CENTER[1]
            if abs(arena._angle_delta(math.atan2(dy, dx), gap)) > arena.OPENING_HALF_ANGLE + .15:
                assert math.hypot(dx, dy) <= arena.ARENA_RADIUS - arena.WALL_STROKE_WIDTH / 2 - arena.BALL_RADIUS + .5


def test_capsule_lip_end_cap_blocks_diagonal_slip() -> None:
    start = (0.0, 0.0)
    end = (100.0, 0.0)
    wall_radius = arena.WALL_STROKE_WIDTH / 2
    ball = {
        "id": 0,
        "position": [124.0, 34.0],
        "velocity": [-150.0, -175.0],
    }
    before_normal_speed = (
        ball["velocity"][0] * (ball["position"][0] - end[0])
        + ball["velocity"][1] * (ball["position"][1] - end[1])
    )
    assert before_normal_speed < 0
    assert arena.resolve_capsule_collision(ball, start, end, wall_radius)
    distance_from_cap = math.dist(ball["position"], end)
    assert distance_from_cap >= arena.BALL_RADIUS + wall_radius
    nx = (ball["position"][0] - end[0]) / distance_from_cap
    ny = (ball["position"][1] - end[1]) / distance_from_cap
    assert ball["velocity"][0] * nx + ball["velocity"][1] * ny > 0


def test_energy_floor_keeps_direction_and_has_no_opening_input() -> None:
    floor_y = arena.ARENA_CENTER[1] + arena.ARENA_RADIUS - arena.BALL_RADIUS
    slow = {"id": 2, "position": [540.0, floor_y], "velocity": [30.0, -40.0]}
    before = math.atan2(slow["velocity"][1], slow["velocity"][0])
    arena.keep_bouncy(slow)
    assert arena.bounce_height(slow) == pytest.approx(arena.MIN_BOUNCE_HEIGHT)
    assert math.atan2(slow["velocity"][1], slow["velocity"][0]) == pytest.approx(before)
    wild = {"id": 3, "position": [540.0, floor_y], "velocity": [0.0, -5000.0]}
    arena.keep_bouncy(wild)
    assert arena.bounce_height(wild) == pytest.approx(arena.MAX_BOUNCE_HEIGHT)
    fine = {"id": 4, "position": [540.0, floor_y], "velocity": [0.0, -1300.0]}
    arena.keep_bouncy(fine)
    assert fine["velocity"] == [0.0, -1300.0]
    source = inspect.getsource(arena.keep_bouncy)
    assert "opening" not in source and "gap" not in source


def test_head_on_equal_mass_collision_transfers_momentum() -> None:
    p1, v1, p2, v2 = arena.elastic_collision(
        (0.0, 0.0), (20.0, 0.0), (70.0, 0.0), (0.0, 0.0), 40.0)
    assert math.dist(p1, p2) == pytest.approx(80.0)
    assert v1 == pytest.approx((0.0, 0.0))
    assert v2 == pytest.approx((20.0, 0.0))  # perfectly elastic: momentum and energy are conserved
    assert all(math.isfinite(value) for pair in (p1, v1, p2, v2) for value in pair)


def test_glancing_collision_conserves_energy() -> None:
    _, first_velocity, _, second_velocity = arena.elastic_collision(
        (0.0, 0.0), (500.0, 120.0), (70.0, 20.0), (-300.0, 0.0), 40.0)
    before = 500.0 ** 2 + 120.0 ** 2 + 300.0 ** 2
    after = sum(value * value for value in (*first_velocity, *second_velocity))
    assert after == pytest.approx(before)


def test_gravity_pulls_balls_and_records_impacts() -> None:
    data = arena.simulate(4402)
    assert data["arena"]["gravity"] == arena.GRAVITY > 0 and data["version"] == arena.VERSION
    assert data["impacts"] and all(len(item) == 7 and item[1] in ("wall", "ball") for item in data["impacts"])
    assert [item[0] for item in data["impacts"]] == sorted(item[0] for item in data["impacts"])
    assert all("velocity" in event for event in data["eliminations"])
    assert arena.ACCEPTANCE_MIN_SECONDS <= data["simulation_duration"] <= arena.ACCEPTANCE_MAX_SECONDS
    assert data["eliminations"][0]["time"] >= arena.FIRST_EXIT_MIN_SECONDS


def test_eliminations_use_actual_opening_and_leave_one_winner() -> None:
    data = arena.simulate(91827)
    assert len(data["eliminations"]) == 5
    assert len(set(data["elimination_order"])) == 5
    assert data["winner"] not in data["elimination_order"]
    assert {int(item[0]) for item in data["frames"][-1]["balls"]} == {data["winner"]}
    for event in data["eliminations"]:
        expected = arena.gap_angle(data["arena"], float(event["gap_entry_time"]))
        assert float(event["gap_angle"]) == pytest.approx(expected, abs=2e-6)
        assert abs(arena._angle_delta(float(event["gap_entry_angle"]), float(event["gap_angle"]))) < arena.OPENING_HALF_ANGLE
    first = data["eliminations"][0]
    assert abs(arena._angle_delta(float(first["gap_angle"]),
                                  float(data["arena"]["opening_start_angle"]))) > .05


def test_eliminated_balls_never_return_and_states_are_finite() -> None:
    data = arena.simulate(4402)
    events = {int(event["ball_id"]): float(event["time"]) for event in data["eliminations"]}
    for frame in data["frames"]:
        assert math.isfinite(float(frame["time"]))
        ids = {int(item[0]) for item in frame["balls"]}
        for ball_id, eliminated_at in events.items():
            if float(frame["time"]) >= eliminated_at - 1e-4:
                assert ball_id not in ids
        assert all(math.isfinite(float(value)) for item in frame["balls"] for value in item)


def test_timeout_rejects_attempt_without_forcing_elimination() -> None:
    result = arena._run_attempt(77, 0, safety_cap=0.0)
    assert result["completed"] is False
    assert result["winner"] is None
    assert result["eliminations"] == []
    assert result["elimination_order"] == []


def test_spec_fingerprint_validation_filename_and_sqlite(tmp_path) -> None:
    spec = generate_spec("bounce_arena", 4402)
    assert validation_errors(spec) == []
    assert spec.difficulty is None and spec.round_count == 1
    assert spec.outro_duration == pytest.approx(3.7)
    assert spec.total_duration == pytest.approx(spec.round_duration + 3.7, abs=1e-3)
    assert spec.total_duration <= arena.MAX_VIDEO_DURATION == 32.0  # 30 s of game plus the longer end card
    assert output_stem(23, spec) == "PZ_0023_bounce_arena"
    assert spec.fingerprint() == generate_spec("bounce_arena", 4402).fingerprint()
    changed_data = dict(spec.rounds[0].data)
    changed_data["opening_probe"] = 1
    changed_round = replace(spec.rounds[0], data=changed_data)
    assert spec.fingerprint() != replace(spec, rounds=(changed_round,)).fingerprint()
    history = HistoryStore(tmp_path / "generation_history.sqlite")
    record = history.commit_success(
        puzzle_type=spec.puzzle_type, difficulty=spec.difficulty, seed=spec.seed,
        fingerprint=spec.fingerprint(),
        finalize_files=lambda sequence: (f"PZ_{sequence:04d}_bounce_arena.mp4",
                                         f"PZ_{sequence:04d}_bounce_arena.jpg"),
    )
    assert record.difficulty == ""
    assert history.contains(spec.fingerprint())


def test_ui_hides_difficulty_and_challenge_count() -> None:
    app = AppTest.from_file("app.py").run()
    app.selectbox[0].select("Bounce Arena").run()
    assert not app.exception
    labels = [box.label for box in app.selectbox]
    assert "Difficulty" not in labels and "Challenges per video" not in labels
    assert "Number of videos" in labels and "Quality" in labels
    assert any(item.label == "Optional Seed" for item in app.text_input)
    assert "1 game" in app.info[0].value


def test_audio_uses_safe_existing_pipeline() -> None:
    audio = timeline_audio(generate_spec("bounce_arena", 903))
    assert audio.ndim == 2 and audio.shape[1] == 2
    assert all(math.isfinite(float(value)) for value in audio[::4800].flat)
    assert float(abs(audio).max()) <= MIX_PEAK_LIMIT + 1e-9


def test_winner_effect_is_prominent_and_settles_cleanly() -> None:
    start_scale, start_glow, start_progress = bounce_visual.winner_effect_state(0.0)
    final_scale, final_glow, final_progress = bounce_visual.winner_effect_state(.7)
    assert (start_scale, start_glow, start_progress) == pytest.approx((1.0, 0.0, 0.0))
    assert 1.40 <= final_scale <= 1.50
    assert final_glow == pytest.approx(1.0)
    assert final_progress == pytest.approx(1.0)


def test_exit_flight_lands_on_the_out_shelf() -> None:
    event = {"position": [540.0, 1340.0], "velocity": [300.0, 900.0]}
    start, zoom = bounce_visual.exit_position(event, 0.0, 0)
    assert start == pytest.approx((540.0, 1340.0)) and zoom == 1.0
    end, zoom = bounce_visual.exit_position(event, bounce_visual.EXIT_FLIGHT + .1, 3)
    assert end == pytest.approx((540 + bounce_visual.SHELF_SPACING, bounce_visual.SHELF_Y)) and zoom == bounce_visual.SHELF_SCALE


def test_bounce_frames_cover_and_outro() -> None:
    from puzzly.renderer import render_cover, render_frame
    spec = generate_spec("bounce_arena", 4402)
    data = spec.rounds[0].data
    moments = (1.0, 5.5, 5.0 + data["eliminations"][0]["time"] + .2, spec.round_duration - .3, spec.total_duration - .2)
    frames = [render_frame(spec, moment, (540, 960)) for moment in moments]
    assert all(frame.size == (540, 960) for frame in frames)
    assert render_cover(spec).size == (1080, 1920)
