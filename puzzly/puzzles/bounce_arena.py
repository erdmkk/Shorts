from __future__ import annotations

from hashlib import sha256
import math
import random
from typing import Any

from ..config import BOUNCE_CTA_DURATION, BOUNCE_SELECTION_DURATION, BOUNCE_WINNER_HOLD
from ..models import RoundSpec, VideoSpec

VERSION = 8  # gravity arena
BALL_COUNT = 6
BALL_RADIUS = 40.0
ARENA_CENTER = (540.0, 930.0)
ARENA_RADIUS = 400.0
FIXED_TIMESTEP = 1 / 240
TIMELINE_FPS = 30
MAX_VIDEO_DURATION = 32.0  # 30 s of game plus the 2 s the end card grew by: the simulation window stays 9-21.8 s
FIXED_VIDEO_OVERHEAD = BOUNCE_SELECTION_DURATION + BOUNCE_WINNER_HOLD + BOUNCE_CTA_DURATION
ACCEPTANCE_MAX_SECONDS = MAX_VIDEO_DURATION - FIXED_VIDEO_OVERHEAD
ACCEPTANCE_MIN_SECONDS = 9.0  # shorter games feel over before the tension builds
FIRST_EXIT_MIN_SECONDS = 2.0
SAFETY_CAP_SECONDS = ACCEPTANCE_MAX_SECONDS
MAX_INITIAL_CONDITION_ATTEMPTS = 80
GRAVITY = 980.0
PASSAGE_HALF_ANGLE = 0.20
GAP_LIP_ANGLE = 0.035
EXIT_HALF_ANGLE = PASSAGE_HALF_ANGLE - GAP_LIP_ANGLE
SOLID_EDGE_EPSILON = 1e-6
OPENING_TOLERANCE = 0.012
WALL_STROKE_WIDTH = 20.0
# The ring is solid everywhere except the gap; its round caps sit at +/- this angle from the gap centre.
# A ball's centre must stay about 0.125 rad inside each cap to fit through, so the clear window is about +/- 0.165 rad.
OPENING_HALF_ANGLE = 0.29
GAP_REVOLUTION_SECONDS = 7.0
WALL_GRIP = 0.12  # share of the ring's surface speed passed to a bouncing ball
INNER_DROP = 2 * (ARENA_RADIUS - BALL_RADIUS)  # floor-to-ceiling height a ball can travel inside the ring
MIN_BOUNCE_HEIGHT = 0.85 * INNER_DROP  # every wall bounce restores at least this much energy
MAX_BOUNCE_HEIGHT = 1.45 * INNER_DROP
ESCAPE_COMMIT_RADIUS = ARENA_RADIUS - BALL_RADIUS
IMPACT_MIN_SPEED = 160.0
IMPACT_MIN_INTERVAL = 0.06
COLORS = ("#FF4D6D", "#3DA9FF", "#FFD23F", "#3DF08F", "#B388FF", "#FF8A3D")
COLOR_NAMES = ("red", "blue", "yellow", "green", "purple", "orange")


def _angle_delta(first: float, second: float) -> float:
    return (first - second + math.pi) % (2 * math.pi) - math.pi


