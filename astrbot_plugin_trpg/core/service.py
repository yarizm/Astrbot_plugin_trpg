from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("astrbot")

from .builtin_scenarios import BUILTIN_SCENARIO_MARKDOWN, BUILTIN_SCENARIO_SOURCE_KEY
from .parser import OutlineParseError, parse_scenario_outline
from .solo_mode import (
    build_summary_prompt,
    build_system_prompt,
)
from .store import (
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    GroupSelectionView,
    ScenarioRecord,
    SessionHistoryRecord,
    SoloSessionExistsError,
    SoloSessionView,
    TrpgStore,
)


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

    def resolve_published_scenario(self, scenario_ref: str | int) -> ScenarioRecord | None:
        if isinstance(scenario_ref, int):
            scenario = self.store.get_scenario(scenario_ref)
            if scenario and scenario.status == STATUS_PUBLISHED:
                return scenario
            return None

        ref = str(scenario_ref or "").strip()
        if not ref:
            return None

        digit_match = re.fullmatch(r"\s*(\d+)\s*(?:号|號|#)?\s*", ref)
        if digit_match:
            return self.resolve_published_scenario(int(digit_match.group(1)))

        normalized_ref = _normalize_scenario_ref(ref)
        exact_matches: list[ScenarioRecord] = []
        partial_matches: list[ScenarioRecord] = []
        for scenario in self.list_published(limit=1000):
            normalized_title = _normalize_scenario_ref(scenario.title)
            if normalized_title == normalized_ref:
                exact_matches.append(scenario)
            elif normalized_ref in normalized_title or normalized_title in normalized_ref:
                partial_matches.append(scenario)

        if len(exact_matches) == 1:
            return exact_matches[0]
        if not exact_matches and len(partial_matches) == 1:
            return partial_matches[0]
        return None

    def seed_builtin_scenarios(self, imported_by: str, imported_session: str) -> list[ScenarioRecord]:
        if self.store.has_import_source(BUILTIN_SCENARIO_SOURCE_KEY):
            return []

        return self.store.create_import_with_scenarios(
            source_markdown=BUILTIN_SCENARIO_MARKDOWN,
            imported_by=imported_by,
            imported_session=imported_session,
            scenarios=parse_scenario_outline(BUILTIN_SCENARIO_MARKDOWN),
            source_key=BUILTIN_SCENARIO_SOURCE_KEY,
            scenario_status=STATUS_PUBLISHED,
        )

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

    def start_solo_session(
        self,
        platform_name: str,
        session_id: str,
        user_id: str,
        scenario_id: int,
    ) -> tuple[SoloSessionView, str]:
        scenario = self.store.get_scenario(scenario_id)
        if not scenario or scenario.status != STATUS_PUBLISHED:
            raise ValueError(f"编号 {scenario_id} 不是可用的已发布剧本。")
        if self.store.get_solo_session(platform_name, session_id):
            raise SoloSessionExistsError("solo session already exists")

        session = self.store.create_solo_session(
            platform_name=platform_name,
            session_id=session_id,
            user_id=user_id,
            scenario_id=scenario_id,
            transcript_json="[]",
        )
        opening = (
            f"单人跑团已开始：《{scenario.title}》\n"
            f"简介：{scenario.summary or '暂无简介'}\n"
            f"开场设定：{scenario.opening_scene or '故事即将开始。'}\n\n"
            "请发送你的第一条行动，GM 将为你推进剧情。"
        )
        return session, opening

    def get_solo_session(self, platform_name: str, session_id: str) -> SoloSessionView | None:
        return self.store.get_solo_session(platform_name, session_id)

    def advance_solo_session(
        self,
        platform_name: str,
        session_id: str,
        player_message: str,
    ) -> str | None:
        """Legacy deterministic mode — kept for backward compatibility with existing tests."""
        return None

    async def advance_solo_session_llm(
        self,
        context: object,
        event: object,
        provider_id: str,
        platform_name: str,
        session_id: str,
        player_message: str,
        max_steps: int = 10,
        system_prompt_override: str = "",
        fallback_provider_id: str = "",
    ) -> str | None:
        """LLM-driven solo session turn. Returns the LLM's narrative reply."""
        from astrbot.core.agent.tool import ToolSet
        from .tools import build_solo_tools

        session = self.store.get_solo_session(platform_name, session_id)
        if not session:
            return None

        scenario = self.store.get_scenario(session.scenario_id)
        if not scenario:
            raise ValueError("当前单人剧本不存在，可能已被删除。")

        # Build system prompt
        history_summary = self._get_latest_history_summary(
            platform_name,
            session_id,
            session.scenario_id,
        )
        if system_prompt_override:
            system_prompt = system_prompt_override.format(
                title=scenario.title,
                summary=scenario.summary,
                tags=" / ".join(scenario.tag_list),
                recommended_players=scenario.recommended_players,
                opening_scene=scenario.opening_scene,
                current_stage=session.current_stage,
                turn_count=session.turn_count,
            )
        else:
            system_prompt = build_system_prompt(
                scenario_title=scenario.title,
                scenario_summary=scenario.summary,
                scenario_tags=scenario.tag_list,
                recommended_players=scenario.recommended_players,
                opening_scene=scenario.opening_scene,
                current_stage=session.current_stage,
                turn_count=session.turn_count,
                notes_json=session.notes_json,
                history_summary=history_summary,
            )

        # Build tools
        tools_list = build_solo_tools(self.store, platform_name, session_id)
        tool_set = ToolSet(tools=tools_list)

        # Build conversation history from transcript
        contexts = []
        try:
            from astrbot.core.agent.message import Message as AgentMessage
            history = json.loads(session.transcript_json or "[]")
            if isinstance(history, list):
                for msg in history:
                    if isinstance(msg, dict) and msg.get("role") in ("user", "assistant"):
                        contexts.append(AgentMessage(role=msg["role"], content=msg.get("content", "")))
        except (ImportError, json.JSONDecodeError, Exception):
            contexts = []

        # Call LLM agent loop (with fallback support)
        try:
            llm_resp = await context.tool_loop_agent(
                event=event,
                chat_provider_id=provider_id,
                prompt=player_message,
                contexts=contexts if contexts else None,
                tools=tool_set,
                system_prompt=system_prompt,
                max_steps=max_steps,
            )
        except Exception as primary_exc:
            if not fallback_provider_id:
                raise
            logger.warning("TRPG primary provider %s failed (%s), trying fallback %s",
                           provider_id, primary_exc, fallback_provider_id)
            llm_resp = await context.tool_loop_agent(
                event=event,
                chat_provider_id=fallback_provider_id,
                prompt=player_message,
                contexts=contexts if contexts else None,
                tools=tool_set,
                system_prompt=system_prompt,
                max_steps=max_steps,
            )

        reply = llm_resp.completion_text or "（GM 没有回应，请重试。）"

        # Update session state
        transcript = self._append_transcript(
            session.transcript_json, player_message, reply,
        )
        self.store.update_solo_session(
            platform_name=platform_name,
            session_id=session_id,
            transcript_json=transcript,
            turn_count=session.turn_count + 1,
        )

        # Check for end session signal
        if "[SESSION_END]" in reply:
            cleaned = reply.replace("[SESSION_END]", "").strip()
            final_message = await self._finalize_session(
                context,
                event,
                provider_id,
                platform_name,
                session_id,
                fallback_provider_id,
            )
            return self._build_session_end_reply(cleaned, final_message)

        return reply

    async def end_solo_session_with_summary(
        self,
        context: object,
        event: object,
        provider_id: str,
        platform_name: str,
        session_id: str,
        fallback_provider_id: str = "",
    ) -> str:
        """End session with LLM-generated summary. Returns the summary text."""
        session = self.store.get_solo_session(platform_name, session_id)
        if not session:
            return "当前没有正在进行的单人跑团。"

        return await self._finalize_session(context, event, provider_id, platform_name, session_id, fallback_provider_id)

    async def _finalize_session(
        self,
        context: object,
        event: object,
        provider_id: str,
        platform_name: str,
        session_id: str,
        fallback_provider_id: str = "",
    ) -> str:
        """Generate summary via LLM, save history, and reset session."""
        session = self.store.get_solo_session(platform_name, session_id)
        if not session:
            return "当前没有正在进行的单人跑团。"

        # Generate summary (with fallback)
        summary_prompt = build_summary_prompt(session.transcript_json)
        try:
            summary_resp = await context.llm_generate(
                chat_provider_id=provider_id,
                prompt=summary_prompt,
            )
            summary = summary_resp.completion_text or "跑团已结束，未能生成总结。"
        except Exception as primary_exc:
            if not fallback_provider_id:
                summary = "跑团已结束，总结生成失败。"
            else:
                try:
                    logger.warning("TRPG summary primary provider %s failed (%s), trying fallback %s",
                                   provider_id, primary_exc, fallback_provider_id)
                    summary_resp = await context.llm_generate(
                        chat_provider_id=fallback_provider_id,
                        prompt=summary_prompt,
                    )
                    summary = summary_resp.completion_text or "跑团已结束，未能生成总结。"
                except Exception:
                    summary = "跑团已结束，总结生成失败。"

        # Save history
        self.store.create_session_history(
            platform_name=platform_name,
            session_id=session_id,
            scenario_id=session.scenario_id,
            user_id=session.user_id,
            turn_count=session.turn_count,
            summary=summary,
            notes_snapshot=session.notes_json,
            final_stage=session.current_stage,
            started_at=session.created_at,
        )

        # Reset session
        self.store.reset_solo_session(platform_name, session_id)

        return f"跑团已结束。\n\n总结：{summary}"

    def _get_latest_history_summary(
        self,
        platform_name: str,
        session_id: str,
        scenario_id: int,
    ) -> str:
        """Get the summary from the most recent history entry for the same scenario."""
        history = self.store.list_session_history(
            platform_name,
            session_id,
            limit=1,
            scenario_id=scenario_id,
        )
        if history:
            return history[0].summary
        return ""

    def list_session_history(self, platform_name: str, session_id: str, limit: int = 10) -> list[SessionHistoryRecord]:
        return self.store.list_session_history(platform_name, session_id, limit)

    def export_scenario_markdown(self, scenario_id: int, output_dir: Path) -> Path | None:
        scenario = self.store.get_scenario(scenario_id)
        if not scenario:
            return None
        return self.store.export_scenario_markdown(scenario, output_dir)

    def reset_solo_session(self, platform_name: str, session_id: str) -> bool:
        return self.store.reset_solo_session(platform_name, session_id)

    @staticmethod
    def format_solo_status(session: SoloSessionView) -> str:
        notes: list[str] = json.loads(session.notes_json or "[]")
        notes_str = "\n".join(f"  - {n}" for n in notes) if notes else "  暂无记录"
        return (
            f"当前单人剧本：[{session.scenario_id}] {session.scenario_title}\n"
            f"简介：{session.scenario_summary or '暂无简介'}\n"
            f"阶段：{session.current_stage}\n"
            f"回合数：{session.turn_count}\n"
            f"记录板：\n{notes_str}\n"
            f"开始时间：{session.created_at}\n"
            f"最后推进：{session.updated_at}"
        )

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

    @staticmethod
    def _append_transcript(transcript_json: str, player_message: str, assistant_message: str, limit: int = 12) -> str:
        try:
            history = json.loads(transcript_json or "[]")
            if not isinstance(history, list):
                history = []
        except json.JSONDecodeError:
            history = []

        history.append({"role": "user", "content": player_message})
        history.append({"role": "assistant", "content": assistant_message})
        trimmed = history[-limit:]
        return json.dumps(trimmed, ensure_ascii=False)

    @staticmethod
    def _build_session_end_reply(cleaned_reply: str, final_message: str) -> str:
        if not cleaned_reply:
            return final_message
        return f"{cleaned_reply}\n\n{final_message}"


def _normalize_scenario_ref(value: str) -> str:
    return re.sub(r"[\s《》「」『』【】\[\]（）()\"'“”‘’]+", "", value).casefold()
