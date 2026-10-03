"""Find the Exit, circular mazes (Hard): the start in the middle, four or five exits around the rim."""
import math
from dataclasses import replace

import numpy as np

from puzzly.config import EXIT_HARD_ENTRANCE, EXIT_HARD_TRACE
from puzzly.generator import generate_spec
from puzzly.puzzles import exit_polar
from puzzly.puzzles.find_the_exit import generate, hard_average_round, level_layouts, routes
from puzzly.validation import round_errors, validation_errors


def test_sector_counts_keep_cells_the_same_shape_from_the_middle_to_the_rim() -> None:
    for rings in range(3, 11):
        counts = exit_polar.sector_counts(rings)
        assert counts[0] == 8 and len(counts) == rings
        assert all(b in (a, 2 * a) for a, b in zip(counts, counts[1:]))  # equal or doubling
        height = exit_polar.ring_height(rings)
        for ring, count in enumerate(counts, start=1):
            length = 2 * math.pi * (exit_polar.CENTRE + (ring - .5) * height) / count
            assert length <= exit_polar.ASPECT * height * 1.4 or ring == 1  # no needle-thin corridors
    sizes = [exit_polar.build_graph(tuple(exit_polar.sector_counts(rings)))["total"] for rings in (5, 6, 7, 8, 9)]
    assert sizes == sorted(sizes) and 90 <= sizes[0] <= 130 and sizes[-1] >= 250  # about as many cells as the rectangular levels


def test_graph_is_symmetric_and_every_cell_has_an_inward_neighbour() -> None:
    sectors = tuple(exit_polar.sector_counts(7))
    graph = exit_polar.build_graph(sectors)
    for node, others in enumerate(graph["adj"]):
        assert all(node in graph["adj"][other] for other in others)
        if node:
            inward = exit_polar.inward_of(graph, node)
            assert graph["ring"][inward] == graph["ring"][node] - 1
    assert len(graph["adj"][0]) == sectors[0]  # the middle touches every cell of the first ring


def test_circle_videos_have_four_then_five_exits_and_validate() -> None:
    for seed in (3, 11):
        spec = generate(seed, "hard", round_count=5, shape="circle")
        assert validation_errors(spec) == []
        assert [item.data["rings"] for item in spec.rounds] == [5, 6, 7, 8, 9]  # more rings, tighter corridors, longer routes
        assert [len(item.data["exits"]) for item in spec.rounds] == [4, 4, 4, 5, 5]  # the user's rule
        assert [item.data["thinking_seconds"] for item in spec.rounds] == [6.0, 7.0, 8.0, 9.0, 10.0]
        assert spec.round_duration == hard_average_round(spec.rounds)
        lengths = [len(item.data["route"]) for item in spec.rounds]
        assert lengths == sorted(lengths) and len(set(lengths)) == len(lengths)
        for item in spec.rounds:
            data = item.data
            assert data["layout"] == "polar_v1" and data["start"] == 0 and exit_polar.errors(data, item.answer) == []
            reachable = routes(0, data["edges"])
            assert [index for index, node in enumerate(data["exits"]) if node in reachable] == [item.answer]  # one open exit
            graph = exit_polar.build_graph(tuple(data["sectors"]))
            assert all(graph["ring"][node] == data["rings"] for node in data["exits"])
            assert exit_polar.radial_runs(data["route"], graph["ring"]) >= 3  # the route goes out and back in: no plain spiral
            assert exit_polar.longest_arc_wall(data["edges"], tuple(data["sectors"]), graph) <= exit_polar.MAX_ARC_WALL
            # Tracing back from a false exit is as long as solving from the start: its region digs well toward the middle.
            for index, node in enumerate(data["exits"]):
                if index != item.answer:
                    assert exit_polar.region_reach(set(routes(node, data["edges"])), graph, data["rings"]) >= exit_polar.DECOY_REACH
    assert generate(3, "hard", round_count=5, shape="circle") == generate(3, "hard", round_count=5, shape="circle")


def test_mixed_videos_draw_a_different_shape_for_every_level() -> None:
    from collections import Counter
    from puzzly.puzzles.find_the_exit import SINGLE_SHAPES
    assert level_layouts(3, "rect") == ["rect"] * 3 and level_layouts(4, "hex") == ["hex"] * 4
    seen = Counter()
    for seed in range(60):
        layouts = level_layouts(5, "mixed", seed)
        assert layouts == level_layouts(5, "mixed", seed) and len(set(layouts)) == 5  # random, seeded, no shape twice
        seen.update(layouts)
    assert set(seen) == set(SINGLE_SHAPES) and min(seen.values()) > 20  # every shape comes up
    assert all(first != second for first, second in zip(level_layouts(9, "mixed", 4), level_layouts(9, "mixed", 4)[1:]))
    spec = generate_spec("find_the_exit", 8, "hard", challenges=3, maze_shape="mixed")
    assert validation_errors(spec) == []
    exits = {"deceptive_v2": [3, 3, 3, 4, 4], "polar_v1": [4, 4, 4, 5, 5], "cells_v1": [4, 4, 4, 5, 5]}
    assert [len(item.data["exits"]) for item in spec.rounds] == [exits[item.data["layout"]][index] for index, item in enumerate(spec.rounds)]
    assert spec.round_duration == hard_average_round(spec.rounds)
    plain = generate_spec("find_the_exit", 8, "hard")  # the default is still the rectangular video
    assert all(item.data["layout"] == "deceptive_v2" for item in plain.rounds) and plain != spec