def _normalize_angle(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def gap_angle(arena: dict[str, Any], simulation_time: float) -> float:
    return _normalize_angle(
        float(arena["opening_start_angle"]) + float(arena["angular_velocity"]) * simulation_time)


def gap_geometry(arena: dict[str, Any], simulation_time: float) -> dict[str, float]:
    return {
        "angle": gap_angle(arena, simulation_time),
        "wall_half_angle": float(arena["opening_half_angle"]),
        "passage_half_angle": float(arena["passage_half_angle"]),
        "exit_half_angle": float(arena["exit_half_angle"]),
        "lip_angle": float(arena["lip_angle"]),
        "visible_open_half_angle": float(arena["visible_open_half_angle"]),
        "tolerance": float(arena.get("opening_tolerance", 0.0)),
    }


def lip_segments(
    arena: dict[str, Any], simulation_time: float,
) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
    geometry = gap_geometry(arena, simulation_time)
    center = tuple(float(value) for value in arena["center"])
    radius = float(arena["radius"])

    def point(angle: float) -> tuple[float, float]:
        return center[0] + math.cos(angle) * radius, center[1] + math.sin(angle) * radius

    angle = geometry["angle"]
    outer = geometry["wall_half_angle"]
    visible = geometry["visible_open_half_angle"]
    return (
        (point(angle - outer), point(angle - visible)),
        (point(angle + visible), point(angle + outer)),
    )


def angle_inside_opening(angle: float, arena: dict[str, Any], simulation_time: float) -> bool:
    geometry = gap_geometry(arena, simulation_time)
    return abs(_angle_delta(angle, geometry["angle"])) < (
        geometry["exit_half_angle"] - SOLID_EDGE_EPSILON)


def resolve_capsule_collision(
    ball: dict[str, Any], start: tuple[float, float], end: tuple[float, float],
    wall_radius: float, angular_velocity: float = 0.0,
    rotation_center: tuple[float, float] = ARENA_CENTER,
) -> bool:
    sx, sy = start
    ex, ey = end
    segment_x, segment_y = ex - sx, ey - sy
    segment_length_sq = segment_x * segment_x + segment_y * segment_y
    px, py = float(ball["position"][0]), float(ball["position"][1])
    if segment_length_sq <= 1e-12:
        amount = 0.0
    else:
        amount = max(0.0, min(1.0, ((px - sx) * segment_x + (py - sy) * segment_y) / segment_length_sq))
    closest_x = sx + segment_x * amount
    closest_y = sy + segment_y * amount
    dx, dy = px - closest_x, py - closest_y
    distance = math.hypot(dx, dy)
    collision_distance = BALL_RADIUS + wall_radius
    if distance >= collision_distance:
        return False
    if distance <= 1e-9:
        radial_x, radial_y = closest_x - rotation_center[0], closest_y - rotation_center[1]
        radial_length = max(1e-9, math.hypot(radial_x, radial_y))
        nx, ny = -radial_x / radial_length, -radial_y / radial_length
    else:
        nx, ny = dx / distance, dy / distance
    correction = collision_distance - distance + 1e-6
    ball["position"][0] += nx * correction
    ball["position"][1] += ny * correction
    wall_vx = -angular_velocity * (closest_y - rotation_center[1])
    wall_vy = angular_velocity * (closest_x - rotation_center[0])
    relative_normal = (ball["velocity"][0] - wall_vx) * nx + (ball["velocity"][1] - wall_vy) * ny
    if relative_normal < 0:
        ball["velocity"][0] -= 2 * relative_normal * nx
        ball["velocity"][1] -= 2 * relative_normal * ny
    ball["last_normal"] = (nx, ny, -relative_normal)
    return True


def elastic_collision(
    first_position: tuple[float, float], first_velocity: tuple[float, float],
    second_position: tuple[float, float], second_velocity: tuple[float, float],
    radius: float = BALL_RADIUS,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], tuple[float, float]]:
    """One perfectly elastic equal-mass collision, including overlap correction. Momentum and energy are conserved."""
    dx = second_position[0] - first_position[0]
    dy = second_position[1] - first_position[1]
    distance = math.hypot(dx, dy)
    if distance >= 2 * radius:
        return first_position, first_velocity, second_position, second_velocity
    if distance < 1e-9:
        nx, ny, distance = 1.0, 0.0, 0.0
    else:
        nx, ny = dx / distance, dy / distance
    overlap = 2 * radius - distance
    first_position = (first_position[0] - nx * overlap / 2, first_position[1] - ny * overlap / 2)
    second_position = (second_position[0] + nx * overlap / 2, second_position[1] + ny * overlap / 2)
    closing_speed = (first_velocity[0] - second_velocity[0]) * nx + (first_velocity[1] - second_velocity[1]) * ny
    if closing_speed > 0:
        first_velocity = (first_velocity[0] - closing_speed * nx, first_velocity[1] - closing_speed * ny)
        second_velocity = (second_velocity[0] + closing_speed * nx, second_velocity[1] + closing_speed * ny)
    return first_position, first_velocity, second_position, second_velocity


def bounce_height(ball: dict[str, Any]) -> float:
    """Mechanical energy as a height above the inner floor of the ring."""
    floor = ARENA_CENTER[1] + ARENA_RADIUS - BALL_RADIUS
    speed_sq = ball["velocity"][0] ** 2 + ball["velocity"][1] ** 2
    return (floor - ball["position"][1]) + speed_sq / (2 * GRAVITY)


