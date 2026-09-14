from collections import Counter

from puzzly.puzzles.missing_number import generate
from puzzly.validation import validation_errors


def _check_spec(spec) -> None:
    assert len(spec.rounds) == 5
    assert len({round_spec.fingerprint() for round_spec in spec.rounds}) == 5
    assert validation_errors(spec) == []
    assert len({(item.data["sequence_family"], item.data["step_or_ratio"]) for item in spec.rounds}) == 5
    assert len({item.data["hidden_index"] for item in spec.rounds}) > 1
    for item in spec.rounds:
        data, sequence = item.data, item.data["sequence"]
        family, value = data["sequence_family"], data["step_or_ratio"]
        assert data["hidden_index"] in (1, 2, 3)
        assert sum(entry is None for entry in data["shown"]) == 1
        assert item.answer == sequence[data["hidden_index"]]
        assert 0 <= min(sequence) <= max(sequence) <= 999
        if family == "addition":
            assert all(b - a == value for a, b in zip(sequence, sequence[1:]))
        elif family == "subtraction":
            assert all(a - b == value for a, b in zip(sequence, sequence[1:]))
        else:
            assert value in ((2,) if spec.difficulty == "medium" else (2, 3, 4, 5))
            assert all(b == a * value for a, b in zip(sequence, sequence[1:]))


def test_v7_missing_number_volume_correctness_and_distributions() -> None:
    requested = {"easy": 300, "medium": 400, "hard": 500}
    totals = {difficulty: Counter() for difficulty in requested}
    for difficulty, count in requested.items():
        for seed in range(count):
            spec = generate(seed, difficulty)
            _check_spec(spec)
            totals[difficulty].update(item.data["sequence_family"] for item in spec.rounds)
    assert totals["easy"] == {"addition": 1200, "subtraction": 300}
    assert totals["medium"] == {"addition": 800, "subtraction": 800, "multiplication": 400}
    assert totals["hard"] == {"addition": 500, "subtraction": 1000, "multiplication": 1000}


def test_missing_number_is_deterministic() -> None:
    assert generate(4123, "hard", round_count=5) == generate(4123, "hard", round_count=5)
