from collections import Counter

from puzzly.config import (DEFAULT_ROUNDS, PUZZLE_FIT_INTRO_DURATION, PUZZLE_FIT_OUTRO_DURATION, QUICK_MATH_THINKING,
                           quick_math_round)
from puzzly.puzzles.quick_math import MAX_ANSWER, MAX_SMALL_FACTOR, SHAPE_POOL, TIERS, evaluate, generate, shape_errors, tier_for
from puzzly.visuals.quick_math import schedule
from puzzly.renderer import render_cover, render_frame
from puzzly.validation import validation_errors


def _check_round(item) -> None:
    data = item.data
    tier = TIERS[data["tier"]]
    values = {entry["name"]: entry["value"] for entry in data["shapes"]}
    assert data["format"] == "shapes" and shape_errors(data, item.answer) == []
    assert len(data["shapes"]) == tier["shapes"] == len(data["clues"])
    assert {entry["shape"] for entry in data["shapes"]} <= set(SHAPE_POOL)
    known: set[str] = set()
    for slot, clue in enumerate(data["clues"]):  # every clue unlocks exactly one new shape
        used = set(clue["terms"][0::2])
        assert used - known == {f"s{slot}"}
        known |= used
        assert evaluate(clue["terms"], values) == clue["result"]
    terms = data["question"]["terms"]
    assert set(terms[0::2]) == set(values) and evaluate(terms, values) == item.answer >= 0
    assert item.answer not in values.values() and item.answer <= MAX_ANSWER
    for row in [clue["terms"] for clue in data["clues"]] + [terms]:  # no products like 11 × 12
        for position, op in enumerate(row[1::2]):
            left, right = row[2 * position], row[2 * position + 2]
            if op == "×" and left != right:
                assert min(values[left], values[right]) <= MAX_SMALL_FACTOR
    if tier["trap"]:
        assert evaluate(terms, values, precedence=False) != item.answer == evaluate(terms, values)
        assert data["hint_shape"] == f"s{tier['shapes'] - 1}"  # halfway hint: the hardest shape
    else:
        assert data["hint_shape"] is None


def test_shape_equations_volume_levels_and_traps() -> None:
    counts = {"easy": 300, "medium": 400, "hard": 500}
    tiers: Counter[int] = Counter()
    for difficulty, count in counts.items():
        for seed in range(count):
            spec = generate(seed, difficulty)
            assert validation_errors(spec) == []
            assert spec.round_count == DEFAULT_ROUNDS["quick_math"] == 3
            assert [item.data["tier"] for item in spec.rounds] == [0, 2, 3]
            assert len({item.answer for item in spec.rounds}) == 3
            times = [item.data["thinking_seconds"] for item in spec.rounds]
            assert times == sorted(times) and max(times) <= 15 and times == [QUICK_MATH_THINKING[difficulty][tier] for tier in (0, 2, 3)]
            levels = schedule(spec)
            assert levels[0][0] == PUZZLE_FIT_INTRO_DURATION
            assert [duration for _, duration in levels] == [quick_math_round(difficulty, tier) for tier in (0, 2, 3)]
            assert abs(spec.total_duration - (levels[-1][0] + levels[-1][1] + PUZZLE_FIT_OUTRO_DURATION)) < .002
            for item in spec.rounds:
                _check_round(item)
                tiers[item.data["tier"]] += 1
    assert set(tiers) == {0, 2, 3}
    assert all(value <= 15 for levels in QUICK_MATH_THINKING.values() for value in levels)


def test_manual_round_counts_keep_the_level_ramp() -> None:
    assert [tier_for(index, 3) for index in range(3)] == [0, 2, 3]
    assert [tier_for(index, 5) for index in range(5)] == [0, 1, 2, 2, 3]
    for count in (3, 4, 5):
        spec = generate(11, "hard", round_count=count)
        assert spec.round_count == count and validation_errors(spec) == []
        assert [item.data["tier"] for item in spec.rounds] == [tier_for(index, count) for index in range(count)]


def test_order_of_operations_evaluator() -> None:
    values = {"s0": 2, "s1": 3, "s2": 4}
    assert evaluate(["s0", "+", "s1", "×", "s2"], values) == 14
    assert evaluate(["s0", "+", "s1", "×", "s2"], values, precedence=False) == 20
    assert evaluate(["s2", "÷", "s0", "−", "s1"], values) == -1
    assert evaluate(["s1", "÷", "s0"], values) is None  # inexact division is rejected


def test_quick_math_is_deterministic_and_rejects_tampering() -> None:
    first = generate(9876, "hard")
    assert first == generate(9876, "hard")
    item = first.rounds[-1]
    assert shape_errors(item.data, item.answer + 1)
    broken = {**item.data, "clues": item.data["clues"][:-1]}
    assert shape_errors(broken, item.answer)


def test_frames_and_cover_render() -> None:
    spec = generate(21, "hard")
    start, duration = schedule(spec)[-1]
    for moment in (.5, 2.0, start + duration - 3.2, start + duration - .5, spec.total_duration - .2):
        assert render_frame(spec, moment, (540, 960)).size == (540, 960)
    assert render_cover(spec).size == (1080, 1920)


def test_missing_operators_have_exactly_one_solution_and_traps() -> None:
    from puzzly.puzzles.quick_math import OPERATOR_TIERS, operator_errors, operator_solutions
    for difficulty, count in (("easy", 150), ("medium", 150), ("hard", 300)):
        for seed in range(count):
            spec = generate(seed, difficulty, "operators")
            assert spec.operation == "operators" and validation_errors(spec) == []
            assert [item.data["tier"] for item in spec.rounds] == [0, 2, 3]
            assert [item.data["thinking_seconds"] for item in spec.rounds] == [QUICK_MATH_THINKING[difficulty][t] for t in (0, 2, 3)]
            for item in spec.rounds:
                data = item.data
                tier = OPERATOR_TIERS[data["tier"]]
                assert operator_errors(data, item.answer, difficulty) == []
                assert operator_solutions(data["numbers"], tier["ops"], data["target"]) == [tuple(data["operators"])]
                assert item.answer == "".join(data["operators"]) and 0 <= data["target"] <= 150
                if tier["trap"]:
                    assert data["left_to_right"] != data["target"]
                    assert data["operators"][data["hint_slot"]] in ("×", "÷")
                    assert all(op in ("+", "−") for op in data["operators"][:data["hint_slot"]])
                else:
                    assert data["hint_slot"] is None
                assert not any(op == "÷" and a == b for op, a, b in zip(data["operators"], data["numbers"], data["numbers"][1:]))
            assert "÷" in spec.rounds[-1].data["operators"]
    first = generate(5, "hard", "operators").rounds[-1]
    assert operator_errors({**first.data, "operators": ["+"] * len(first.data["operators"])}, first.answer)


def test_missing_operator_frames_render() -> None:
    spec = generate(8, "hard", "operators")
    start, duration = schedule(spec)[-1]
    for moment in (.5, 3.0, start + duration - 3.2, start + duration - .5, spec.total_duration - .2):
        assert render_frame(spec, moment, (540, 960)).size == (540, 960)
    assert render_cover(spec).size == (1080, 1920)
