from dataclasses import replace

import pytest

from puzzly.puzzles.quick_math import generate
from puzzly.validation import InvalidPuzzleError, validate_spec


def test_invalid_math_answer_is_rejected() -> None:
    valid = generate(1)
    bad_round = replace(valid.rounds[0], answer=999)
    invalid = replace(valid, rounds=(bad_round, *valid.rounds[1:]))
    with pytest.raises(InvalidPuzzleError):
        validate_spec(invalid)
