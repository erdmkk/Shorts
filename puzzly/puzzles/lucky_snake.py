"""Lucky Pick, snake chase: seven targets scatter in an open arena while a neon snake hunts them. Last one left wins.

The chase is a deterministic, seeded simulation run once at generation time (like Bounce Arena). Every target uses
exactly the same dodging behaviour and only the random start layout differs, so no colour or position is favoured.
The snake roams the arena at random, strikes at whatever comes close in front of it, gives up on prey that gets
away, and hunts the nearest target when it has gone hungry. Its turn rate is limited, so it sweeps in arcs and
overshoots: near misses and fake-outs happen on their own. It speeds up and grows with every catch.
"""
from __future__ import annotations

import math
import random
from typing import Any

from ..config import LUCKY_APPEARANCE_DURATION, LUCKY_SELECTION_DURATION, LUCKY_WINNER_HOLD

VERSION = "snake_chase_v1"
TARGET_COUNT = 7
ARENA_CENTER = (540.0, 1000.0)
ARENA_RADIUS = 440.0
TARGET_RADIUS = 40.0  # collision radius; the token is drawn TARGET_SIZE px wide
TARGET_SIZE = 88
TARGET_MAX_SPEED = 250.0
TARGET_ACCEL = 900.0
FLEE_RADIUS = 280.0
SEPARATION = 135.0
SEPARATION_WEIGHT = 1.7  # targets keep clear of each other so every colour stays readable
WALL_MARGIN = 90.0
SNAKE_SPEED = 195.0
SNAKE_SPEED_PER_CATCH = 14.0
SNAKE_STALL_BOOST = 40.0  # px/s added per second without a catch after STALL_AFTER, so no chase drags on
SNAKE_STALL_AFTER = 3.0
SNAKE_STALL_MAX = 160.0
SNAKE_TURN_RATE = 3.4  # rad/s: it sweeps in arcs instead of turning on the spot
SNAKE_STRIKE_TURN_RATE = 4.6  # it is more agile while striking at prey
SNAKE_HEAD_RADIUS = 24.0
SNAKE_BASE_LENGTH = 230.0
SNAKE_LENGTH_PER_CATCH = 55.0
CATCH_DISTANCE = SNAKE_HEAD_RADIUS + TARGET_RADIUS * .75
# Behaviour: it prowls the arena toward random waypoints, strikes at a target that comes close in front of it, gives
# up on one that gets away, and goes hunting for the nearest one when it has not eaten for a while.
PROWL_SPEED = 0.8  # share of its speed while prowling; it surges to full speed when it strikes
WAYPOINT_RADIUS = ARENA_RADIUS * .55
WAYPOINT_TIME = (1.2, 2.4)  # seconds before it picks a new waypoint, if it has not reached this one
WAYPOINT_MIN_DISTANCE = 320.0
CALM_DRIFT = 0.9  # targets are pulled back from the rim into open space
DODGE = 0.6  # share of a target's escape that is a side-step out of the snake's path
STRIKE_RADIUS = 250.0
STRIKE_CONE = math.radians(75)
GIVE_UP_DISTANCE = 400.0
GIVE_UP_AFTER = 1.2
HUNGRY_AFTER = 3.2  # without a catch for this long, it hunts the nearest target
MAX_CHASE = 2.2  # a chase that drags on this long makes it turn on another target
SLITHER = 0.28  # radians of side-to-side sway, so its path is organic rather than geometric
SLITHER_RATE = 1.3
ENTRY = (ARENA_CENTER[0], ARENA_CENTER[1] + ARENA_RADIUS - 30.0)  # the snake emerges from the bottom of the arena
DT = 1 / 120
TIMELINE_FPS = 30
SIM_MIN, SIM_MAX = 9.0, 20.0  # accepted chase lengths (seconds)
FIRST_CATCH_MIN = 1.6
CATCH_GAP_MIN = 0.45
FINAL_DUEL_MIN = 1.2  # the last two targets get at least this long a showdown
MAX_ATTEMPTS = 80
START_SPACING = 150.0
START_RADIUS = ARENA_RADIUS * .72


