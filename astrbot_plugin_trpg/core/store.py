from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .parser import ParsedScenario


STATUS_DRAFT = "draft"
STATUS_PUBLISHED = "published"
STATUS_ARCHIVED = "archived"


class GroupSessionExistsError(RuntimeError):
    """Raised when a group already has an active scenario binding."""


class SoloSessionExistsError(RuntimeError):
    """Raised when a private solo session already has an active binding."""


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


@dataclass(slots=True)
class SoloSessionView:
    platform_name: str
    session_id: str
    user_id: str
    scenario_id: int
    scenario_title: str
    scenario_summary: str
    scenario_opening_scene: str
    transcript_json: str
    turn_count: int
    notes_json: str
    current_stage: str
    created_at: str
    updated_at: str


@dataclass(slots=True)
class SessionHistoryRecord:
    id: int
    platform_name: str
    session_id: str
    scenario_id: int
    user_id: str
    turn_count: int
    summary: str
    notes_snapshot: str
    final_stage: str
    started_at: str
    ended_at: str


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
        source_key: str | None = None,
        scenario_status: str = STATUS_DRAFT,
    ) -> list[ScenarioRecord]:
        scenario_items = list(scenarios)
        if not scenario_items:
            return []
        if source_key and self.has_import_source(source_key):
            return []

        now = _utc_now()
        published_at = now if scenario_status == STATUS_PUBLISHED else None
        created_records: list[ScenarioRecord] = []
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO outline_imports (source_markdown, imported_by, imported_session, source_key, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (source_markdown, imported_by, imported_session, source_key, now),
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
                        ,
                        published_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        outline_import_id,
                        scenario.title,
                        scenario.summary,
                        ",".join(scenario.tags),
                        scenario.recommended_players,
                        scenario.opening_scene,
                        scenario.raw_markdown,
                        scenario_status,
                        now,
                        published_at,
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
                        status=scenario_status,
                        created_at=now,
                        published_at=published_at,
                    )
                )

        return created_records

    def has_import_source(self, source_key: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM outline_imports
                WHERE source_key = ?
                LIMIT 1
                """,
                (source_key,),
            ).fetchone()
        return row is not None

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

    def create_solo_session(
        self,
        platform_name: str,
        session_id: str,
        user_id: str,
        scenario_id: int,
        transcript_json: str,
    ) -> SoloSessionView:
        now = _utc_now()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO solo_sessions (
                        platform_name,
                        session_id,
                        user_id,
                        scenario_id,
                        transcript_json,
                        turn_count,
                        notes_json,
                        current_stage,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, 0, '[]', '开场', ?, ?)
                    """,
                    (
                        platform_name,
                        session_id,
                        user_id,
                        scenario_id,
                        transcript_json,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise SoloSessionExistsError("solo session already exists") from exc

        session = self.get_solo_session(platform_name, session_id)
        if not session:
            raise RuntimeError("solo session create failed")
        return session

    def get_solo_session(self, platform_name: str, session_id: str) -> SoloSessionView | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    ss.platform_name,
                    ss.session_id,
                    ss.user_id,
                    ss.scenario_id,
                    ss.transcript_json,
                    ss.turn_count,
                    ss.notes_json,
                    ss.current_stage,
                    ss.created_at,
                    ss.updated_at,
                    sc.title AS scenario_title,
                    sc.summary AS scenario_summary,
                    sc.opening_scene AS scenario_opening_scene
                FROM solo_sessions AS ss
                JOIN scenario_candidates AS sc ON sc.id = ss.scenario_id
                WHERE ss.platform_name = ? AND ss.session_id = ?
                LIMIT 1
                """,
                (platform_name, session_id),
            ).fetchone()

        if not row:
            return None

        return SoloSessionView(
            platform_name=row["platform_name"],
            session_id=row["session_id"],
            user_id=row["user_id"],
            scenario_id=row["scenario_id"],
            scenario_title=row["scenario_title"],
            scenario_summary=row["scenario_summary"],
            scenario_opening_scene=row["scenario_opening_scene"],
            transcript_json=row["transcript_json"],
            turn_count=row["turn_count"],
            notes_json=row["notes_json"],
            current_stage=row["current_stage"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_solo_session(
        self,
        platform_name: str,
        session_id: str,
        transcript_json: str,
        turn_count: int,
    ) -> SoloSessionView | None:
        updated_at = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE solo_sessions
                SET transcript_json = ?, turn_count = ?, updated_at = ?
                WHERE platform_name = ? AND session_id = ?
                """,
                (transcript_json, turn_count, updated_at, platform_name, session_id),
            )
        return self.get_solo_session(platform_name, session_id)

    def reset_solo_session(self, platform_name: str, session_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM solo_sessions
                WHERE platform_name = ? AND session_id = ?
                """,
                (platform_name, session_id),
            )
        return cursor.rowcount > 0

    def update_solo_session_extra(
        self,
        platform_name: str,
        session_id: str,
        notes_json: str | None = None,
        current_stage: str | None = None,
    ) -> None:
        updates = []
        params: list[object] = []
        if notes_json is not None:
            updates.append("notes_json = ?")
            params.append(notes_json)
        if current_stage is not None:
            updates.append("current_stage = ?")
            params.append(current_stage)
        if not updates:
            return
        updates.append("updated_at = ?")
        params.append(_utc_now())
        params.extend([platform_name, session_id])
        with self._connect() as connection:
            connection.execute(
                f"UPDATE solo_sessions SET {', '.join(updates)} WHERE platform_name = ? AND session_id = ?",
                params,
            )

    def create_session_history(
        self,
        platform_name: str,
        session_id: str,
        scenario_id: int,
        user_id: str,
        turn_count: int,
        summary: str,
        notes_snapshot: str,
        final_stage: str,
        started_at: str,
    ) -> SessionHistoryRecord:
        ended_at = _utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO session_history (
                    platform_name, session_id, scenario_id, user_id,
                    turn_count, summary, notes_snapshot, final_stage,
                    started_at, ended_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (platform_name, session_id, scenario_id, user_id,
                 turn_count, summary, notes_snapshot, final_stage,
                 started_at, ended_at),
            )
        return SessionHistoryRecord(
            id=int(cursor.lastrowid),
            platform_name=platform_name,
            session_id=session_id,
            scenario_id=scenario_id,
            user_id=user_id,
            turn_count=turn_count,
            summary=summary,
            notes_snapshot=notes_snapshot,
            final_stage=final_stage,
            started_at=started_at,
            ended_at=ended_at,
        )

    def list_session_history(
        self,
        platform_name: str,
        session_id: str,
        limit: int = 10,
        scenario_id: int | None = None,
    ) -> list[SessionHistoryRecord]:
        limit = max(1, limit)
        query = """
                SELECT id, platform_name, session_id, scenario_id, user_id,
                       turn_count, summary, notes_snapshot, final_stage,
                       started_at, ended_at
                FROM session_history
                WHERE platform_name = ? AND session_id = ?
                """
        params: list[object] = [platform_name, session_id]
        if scenario_id is not None:
            query += " AND scenario_id = ?"
            params.append(scenario_id)
        query += """
                ORDER BY id DESC
                LIMIT ?
                """
        params.append(limit)
        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [
            SessionHistoryRecord(
                id=row["id"],
                platform_name=row["platform_name"],
                session_id=row["session_id"],
                scenario_id=row["scenario_id"],
                user_id=row["user_id"],
                turn_count=row["turn_count"],
                summary=row["summary"],
                notes_snapshot=row["notes_snapshot"],
                final_stage=row["final_stage"],
                started_at=row["started_at"],
                ended_at=row["ended_at"],
            )
            for row in rows
        ]

    def export_scenario_markdown(self, scenario: ScenarioRecord, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        safe_title = _sanitize_filename_component(scenario.title)
        filename = f"{scenario.id}_{safe_title}.md"
        filepath = output_dir / filename

        tags = " / ".join(scenario.tag_list) if scenario.tag_list else "无标签"
        status_map = {"draft": "草稿", "published": "已发布", "archived": "已归档"}
        status_label = status_map.get(scenario.status, scenario.status)

        content = (
            f"# {scenario.title}\n\n"
            f"**标签**：{tags}\n"
            f"**推荐人数**：{scenario.recommended_players or '未填写'}\n"
            f"**状态**：{status_label}\n\n"
            f"## 简介\n{scenario.summary or '暂无简介'}\n\n"
        )
        if scenario.opening_scene:
            content += f"## 开场设定\n{scenario.opening_scene}\n\n"
        content += f"## 剧本原文\n{scenario.raw_markdown}\n"

        filepath.write_text(content, encoding="utf-8")
        return filepath

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS outline_imports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_markdown TEXT NOT NULL,
                    imported_by TEXT NOT NULL,
                    imported_session TEXT NOT NULL,
                    source_key TEXT,
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

                CREATE TABLE IF NOT EXISTS solo_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform_name TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    scenario_id INTEGER NOT NULL,
                    transcript_json TEXT NOT NULL DEFAULT '[]',
                    turn_count INTEGER NOT NULL DEFAULT 0,
                    notes_json TEXT NOT NULL DEFAULT '[]',
                    current_stage TEXT NOT NULL DEFAULT '开场',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(platform_name, session_id),
                    FOREIGN KEY(scenario_id) REFERENCES scenario_candidates(id)
                );

                CREATE TABLE IF NOT EXISTS session_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform_name TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    scenario_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    turn_count INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    notes_snapshot TEXT NOT NULL DEFAULT '[]',
                    final_stage TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    FOREIGN KEY(scenario_id) REFERENCES scenario_candidates(id)
                );
                """
            )
            self._ensure_column(connection, "outline_imports", "source_key", "TEXT")
            self._ensure_column(connection, "solo_sessions", "notes_json", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(connection, "solo_sessions", "current_stage", "TEXT NOT NULL DEFAULT '开场'")
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_outline_imports_source_key
                ON outline_imports(source_key)
                WHERE source_key IS NOT NULL
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

    @staticmethod
    def _ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
        rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        existing_columns = {row["name"] for row in rows}
        if column_name in existing_columns:
            return
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


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


_INVALID_FILENAME_CHARS_RE = re.compile(r'[<>:"/\\\\|?*]+')


def _sanitize_filename_component(title: str) -> str:
    sanitized = _INVALID_FILENAME_CHARS_RE.sub("_", title).strip().rstrip(". ")
    return sanitized or "scenario"