def keep_bouncy(ball: dict[str, Any]) -> None:
    """After a wall bounce, keep the ball's energy between a lively floor and a sane ceiling.

    Only the speed changes, never the direction, so no ball is steered toward any exit.
    """
    floor = ARENA_CENTER[1] + ARENA_RADIUS - BALL_RADIUS
    potential = floor - ball["position"][1]
    height = bounce_height(ball)
    target = MIN_BOUNCE_HEIGHT if height < MIN_BOUNCE_HEIGHT else (MAX_BOUNCE_HEIGHT if height > MAX_BOUNCE_HEIGHT else None)
    if target is None:
        return
    speed = math.hypot(*ball["velocity"])
    wanted = math.sqrt(max(0.0, 2 * GRAVITY * (target - potential)))
    if speed > 1e-9:
        factor = wanted / speed
        ball["velocity"][0] *= factor
        ball["velocity"][1] *= factor


def _surface_drag(ball: dict[str, Any], nx: float, ny: float, angular_velocity: float) -> None:
    """The spinning ring drags a bouncing ball a little along its surface."""
    tx, ty = -ny, nx
    surface = angular_velocity * ARENA_RADIUS
    tangential = ball["velocity"][0] * tx + ball["velocity"][1] * ty
    kick = WALL_GRIP * (surface - tangential)
    ball["velocity"][0] += kick * tx
    ball["velocity"][1] += kick * ty


def resolve_circular_wall(ball: dict[str, Any], arena: dict[str, Any], simulation_time: float) -> bool:
    """Collide a ball with the solid ring: a thick band everywhere except the gap, with round caps at the gap edges.

    A ball leaves only when its whole body fits through the gap; otherwise it bounces off the band or a cap.
    Returns True when the ball bounced off the inside of the ring (the caller then keeps it lively).
    """
    center = tuple(float(value) for value in arena["center"])
    radius = float(arena["radius"])
    half_wall = float(arena["wall_stroke_width"]) / 2
    omega = float(arena["angular_velocity"])
    gap = gap_angle(arena, simulation_time)
    wall_half = float(arena["opening_half_angle"])
    dx = ball["position"][0] - center[0]
    dy = ball["position"][1] - center[1]
    distance = max(1e-9, math.hypot(dx, dy))
    nx, ny = dx / distance, dy / distance
    delta = _angle_delta(math.atan2(dy, dx), gap)
    if abs(delta) >= wall_half:  # facing the band itself
        outward = ball["velocity"][0] * nx + ball["velocity"][1] * ny
        if distance < radius:
            limit = radius - half_wall - BALL_RADIUS
            if distance <= limit:
                return False
            ball["position"][0] = center[0] + nx * limit
            ball["position"][1] = center[1] + ny * limit
            if outward > 0:
                ball["velocity"][0] -= 2 * outward * nx
                ball["velocity"][1] -= 2 * outward * ny
                _surface_drag(ball, nx, ny, omega)
                ball["last_normal"] = (nx, ny, outward)
                return True
            return False
        limit = radius + half_wall + BALL_RADIUS  # already outside: the band only pushes it further out
        if distance < limit:
            ball["position"][0] = center[0] + nx * limit
            ball["position"][1] = center[1] + ny * limit
            if outward < 0:
                ball["velocity"][0] -= 2 * outward * nx
                ball["velocity"][1] -= 2 * outward * ny
        return False
    bounced = False
    for sign in (-1, 1):  # the round caps at both gap edges
        edge = gap + sign * wall_half
        cap = (center[0] + math.cos(edge) * radius, center[1] + math.sin(edge) * radius)
        if resolve_capsule_collision(ball, cap, cap, half_wall, omega, center):
            bounced = True
    return bounced and math.hypot(ball["position"][0] - center[0], ball["position"][1] - center[1]) < radius


def clear_of_ring(ball: dict[str, Any], arena: dict[str, Any]) -> bool:
    center = arena["center"]
    distance = math.hypot(ball["position"][0] - center[0], ball["position"][1] - center[1])
    return distance > float(arena["radius"]) + float(arena["wall_stroke_width"]) / 2 + BALL_RADIUS + 1


def outside_ring(ball: dict[str, Any], arena: dict[str, Any]) -> bool:
    center = arena["center"]
    return math.hypot(ball["position"][0] - center[0], ball["position"][1] - center[1]) > float(arena["radius"])


