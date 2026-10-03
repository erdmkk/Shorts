"""Find the Exit, shaped mazes: a hexagon, a star, and a diamond (start in the middle, exits around the rim)."""
from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
import pytest

from puzzly.generator import generate_spec
from puzzly.puzzles import exit_shapes
from puzzly.puzzles.exit_shapes import SHAPES, SIZES, TIERS, layout_of, rules_for
from puzzly.puzzles.find_the_exit import generate, hard_average_round, routes
from puzzly.validation import round_errors, validate_spec, validation_errors


def test_every_shape_is_a_clean_cell_graph_inscribed_in_the_plate() -> None:
    expected = {"hex": [91, 127, 169, 217, 271], "star": [108, 192, 192, 300, 432],
                "diamond": [81, 121, 169, 225, 289]}
    for shape in SHAPES:
        counts = []
        for size in SIZES[shape]:
            layout = layout_of(shape, size)
            counts.append(layout.total)
            assert max(math.hypot(x, y) for polygon in layout.polygons for x, y in polygon) <= exit_shapes.OUTER + 1.0
            assert all(layout.adj[b].count(a) == 1 for a in range(layout.total) for b in layout.adj[a])  # symmetric
            connected = routes(layout.start, [[a, b] for a in range(layout.total) for b in layout.adj[a] if a < b])
            assert len(connected) == layout.total  # one piece
            assert layout.start not in layout.rim and len(layout.rim) >= 24
            assert layout.depth[layout.start] < .13 and layout.unit >= 24
        assert counts == expected[shape], shape


def test_shaped_videos_are_valid_hard_and_escalate() -> None:
    for shape in SHAPES:
        for seed in range(4):
            spec = generate(seed, "hard", round_count=4, shape=shape)
            validate_spec(spec)
            assert spec == generate(seed, "hard", round_count=4, shape=shape)
            assert [item.data["shape"] for item in spec.rounds] == [shape] * 4
            assert [item.data["tier"] for item in spec.rounds] == [0, 1, 2, 3]
            assert [len(item.data["exits"]) for item in spec.rounds] == [4, 4, 4, 5]  # the user's rule: 4, then 5 exits
            assert spec.round_duration == hard_average_round(spec.rounds)
            cells = [layout_of(shape, item.data["size"]).total for item in spec.rounds]
            assert cells == sorted(cells)
            for item in spec.rounds:
                data = item.data
                layout = layout_of(shape, data["size"])
                assert data["start"] == layout.start and sum(layout.start in edge for edge in data["edges"]) == 1  # one opening
                reachable = routes(data["start"], data["edges"])
                assert [i for i, node in enumerate(data["exits"]) if node in reachable] == [item.answer]
                assert data["route"] == reachable[data["exits"][item.answer]]
                assert len(data["route"]) >= rules_for(shape, data["tier"])["min_route"] or data["rules"]["min_route"] <= len(data["route"])
                for node in data["exits"]:  # an exit is a leaf that opens inward
                    assert sum(node in pair for pair in data["edges"]) == 1 and layout.outer_edges[node]
                angles = [layout.angle[node] for node in data["exits"]]
                assert angles == sorted(angles)
    # Level 5 has five exits and the hardest size.
    spec = generate(2, "hard", round_count=5, shape="hex")
    assert [len(item.data["exits"]) for item in spec.rounds] == [4, 4, 4, 5, 5]
    assert [item.data["size"] for item in spec.rounds] == list(SIZES["hex"])


def test_straight_seams_are_limited_so_sealed_regions_stay_hidden() -> None:
    for shape in ("star", "diamond"):
        item = generate(5, "hard", round_count=3, shape=shape).rounds[2]
        layout = layout_of(shape, item.data["size"])
        assert exit_shapes.longest_straight_wall(layout, item.data["edges"]) <= exit_shapes.MAX_STRAIGHT[shape]


def test_every_false_exit_digs_deep_and_cannot_be_ruled_out() -> None:
    for shape in SHAPES:
        item = generate(6, "hard", round_count=4, shape=shape).rounds[3]
        data = item.data
        layout = layout_of(shape, data["size"])
        quota = round(exit_shapes.DECOY_QUOTA * (layout.total - len(data["route"])) / (len(data["exits"]) - 1))
        for position, node in enumerate(data["exits"]):
            if position == item.answer:
                continue
            region = set(routes(node, data["edges"]))
            assert exit_shapes.region_reach(region, layout) >= exit_shapes.DECOY_REACH
            assert len(region) >= exit_shapes.MIN_DECOY_SHARE * quota


def test_a_broken_shaped_maze_is_rejected() -> None:
    item = generate(5, "hard", round_count=3, shape="star").rounds[0]
    data = item.data
    layout = layout_of("star", data["size"])
    assert round_errors(replace(item, answer=(item.answer + 1) % len(data["exits"])), "hard")
    extra = next(other for other in layout.adj[data["exits"][0]] if other != layout.inward(data["exits"][0]))
    assert round_errors(replace(item, data={**data, "edges": sorted([*data["edges"], sorted((data["exits"][0], extra))])}), "hard")
    assert round_errors(replace(item, data={**data, "shape": "heptagon"}), "hard")
    assert round_errors(replace(item, data={**data, "size": 99}), "hard")
    assert round_errors(replace(item, data={**data, "exits": list(reversed(data["exits"]))}), "hard")  # not clockwise
    opened = [edge for edge in data["edges"] if layout.start not in edge]
    assert round_errors(replace(item, data={**data, "edges": opened}), "hard")


