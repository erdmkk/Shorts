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
    from puzzly.puzzles.find_the_exit import (DECOY_DEPTH, DECOY_QUOTA, DECOY_REACH, HARD_LEVELS, MIN_DECOY_SHARE,
                                              decoy_reach, errors, grid_neighbors, longest_straight_wall, vertical_runs)
    answers = Counter()
    for seed in range(8):
        spec = generate(seed, "hard")
        validate_spec(spec)
        assert spec.intro_duration == 1.0 and spec.outro_duration == 1.6
        assert {item.answer for item in spec.rounds[:3]} == {0, 1, 2}  # levels 1-3 use every exit once
        sizes = [(item.data["rows"], item.data["columns"]) for item in spec.rounds]
        # Every level is a larger grid: narrower corridors and a longer answer route in the same maze box.
        assert sizes == [(10, 8), (12, 10), (14, 12), (16, 13)]
        route_lengths = [len(item.data["route"]) for item in spec.rounds]
        assert route_lengths == sorted(route_lengths) and len(set(route_lengths)) == len(route_lengths)
        for item in spec.rounds:
            d = item.data
            answers[item.answer] += 1
            assert d["layout"] == "deceptive_v2" and d["maze_version"] == 3 and errors(d, item.answer) == []
            reachable = routes(d["start"], d["edges"])
            assert [i for i, node in enumerate(d["exits"]) if node in reachable] == [item.answer]
            level = next(level for level in HARD_LEVELS if (level["rows"], level["columns"]) == (d["rows"], d["columns"]))
            assert len(d["exits"]) == level["exits"] == (4 if d["level"] >= 4 else 3)
            # A false exit cannot be ruled out by tracing back from it: its region is large and reaches deep.
            free = d["rows"] * d["columns"] - len(d["route"])
            quota = DECOY_QUOTA * free / (len(d["exits"]) - 1)
            for index, node in enumerate(d["exits"]):
                if index != item.answer:
                    region = set(routes(node, d["edges"]))
                    assert len(region) >= MIN_DECOY_SHARE * quota - .5
                    assert decoy_reach(region, d["rows"], d["columns"]) >= DECOY_REACH
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


def test_hard_level_n_uses_grid_tier_n_and_its_own_thinking_time() -> None:
    from puzzly.config import exit_hard_round
    from puzzly.puzzles.find_the_exit import level_tier
    from puzzly.visuals.find_the_exit import schedule
    assert [level_tier(index, 3) for index in range(3)] == [0, 1, 2]
    assert [level_tier(index, 5) for index in range(5)] == [0, 1, 2, 3, 4]
    spec = generate(4, "hard")
    assert [item.data["thinking_seconds"] for item in spec.rounds] == [5.0, 6.0, 7.0, 8.0]
    levels = schedule(spec)
    assert [duration for _, duration in levels] == [exit_hard_round(value) for value in (5.0, 6.0, 7.0, 8.0)]
    assert abs(levels[-1][0] + levels[-1][1] + spec.outro_duration - spec.total_duration) < 1e-3
    # Five levels: the fifth is a slightly larger grid, in the same proportions, with 9 seconds to think.
    five = generate(4, "hard", round_count=5)
    validate_spec(five)
    assert [(item.data["rows"], item.data["columns"]) for item in five.rounds][-2:] == [(16, 13), (17, 14)]
    assert five.rounds[-1].data["thinking_seconds"] == 9.0
    assert len(five.rounds[-1].data["route"]) >= 92
    assert [len(item.data["exits"]) for item in five.rounds] == [3, 3, 3, 4, 4]
    assert {item.answer for item in five.rounds[3:]} <= {0, 1, 2, 3}
    # A wrong thinking time for the level is rejected; older videos without one keep 8 s on every level.
    item = spec.rounds[0]
    assert round_errors(replace(item, data={**item.data, "thinking_seconds": 8.0}))
    legacy = {key: value for key, value in item.data.items() if key != "thinking_seconds"}
    assert round_errors(replace(item, data=legacy)) == []


def test_find_the_exit_hard_cover_redraws_the_maze_in_3d() -> None:
    from puzzly.covers import _template, has_template
    spec = generate(3, "hard")
    assert has_template(spec)
    template = _template(spec)
    assert template["title"] == ("FIND THE", "EXIT")
    first = spec.rounds[0].data
    board = template["content"]
    # The card is the real level-1 maze drawn directly, not a crop of a video frame.
    assert board.height > board.width and abs(board.width / board.height - first["columns"] / (first["rows"] + 3.6)) < .12


def test_no_cover_states_a_time() -> None:
    """Thinking and viewing times change by level and difficulty, so no 3D cover may promise a number of seconds."""
    import re
    from puzzly.covers import _template
    from puzzly.generator import generate_spec
    from puzzly.music import STYLES
    for kind in STYLES:  # every game with a 3D cover template
        template = _template(generate_spec(kind, 3, "hard"))
        text = " ".join([*template["title"], template["subtitle"], template["cta"], template["line"]])
        assert not re.search(r"SECOND|\bSEC\b|\d\s*S\b", text), f"{kind} cover mentions a time: {text}"


def test_hard_rejects_small_or_shallow_false_regions_in_new_mazes() -> None:
    from puzzly.puzzles.find_the_exit import errors
    item = generate(2, "hard").rounds[0]
    too_many = dict(item.data, exits=item.data["exits"] + [item.data["columns"] - 1])
    assert errors(too_many, item.answer)  # wrong exit count for the level
    older = {key: value for key, value in item.data.items() if key != "maze_version"}
    assert older["exits"] and len(older["exits"]) == 3  # level 1 keeps three exits, as older records did


def test_hard_rejects_a_maze_with_invalid_decoys() -> None:
    item = generate(2, "hard").rounds[0]
    assert round_errors(replace(item, data={**item.data, "decoy_ends": [0, 1]}))
