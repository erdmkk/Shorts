import copy

import pytest
from PIL import Image, ImageChops

from puzzly.longform_cover import (LOGICAL_H, LOGICAL_W, _circle_hits_quad, _hero_board, _sticker_spot,
                                    render_longform_thumbnail)
from puzzly.puzzles import quick_math


@pytest.fixture(scope="module")
def rounds():
    return quick_math.generate(7, "hard", "shapes", round_count=10).rounds


def _hero(rounds, tier: int) -> dict:
    return next(item.data for item in rounds if item.data["tier"] == tier)


@pytest.fixture(scope="module")
def violet_hard(rounds):
    return render_longform_thumbnail("violet", _hero(rounds, 3))


def test_thumbnail_is_1920x1080_rgb_for_two_themes_and_tiers(rounds, violet_hard):
    teal_easy = render_longform_thumbnail("teal", _hero(rounds, 0))
    for image in (violet_hard, teal_easy):
        assert isinstance(image, Image.Image)
        assert image.size == (LOGICAL_W, LOGICAL_H) == (1920, 1080)
        assert image.mode == "RGB"
    # The background tone follows the theme.
    assert ImageChops.difference(violet_hard, teal_easy).getbbox() is not None


def test_thumbnail_is_deterministic(rounds, violet_hard):
    again = render_longform_thumbnail("violet", _hero(rounds, 3))
    assert ImageChops.difference(violet_hard, again).getbbox() is None


def test_card_never_depends_on_shape_values_or_answer(rounds):
    for tier in (0, 3):
        hero = _hero(rounds, tier)
        scrambled = copy.deepcopy(hero)
        for entry in scrambled["shapes"]:
            entry["value"] = entry["value"] + 7
        scrambled["left_to_right"] = -1
        colors = ((30, 34, 70), (90, 100, 160))
        first, slot, size, boxes = _hero_board(hero, *colors)
        second, slot_2, size_2, boxes_2 = _hero_board(scrambled, *colors)
        assert (slot, size, boxes) == (slot_2, size_2, boxes_2)
        assert ImageChops.difference(first, second).getbbox() is None


def test_sticker_never_covers_a_clue():
    corner, radius = (2000.0, 700.0), 236.0
    rows = [[(2040.0, 740.0), (3600.0, 700.0), (3600.0, 940.0), (2040.0, 980.0)]]
    headline = (100.0, 400.0, 1500.0, 690.0)
    spot = _sticker_spot(corner, radius, rows, headline)
    assert not _circle_hits_quad(spot, radius, rows[0])
    # An empty top-left corner keeps the sticker right on the card's corner.
    assert _sticker_spot(corner, radius, [], headline) == corner
