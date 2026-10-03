"""Mind Mix: one hard level of each of three games in one video (the user's idea: Puzzle Fit, Memory Challenge and Shade Spot
each lost views on their own, so they share a video and are paused as separate games).

Level 1 is Memory Challenge's hardest level (a 3x3 board, "where was it?"), level 2 is Shade Spot's hardest (a 5x5 pair, the
tile that changed), and level 3 is Puzzle Fit (three missing pieces) with a shorter timer than its own video had. Every section
stores the game's own round data, so the games' generators and validators do the real work; this module only picks them.
`puzzly/config.py` holds the tuning (`MIX_FIT_THINKING`, `MIX_SECTION_INTRO`).
"""
from __future__ import annotations

from hashlib import sha256
import random
from typing import Any

from ..config import (MEMORY_LEVELS, MIX_FIT_THINKING, MIX_GAMES, MIX_SECTION_INTRO, PUZZLE_FIT_INTRO_DURATION,
                      PUZZLE_FIT_OUTRO_DURATION, SHADE_LEVELS, mix_average_round)
from ..models import RoundSpec, VideoSpec

VERSION = "mix_v1"
FIT_THINKING_RANGE = (6.0, 30.0)
INTRO_RANGE = (0.8, 3.0)


def _memory(rng: random.Random) -> RoundSpec:
    from . import memory_levels
    return memory_levels.make_hard_level(rng)


def _shade(rng: random.Random) -> RoundSpec:
    from . import shade_spot
    return shade_spot.make_round(0, len(SHADE_LEVELS) - 1, None, rng)


def _fit(rng: random.Random) -> RoundSpec:
    from . import puzzle_fit_v12
    for _ in range(500):
        item = puzzle_fit_v12.make_round("hard", rng)
        if item is not None:
            return RoundSpec(0, "puzzle_fit", {**item.data, "thinking_seconds": MIX_FIT_THINKING}, item.answer)
    raise RuntimeError("could not build a puzzle fit picture")


MAKERS = {"memory_challenge": _memory, "shade_spot": _shade, "puzzle_fit": _fit}


def generate(seed: int, theme: str = "mix", round_count: int | None = None) -> VideoSpec:
    if round_count not in (None, len(MIX_GAMES)):
        raise ValueError("Mind Mix has three levels, one for each game")
    rng = random.Random(f"mind_mix_v1:{seed}")
    rounds = []
    for index, game in enumerate(MIX_GAMES):
        sub = MAKERS[game](rng)
        data = {"version": VERSION, "game": game, "level": index + 1, "intro_seconds": MIX_SECTION_INTRO,
                "sub": {**sub.data, "level": index + 1}}
        rounds.append(RoundSpec(index, "mind_mix", data, sub.answer))
    stable_id = sha256(f"mind_mix_v1:{seed}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "mind_mix", seed, "hard", "mix", tuple(rounds), PUZZLE_FIT_INTRO_DURATION,
                     mix_average_round([item.data for item in rounds]), PUZZLE_FIT_OUTRO_DURATION)


def sub_round(item: RoundSpec) -> RoundSpec:
    """The game's own round of a section, as that game's code expects it."""
    return RoundSpec(item.index, item.data["game"], item.data["sub"], item.answer)


def errors(data: dict[str, Any], answer: Any, difficulty: str | None = None) -> list[str]:
    game, sub = data.get("game"), data.get("sub")
    if data.get("version") != VERSION or game not in MIX_GAMES or not isinstance(sub, dict):
        return ["mind mix section metadata is invalid"]
    if data.get("level") not in (1, 2, 3) or sub.get("level") != data.get("level"):
        return ["mind mix levels are numbered 1 to 3"]
    intro = data.get("intro_seconds")
    if not isinstance(intro, (int, float)) or not INTRO_RANGE[0] <= intro <= INTRO_RANGE[1]:
        return ["mind mix section intro length is out of range"]
    if game == "memory_challenge":
        from . import memory_levels
        problems = memory_levels.errors(sub, answer, "hard")
        if sub.get("kind") != "where" or len(sub.get("tokens", [])) != 9:
            problems.append("mind mix uses Memory Challenge's hardest level: the full 3x3 board")
    elif game == "shade_spot":
        from . import shade_spot
        problems = shade_spot.errors(sub, answer, "hard")
        if sub.get("grid") != 5:
            problems.append("mind mix uses Shade Spot's hardest level: the 5x5 pair")
    else:
        from . import puzzle_fit_v12
        problems = puzzle_fit_v12.errors(sub, answer, None)  # its own timer check is for the standalone game
        if not FIT_THINKING_RANGE[0] <= float(sub.get("thinking_seconds", 0)) <= FIT_THINKING_RANGE[1]:
            problems.append("mind mix puzzle fit timer is out of range")
    return problems
