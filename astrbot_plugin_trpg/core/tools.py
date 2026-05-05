"""FunctionTool definitions for the solo TRPG session.

This module is only imported at runtime inside AstrBot (where astrbot package is available).
Tests import solo_mode.py directly for pure utility functions.
"""
from __future__ import annotations

import json
from typing import Any

from astrbot.core.agent.tool import FunctionTool, ToolExecResult

from .solo_mode import roll_dice
from .store import TrpgStore


class TrpgRollTool(FunctionTool[Any]):
    """Roll dice for the solo TRPG session."""

    name: str = "trpg_roll"
    description: str = "投掷骰子。格式如 2d6+3（2个6面骰+3）、d20（1个20面骰）、d100（百分骰）"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "骰子表达式，如 2d6+3, d20, d100",
            },
        },
        "required": ["expression"],
    }

    async def call(self, _ctx: Any, **kwargs: Any) -> ToolExecResult:
        expression = kwargs.get("expression", "d20")
        return roll_dice(expression)


class TrpgNotesTool(FunctionTool[Any]):
    """Read/write the player's adventure notes board."""

    _store: TrpgStore
    _platform_name: str
    _session_id: str

    name: str = "trpg_notes"
    description: str = (
        "读写玩家的冒险记录板。action='write' 时追加记录，action='read' 时返回全部记录。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write"],
                "description": "read 读取记录，write 追加记录",
            },
            "content": {
                "type": "string",
                "description": "write 时要记录的内容",
            },
        },
        "required": ["action"],
    }

    async def call(self, _ctx: Any, **kwargs: Any) -> ToolExecResult:
        action = kwargs.get("action", "read")
        session = self._store.get_solo_session(self._platform_name, self._session_id)
        if not session:
            return "当前没有进行中的跑团会话。"

        notes: list[str] = json.loads(session.notes_json or "[]")

        if action == "read":
            if not notes:
                return "记录板为空，还没有任何记录。"
            return "\n".join(f"- {n}" for n in notes)

        # write
        content = (kwargs.get("content") or "").strip()
        if not content:
            return "请提供要记录的内容。"
        notes.append(content)
        self._store.update_solo_session_extra(
            self._platform_name, self._session_id, notes_json=json.dumps(notes, ensure_ascii=False),
        )
        return f"已记录：{content}"


class TrpgProgressTool(FunctionTool[Any]):
    """Get or set the current scenario stage."""

    _store: TrpgStore
    _platform_name: str
    _session_id: str

    name: str = "trpg_progress"
    description: str = "更新或查询剧本进行进度。stage 可设为：开场/调查/危机/高潮/结局"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["get", "set"],
                "description": "get 查询当前阶段，set 设置新阶段",
            },
            "stage": {
                "type": "string",
                "description": "要设置的阶段名称，如：开场/调查/危机/高潮/结局",
            },
        },
        "required": ["action"],
    }

    async def call(self, _ctx: Any, **kwargs: Any) -> ToolExecResult:
        action = kwargs.get("action", "get")
        session = self._store.get_solo_session(self._platform_name, self._session_id)
        if not session:
            return "当前没有进行中的跑团会话。"

        if action == "get":
            return f"当前阶段：{session.current_stage}"

        stage = (kwargs.get("stage") or "").strip()
        if not stage:
            return "请指定要设置的阶段名称。"
        self._store.update_solo_session_extra(
            self._platform_name, self._session_id, current_stage=stage,
        )
        return f"阶段已更新为：{stage}"


class TrpgEndSessionTool(FunctionTool[Any]):
    """End the current solo TRPG session."""

    name: str = "trpg_end_session"
    description: str = (
        "结束当前跑团会话。会自动生成跑团总结并保存历史记录。"
        "仅在故事自然完结或玩家明确要求结束时调用。"
    )
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    async def call(self, _ctx: Any, **_kwargs: Any) -> ToolExecResult:
        return "[SESSION_END] 跑团会话即将结束。"


def build_solo_tools(
    store: TrpgStore,
    platform_name: str,
    session_id: str,
) -> list[FunctionTool[Any]]:
    """Build the set of FunctionTool instances for a solo TRPG session."""
    return [
        TrpgRollTool(),
        TrpgNotesTool(
            _store=store,
            _platform_name=platform_name,
            _session_id=session_id,
        ),
        TrpgProgressTool(
            _store=store,
            _platform_name=platform_name,
            _session_id=session_id,
        ),
        TrpgEndSessionTool(),
    ]
