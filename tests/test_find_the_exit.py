from dataclasses import replace
from puzzly.puzzles.find_the_exit import DIFFICULTY_RULES, generate, route_metrics, routes
from puzzly.validation import validate_spec, round_errors


def test_easy_and_medium_maze_rounds_have_one_reachable_exit() -> None:
    for difficulty in ("easy", "medium"):
        for seed in range(50):
            spec = generate(seed, difficulty)
            validate_spec(spec)
            assert spec == generate(seed, difficulty)
            for item in spec.rounds:
                d = item.data
                reachable = routes(d["start"], d["edges"])
                assert [i for i, node in enumerate(d["exits"]) if node in reachable] == [item.answer]
                assert 760 / d["size"] >= 100
                rules = DIFFICULTY_RULES[difficulty]
                metrics = route_metrics(d["route"], d["size"])
                assert d["route_metrics"] == metrics
                assert rules["min_route"] <= metrics["nodes"] <= rules["max_route"]
                assert metrics["turns"] >= rules["turns"]
                assert metrics["down_steps"] >= rules["down_steps"]
                assert metrics["horizontal_steps"] >= rules["horizontal_steps"]
                assert d["route_branch_points"] >= rules["route_branches"]
                edge_set = {tuple(edge) for edge in d["edges"]}
                assert all((exit_node, exit_node + d["size"]) in edge_set for exit_node in d["exits"])
                assert all(size >= rules["false_depth"] + 1 for size in d["exit_component_sizes"])


def test_invalid_maze_answer_and_route_are_rejected() -> None:
    item = generate(45).rounds[0]
    assert round_errors(replace(item, answer=(item.answer + 1) % 3))
    assert round_errors(replace(item, data={**item.data, "route": [item.data["start"]]}))


def test_hard_mazes_snake_hide_their_seams_and_escalate() -> None:
    from collections import Counter
    from puzzly.puzzles.find_the_exit import (DECOY_DEPTH, HARD_LEVELS, errors, grid_neighbors,
                                              longest_straight_wall, vertical_runs)
    answers = Counter()
    for seed in range(8):
        spec = generate(seed, "hard")
        validate_spec(spec)
        assert spec.intro_duration == 1.0 and spec.outro_duration == 1.6
        assert {item.answer for item in spec.rounds} == {0, 1, 2}
        sizes = [(item.data["rows"], item.data["columns"]) for item in spec.rounds]
        assert sizes == [(10, 8), (10, 8), (11, 9), (12, 10)]
        for item in spec.rounds:
            d = item.data
            answers[item.answer] += 1
            assert d["layout"] == "deceptive_v2" and errors(d, item.answer) == []
            reachable = routes(d["start"], d["edges"])
            assert [i for i, node in enumerate(d["exits"]) if node in reachable] == [item.answer]
            level = next(level for level in HARD_LEVELS if level["rows"] == d["rows"])
            # The answer snakes: up, down, up (... down, up) and is long.
            assert vertical_runs(d["route"], d["columns"]) >= 2 * level["sweeps"] + 1
            assert len(d["route"]) >= level["min_route"]
            # No long unbroken seam gives away a sealed region.
            assert longest_straight_wall(d["edges"], d["rows"], d["columns"]) <= level["max_straight"]
            # Each decoy dives deep and dead-ends one wall away from the answer route.
            route_cells = set(d["route"])
            for node in d["decoy_ends"]:
                assert node not in reachable and node // d["columns"] >= d["rows"] * DECOY_DEPTH
                assert any(n in route_cells for n in grid_neighbors(node, d["rows"], d["columns"]))
    assert min(answers.values()) >= 8


def test_hard_rejects_a_maze_with_invalid_decoys() -> None:
    item = generate(2, "hard").rounds[0]
    assert round_errors(replace(item, data={**item.data, "decoy_ends": [0, 1]}))
