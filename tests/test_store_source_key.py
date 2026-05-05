from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from Astrbot_plugin_trpg.core.parser import ParsedScenario
from Astrbot_plugin_trpg.core.store import STATUS_DRAFT, TrpgStore


class StoreSourceKeyTest(unittest.TestCase):
    def test_create_import_with_source_key_is_idempotent(self) -> None:
        temp_root = Path.cwd() / "test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        db_path = temp_root / f"store-source-key-{uuid4().hex}.sqlite3"
        try:
            store = TrpgStore(db_path)
            scenario = ParsedScenario(
                title="测试剧本",
                summary="测试简介",
                tags=["测试", "内置"],
                recommended_players="3-4 人",
                opening_scene="测试开场",
                raw_markdown="## 剧本：测试剧本",
            )

            created = store.create_import_with_scenarios(
                source_markdown=scenario.raw_markdown,
                imported_by="tester",
                imported_session="unit-test",
                scenarios=[scenario],
                source_key="builtin:test-pack:v1",
                scenario_status=STATUS_DRAFT,
            )
            self.assertEqual(len(created), 1)
            self.assertTrue(store.has_import_source("builtin:test-pack:v1"))

            created_again = store.create_import_with_scenarios(
                source_markdown=scenario.raw_markdown,
                imported_by="tester",
                imported_session="unit-test",
                scenarios=[scenario],
                source_key="builtin:test-pack:v1",
                scenario_status=STATUS_DRAFT,
            )
            self.assertEqual(created_again, [])
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
