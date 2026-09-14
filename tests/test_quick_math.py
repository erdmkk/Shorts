from collections import Counter
from dataclasses import replace

import numpy as np

from puzzly.puzzles.quick_math import OPERATIONS, allowed_operations, allowed_positions, generate
from puzzly.validation import validation_errors
from puzzly.renderer import render_cover, render_frame


def _check_spec(spec) -> None:
    assert len(spec.rounds) == 5
    assert len({round_spec.fingerprint() for round_spec in spec.rounds}) == 5
    assert validation_errors(spec) == []
    for item in spec.rounds:
        data = item.data
        a, b, result, operation = data["a"], data["b"], data["result"], data["operation"]
        assert operation in allowed_operations(spec.difficulty)
        assert data["unknown_position"] in allowed_positions(operation, spec.difficulty)
        assert data["equation_template"] == f'{operation}_{data["unknown_position"]}'
        assert data["symbol"] in ("+", "−", "×")
        assert result == ({"addition": a + b, "subtraction": a - b, "multiplication": a * b}[operation])
        assert item.answer == {"left": a, "right": b, "result": result}[data["unknown_position"]]
        assert isinstance(item.answer, int) and item.answer >= 0
        if operation == "multiplication":
            assert min(a, b) >= 2


def test_v7_quick_math_volume_correctness_and_distributions() -> None:
    counts = {"easy": 300, "medium": 400, "hard": 500}
    positions = {level: Counter() for level in counts}
    operations = {level: Counter() for level in counts}
    for difficulty, count in counts.items():
        for seed in range(count):
            spec = generate(seed, difficulty, "mixed")
            _check_spec(spec)
            positions[difficulty].update(item.data["unknown_position"] for item in spec.rounds)
            operations[difficulty].update(item.data["operation"] for item in spec.rounds)
    assert set(operations["easy"]) == {"addition", "subtraction"}
    assert "multiplication" not in operations["easy"]
    assert set(operations["medium"]) == set(OPERATIONS) == set(operations["hard"])
    assert set(positions["easy"]) == {"left", "right", "result"}
    assert set(positions["medium"]) == set(positions["hard"]) == {"left", "right", "result"}


def test_explicit_operations_and_template_variety() -> None:
    for difficulty in ("easy", "medium", "hard"):
        for operation in allowed_operations(difficulty):
            for seed in range(30):
                spec = generate(seed, difficulty, operation)
                _check_spec(spec)
                assert {item.data["operation"] for item in spec.rounds} == {operation}
                if len(allowed_positions(operation, difficulty)) > 1:
                    assert len({item.data["unknown_position"] for item in spec.rounds}) > 1


def test_quick_math_is_deterministic() -> None:
    assert generate(9876, "hard", "mixed", 5) == generate(9876, "hard", "mixed", 5)


def test_intro_is_concept_only_and_does_not_depend_on_first_question() -> None:
    spec = generate(9876, "hard", "mixed", 5)
    different_rounds = generate(7654, "hard", "mixed", 5).rounds
    changed = replace(spec, rounds=different_rounds)
    assert np.array_equal(np.asarray(render_frame(spec, .9, (540, 960))),
                          np.asarray(render_frame(changed, .9, (540, 960))))
    assert np.array_equal(np.asarray(render_cover(spec)), np.asarray(render_cover(changed)))
