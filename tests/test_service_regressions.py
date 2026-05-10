from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path
from uuid import uuid4

from core.parser import ParsedScenario
from core.service import TrpgService
from core.store import STATUS_PUBLISHED, TrpgStore


class _FakeFunctionTool:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeToolSet:
    def __init__(self, tools):
        self.tools = tools


class _FakeCompletion:
    def __init__(self, completion_text: str):
        self.completion_text = completion_text


class _FakeContext:
    async def tool_loop_agent(self, **_kwargs):
        return _FakeCompletion("[SESSION_END] 你走出了最后一扇门。")

    async def llm_generate(self, **_kwargs):
        return _FakeCompletion("调查员成功离开灯塔，真相被记录下来。")


class ServiceRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = Path.cwd() / "test_tmp"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.temp_root / f"service-regression-{uuid4().hex}.sqlite3"
        self.store = TrpgStore(self.db_path)
        self.service = TrpgService(self.store)

    def tearDown(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()

    def _create_published_scenario(self, title: str) -> int:
        created = self.store.create_import_with_scenarios(
            source_markdown=f"## 剧本：{title}",
            imported_by="tester",
            imported_session="unit-test",
            scenarios=[
                ParsedScenario(
                    title=title,
                    summary=f"{title} 简介",
                    tags=["测试"],
                    recommended_players="1 人",
                    opening_scene=f"{title} 开场",
                    raw_markdown=f"## 剧本：{title}",
                )
            ],
            scenario_status=STATUS_PUBLISHED,
        )
        return created[0].id

    def test_auto_end_reply_includes_summary_and_resets_session(self) -> None:
        scenario_id = self._create_published_scenario("自动结团测试")
        self.service.start_solo_session(
            platform_name="test-platform",
            session_id="private-session",
            user_id="user-1",
            scenario_id=scenario_id,
        )

        fake_tool_module = types.ModuleType("astrbot.core.agent.tool")
        fake_tool_module.FunctionTool = _FakeFunctionTool
        fake_tool_module.ToolExecResult = str
        fake_tool_module.ToolSet = _FakeToolSet

        original_modules = {
            name: sys.modules.get(name)
            for name in (
                "astrbot",
                "astrbot.core",
                "astrbot.core.agent",
                "astrbot.core.agent.tool",
                "core.tools",
            )
        }
        try:
            sys.modules["astrbot"] = types.ModuleType("astrbot")
            sys.modules["astrbot.core"] = types.ModuleType("astrbot.core")
            sys.modules["astrbot.core.agent"] = types.ModuleType("astrbot.core.agent")
            sys.modules["astrbot.core.agent.tool"] = fake_tool_module
            sys.modules.pop("core.tools", None)

            result = asyncio.run(
                self.service.advance_solo_session_llm(
                    context=_FakeContext(),
                    event=object(),
                    provider_id="provider",
                    platform_name="test-platform",
                    session_id="private-session",
                    player_message="我推开大门。",
                )
            )
        finally:
            for name, module in original_modules.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

        self.assertIsNotNone(result)
        self.assertIn("你走出了最后一扇门。", result)
        self.assertIn("调查员成功离开灯塔，真相被记录下来。", result)
        self.assertIsNone(self.service.get_solo_session("test-platform", "private-session"))

        history = self.service.list_session_history("test-platform", "private-session")
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].scenario_id, scenario_id)

    def test_history_summary_uses_same_scenario_only(self) -> None:
        first_scenario_id = self._create_published_scenario("旧剧本")
        second_scenario_id = self._create_published_scenario("新剧本")

        self.store.create_session_history(
            platform_name="test-platform",
            session_id="private-session",
            scenario_id=first_scenario_id,
            user_id="user-1",
            turn_count=4,
            summary="这是旧剧本的历史摘要",
            notes_snapshot="[]",
            final_stage="结局",
            started_at="2024-01-01T00:00:00+00:00",
        )
        self.store.create_session_history(
            platform_name="test-platform",
            session_id="private-session",
            scenario_id=second_scenario_id,
            user_id="user-1",
            turn_count=2,
            summary="这是新剧本的历史摘要",
            notes_snapshot="[]",
            final_stage="开场",
            started_at="2024-01-02T00:00:00+00:00",
        )

        same_scenario_summary = self.service._get_latest_history_summary(
            "test-platform",
            "private-session",
            first_scenario_id,
        )
        self.assertEqual(same_scenario_summary, "这是旧剧本的历史摘要")

    def test_export_scenario_sanitizes_windows_invalid_filename_chars(self) -> None:
        scenario_id = self._create_published_scenario('雾港?回声*<终局>|"档案":版')
        export_dir = self.temp_root / f"exports-{uuid4().hex}"
        try:
            exported = self.service.export_scenario_markdown(scenario_id, export_dir)
            self.assertIsNotNone(exported)
            self.assertTrue(exported.exists())
            self.assertEqual(exported.suffix, ".md")
            for invalid_char in '<>:"/\\|?*':
                self.assertNotIn(invalid_char, exported.name)
        finally:
            if export_dir.exists():
                for child in export_dir.iterdir():
                    child.unlink()
                export_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
