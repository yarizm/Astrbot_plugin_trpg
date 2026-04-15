from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from core.parser import ParsedScenario


STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUS_ARCHIVED = "archived"


class GroupSessionExistsError(RuntimeError):
    """Raised when a group already has an active scenario binding."""


@dataclass(slots=True)
class ScenarioRecord:
    id: int
    outline_import_id: int
    title: str
    summary: str
    tags: str
    recommended_players: str
    opening_scene: str
    raw_markdown: str
    status: str
    created_at: str
    published_at: str | None

    @property
    def tag_list(self) -> list[str]:
        return [item for item in self.tags.split(",") if item]


@dataclass(slots=True)
class GroupSessionRecord:
    id: int
    platform_name: str
    session_id: str
    scenario_id: int
    selected_by: str
    selected_at: str


@dataclass(slots=True)
class GroupSelectionView:
    platform_name: str
    session_id: str
    scenario_id: int
    scenario_title: str
    scenario_summary: str
    selected_by: str
    selected_at: str


class TrpgStore:
    """SQLite-backed storage for imports, scenario drafts, and group bindings."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def create_import_with_scenarios(
        self,
        source_markdown: str,
        imported_by: str,
        imported_session: str,
        scenarios: Iterable[ParsedScenario],
    ) -> list[ScenarioRecord]:
        scenario_items = list(scenarios)
        if not scenario_items:
            return []

        now = _utc_now()
        created_records: list[ScenarioRecord] = []
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO outline_imports (source_markdown, imported_by, imported_session, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (source_markdown, imported_by, imported_session, now),
            )
            outline_import_id = int(cursor.lastrowid)

            for scenario in scenario_items:
                cursor.execute(
                    """
                    INSERT INTO scenario_candidates (
                        outline_import_id,
                        title,
                        summary,
                        tags,
                        recommended_players,
                        opening_scene,
                        raw_markdown,
                        status,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        outline_import_id,
                        scenario.title,
                        scenario.summary,
                        ",".join(scenario.tags),
                        scenario.recommended_players,
                        scenario.opening_scene,
                        scenario.raw_markdown,
                        STATUS_DRAFT,
                        now,
                    ),
                )
                created_records.append(
                    ScenarioRecord(
                        id=int(cursor.lastrowid),
                        outline_import_id=outline_import_id,
                        title=scenario.title,
                        summary=scenario.summary,
                        tags=",".join(scenario.tags),
                        recommended_players=scenario.recommended_players,
                        opening_scene=scenario.opening_scene,
                        raw_markdown=scenario.raw_markdown,
                        status=STATUS_DRAFT,
                        created_at=now,
                        published_at=None,
                    )
                )

        return created_records

    def list_scenarios(self, status: str, limit: int) -> list[ScenarioRecord]:
        limit = max(1, limit)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    outline_import_id,
                    title,
                    summary,
                    tags,
                    recommended_players,
                    opening_scene,
                    raw_markdown,
                    status,
                    created_at,
                    published_at
                FROM scenario_candidates
                WHERE status = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (status, limit),
            ).fetchall()
        return [_row_to_scenario(row) for row in rows]

    def get_scenario(self, scenario_id: int) -> ScenarioRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    outline_import_id,
                    title,
                    summary,
                    tags,
                    recommended_players,
                    opening_scene,
                    raw_markdown,
                    status,
                    created_at,
                    published_at
                FROM scenario_candidates
                WHERE id = ?
                """,
                (scenario_id,),
            ).fetchone()
        return _row_to_scenario(row) if row else None

    def publish_scenario(self, scenario_id: int) -> ScenarioRecord | None:
        existing = self.get_scenario(scenario_id)
        if not existing:
            return None
        if existing.status == STATUS_PUBLISHED:
            return existing

        published_at = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE scenario_candidates
                SET status = ?, published_at = ?
                WHERE id = ?
                """,
                (STATUS_PUBLISHED, published_at, scenario_id),
            )

        return self.get_scenario(scenario_id)

    def create_group_session(
        self,
        platform_name: str,
        session_id: str,
        scenario_id: int,
        selected_by: str,
    ) -> GroupSessionRecord:
        selected_at = _utc_now()
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO group_sessions (
                        platform_name,
                        session_id,
                        scenario_id,
                        selected_by,
                        selected_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (platform_name, session_id, scenario_id, selected_by, selected_at),
                )
                record_id = int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            raise GroupSessionExistsError("group session already exists") from exc

        return GroupSessionRecord(
            id=record_id,
            platform_name=platform_name,
            session_id=session_id,
            scenario_id=scenario_id,
            selected_by=selected_by,
            selected_at=selected_at,
        )

    def get_group_selection(self, platform_name: str, session_id: str) -> GroupSelectionView | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    gs.platform_name,
                    gs.session_id,
                    gs.scenario_id,
                    gs.selected_by,
                    gs.selected_at,
                    sc.title AS scenario_title,
                    sc.summary AS scenario_summary
                FROM group_sessions AS gs
                JOIN scenario_candidates AS sc ON sc.id = gs.scenario_id
                WHERE gs.platform_name = ? AND gs.session_id = ?
                """,
                (platform_name, session_id),
            ).fetchone()

        if not row:
            return None

        return GroupSelectionView(
            platform_name=row["platform_name"],
            session_id=row["session_id"],
            scenario_id=row["scenario_id"],
            scenario_title=row["scenario_title"],
            scenario_summary=row["scenario_summary"],
            selected_by=row["selected_by"],
            selected_at=row["selected_at"],
        )

    def reset_group_session(self, platform_name: str, session_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM group_sessions
                WHERE platform_name = ? AND session_id = ?
                """,
                (platform_name, session_id),
            )
        return cursor.rowcount > 0

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS outline_imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_markdown TEXT NOT NULL,
                    imported_by TEXT NOT NULL,
                    imported_session TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS scenario_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    outline_import_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    tags TEXT NOT NULL DEFAULT '',
                    recommended_players TEXT NOT NULL DEFAULT '',
                    opening_scene TEXT NOT NULL DEFAULT '',
                    raw_markdown TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    published_at TEXT,
                    FOREIGN KEY(outline_import_id) REFERENCES outline_imports(id)
                );

                CREATE TABLE IF NOT EXISTS group_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform_name TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    scenario_id INTEGER NOT NULL,
                    selected_by TEXT NOT NULL,
                    selected_at TEXT NOT NULL,
                    UNIQUE(platform_name, session_id),
                    FOREIGN KEY(scenario_id) REFERENCES scenario_candidates(id)
                );
                """
            )

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def _row_to_scenario(row: sqlite3.Row) -> ScenarioRecord:
    return ScenarioRecord(
        id=row["id"],
        outline_import_id=row["outline_import_id"],
        title=row["title"],
        summary=row["summary"],
        tags=row["tags"],
        recommended_players=row["recommended_players"],
        opening_scene=row["opening_scene"],
        raw_markdown=row["raw_markdown"],
        status=row["status"],
        created_at=row["created_at"],
        published_at=row["published_at"],
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
