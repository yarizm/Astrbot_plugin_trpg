from __future__ import annotations

import json
import unittest
from pathlib import Path
from uuid import uuid4

from astrbot_plugin_trpg.core.service import TrpgService
from astrbot_plugin_trpg.core.solo_mode import build_system_prompt, roll_dice
from astrbot_plugin_trpg.core.store import TrpgStore


class DiceRollTest(unittest.TestCase):
    def test_roll_d20(self) -> None:
        result = roll_dice("d20")
        self.assertIn("d20 = ", result)
        value = int(result.split("=")[1].strip())
        self.assertGreaterEqual(value, 1)
        self.assertLessEqual(value, 20)

    def test_roll_2d6_plus_3(self) -> None:
        result = roll_dice("2d6+3")
        self.assertIn("=", result)
        total = int(result.split("=")[-1].strip())
        self.assertGreaterEqual(total, 5)  # 2*1 + 3
        self.assertLessEqual(total, 15)  # 2*6 + 3

    def test_roll_d100(self) -> None:
        result = roll_dice("d100")
        self.assertIn("d100 = ", result)
        value = int(result.split("=")[1].strip())
        self.assertGreaterEqual(value, 1)
        self.assertLessEqual(value, 100)

    def test_invalid_expression(self) -> None:
        result = roll_dice("abc")
        self.assertIn("无效", result)

    def test_roll_with_spaces(self) -> None:
        result = roll_dice(" d20 ")
        self.assertIn("d20 = ", result)


class SystemPromptTest(unittest.TestCase):
    def test_build_system_prompt(self) -> None:
        prompt = build_system_prompt(
            scenario_title="测试剧本",
            scenario_summary="测试简介",
            scenario_tags=["悬疑", "克苏鲁"],
            recommended_players="3-5 人",
            opening_scene="玩家来到港口",
            current_stage="开场",
            turn_count=0,
            notes_json="[]",
        )
        self.assertIn("测试剧本", prompt)
        self.assertIn("悬疑 / 克苏鲁", prompt)
        self.assertIn("暂无记录", prompt)
        self.assertIn("开场", prompt)

    def test_build_system_prompt_with_notes(self) -> None:
        notes = json.dumps(["线索1", "线索2"], ensure_ascii=False)
        prompt = build_system_prompt(
            scenario_title="测试剧本",
            scenario_summary="测试简介",
            scenario_tags=[],
            recommended_players="",
            opening_scene="",
            current_stage="调查",
            turn_count=3,
            notes_json=notes,
        )
        self.assertIn("线索1", prompt)
        self.assertIn("线索2", prompt)
        self.assertIn("调查", prompt)

    def test_build_system_prompt_with_history(self) -> None:
        prompt = build_system_prompt(
            scenario_title="测试剧本",
            scenario_summary="测试简介",
            scenario_tags=[],
            recommended_players="",
            opening_scene="",
            current_stage="开场",
            turn_count=0,
            notes_json="[]",
            history_summary="上一局玩家发现了真相",
        )
        self.assertIn("上一局玩家发现了真相", prompt)
        self.assertIn("历史摘要", prompt)


class SoloModeServiceTest(unittest.TestCase):
    def test_start_and_reset_solo_session(self) -> None:
        temp_root = Path.cwd() / "test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        db_path = temp_root / f"solo-mode-{uuid4().hex}.sqlite3"
        try:
            store = TrpgStore(db_path)
            service = TrpgService(store)
            seeded = service.seed_builtin_scenarios(
                imported_by="tester",
                imported_session="unit-test",
            )
            self.assertGreaterEqual(len(seeded), 1)
            scenario_id = seeded[0].id

            session, opening = service.start_solo_session(
                platform_name="test-platform",
                session_id="private-session",
                user_id="user-1",
                scenario_id=scenario_id,
            )
            self.assertEqual(session.turn_count, 0)
            self.assertEqual(session.current_stage, "开场")
            self.assertEqual(session.notes_json, "[]")
            self.assertIn(seeded[0].title, opening)

            # Verify session is retrievable
            current = service.get_solo_session("test-platform", "private-session")
            self.assertIsNotNone(current)
            self.assertEqual(current.current_stage, "开场")

            # Reset
            removed = service.reset_solo_session("test-platform", "private-session")
            self.assertTrue(removed)
            self.assertIsNone(service.get_solo_session("test-platform", "private-session"))
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_update_solo_session_extra(self) -> None:
        temp_root = Path.cwd() / "test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        db_path = temp_root / f"solo-extra-{uuid4().hex}.sqlite3"
        try:
            store = TrpgStore(db_path)
            service = TrpgService(store)
            seeded = service.seed_builtin_scenarios(
                imported_by="tester",
                imported_session="unit-test",
            )
            scenario_id = seeded[0].id

            service.start_solo_session(
                platform_name="test-platform",
                session_id="private-session",
                user_id="user-1",
                scenario_id=scenario_id,
            )

            # Update notes and stage
            store.update_solo_session_extra(
                "test-platform", "private-session",
                notes_json=json.dumps(["线索A"], ensure_ascii=False),
                current_stage="调查",
            )

            session = service.get_solo_session("test-platform", "private-session")
            self.assertIsNotNone(session)
            self.assertEqual(session.current_stage, "调查")
            self.assertIn("线索A", session.notes_json)

            service.reset_solo_session("test-platform", "private-session")
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_session_history(self) -> None:
        temp_root = Path.cwd() / "test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        db_path = temp_root / f"solo-history-{uuid4().hex}.sqlite3"
        try:
            store = TrpgStore(db_path)
            service = TrpgService(store)
            seeded = service.seed_builtin_scenarios(
                imported_by="tester",
                imported_session="unit-test",
            )
            scenario_id = seeded[0].id

            service.start_solo_session(
                platform_name="test-platform",
                session_id="private-session",
                user_id="user-1",
                scenario_id=scenario_id,
            )

            # Create history record directly
            store.create_session_history(
                platform_name="test-platform",
                session_id="private-session",
                scenario_id=scenario_id,
                user_id="user-1",
                turn_count=5,
                summary="玩家调查了港口，发现了失踪渔船的秘密",
                notes_snapshot=json.dumps(["线索1"], ensure_ascii=False),
                final_stage="危机",
                started_at="2024-01-01T00:00:00+00:00",
            )

            history = service.list_session_history("test-platform", "private-session")
            self.assertEqual(len(history), 1)
            self.assertIn("港口", history[0].summary)
            self.assertEqual(history[0].turn_count, 5)
            self.assertEqual(history[0].final_stage, "危机")

            service.reset_solo_session("test-platform", "private-session")
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
