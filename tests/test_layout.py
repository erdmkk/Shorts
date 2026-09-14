from puzzly.visuals.layout import Bounds, bounds_inside, center_offset, centered_x_positions, no_box_overlaps, union_bounds


def test_centered_group_is_within_twenty_pixels() -> None:
    widths = [120, 150, 105, 130, 115]
    centers = centered_x_positions(widths, 25)
    boxes = [Bounds(center - width / 2, 650, center + width / 2, 790) for center, width in zip(centers, widths)]
    group = union_bounds(boxes)
    assert abs(center_offset(group)) <= 20
    assert bounds_inside(group)
    assert no_box_overlaps(boxes, padding=20)


def test_candidate_cards_are_centered_non_overlapping_and_separate_from_progress() -> None:
    cards = [Bounds(110, 1150, 370, 1490), Bounds(410, 1150, 670, 1490), Bounds(710, 1150, 970, 1490)]
    assert center_offset(union_bounds(cards)) == 0
    assert no_box_overlaps(cards, padding=30)
    progress = Bounds(245, 1550, 835, 1572)
    assert all(not (card.bottom > progress.top) for card in cards)
    hard_cards = [Bounds(110, 1150, 490, 1390), Bounds(590, 1150, 970, 1390),
                  Bounds(110, 1410, 490, 1650), Bounds(590, 1410, 970, 1650)]
    assert center_offset(union_bounds(hard_cards)) == 0
    assert no_box_overlaps(hard_cards, padding=20)
    assert all(card.bottom <= 1650 for card in hard_cards)


def test_missing_number_capsules_fit_and_center() -> None:
    centers = centered_x_positions([150] * 5, 20)
    capsules = [Bounds(center - 75, 740, center + 75, 890) for center in centers]
    assert abs(center_offset(union_bounds(capsules))) <= 20
    assert bounds_inside(union_bounds(capsules))
    assert no_box_overlaps(capsules, padding=15)
