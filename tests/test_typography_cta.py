from __future__ import annotations

import inspect

from puzzly import renderer
from puzzly.visuals import bounce_arena, flash_count, hidden_motion, lucky_pick, memory, text


def test_display_font_is_local_and_playful_first() -> None:
    assert text.DISPLAY_FONT_FILES[:2] == ("Inkfree.ttf", "segoeprb.ttf")
    assert text.display_font(42) is text.display_font(42)


def test_short_prompts_and_badges_use_display_font_but_math_does_not() -> None:
    sources = (
        inspect.getsource(flash_count.draw_flash_intro),
        inspect.getsource(renderer._intro_frame),
    )
    assert all("display_font" in source for source in sources)
    equation_source = inspect.getsource(renderer._equation_frame)
    sequence_source = inspect.getsource(renderer._sequence_frame)
    assert "fitted_font" in equation_source and "display_font" not in equation_source
    assert "fitted_font" in sequence_source and "display_font" not in sequence_source


def test_cta_is_shared_across_outro_final_holds_and_loop_overlay() -> None:
    assert "draw_cta" in inspect.getsource(renderer.render_frame)
    assert "draw_puzzle_fit_outro" in inspect.getsource(bounce_arena.draw_bounce_frame)  # shared outro carries the CTA
    assert "draw_puzzle_fit_outro" in inspect.getsource(lucky_pick.draw_lucky_frame)  # shared outro carries the CTA
    assert "draw_puzzle_fit_outro" in inspect.getsource(memory.draw_memory_frame)  # shared outro carries the CTA
    hidden_source = inspect.getsource(hidden_motion.draw_hidden_motion)
    assert "draw_cta" in hidden_source
    assert "overlay_end = HIDDEN_MOTION_DURATION - .20" in hidden_source
