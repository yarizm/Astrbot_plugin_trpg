"""FunctionTool definitions for the solo TRPG session.

This module is only imported at runtime inside AstrBot (where astrbot package is available).
Tests import solo_mode.py directly for pure utility functions.

Uses factory functions + closures instead of subclassing FunctionTool,
because AstrBot's FunctionTool is a Pydantic v2 dataclass and does not
support subclass-level attribute defaults for required parent fields.
"""
from __future__ import annotations

import json
from typing import Any

from astrbot.core.agent.tool import FunctionTool, ToolExecResult

from .solo_mode import roll_dice
from .store import TrpgStore


def _make_roll_tool() -> FunctionTool:
    """Roll dice for the solo TRPG session."""

    async def _call(_ctx: Any, **kwargs: Any) -> ToolExecResult:
        expression = kwargs.get("expression", "d20")
        return roll_dice(expression)

    return FunctionTool(
        name="trpg_roll",
        description="投掷骰子。格式如 2d6+3（2个6面骰+3）、d20（1个20面骰）、d100（百分骰）",
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "骰子表达式，如 2d6+3, d20, d100",
                },
            },
            "required": ["expression"],
        },
        handler=_call,
    )


def _make_notes_tool(
    store: TrpgStore,
    platform_name: str,
    session_id: str,
) -> FunctionTool:
    """Read/write the player's adventure notes board."""

    async def _call(_ctx: Any, **kwargs: Any) -> ToolExecResult:
        action = kwargs.get("action", "read")
        session = store.get_solo_session(platform_name, session_id)
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
        store.update_solo_session_extra(
            platform_name, session_id, notes_json=json.dumps(notes, ensure_ascii=False),
        )
        return f"已记录：{content}"

    return FunctionTool(
        name="trpg_notes",
        description="读写玩家的冒险记录板。action='write' 时追加记录，action='read' 时返回全部记录。",
        parameters={
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
        },
        handler=_call,
    )


def _make_progress_tool(
    store: TrpgStore,
    platform_name: str,
    session_id: str,
) -> FunctionTool:
    """Get or set the current scenario stage."""

    async def _call(_ctx: Any, **kwargs: Any) -> ToolExecResult:
        action = kwargs.get("action", "get")
        session = store.get_solo_session(platform_name, session_id)
        if not session:
            return "当前没有进行中的跑团会话。"

        if action == "get":
            return f"当前阶段：{session.current_stage}"

        stage = (kwargs.get("stage") or "").strip()
        if not stage:
            return "请指定要设置的阶段名称。"
        store.update_solo_session_extra(
            platform_name, session_id, current_stage=stage,
        )
        return f"阶段已更新为：{stage}"

    return FunctionTool(
        name="trpg_progress",
        description="更新或查询剧本进行进度。stage 可设为：开场/调查/危机/高潮/结局",
        parameters={
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
        },
        handler=_call,
    )


def _make_end_session_tool() -> FunctionTool:
    """End the current solo TRPG session."""

    async def _call(_ctx: Any, **_kwargs: Any) -> ToolExecResult:
        return "[SESSION_END] 跑团会话即将结束。"

    return FunctionTool(
        name="trpg_end_session",
        description=(
            "结束当前跑团会话。会自动生成跑团总结并保存历史记录。"
            "仅在故事自然完结或玩家明确要求结束时调用。"
        ),
        parameters={"type": "object", "properties": {}},
        handler=_call,
    )


def build_solo_tools(
    store: TrpgStore,
    platform_name: str,
    session_id: str,
) -> list[FunctionTool]:
    """Build the set of FunctionTool instances for a solo TRPG session."""
    return [
        _make_roll_tool(),
        _make_notes_tool(store, platform_name, session_id),
        _make_progress_tool(store, platform_name, session_id),
        _make_end_session_tool(),
    ]