def _initial_state(rng: random.Random) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    opening_start_angle = rng.uniform(-math.pi, math.pi)
    angular_velocity = rng.choice((-1.0, 1.0)) * 2 * math.pi / GAP_REVOLUTION_SECONDS
    arena = {
        "center": list(ARENA_CENTER), "radius": ARENA_RADIUS,
        "opening_start_angle": opening_start_angle, "opening_angle": opening_start_angle,
        "opening_half_angle": OPENING_HALF_ANGLE, "passage_half_angle": PASSAGE_HALF_ANGLE,
        "exit_half_angle": EXIT_HALF_ANGLE, "lip_angle": GAP_LIP_ANGLE,
        "visible_open_half_angle": OPENING_HALF_ANGLE - GAP_LIP_ANGLE,
        "opening_tolerance": OPENING_TOLERANCE, "wall_stroke_width": WALL_STROKE_WIDTH,
        "angular_velocity": angular_velocity, "revolution_seconds": GAP_REVOLUTION_SECONDS,
        "gravity": GRAVITY,
    }
    rotation = rng.uniform(0, 2 * math.pi)
    balls: list[dict[str, Any]] = []
    for ball_id, color in enumerate(COLORS):
        angle = rotation + ball_id * 2 * math.pi / BALL_COUNT
        ring = 170.0 + rng.uniform(-20.0, 20.0)
        speed = rng.uniform(260.0, 420.0)
        velocity_angle = rng.uniform(0, 2 * math.pi)
        balls.append({
            "id": ball_id, "color": color,
            "position": [ARENA_CENTER[0] + ring * math.cos(angle), ARENA_CENTER[1] + ring * math.sin(angle)],
            "velocity": [speed * math.cos(velocity_angle), speed * math.sin(velocity_angle)],
        })
    return balls, arena


def _snapshot(time_value: float, balls: list[dict[str, Any]]) -> dict[str, Any]:
    return {"time": round(time_value, 4), "balls": [
        [ball["id"], round(ball["position"][0], 2), round(ball["position"][1], 2)]
        for ball in sorted(balls, key=lambda item: item["id"])
    ]}


