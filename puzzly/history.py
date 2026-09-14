from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import sqlite3

from .config import GENERATION_HISTORY_PATH, HISTORY_PATH, OUTPUT_DIR


@dataclass(frozen=True)
class GenerationRecord:
    generation_id: int
    sequence_no: int
    puzzle_type: str
    difficulty: str
    seed: int | None
    fingerprint: str
    created_at: str
    output_filename: str
    cover_filename: str


class HistoryStore:
    """Authoritative, output-independent generation history."""

    def __init__(
        self,
        path: Path = GENERATION_HISTORY_PATH,
        *,
        legacy_path: Path | None = None,
        legacy_output_dir: Path | None = None,
    ) -> None:
        self.path = path
        self.legacy_path = HISTORY_PATH if legacy_path is None and path == GENERATION_HISTORY_PATH else legacy_path
        self.legacy_output_dir = OUTPUT_DIR if legacy_output_dir is None and path == GENERATION_HISTORY_PATH else legacy_output_dir
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS generations (
                    generation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sequence_no INTEGER NOT NULL UNIQUE,
                    puzzle_type TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    seed INTEGER,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    output_filename TEXT NOT NULL,
                    cover_filename TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sequence_state (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    last_sequence INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO sequence_state(singleton, last_sequence) VALUES (1, 0);
                CREATE TABLE IF NOT EXISTS migrations (
                    name TEXT PRIMARY KEY,
                    completed_at TEXT NOT NULL,
                    details TEXT NOT NULL
                );
                """
            )
        self._migrate_legacy_json()

    def _legacy_max_sequence(self) -> int:
        if self.legacy_output_dir is None or not self.legacy_output_dir.exists():
            return 0
        maximum = 0
        for path in self.legacy_output_dir.rglob("PZ_*.mp4"):
            match = re.match(r"PZ_(\d+)_", path.name)
            if match:
                maximum = max(maximum, int(match.group(1)))
        return maximum

    def _migrate_legacy_json(self) -> None:
        if self.legacy_path is None or not self.legacy_path.exists():
            return
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM migrations WHERE name = 'history_json_v1'").fetchone():
                return
        try:
            payload = json.loads(self.legacy_path.read_text(encoding="utf-8"))
            fingerprints = sorted(set(payload.get("fingerprints", [])))
        except (json.JSONDecodeError, OSError, TypeError):
            return
        backup = self.legacy_path.with_name(f"{self.legacy_path.name}.backup-before-sqlite")
        if not backup.exists():
            shutil.copy2(self.legacy_path, backup)
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = int(connection.execute("SELECT last_sequence FROM sequence_state WHERE singleton=1").fetchone()[0])
            next_sequence = current
            for fingerprint in fingerprints:
                if connection.execute("SELECT 1 FROM generations WHERE fingerprint=?", (fingerprint,)).fetchone():
                    continue
                next_sequence += 1
                connection.execute(
                    """INSERT INTO generations
                    (sequence_no, puzzle_type, difficulty, seed, fingerprint, created_at, output_filename, cover_filename)
                    VALUES (?, 'legacy_unknown', 'legacy_unknown', NULL, ?, ?, '', '')""",
                    (next_sequence, fingerprint, created_at),
                )
            high_water = max(next_sequence, self._legacy_max_sequence())
            connection.execute("UPDATE sequence_state SET last_sequence=? WHERE singleton=1", (high_water,))
            connection.execute(
                "INSERT INTO migrations(name, completed_at, details) VALUES ('history_json_v1', ?, ?)",
                (created_at, f"Imported {len(fingerprints)} fingerprints; high-water mark {high_water}"),
            )

    def load(self) -> set[str]:
        with self._connect() as connection:
            return {str(row[0]) for row in connection.execute("SELECT fingerprint FROM generations")}

    def contains(self, fingerprint: str) -> bool:
        with self._connect() as connection:
            return connection.execute("SELECT 1 FROM generations WHERE fingerprint=?", (fingerprint,)).fetchone() is not None

    def last_sequence(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT last_sequence FROM sequence_state WHERE singleton=1").fetchone()[0])

    def commit_success(
        self,
        *,
        puzzle_type: str,
        difficulty: str | None,
        seed: int,
        fingerprint: str,
        finalize_files: Callable[[int], tuple[str, str]],
    ) -> GenerationRecord:
        """Assign a sequence and commit only after both output files are finalized."""
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM generations WHERE fingerprint=?", (fingerprint,)).fetchone():
                raise ValueError("Puzzle fingerprint already exists in generation history")
            sequence_no = int(connection.execute("SELECT last_sequence FROM sequence_state WHERE singleton=1").fetchone()[0]) + 1
            output_filename, cover_filename = finalize_files(sequence_no)
            cursor = connection.execute(
                """INSERT INTO generations
                (sequence_no, puzzle_type, difficulty, seed, fingerprint, created_at, output_filename, cover_filename)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (sequence_no, puzzle_type, difficulty or "", seed, fingerprint, created_at, output_filename, cover_filename),
            )
            connection.execute("UPDATE sequence_state SET last_sequence=? WHERE singleton=1", (sequence_no,))
            generation_id = int(cursor.lastrowid)
        return GenerationRecord(generation_id, sequence_no, puzzle_type, difficulty or "", seed, fingerprint,
                                created_at, output_filename, cover_filename)

    def records(self) -> list[GenerationRecord]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM generations ORDER BY sequence_no").fetchall()
        return [GenerationRecord(**dict(row)) for row in rows]
