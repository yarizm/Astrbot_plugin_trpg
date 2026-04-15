from __future__ import annotations

from dataclasses import dataclass

from core.parser import OutlineParseError, parse_scenario_outline
from core.store import STATUS_DRAFT, STATUS_PUBLISHED, GroupSelectionView, ScenarioRecord, TrpgStore


@dataclass(slots=True)
class PendingImport:
    trigger_message_id: str
    session_id: str


class TrpgService:
    """Application service for import flow, publishing, and group selection."""

    def __init__(self, store: TrpgStore):
        self.store = store
        self._pending_imports: dict[str, PendingImport] = {}

    def arm_import(self, sender_id: str, session_key: str, trigger_message_id: str) -> None:
        self._pending_imports[self._pending_key(sender_id, session_key)] = PendingImport(
            trigger_message_id=trigger_message_id,
            session_id=session_key,
        )

    def consume_import(
        self,
        sender_id: str,
        session_key: str,
        message_id: str,
        markdown_text: str,
        imported_by: str,
        imported_session: str,
        max_chars: int,
    ) -> list[ScenarioRecord] | None:
        key = self._pending_key(sender_id, session_key)
        pending = self._pending_imports.get(key)
        if not pending:
            return None

        if message_id == pending.trigger_message_id:
            return None

        self._pending_imports.pop(key, None)
        normalized = (markdown_text or "").strip()
        if not normalized:
            raise OutlineParseError("下一条消息必须是 Markdown 文本。")
        if len(normalized) > max_chars:
            raise OutlineParseError(f"文本长度超过限制（{max_chars} 字符）。请拆分后重新导入。")

        parsed_scenarios = parse_scenario_outline(normalized)
        return self.store.create_import_with_scenarios(
            source_markdown=normalized,
            imported_by=imported_by,
            imported_session=imported_session,
            scenarios=parsed_scenarios,
        )

    def list_drafts(self, limit: int) -> list[ScenarioRecord]:
        return self.store.list_scenarios(STATUS_DRAFT, limit)

    def list_published(self, limit: int) -> list[ScenarioRecord]:
        return self.store.list_scenarios(STATUS_PUBLISHED, limit)

    def publish_scenario(self, scenario_id: int) -> ScenarioRecord | None:
        return self.store.publish_scenario(scenario_id)

    def select_group_scenario(
        self,
        platform_name: str,
        session_id: str,
        scenario_id: int,
        selected_by: str,
    ) -> ScenarioRecord:
        scenario = self.store.get_scenario(scenario_id)
        if not scenario or scenario.status != STATUS_PUBLISHED:
            raise ValueError(f"编号 {scenario_id} 不是可选的已发布剧本。")

        self.store.create_group_session(platform_name, session_id, scenario_id, selected_by)
        return scenario

    def get_group_selection(self, platform_name: str, session_id: str) -> GroupSelectionView | None:
        return self.store.get_group_selection(platform_name, session_id)

    def reset_group_session(self, platform_name: str, session_id: str) -> bool:
        return self.store.reset_group_session(platform_name, session_id)

    def format_scenario_list(self, title: str, scenarios: list[ScenarioRecord]) -> str:
        lines = [title]
        for scenario in scenarios:
            tags = " / ".join(scenario.tag_list) if scenario.tag_list else "无标签"
            recommend = scenario.recommended_players or "未填写"
            summary = scenario.summary or "暂无简介"
            lines.append(
                f"[{scenario.id}] {scenario.title}\n"
                f"简介：{summary}\n"
                f"标签：{tags}\n"
                f"推荐人数：{recommend}"
            )
        return "\n\n".join(lines)

    @staticmethod
    def preview_titles(scenarios: list[ScenarioRecord], limit: int = 5) -> str:
        titles = "、".join(record.title for record in scenarios[:limit])
        if len(scenarios) <= limit:
            return titles
        return f"{titles} 等 {len(scenarios)} 个剧本"

    @staticmethod
    def _pending_key(sender_id: str, session_key: str) -> str:
        return f"{sender_id}::{session_key}"