def test_retuning_never_invalidates_a_made_video(monkeypatch) -> None:
    spec = generate(3, "hard", round_count=3, shape="hex")
    monkeypatch.setattr(exit_shapes, "TIERS", tuple({**tier, "runs": 99, "waypoints": ()} for tier in TIERS))
    assert validation_errors(spec) == []  # a made video validates against the rules it stored


def test_frames_cover_audio_and_the_arrow_for_every_shape() -> None:
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    from puzzly.config import EXIT_HARD_ENTRANCE, EXIT_HARD_TRACE
    from puzzly.renderer import render_cover, render_frame
    from puzzly.visuals.find_the_exit import cells_layout, cells_xy, route_polyline, schedule
    for shape in SHAPES:
        spec = generate_spec("find_the_exit", 5, "hard", challenges=3, maze_shape=shape)
        start, _ = schedule(spec)[0]
        item = spec.rounds[0]
        think = EXIT_HARD_ENTRANCE + item.data["thinking_seconds"]
        board = np.asarray(render_frame(spec, start + 1.5, (540, 960))).astype(int)
        traced = np.asarray(render_frame(spec, start + think + 1.0, (540, 960))).astype(int)
        assert np.abs(board - traced).mean() > 1.0  # the neon trace appears
        points = route_polyline(item)
        layout = cells_layout(item.data)
        assert math.dist(points[0], cells_xy(layout.centers[item.data["start"]])) < 1.0
        steps = [math.dist(a, b) for a, b in zip(points, points[1:])]
        assert max(steps) <= 12  # dense, no long cuts across cells
        assert render_cover(spec).size == (1080, 1920)
        audio = timeline_audio(spec)
        assert 0.03 < np.abs(audio).max() <= MIX_PEAK_LIMIT + 1e-9


def test_the_selector_offers_every_shape_and_mixed_includes_the_new_ones() -> None:
    from streamlit.testing.v1 import AppTest
    from puzzly.puzzles.find_the_exit import level_layouts
    app = AppTest.from_file("app.py").run()
    app.selectbox[0].select("Find the Exit").run()
    shape = next(box for box in app.selectbox if box.label == "Labirent şekli")
    assert shape.options == ["Dikdörtgen", "Daire", "Altıgen", "Yıldız", "Elmas", "Karışık (rastgele)"]
    for choice in ("hex", "star", "diamond", "mixed"):
        shape.select(choice).run()
        assert not app.exception
    drawn = {kind for seed in range(40) for kind in level_layouts(4, "mixed", seed)}
    assert {"hex", "star", "diamond", "rect", "circle"} == drawn
    spec = generate_spec("find_the_exit", 12, "hard", challenges=3, maze_shape="mixed")
    assert validation_errors(spec) == [] and len({item.data.get("shape", item.data["layout"]) for item in spec.rounds}) == 3


def test_a_five_level_mixed_video_uses_every_shape_once_and_gets_harder() -> None:
    from puzzly.puzzles.find_the_exit import SINGLE_SHAPES, level_layouts
    orders = set()
    for seed in range(40):
        layouts = level_layouts(5, "mixed", seed)
        assert sorted(layouts) == sorted(SINGLE_SHAPES)  # rectangle, circle, hexagon, star, diamond: one each
        orders.add(tuple(layouts))
    assert len(orders) > 10  # the order is random
    spec = generate_spec("find_the_exit", 4, "hard", challenges=5, maze_shape="mixed")
    assert validation_errors(spec) == []
    assert [item.data["level"] for item in spec.rounds] == [1, 2, 3, 4, 5]
    thinking = [item.data["thinking_seconds"] for item in spec.rounds]
    assert thinking == sorted(thinking) and thinking[0] < thinking[-1]  # difficulty follows the level, whatever the shape


def test_shaped_mazes_have_a_frame_in_their_own_shape_not_a_round_plate() -> None:
    from puzzly.renderer import render_frame
    from puzzly.visuals.find_the_exit import schedule
    for shape in SHAPES:
        spec = generate_spec("find_the_exit", 5, "hard", challenges=3, maze_shape=shape)
        start, _ = schedule(spec)[0]
        frame = np.asarray(render_frame(spec, start + 1.5, (540, 960))).astype(int)
        # The corners of the old circular plate's bounding square (just inside the circle's corner) are plain background for
        # a shape whose own frame does not fill them: the diamond leaves them empty and the hexagon and star do too.
        plate_corner = frame[905 // 2 - 235:905 // 2 - 215, 540 // 2 - 235:540 // 2 - 215].mean()
        background = frame[40:60, 20:40].mean()
        assert abs(plate_corner - background) < 40, shape