def _unit(x: float, y: float) -> tuple[float, float, float]:
    length = math.hypot(x, y)
    return (x / length, y / length, length) if length > 1e-9 else (0.0, 0.0, 0.0)


def _layout(rng: random.Random) -> list[list[float]]:
    """Seven random, well-spaced start positions inside the arena, away from the snake's entry."""
    for _ in range(2000):
        points: list[list[float]] = []
        for _ in range(4000):
            angle, radius = rng.uniform(0, 2 * math.pi), START_RADIUS * math.sqrt(rng.random())
            point = [ARENA_CENTER[0] + math.cos(angle) * radius, ARENA_CENTER[1] + math.sin(angle) * radius]
            if math.dist(point, ENTRY) < 240 or any(math.dist(point, other) < START_SPACING for other in points):
                continue
            points.append(point)
            if len(points) == TARGET_COUNT:
                rng.shuffle(points)  # later points fill the leftover gaps; shuffling keeps every index equally likely
                return [[round(x, 2), round(y, 2)] for x, y in points]
    raise RuntimeError("Could not lay out the Lucky Pick targets")


def _run(seed: int, attempt: int) -> dict[str, Any]:
    rng = random.Random(f"{VERSION}:{seed}:{attempt}")
    starts = _layout(rng)
    wander = [(rng.uniform(0, 2 * math.pi), rng.uniform(.6, 1.1), rng.uniform(1.3, 2.1), rng.uniform(0, 6.3), rng.uniform(0, 6.3))
              for _ in range(TARGET_COUNT)]
    alive = {index: {"p": list(point), "v": [0.0, 0.0]} for index, point in enumerate(starts)}
    head = list(ENTRY)
    heading = -math.pi / 2  # straight up
    history: list[tuple[float, float]] = [tuple(head)]
    prey: int | None = None
    hunting = 0.0

    def new_waypoint() -> list[float]:
        for _ in range(50):
            angle, radius = rng.uniform(0, 2 * math.pi), WAYPOINT_RADIUS * math.sqrt(rng.random())
            point = [ARENA_CENTER[0] + math.cos(angle) * radius, ARENA_CENTER[1] + math.sin(angle) * radius]
            if math.dist(point, head) > WAYPOINT_MIN_DISTANCE:  # far away, so it cuts across the arena
                return point
        return list(ARENA_CENTER)

    waypoint = new_waypoint()
    waypoint_left = rng.uniform(*WAYPOINT_TIME)
    catches: list[dict[str, Any]] = []
    frames: list[list[Any]] = []
    elapsed = 0.0
    step = 0
    sample = round((1 / TIMELINE_FPS) / DT)
    last_catch = 0.0

    def speed_now() -> float:
        stall = min(SNAKE_STALL_MAX, SNAKE_STALL_BOOST * max(0.0, elapsed - last_catch - SNAKE_STALL_AFTER))
        return SNAKE_SPEED + SNAKE_SPEED_PER_CATCH * len(catches) + stall

    def length_now() -> float:
        return SNAKE_BASE_LENGTH + SNAKE_LENGTH_PER_CATCH * len(catches)

    def snapshot() -> None:
        frames.append([round(elapsed, 4), round(head[0], 2), round(head[1], 2), round(heading, 4), round(length_now(), 1),
                       [[index, round(item["p"][0], 2), round(item["p"][1], 2)] for index, item in sorted(alive.items())]])

    snapshot()
    while len(alive) > 1 and elapsed < SIM_MAX + 2:
        elapsed += DT
        step += 1
        # --- decide: prowl toward a waypoint, strike at prey in front of it, give up, or hunt when hungry
        def bearing(index: int) -> tuple[float, float]:
            dx, dy = alive[index]["p"][0] - head[0], alive[index]["p"][1] - head[1]
            return math.hypot(dx, dy), abs((math.atan2(dy, dx) - heading + math.pi) % (2 * math.pi) - math.pi)

        hungry = elapsed - last_catch > HUNGRY_AFTER
        if prey is not None and prey not in alive:
            prey = None
            waypoint, waypoint_left = new_waypoint(), rng.uniform(*WAYPOINT_TIME)
        if prey is None:
            in_reach = [index for index in alive if bearing(index)[0] < STRIKE_RADIUS and bearing(index)[1] < STRIKE_CONE]
            if in_reach:
                prey, hunting = min(in_reach, key=lambda index: (bearing(index)[0], index)), 0.0
            elif hungry:
                prey, hunting = min(alive, key=lambda index: (bearing(index)[0] * (1 + .6 * bearing(index)[1] / math.pi), index)), 0.0
        else:
            hunting += DT
            if not hungry and hunting > GIVE_UP_AFTER and bearing(prey)[0] > GIVE_UP_DISTANCE:  # it got away
                prey = None
                waypoint, waypoint_left = new_waypoint(), rng.uniform(*WAYPOINT_TIME)
            elif hunting > MAX_CHASE and len(alive) > 2:  # a long tail-chase: turn on someone else
                others = [index for index in alive if index != prey]
                prey, hunting = min(others, key=lambda index: (bearing(index)[0] * (1 + .6 * bearing(index)[1] / math.pi), index)), 0.0
        # --- steer, with a limited turn rate and a slow side-to-side sway
        if prey is None:
            speed = speed_now() * PROWL_SPEED
            waypoint_left -= DT
            if waypoint_left <= 0 or math.dist(waypoint, head) < 70:
                waypoint, waypoint_left = new_waypoint(), rng.uniform(*WAYPOINT_TIME)
            aim_x, aim_y = waypoint
        else:
            speed = speed_now()
            target = alive[prey]
            dx, dy = target["p"][0] - head[0], target["p"][1] - head[1]
            lead = min(.5, math.hypot(dx, dy) / speed) * .6
            aim_x, aim_y = target["p"][0] + target["v"][0] * lead, target["p"][1] + target["v"][1] * lead
        cx, cy, radius = _unit(head[0] - ARENA_CENTER[0], head[1] - ARENA_CENTER[1])
        if radius > ARENA_RADIUS - 110:  # near the rim it curls back inward
            pull = min(1.0, (radius - (ARENA_RADIUS - 110)) / 70)
            aim_x += (ARENA_CENTER[0] - aim_x) * pull
            aim_y += (ARENA_CENTER[1] - aim_y) * pull
        wanted = math.atan2(aim_y - head[1], aim_x - head[0]) + SLITHER * math.sin(elapsed * 2 * math.pi * SLITHER_RATE)
        turn = (wanted - heading + math.pi) % (2 * math.pi) - math.pi
        rate = (SNAKE_TURN_RATE if prey is None else SNAKE_STRIKE_TURN_RATE) * DT
        heading += max(-rate, min(rate, turn))
        head[0] += math.cos(heading) * speed * DT
        head[1] += math.sin(heading) * speed * DT
        cx, cy, radius = _unit(head[0] - ARENA_CENTER[0], head[1] - ARENA_CENTER[1])
        if radius > ARENA_RADIUS - SNAKE_HEAD_RADIUS:
            head[0] = ARENA_CENTER[0] + cx * (ARENA_RADIUS - SNAKE_HEAD_RADIUS)
            head[1] = ARENA_CENTER[1] + cy * (ARENA_RADIUS - SNAKE_HEAD_RADIUS)
        history.append((head[0], head[1]))
        body = history[-1:-int(length_now() / (speed * DT)) - 1:-6]  # coarse body samples for the targets to avoid
        # --- every target runs the same rules: wander, flee the head and body, keep off the rim, keep apart
        for index, item in alive.items():
            px, py = item["p"]
            base, amplitude, frequency, phase_a, phase_b = wander[index]
            angle = base + amplitude * math.sin(elapsed * frequency + phase_a) + .7 * math.sin(elapsed * frequency * .53 + phase_b)
            fx, fy = math.cos(angle) * .35, math.sin(angle) * .35
            ux, uy, distance = _unit(px - head[0], py - head[1])
            if distance < FLEE_RADIUS:
                # Dodge like real prey: mostly side-step out of the snake's line of travel (to whichever side it is
                # already on), partly move away. Pure running-away would push everyone to the rim.
                sx, sy = -math.sin(heading), math.cos(heading)
                if sx * ux + sy * uy < 0:
                    sx, sy = -sx, -sy
                fear = 1.7 * (1 - distance / FLEE_RADIUS)
                fx += (sx * DODGE + ux * (1 - DODGE)) * fear
                fy += (sy * DODGE + uy * (1 - DODGE)) * fear
            rx, ry, radius = _unit(px - ARENA_CENTER[0], py - ARENA_CENTER[1])
            if radius > ARENA_RADIUS * .45:  # a steady pull back into open space
                pull = CALM_DRIFT * (radius - ARENA_RADIUS * .45) / (ARENA_RADIUS * .55)
                fx -= rx * pull
                fy -= ry * pull
            for bx, by in body:
                ux, uy, distance = _unit(px - bx, py - by)
                if distance < 90:
                    fx += ux * .8 * (1 - distance / 90)
                    fy += uy * .8 * (1 - distance / 90)
            rx, ry, radius = _unit(px - ARENA_CENTER[0], py - ARENA_CENTER[1])
            edge = ARENA_RADIUS - TARGET_RADIUS - WALL_MARGIN
            if radius > edge:
                push = (radius - edge) / WALL_MARGIN
                fx -= rx * push * 2.2
                fy -= ry * push * 2.2
                # Cornered against the rim: dart back into the open at an angle, away from the head, instead of
                # pinning there or running along the rim (which would drag the snake round in circles).
                tx, ty = -ry, rx
                side = 1.0 if tx * (px - head[0]) + ty * (py - head[1]) >= 0 else -1.0
                dart = min(1.0, push * 2)
                fx += (tx * side * .5 - rx * .7) * dart
                fy += (ty * side * .5 - ry * .7) * dart
            for other_index, other in alive.items():
                if other_index != index:
                    ux, uy, distance = _unit(px - other["p"][0], py - other["p"][1])
                    if distance < SEPARATION:
                        fx += ux * SEPARATION_WEIGHT * (1 - distance / SEPARATION)
                        fy += uy * SEPARATION_WEIGHT * (1 - distance / SEPARATION)
            ux, uy, strength = _unit(fx, fy)
            desired = (ux * TARGET_MAX_SPEED * min(1.0, strength), uy * TARGET_MAX_SPEED * min(1.0, strength))
            ax, ay, change = _unit(desired[0] - item["v"][0], desired[1] - item["v"][1])
            change = min(change, TARGET_ACCEL * DT)
            item["v"][0] += ax * change
            item["v"][1] += ay * change
            item["p"][0] += item["v"][0] * DT
            item["p"][1] += item["v"][1] * DT
            rx, ry, radius = _unit(item["p"][0] - ARENA_CENTER[0], item["p"][1] - ARENA_CENTER[1])
            if radius > ARENA_RADIUS - TARGET_RADIUS:  # the rim is solid
                item["p"][0] = ARENA_CENTER[0] + rx * (ARENA_RADIUS - TARGET_RADIUS)
                item["p"][1] = ARENA_CENTER[1] + ry * (ARENA_RADIUS - TARGET_RADIUS)
                outward = item["v"][0] * rx + item["v"][1] * ry
                if outward > 0:
                    item["v"][0] -= rx * outward
                    item["v"][1] -= ry * outward
        # --- catches (any target the head reaches, not only the chosen prey)
        for index in sorted(alive):
            if len(alive) > 1 and math.dist(alive[index]["p"], head) < CATCH_DISTANCE:
                catches.append({"target_index": index, "time": round(elapsed, 4),
                                "position": [round(value, 2) for value in alive[index]["p"]]})
                del alive[index]
                last_catch = elapsed
        if step % sample == 0 or len(alive) <= 1:
            snapshot()
    return {"completed": len(alive) == 1, "attempt": attempt, "starts": starts, "catches": catches, "frames": frames,
            "winner": next(iter(alive)) if len(alive) == 1 else None, "simulation_duration": round(elapsed, 4)}


