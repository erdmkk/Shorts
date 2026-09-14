from puzzly.puzzles.missing_number import generate as missing_number
from puzzly.puzzles.puzzle_fit import generate as puzzle_fit
from puzzly.puzzles.quick_math import generate as quick_math
from puzzly.renderer import render_frame, _tutorial_round
from puzzly.puzzles.find_the_exit import generate as find_the_exit
from puzzly.puzzles.line_follow import generate as line_follow
from puzzly.puzzles.memory_challenge import generate as memory_challenge


def test_representative_frames_render_at_draft_size() -> None:
    specs = (quick_math(1), missing_number(2), puzzle_fit(3), find_the_exit(4), line_follow(5), memory_challenge(6))
    for spec in specs:
        moments = (0.2, spec.intro_duration + 0.2, spec.intro_duration + spec.round_duration * 0.6, spec.total_duration - 0.2)
        for moment in moments:
            assert render_frame(spec, moment, (540, 960)).size == (540, 960)


def test_tutorial_never_previews_an_actual_round_answer() -> None:
    for spec in (puzzle_fit(7301), find_the_exit(7401), line_follow(7501)):
        excluded = tuple(item.fingerprint() for item in spec.rounds)
        tutorial = _tutorial_round(spec.puzzle_type, spec.seed, excluded)
        assert tutorial.fingerprint() not in excluded
