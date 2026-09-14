from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
import json
from typing import Any

from .config import FPS


@dataclass(frozen=True)
class RoundSpec:
    index: int
    kind: str
    data: dict[str, Any]
    answer: Any

    def fingerprint(self) -> str:
        value = json.dumps({"kind": self.kind, "data": self.data, "answer": self.answer}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha256(value.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class VideoSpec:
    id: str
    puzzle_type: str
    seed: int
    difficulty: str | None
    theme: str
    rounds: tuple[RoundSpec, ...]
    intro_duration: float
    round_duration: float
    outro_duration: float
    operation: str = "mixed"
    fps: int = FPS
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def total_duration(self) -> float:
        return round(self.intro_duration + len(self.rounds) * self.round_duration + self.outro_duration, 3)

    @property
    def duration_seconds(self) -> float:
        return self.total_duration

    @property
    def round_count(self) -> int:
        return len(self.rounds)

    def fingerprint(self) -> str:
        content = {
            "puzzle_type": self.puzzle_type, "difficulty": self.difficulty,
            "theme": self.theme, "operation": self.operation,
            "rounds": [asdict(round_spec) for round_spec in self.rounds],
        }
        encoded = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha256(encoded.encode("utf-8")).hexdigest()[:20]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["total_duration"] = self.total_duration
        return result