def acceptable(result: dict[str, Any]) -> bool:
    if not result["completed"]:
        return False
    times = [event["time"] for event in result["catches"]]
    return (SIM_MIN <= result["simulation_duration"] <= SIM_MAX and times[0] >= FIRST_CATCH_MIN
            and min(b - a for a, b in zip(times, times[1:])) >= CATCH_GAP_MIN and times[-1] - times[-2] >= FINAL_DUEL_MIN)


def simulate(seed: int) -> dict[str, Any]:
    for attempt in range(MAX_ATTEMPTS):
        result = _run(seed, attempt)
        if acceptable(result):
            return result
    raise RuntimeError(f"Lucky Pick seed {seed} produced no acceptable chase after {MAX_ATTEMPTS} attempts")


def release_time() -> float:
    """Round-local time at which the chase starts: after the targets appear and the pick window closes."""
    return LUCKY_APPEARANCE_DURATION + LUCKY_SELECTION_DURATION


def timeline_duration(simulation_duration: float) -> float:
    return round(release_time() + simulation_duration + LUCKY_WINNER_HOLD, 4)


def game_data(seed: int, shape_id: str, colors: dict[str, str], color_ids: list[str]) -> dict[str, Any]:
    result = simulate(seed)
    targets = [{"index": index, "shape_id": shape_id, "color_id": color_id, "color_value": colors[color_id],
                "position": result["starts"][index]} for index, color_id in enumerate(color_ids)]
    winner = result["winner"]
    return {"map_version": VERSION, "map_seed": seed, "attempt": result["attempt"],
            "arena": {"center": list(ARENA_CENTER), "radius": ARENA_RADIUS},
            "targets": targets, "target_count": TARGET_COUNT, "target_size": TARGET_SIZE, "shape_id": shape_id,
            "winner_index": winner, "winner_color": targets[winner]["color_id"],
            "elimination_order": [event["target_index"] for event in result["catches"]],
            "catches": result["catches"], "frames": result["frames"],
            "selection_seconds": LUCKY_SELECTION_DURATION, "simulation_duration": result["simulation_duration"],
            "timeline_duration": timeline_duration(result["simulation_duration"])}


