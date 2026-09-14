from dataclasses import replace
import math

import pytest

from puzzly.config import LINE_FOLLOW_FINAL_PATH_SCALE, thinking_duration
from puzzly.puzzles.line_follow import (
    DIFFICULTY_RULES, crossing_curve, crossing_halo_curve, cubic_point, curve_geometry, generate, geometry, lane_positions, TOP,
)
from puzzly.validation import round_errors, validate_spec
from puzzly.visuals.paths import _static_line_layer


@pytest.mark.parametrize(("difficulty", "rounds"), (("easy", 300), ("medium", 500), ("hard", 700)))
def test_line_follow_volume_is_valid_deterministic_and_unambiguous(difficulty: str, rounds: int) -> None:
    seeds = math.ceil(rounds / 4)
    seen = 0
    rules = DIFFICULTY_RULES[difficulty]
    for seed in range(seeds):
        spec = generate(seed, difficulty)
        validate_spec(spec)
        assert spec == generate(seed, difficulty)
        for item in spec.rounds:
            seen += 1
            data = item.data
            paths, crossings, destinations = geometry(data["swaps"], data["path_count"])
            assert len(paths) == data["path_count"] == rules["path_count"]
            assert len(crossings) == rules["crossings"]
            assert sorted(destinations) == list(range(data["path_count"]))
            assert destinations[data["source"]] == item.answer
            assert len({tuple(path) for path in paths}) == data["path_count"]
            assert all(180 <= x <= 900 and 400 <= y <= 1350 for path in paths for x, y in path)
            assert min(b - a for a, b in zip(lane_positions(data["path_count"]), lane_positions(data["path_count"])[1:])) >= 150
            assert data["metrics"]["target_crossings"] >= rules["target_crossings"]
            assert data["metrics"]["target_span"] >= rules["span"]
            assert data["metrics"]["direction_changes"] >= rules["turns"]
            assert data["metrics"]["min_path_interactions"] >= rules["min_path_interactions"]
            assert data["metrics"]["plausible_exits"] == data["path_count"]
            if difficulty == "hard":
                assert data["metrics"]["target_lower_half_interactions"] >= 4
                assert data["metrics"]["target_final_third_interactions"] >= 2
                assert min(data["metrics"]["target_interactions_by_third"]) >= 2
                assert data["metrics"]["target_max_idle_run"] <= 2
                assert data["metrics"]["lower_half_active_paths"] == 5
            curves, _, _ = curve_geometry(data["swaps"], data["path_count"])
            for crossing in crossings:
                stage = crossing["stage"]
                over = cubic_point(curves[crossing["over"]][stage], 0.5)
                under = cubic_point(curves[crossing["under"]][stage], 0.5)
                assert math.dist(over, under) < 1e-8
                assert crossing["over"] != crossing["under"]
        assert len({item.fingerprint() for item in spec.rounds}) == len(spec.rounds)
    assert seen >= rounds


def test_difficulty_structure_and_thinking_time() -> None:
    assert [(name, rule["path_count"], rule["crossings"]) for name, rule in DIFFICULTY_RULES.items()] == [
        ("easy", 3, 2), ("medium", 4, 6), ("hard", 5, 12),
    ]
    assert [thinking_duration("line_follow", name) for name in DIFFICULTY_RULES] == [5, 6, 7]
    hard = generate(91, "hard").rounds[0].data["metrics"]
    assert hard["first_decision"] <= 1 and hard["last_decision"] >= 10
    assert hard["min_path_interactions"] >= 3 and hard["target_unique_interactions"] >= 3
    assert hard["target_lower_half_interactions"] >= 4
    assert hard["min_lower_half_path_interactions"] >= 1
    assert hard["trace_length"] > generate(91, "easy").rounds[0].data["metrics"]["trace_length"]


def test_cubic_geometry_stays_float_and_adaptively_sampled() -> None:
    item = generate(18, "hard").rounds[0]
    paths, _, _ = geometry(item.data["swaps"], item.data["path_count"])
    assert any(not coordinate.is_integer() for path in paths for point in path for coordinate in point)
    assert all(a[1] < b[1] for path in paths for a, b in zip(path, path[1:]))
    # Curved spans receive dense samples rather than visible long chords.
    assert max(math.dist(a, b) for path in paths for a, b in zip(path, path[1:])) <= 5.1


