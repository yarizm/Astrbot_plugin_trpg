from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from core.parser import ParsedScenario
from core.store import STATUS_DRAFT, STATUS_PUBLISHED, TrpgStore


def _make_store() -> tuple[TrpgStore, Path]:
    temp_root = Path.cwd() / "test_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    db_path = temp_root / f"web-store-{uuid4().hex}.sqlite3"
    return TrpgStore(db_path), db_path


def _make_scenario(title: str = "测试剧本") -> ParsedScenario:
    return ParsedScenario(
        title=title,
        summary="测试简介",
        tags=["测试"],
        recommended_players="3-4 人",
        opening_scene="测试开场",
        raw_markdown=f"## 剧本：{title}",
    )


class ListScenariosAllTest(unittest.TestCase):
    def test_returns_all_statuses(self) -> None:
        store, db_path = _make_store()
        try:
            store.create_import_with_scenarios(
                source_markdown="md", imported_by="t", imported_session="t",
                scenarios=[_make_scenario("草稿剧本")], scenario_status=STATUS_DRAFT,
            )
            store.create_import_with_scenarios(
                source_markdown="md", imported_by="t", imported_session="t",
                scenarios=[_make_scenario("已发布剧本")], scenario_status=STATUS_PUBLISHED,
            )
            all_scenarios = store.list_scenarios_all()
            titles = {s.title for s in all_scenarios}
            self.assertIn("草稿剧本", titles)
            self.assertIn("已发布剧本", titles)
        finally:
            if db_path.exists():
                db_path.unlink()


class UpdateScenarioContentTest(unittest.TestCase):
    def test_update_success(self) -> None:
        store, db_path = _make_store()
        try:
            created = store.create_import_with_scenarios(
                source_markdown="md", imported_by="t", imported_session="t",
                scenarios=[_make_scenario()],
            )
            sid = created[0].id
            updated = store.update_scenario_content(
                scenario_id=sid,
                title="新标题",
                summary="新简介",
                tags="新标签",
                recommended_players="5-6 人",
                opening_scene="新开场",
                raw_markdown="## 剧本：新标题",
            )
            self.assertIsNotNone(updated)
            self.assertEqual(updated.title, "新标题")
            self.assertEqual(updated.summary, "新简介")
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_update_not_found(self) -> None:
        store, db_path = _make_store()
        try:
            result = store.update_scenario_content(
                scenario_id=99999,
                title="x", summary="x", tags="x",
                recommended_players="x", opening_scene="x", raw_markdown="x",
            )
            self.assertIsNone(result)
        finally:
            if db_path.exists():
                db_path.unlink()


class ListActiveSessionsTest(unittest.TestCase):
    def test_returns_solo_session(self) -> None:
        store, db_path = _make_store()
        try:
            created = store.create_import_with_scenarios(
                source_markdown="md", imported_by="t", imported_session="t",
                scenarios=[_make_scenario()],
            )
            sid = created[0].id
            store.create_solo_session(
                platform_name="test-platform",
                session_id="sess-001",
                user_id="user-1",
                scenario_id=sid,
                transcript_json="[]",
            )
            active = store.list_active_sessions()
            self.assertEqual(len(active), 1)
            self.assertEqual(active[0].platform_name, "test-platform")
            self.assertEqual(active[0].session_id, "sess-001")
            self.assertEqual(active[0].scenario_title, "测试剧本")
        finally:
            if db_path.exists():
                db_path.unlink()


class ListAllSessionHistoryTest(unittest.TestCase):
    def test_returns_history_records(self) -> None:
        store, db_path = _make_store()
        try:
            created = store.create_import_with_scenarios(
                source_markdown="md", imported_by="t", imported_session="t",
                scenarios=[_make_scenario()],
            )
            sid = created[0].id
            store.create_session_history(
                platform_name="test-platform",
                session_id="sess-001",
                scenario_id=sid,
                user_id="user-1",
                turn_count=5,
                summary="测试总结",
                notes_snapshot='["笔记1"]',
                final_stage="结束",
                started_at="2025-01-01T00:00:00",
            )
            history = store.list_all_session_history()
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0].summary, "测试总结")
            self.assertEqual(history[0].platform_name, "test-platform")
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