def errors(data: dict[str, Any], answer: Any, colors: dict[str, str], shapes: tuple[str, ...]) -> list[str]:
    result: list[str] = []
    targets = data.get("targets", [])
    if len(targets) != TARGET_COUNT or data.get("target_count") != TARGET_COUNT:
        result.append("lucky pick must contain exactly seven targets")
    shape_id = data.get("shape_id")
    if shape_id not in shapes or any(target.get("shape_id") != shape_id for target in targets):
        result.append("lucky targets must use one supported shape")
    color_ids = [target.get("color_id") for target in targets]
    if len(set(color_ids)) != TARGET_COUNT or set(color_ids) != set(colors):
        result.append("lucky pick must use seven distinct curated colors")
    if any(target.get("index") != index or target.get("color_value") != colors.get(target.get("color_id"))
           for index, target in enumerate(targets)):
        result.append("lucky target mapping is invalid")
    winner, order = data.get("winner_index"), data.get("elimination_order", [])
    if not isinstance(winner, int) or winner not in range(TARGET_COUNT) or answer != winner or winner in order:
        result.append("lucky winner is invalid")
    if len(order) != TARGET_COUNT - 1 or len(set(order)) != TARGET_COUNT - 1:
        result.append("lucky elimination order is invalid")
    if data.get("selection_seconds") != LUCKY_SELECTION_DURATION:
        result.append("lucky timing metadata is invalid")
    if result:
        return result
    # The chase is deterministic: re-running it must give exactly the recorded game.
    seed, attempt = data.get("map_seed"), data.get("attempt")
    if not isinstance(seed, int) or not isinstance(attempt, int):
        return ["lucky chase seed is invalid"]
    expected = _run(seed, attempt)
    if not acceptable(expected):
        result.append("lucky chase is outside the accepted length and pacing")
    if ([target["position"] for target in targets] != expected["starts"] or data.get("catches") != expected["catches"]
            or winner != expected["winner"] or data.get("simulation_duration") != expected["simulation_duration"]):
        result.append("lucky chase does not match its simulation")
    if data.get("timeline_duration") != timeline_duration(expected["simulation_duration"]):
        result.append("lucky movement timeline is invalid")
    return result