def test_a_broken_circular_maze_is_rejected() -> None:
    item = generate(5, "hard", round_count=3, shape="circle").rounds[0]
    data = item.data
    assert round_errors(replace(item, answer=(item.answer + 1) % len(data["exits"])), "hard")
    extra = next(other for other in exit_polar.build_graph(tuple(data["sectors"]))["adj"][data["exits"][0]]
                 if other != exit_polar.inward_of(exit_polar.build_graph(tuple(data["sectors"])), data["exits"][0]))
    assert round_errors(replace(item, data={**data, "edges": sorted([*data["edges"], sorted((data["exits"][0], extra))])}), "hard")
    assert round_errors(replace(item, data={**data, "edges": data["edges"][:-1]}), "hard")  # a missing passage
    assert round_errors(replace(item, data={**data, "route": data["route"][:3]}), "hard")
    assert round_errors(replace(item, data={**data, "start": 5}), "hard")
    assert round_errors(replace(item, data={**data, "sectors": [8, 12, 12, 12, 12]}), "hard")  # not equal or doubling


def test_walls_leave_one_gap_per_exit_in_the_outer_ring() -> None:
    from puzzly.visuals.find_the_exit import POLAR_CENTRE, polar_geometry, polar_walls
    item = generate(5, "hard", round_count=3, shape="circle").rounds[1]
    geometry = polar_geometry(item.data)
    outer = [wall for wall in polar_walls(item.data, geometry) if len(wall) > 2
             and abs(math.dist(wall[0], POLAR_CENTRE) - exit_polar.OUTER) < 1.0]
    assert len(outer) == len(item.data["exits"])  # the outer wall is cut open exactly where the exits are


def test_frames_show_the_middle_start_the_rim_exits_and_the_trace() -> None:
    from puzzly.renderer import render_cover, render_frame
    from puzzly.visuals.find_the_exit import exit_position, route_polyline, schedule
    spec = generate_spec("find_the_exit", 5, "hard", challenges=3, maze_shape="circle")
    start, _ = schedule(spec)[1]
    item = spec.rounds[1]
    think = EXIT_HARD_ENTRANCE + item.data["thinking_seconds"]
    thinking = np.asarray(render_frame(spec, start + 1.5, (540, 960))).astype(int)
    tracing = np.asarray(render_frame(spec, start + think + EXIT_HARD_TRACE * .6, (540, 960))).astype(int)
    solved = np.asarray(render_frame(spec, start + think + EXIT_HARD_TRACE + .5, (540, 960))).astype(int)
    plate = (slice(190, 735), slice(10, 530))
    assert np.abs(thinking[plate] - tracing[plate]).mean() > 1.5 and np.abs(tracing[plate] - solved[plate]).mean() > .5
    points = route_polyline(item)
    assert math.dist(points[0], (540, 905)) < 1 and math.dist(points[-1], exit_position(item)) < 1  # centre to the exit
    assert render_cover(spec).size == (1080, 1920)
    assert np.asarray(render_frame(spec, 0.5, (540, 960))).shape == (960, 540, 3)  # the hook shows level one's circle


def test_audio_is_safe_and_the_ui_offers_the_three_shapes() -> None:
    from streamlit.testing.v1 import AppTest
    from puzzly.audio import MIX_PEAK_LIMIT, timeline_audio
    spec = generate_spec("find_the_exit", 5, "hard", challenges=3, maze_shape="circle")
    audio = timeline_audio(spec)
    assert audio.shape[0] == round(spec.total_duration * 48000) and 0.03 < np.abs(audio).max() <= MIX_PEAK_LIMIT + 1e-9
    app = AppTest.from_file("app.py").run()
    app.selectbox[0].select("Find the Exit").run()
    assert not app.exception
    shape = next(box for box in app.selectbox if box.label == "Labirent şekli")
    assert shape.options == ["Dikdörtgen", "Daire", "Altıgen", "Yıldız", "Elmas", "Karışık (rastgele)"] and shape.value == "rect"
    shape.select("circle").run()
    assert not app.exception


