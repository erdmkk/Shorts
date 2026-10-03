"""Chess: Mate in 1. One real position per video from the Lichess puzzle database (CC0, filtered once, used offline).

The board is shown for the whole video with the side to move and a "mate in 1" hint. The answer is never revealed:
viewers comment their move. Every position is re-checked with python-chess before rendering: it is legal, the game is
not over, and the side to move has exactly one mating move, which is the stored answer.
"""
from __future__ import annotations

import csv
from functools import lru_cache
from hashlib import sha256
import random

import chess

from ..config import CHESS_DATASET, CHESS_DURATION
from ..models import RoundSpec, VideoSpec

VERSION = "mate1_v1"
# Lichess puzzle ratings per difficulty; the dataset only keeps well-played, well-liked puzzles (the filter is described in AGENTS.md).
RATING_BANDS = {"easy": (0, 1199), "medium": (1200, 1599), "hard": (1600, 4000)}


@lru_cache(maxsize=1)
def load_puzzles() -> tuple[dict, ...]:
    if not CHESS_DATASET.is_file():
        raise FileNotFoundError(f"chess puzzle dataset is missing: {CHESS_DATASET}")
    with CHESS_DATASET.open(encoding="utf-8", newline="") as handle:
        return tuple({**row, "rating": int(row["rating"])} for row in csv.DictReader(handle))


def pool(difficulty: str) -> list[dict]:
    low, high = RATING_BANDS[difficulty]
    return [row for row in load_puzzles() if low <= row["rating"] <= high]


def rating_pool(min_rating: int) -> list[dict]:
    return [row for row in load_puzzles() if row["rating"] >= min_rating]


def band_of(rating: int) -> str:
    return next(name for name, (low, high) in RATING_BANDS.items() if low <= rating <= high)


def generate(seed: int, difficulty: str = "hard", min_rating: int | None = None) -> VideoSpec:
    """One puzzle from the difficulty's rating band, or, with `min_rating` (the UI's input), from every puzzle rated at
    least that; the video's difficulty (and filename) then follows the chosen puzzle's own rating."""
    if min_rating is not None:
        candidates = rating_pool(int(min_rating))
        if not candidates:
            raise ValueError(f"No mate-in-1 puzzle is rated {min_rating} or higher.")
        row = random.Random(f"{VERSION}:{seed}:min{int(min_rating)}").choice(candidates)
        difficulty = band_of(row["rating"])
    else:
        if difficulty not in RATING_BANDS:
            raise ValueError(f"unsupported chess difficulty: {difficulty}")
        row = random.Random(f"{VERSION}:{seed}:{difficulty}").choice(pool(difficulty))
    board = chess.Board(row["fen"])
    data = {"version": VERSION, "source": "lichess", "puzzle_id": row["id"], "fen": row["fen"],
            "side": "white" if board.turn == chess.WHITE else "black", "rating": row["rating"]}
    answer = {"uci": row["move"], "san": row["san"]}
    stable_id = sha256(f"{VERSION}:{row['id']}:{seed}".encode()).hexdigest()[:12]
    return VideoSpec(f"PZ-{stable_id}", "chess_mate", seed, difficulty, "lichess",
                     (RoundSpec(0, "chess_mate", data, answer),), 0.0, CHESS_DURATION, 0.0)


def mating_moves(board: chess.Board) -> list[chess.Move]:
    result = []
    for move in board.legal_moves:
        board.push(move)
        if board.is_checkmate():
            result.append(move)
        board.pop()
    return result


def errors(data: dict, answer: dict, difficulty: str | None) -> list[str]:
    problems: list[str] = []
    if data.get("version") != VERSION:
        return ["unsupported chess puzzle version"]
    try:
        board = chess.Board(data["fen"])
    except (KeyError, ValueError):
        return ["chess position is not a valid FEN"]
    if not board.is_valid():
        problems.append("chess position is illegal")
    if board.is_game_over():
        problems.append("chess position is already over")
    if data.get("side") != ("white" if board.turn == chess.WHITE else "black"):
        problems.append("chess side to move does not match the position")
    mates = mating_moves(board)
    if len(mates) != 1:
        problems.append(f"chess position must have exactly one mating move, found {len(mates)}")
    elif not isinstance(answer, dict) or answer.get("uci") != mates[0].uci() or answer.get("san") != board.san(mates[0]):
        problems.append("chess answer is not the mating move")
    if difficulty in RATING_BANDS:
        low, high = RATING_BANDS[difficulty]
        if not low <= int(data.get("rating", -1)) <= high:
            problems.append("chess puzzle rating does not match the difficulty")
    else:
        problems.append("chess puzzle needs a difficulty")
    return problems


PROMOTIONS = {"q": "vezir", "r": "kale", "b": "fil", "n": "at"}


def move_label(answer: dict) -> str:
    """The mating move for the creator (never shown in the video): 'C6 > D5 (Bd5#)', with the promotion piece if any."""
    uci = answer["uci"]
    label = f"{uci[:2].upper()} > {uci[2:4].upper()}"
    if len(uci) == 5:
        label += f", {PROMOTIONS[uci[4]]} çıkar"
    return f"{label} ({answer['san']})"