def test_hard_is_more_lateral_and_complex_on_average() -> None:
    summaries = {}
    for difficulty in DIFFICULTY_RULES:
        metrics = [generate(seed, difficulty).rounds[0].data["metrics"] for seed in range(40)]
        summaries[difficulty] = {
            "lateral": sum(item["average_lateral_travel"] for item in metrics) / len(metrics),
            "target_lateral": sum(item["target_lateral_travel"] for item in metrics) / len(metrics),
            "length": sum(item["trace_length"] for item in metrics) / len(metrics),
            "lower": sum(item["target_lower_half_interactions"] for item in metrics) / len(metrics),
        }
    assert summaries["easy"]["lateral"] < summaries["medium"]["lateral"] < summaries["hard"]["lateral"]
    assert summaries["easy"]["target_lateral"] < summaries["hard"]["target_lateral"]
    assert summaries["easy"]["length"] < summaries["hard"]["length"]
    assert summaries["easy"]["lower"] < summaries["hard"]["lower"]


def test_hard_has_no_isolated_or_trivial_path_group() -> None:
    for seed in range(80):
        for item in generate(seed, "hard").rounds:
            metrics = item.data["metrics"]
            assert min(metrics["path_interactions"]) >= 3
            assert metrics["target_unique_interactions"] >= 3
            assert metrics["max_idle_run"] <= 4
            assert metrics["target_max_idle_run"] <= 2
            assert min(metrics["target_interactions_by_third"]) >= 2
            assert metrics["min_lower_half_path_interactions"] >= 1
            assert metrics["lower_half_active_paths"] == 5
            assert metrics["plausible_exits"] == 5


def test_final_path_layer_uses_four_x_antialiasing() -> None:
    item = generate(8, "medium").rounds[0]
    layer = _static_line_layer(tuple(item.data["swaps"]), item.data["path_count"], 2160, "#244653", "#fffdf7")
    assert LINE_FOLLOW_FINAL_PATH_SCALE == 4
    assert layer.size == (1560, 2100)
    alpha = layer.getchannel("A")
    assert any(value not in (0, 255) for value in alpha.getdata())


def test_bridge_top_centerline_is_continuous_without_gaps() -> None:
    item = generate(808, "hard").rounds[0]
    layer = _static_line_layer(tuple(item.data["swaps"]), 5, 2160, "#244653", "#fffdf7")
    target = (36, 70, 83)
    for crossing in item.data["crossings"]:
        bridge = crossing_curve(item.data["swaps"], 5, crossing)
        halo = crossing_halo_curve(item.data["swaps"], 5, crossing)
        center = crossing["center"]
        assert math.dist(bridge[0], center) > math.dist(halo[0], center)
        assert math.dist(bridge[-1], center) > math.dist(halo[-1], center)
        center_samples = [(round((x - 150) * 2), round((y - 380) * 2)) for x, y in bridge]
        pixels = [layer.getpixel(point)[:3] for point in center_samples]
        assert max(max(abs(channel - expected) for channel, expected in zip(pixel, target)) for pixel in pixels) <= 8


def test_stroke_width_is_stable_near_path_anchors() -> None:
    item = generate(809, "hard").rounds[0]
    layer = _static_line_layer(tuple(item.data["swaps"]), 5, 2160, "#244653", "#fffdf7")
    alpha = layer.getchannel("A")
    # Measure at the shared vertical-tangent anchor; farther down a diagonal
    # path legitimately has a wider horizontal projection.
    y = round((TOP - 380) * 2)
    widths = []
    for lane in lane_positions(5):
        center = round((lane - 150) * 2)
        run = sum(alpha.getpixel((x, y)) >= 128 for x in range(center - 30, center + 31))
        widths.append(run)
    assert all(34 <= width <= 40 for width in widths)


def test_missing_bridge_wrong_destination_and_low_complexity_are_rejected() -> None:
    item = generate(22, "hard").rounds[0]
    assert round_errors(replace(item, data={**item.data, "crossings": []}))
    assert round_errors(replace(item, answer=(item.answer + 1) % item.data["path_count"]))
    metrics = {**item.data["metrics"], "target_crossings": 0}
    assert round_errors(replace(item, data={**item.data, "metrics": metrics}))
