from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from core.service import TrpgService
from core.store import STATUS_PUBLISHED, TrpgStore


class BuiltinScenarioSeedTest(unittest.TestCase):
    def test_seed_builtin_scenarios_only_once_and_publish_immediately(self) -> None:
        temp_root = Path.cwd() / "test_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        db_path = temp_root / f"builtin-seed-{uuid4().hex}.sqlite3"
        try:
            store = TrpgStore(db_path)
            service = TrpgService(store)

            created = service.seed_builtin_scenarios(
                imported_by="tester",
                imported_session="unit-test",
            )
            self.assertEqual(len(created), 3)
            self.assertTrue(all(item.status == STATUS_PUBLISHED for item in created))

            published = service.list_published(limit=10)
            self.assertEqual(len(published), 3)
            by_id = service.resolve_published_scenario(str(published[0].id))
            self.assertIsNotNone(by_id)
            self.assertEqual(by_id.id, published[0].id)

            by_title = service.resolve_published_scenario(published[0].title)
            self.assertIsNotNone(by_title)
            self.assertEqual(by_title.id, published[0].id)

            created_again = service.seed_builtin_scenarios(
                imported_by="tester",
                imported_session="unit-test",
            )
            self.assertEqual(created_again, [])
            self.assertEqual(len(service.list_published(limit=10)), 3)
        finally:
            if db_path.exists():
                db_path.unlink()


if __name__ == "__main__":
    unittest.main()
