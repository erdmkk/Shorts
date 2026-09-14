from dataclasses import replace
from puzzly.puzzles.find_the_exit import DIFFICULTY_RULES, generate, route_metrics, routes
from puzzly.validation import validate_spec, round_errors


def test_600_maze_rounds_have_one_reachable_exit() -> None:
    for difficulty in ("easy", "medium", "hard"):
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
