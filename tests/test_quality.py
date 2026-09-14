from puzzly.config import RENDER_QUALITIES


def test_centralized_render_quality_profiles() -> None:
    draft = RENDER_QUALITIES["draft"]
    final = RENDER_QUALITIES["final"]
    assert draft.output_size == (540, 960)
    assert draft.supersampling == 1 and draft.internal_visual_fps == 15
    assert final.output_size == (1080, 1920)
    assert final.internal_size == (2160, 3840)
    assert final.supersampling == 2 and final.internal_visual_fps == 30
    assert final.encoder_preset == "medium" and 16 <= final.crf <= 18
