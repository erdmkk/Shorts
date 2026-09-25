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

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VideoSpec":
        rounds = tuple(RoundSpec(**item) for item in payload["rounds"])
        return cls(
            id=str(payload["id"]), puzzle_type=str(payload["puzzle_type"]),
            seed=int(payload["seed"]), difficulty=payload.get("difficulty"),
            theme=str(payload["theme"]), rounds=rounds,
            intro_duration=float(payload["intro_duration"]),
            round_duration=float(payload["round_duration"]),
            outro_duration=float(payload["outro_duration"]),
            operation=str(payload.get("operation", "mixed")),
            fps=int(payload.get("fps", FPS)),
            metadata=dict(payload.get("metadata", {})),
        )

    @classmethod
    def from_json(cls, payload: str) -> "VideoSpec":
        return cls.from_dict(json.loads(payload))