def _run_attempt(seed: int, attempt: int, safety_cap: float = SAFETY_CAP_SECONDS) -> dict[str, Any]:
    rng = random.Random(f"bounce_arena_gravity_v8:{seed}:{attempt}")
    balls, arena = _initial_state(rng)
    initial_positions = [[ball["id"], *[round(value, 4) for value in ball["position"]]] for ball in balls]
    initial_velocities = [[ball["id"], *[round(value, 4) for value in ball["velocity"]]] for ball in balls]
    frames = [_snapshot(0.0, balls)]
    eliminations: list[dict[str, Any]] = []
    impacts: list[list[Any]] = []
    last_impact: dict[int, float] = {}
    elapsed = 0.0
    sample_step = round((1 / TIMELINE_FPS) / FIXED_TIMESTEP)
    step_index = 0

    def record(kind: str, ball: dict[str, Any], x: float, y: float, strength: float, other: int = -1) -> None:
        if strength < IMPACT_MIN_SPEED or elapsed - last_impact.get(ball["id"], -1.0) < IMPACT_MIN_INTERVAL:
            return
        last_impact[ball["id"]] = elapsed
        impacts.append([round(elapsed, 4), kind, ball["id"], other, round(x, 1), round(y, 1), round(strength, 1)])

    while len(balls) > 1 and elapsed < safety_cap:
        elapsed += FIXED_TIMESTEP
        step_index += 1
        for ball in balls:
            ball["velocity"][1] += GRAVITY * FIXED_TIMESTEP
            ball["position"][0] += ball["velocity"][0] * FIXED_TIMESTEP
            ball["position"][1] += ball["velocity"][1] * FIXED_TIMESTEP
        leaving: list[dict[str, Any]] = []
        for _ in range(2):
            for first_index in range(len(balls)):
                for second_index in range(first_index + 1, len(balls)):
                    first, second = balls[first_index], balls[second_index]
                    if first.get("exit_entry_time") is not None or second.get("exit_entry_time") is not None:
                        continue  # a ball crossing the ring is already on its way out
                    before = ((first["velocity"][0] - second["velocity"][0]) ** 2 + (first["velocity"][1] - second["velocity"][1]) ** 2) ** .5
                    p1, v1, p2, v2 = elastic_collision(tuple(first["position"]), tuple(first["velocity"]),
                                                       tuple(second["position"]), tuple(second["velocity"]))
                    if v1 != tuple(first["velocity"]):
                        record("ball", first, (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2, before, second["id"])
                    first["position"][:], first["velocity"][:] = p1, v1
                    second["position"][:], second["velocity"][:] = p2, v2
            for ball in balls:
                ball.pop("last_normal", None)
                if resolve_circular_wall(ball, arena, elapsed):
                    keep_bouncy(ball)
                    normal = ball.get("last_normal")
                    if normal:
                        record("wall", ball, ball["position"][0] + normal[0] * BALL_RADIUS,
                               ball["position"][1] + normal[1] * BALL_RADIUS, abs(normal[2]))
                if ball.get("exit_entry_time") is not None and not outside_ring(ball, arena):
                    for key in ("exit_entry_angle", "exit_gap_angle", "exit_entry_time"):
                        ball.pop(key)  # it fell back in through the gap
                if outside_ring(ball, arena) and ball.get("exit_entry_time") is None:
                    dx = ball["position"][0] - ARENA_CENTER[0]
                    dy = ball["position"][1] - ARENA_CENTER[1]
                    ball["exit_entry_angle"] = math.atan2(dy, dx)
                    ball["exit_gap_angle"] = gap_angle(arena, elapsed)
                    ball["exit_entry_time"] = elapsed
                if ball.get("exit_entry_time") is not None and clear_of_ring(ball, arena) and ball not in leaving:
                    leaving.append(ball)
        for ball in sorted(leaving, key=lambda item: item["id"]):
            if ball not in balls:
                continue
            balls.remove(ball)
            dx = ball["position"][0] - ARENA_CENTER[0]
            dy = ball["position"][1] - ARENA_CENTER[1]
            eliminations.append({
                "ball_id": ball["id"], "time": round(elapsed, 4),
                "position": [round(value, 3) for value in ball["position"]],
                "velocity": [round(value, 3) for value in ball["velocity"]],
                "exit_angle": round(math.atan2(dy, dx), 8),
                "gap_entry_angle": round(float(ball["exit_entry_angle"]), 8),
                "gap_angle": round(float(ball["exit_gap_angle"]), 8),
                "gap_entry_time": round(float(ball["exit_entry_time"]), 6),
            })
        if step_index % sample_step == 0 or len(balls) <= 1:
            frames.append(_snapshot(elapsed, balls))

    completed = len(balls) == 1
    winner = int(balls[0]["id"]) if completed else None
    return {
        "completed": completed, "seed": seed, "initial_condition_attempt": attempt, "version": VERSION,
        "ball_count": BALL_COUNT, "colors": list(COLORS), "color_names": list(COLOR_NAMES), "ball_radius": BALL_RADIUS,
        "arena": {key: round(value, 8) if isinstance(value, float) else value for key, value in arena.items()},
        "fixed_timestep": FIXED_TIMESTEP, "timeline_fps": TIMELINE_FPS,
        "initial_positions": initial_positions, "initial_velocities": initial_velocities,
        "frames": frames, "eliminations": eliminations, "impacts": impacts,
        "elimination_order": [event["ball_id"] for event in eliminations],
        "winner": winner, "simulation_duration": round(elapsed, 4),
    }


def acceptable(result: dict[str, Any]) -> bool:
    if not result["completed"]:
        return False
    duration = float(result["simulation_duration"])
    return (ACCEPTANCE_MIN_SECONDS <= duration <= ACCEPTANCE_MAX_SECONDS
            and float(result["eliminations"][0]["time"]) >= FIRST_EXIT_MIN_SECONDS)


def simulate(seed: int) -> dict[str, Any]:
    for attempt in range(MAX_INITIAL_CONDITION_ATTEMPTS):
        result = _run_attempt(seed, attempt)
        if not acceptable(result):
            continue
        result.update({
            "selection_duration": BOUNCE_SELECTION_DURATION, "winner_hold": BOUNCE_WINNER_HOLD,
            "cta_duration": BOUNCE_CTA_DURATION,
            "timeline_duration": round(BOUNCE_SELECTION_DURATION + float(result["simulation_duration"]) + BOUNCE_WINNER_HOLD, 4),
            "safety_cap_seconds": SAFETY_CAP_SECONDS, "acceptance_max_seconds": ACCEPTANCE_MAX_SECONDS,
            "max_video_duration": MAX_VIDEO_DURATION,
        })
        return result
    raise RuntimeError(
        f"Bounce Arena seed {seed} produced no natural winner within "
        f"{ACCEPTANCE_MAX_SECONDS:.0f}s after {MAX_INITIAL_CONDITION_ATTEMPTS} attempts")


def errors(data: dict[str, Any], answer: Any) -> list[str]:
    result: list[str] = []
    if data.get("ball_count") != BALL_COUNT or len(data.get("initial_positions", [])) != BALL_COUNT:
        result.append("bounce arena must start with exactly six balls")
    if len(data.get("colors", [])) != BALL_COUNT or len(set(data.get("colors", []))) != BALL_COUNT:
        result.append("bounce arena balls must use six distinct colors")
    eliminations = data.get("eliminations", [])
    order = data.get("elimination_order", [])
    winner = data.get("winner")
    if len(eliminations) != BALL_COUNT - 1 or len(order) != BALL_COUNT - 1 or len(set(order)) != BALL_COUNT - 1:
        result.append("bounce arena must contain exactly five unique eliminations")
    if not isinstance(winner, int) or winner not in range(BALL_COUNT) or winner in order or answer != winner:
        result.append("bounce arena must have exactly one valid surviving winner")
    duration = float(data.get("simulation_duration", 0))
    minimum = ACCEPTANCE_MIN_SECONDS if data.get("version") == VERSION else 0.0
    if not minimum <= duration <= ACCEPTANCE_MAX_SECONDS or duration <= 0:
        result.append("bounce arena simulation duration is outside the acceptance window")
    if data.get("selection_duration") != BOUNCE_SELECTION_DURATION:
        result.append("bounce arena selection must last exactly five seconds")
    expected_timeline = BOUNCE_SELECTION_DURATION + duration + BOUNCE_WINNER_HOLD
    if not math.isclose(float(data.get("timeline_duration", 0)), expected_timeline, abs_tol=1e-3):
        result.append("bounce arena timeline duration is inconsistent")
    if float(data.get("timeline_duration", math.inf)) + float(data.get("cta_duration", BOUNCE_CTA_DURATION)) > MAX_VIDEO_DURATION + 1e-6:
        result.append("bounce arena total video duration exceeds thirty seconds")
    arena = data.get("arena", {})

    def inside(angle: float, time_value: float) -> bool:
        if data.get("version") != VERSION:
            return angle_inside_opening(angle, arena, time_value)
        # Solid ring: the centre crosses the ring line strictly between the two gap caps.
        return abs(_angle_delta(angle, gap_angle(arena, time_value))) < float(arena["opening_half_angle"])

    for event in eliminations:
        event_time = float(event.get("gap_entry_time", -1))
        expected_gap = gap_angle(arena, event_time) if event_time >= 0 else math.inf
        if (not math.isclose(float(event.get("gap_angle", math.inf)), expected_gap, abs_tol=2e-6)
                or not inside(float(event.get("gap_entry_angle", math.inf)), event_time)):
            result.append("a bounce arena elimination occurred outside the opening")
    seen_eliminated: set[int] = set()
    events = sorted(eliminations, key=lambda event: float(event.get("time", -1)))
    for frame in data.get("frames", []):
        time_value = float(frame.get("time", 0))
        seen_eliminated.update(int(event["ball_id"]) for event in events if float(event["time"]) <= time_value + 1e-4)
        for record in frame.get("balls", []):
            if len(record) != 3 or not all(math.isfinite(float(value)) for value in record):
                result.append("bounce arena timeline contains invalid coordinates")
                continue
            if int(record[0]) in seen_eliminated:
                result.append("an eliminated bounce arena ball returned")
    return list(dict.fromkeys(result))


def generate(seed: int, *_: Any, **__: Any) -> VideoSpec:
    data = simulate(seed)
    game = RoundSpec(0, "bounce_arena", data, data["winner"])
    stable_id = sha256(
        f"bounce_arena_gravity_v8:{seed}:{data['initial_condition_attempt']}".encode()
    ).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "bounce_arena", seed, None, "bounce_arena", (game,),
                     0.0, data["timeline_duration"], BOUNCE_CTA_DURATION)