def test_the_middle_has_one_opening_and_the_arrow_points_at_it() -> None:
    from PIL import Image
    from puzzly.config import PUZZLE_FIT_PALETTE
    from puzzly.visuals.find_the_exit import POLAR_CENTRE, _start_orb, polar_geometry, polar_node_center
    spec = generate_spec("find_the_exit", 7, "hard", challenges=3, maze_shape="circle")
    for item in spec.rounds:
        data = item.data
        assert sum(0 in edge for edge in data["edges"]) == 1 and data["route"][1] in exit_polar.build_graph(tuple(data["sectors"]))["adj"][0]
        # The arrow's heading is the direction of the opening: from the middle toward the route's first cell.
        geometry = polar_geometry(data)
        x, y = polar_node_center(geometry, data["route"][1])
        toward = math.atan2(x - POLAR_CENTRE[0], -(y - POLAR_CENTRE[1])) % (2 * math.pi)
        assert abs(toward - exit_polar.angle_of(tuple(data["sectors"]), geometry["graph"], data["route"][1])) < 1e-6
    background = tuple(int(PUZZLE_FIT_PALETTE["background"][i:i + 2], 16) for i in (1, 3, 5))

    def pointing(heading: float) -> tuple[int, int]:
        """The arrow's tip: its pixel farthest from the orb's middle (the shaft's corners are nearer than the tip)."""
        canvas = Image.new("RGB", (200, 200), (0, 0, 0))
        _start_orb(canvas, (100, 100), 50, 0.0, heading, arrow=True)
        pixels = [(x - 100, y - 100) for x in range(200) for y in range(200) if canvas.getpixel((x, y)) == background]
        return max(pixels, key=lambda point: math.hypot(*point))

    assert pointing(0.0)[1] < -35 and abs(pointing(0.0)[0]) < 5  # up
    assert pointing(math.pi / 2)[0] > 35 and abs(pointing(math.pi / 2)[1]) < 5  # right
    assert pointing(math.pi)[1] > 35 and abs(pointing(math.pi)[0]) < 5  # down
    assert pointing(1.5 * math.pi)[0] < -35 and abs(pointing(1.5 * math.pi)[1]) < 5  # left


def test_each_level_has_a_short_caption_that_fades_when_the_trace_starts() -> None:
    from puzzly.renderer import render_frame
    from puzzly.visuals.find_the_exit import CAPTIONS, caption_y, level_caption, schedule
    assert [level_caption(index, 5) for index in range(5)] == [CAPTIONS[0], CAPTIONS[1], CAPTIONS[2], CAPTIONS[3], CAPTIONS[4]]
    assert level_caption(0, 3) == CAPTIONS[0] and level_caption(2, 3) == CAPTIONS[4] and level_caption(1, 3) == CAPTIONS[1]
    assert all(len(text) <= 28 and not any(char.isdigit() or char == "%" for char in text) for text in CAPTIONS)  # short, no statistics
    spec = generate_spec("find_the_exit", 5, "hard", challenges=3, maze_shape="circle")
    start, _ = schedule(spec)[0]
    item = spec.rounds[0]
    think = EXIT_HARD_ENTRANCE + item.data["thinking_seconds"]
    y = round(caption_y(item.data) / 2)  # Draft pixels
    band = (slice(y - 22, y + 22), slice(80, 460))
    shown = np.asarray(render_frame(spec, start + 2.0, (540, 960))).astype(int)[band]
    gone = np.asarray(render_frame(spec, start + think + 1.0, (540, 960))).astype(int)[band]
    assert np.abs(shown - gone).mean() > 3  # the line is there while thinking and gone once the trace sets off
    quiet = replace(spec, metadata={**spec.metadata, "captions": "off"})  # the long video turns it off
    off = np.asarray(render_frame(quiet, start + 2.0, (540, 960))).astype(int)[band]
    assert np.abs(off - gone).mean() < 2
    assert caption_y(item.data) + 40 < 1700  # clear of the bottom edge of the frame
    rectangle = generate_spec("find_the_exit", 5, "hard", challenges=3)
    assert caption_y(rectangle.rounds[0].data) < 1700  # rectangular mazes get one too


def test_the_trace_follows_the_corridors_with_smooth_corners() -> None:
    from puzzly.visuals.find_the_exit import POLAR_CENTRE, route_polyline
    spec = generate_spec("find_the_exit", 7, "hard", challenges=5, maze_shape="circle")
    for item in spec.rounds:
        points = route_polyline(item)
        assert math.dist(points[0], POLAR_CENTRE) < 1
        steps = [math.dist(a, b) for a, b in zip(points, points[1:])]
        assert max(steps) <= 12  # dense: no long cut across cells
        headings = [math.atan2(b[1] - a[1], b[0] - a[0]) for a, b in zip(points, points[1:]) if math.dist(a, b) > 1e-6]
        turns = [abs((second - first + math.pi) % (2 * math.pi) - math.pi) for first, second in zip(headings, headings[1:])]
        assert max(turns) < math.radians(50)  # corners are rounded: no kinks
        assert all(math.dist(point, POLAR_CENTRE) <= exit_polar.OUTER + 42 for point in points)
