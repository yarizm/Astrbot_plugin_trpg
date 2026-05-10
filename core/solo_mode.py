"""Pure utility functions for the solo TRPG mode.

This module contains no astrbot dependencies and can be imported in tests.
FunctionTool subclasses are in core/tools.py (runtime only).
"""
from __future__ import annotations

import json
import random
import re


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SOLO_SYSTEM_PROMPT = """\
你是一位专业的 TRPG 主持人（GM）。你正在主持一场单人跑团。

## 当前剧本
标题：{title}
简介：{summary}
标签：{tags}
推荐人数：{recommended_players}

## 开场设定
{opening_scene}

## 当前状态
- 阶段：{current_stage}
- 回合数：{turn_count}
- 记录板：{notes_summary}

{history_section}

## 你的职责
1. 根据玩家的行动描述，推进剧情，营造氛围
2. 需要判定结果时，使用 trpg_roll 工具投骰（如 d20 判定、d100 百分骰等）
3. 重要线索或关键信息，使用 trpg_notes 工具记录到记录板
4. 剧情推进到新阶段时，使用 trpg_progress 工具更新进度
5. 故事自然完结或玩家要求结束时，使用 trpg_end_session 工具
6. 每次回复保持叙事张力，给出 2-3 个行动选项引导玩家

## 风格要求
- 沉浸式叙事，用第二人称"你"
- 适度骰子判定增加随机性，但不要每件事都骰
- 回复控制在 200 字以内，保持节奏紧凑
"""

SUMMARY_PROMPT = """\
请将以下跑团对话压缩为一段 100 字以内的总结。
要求：包含剧本名、关键事件、结局走向。
不要添加额外的格式标记，直接输出总结文本。

跑团对话：
{transcript}
"""


# ---------------------------------------------------------------------------
# Dice utilities
# ---------------------------------------------------------------------------

_DICE_RE = re.compile(r"^(\d*)d(\d+)([+-]\d+)?$")


def roll_dice(expression: str) -> str:
    """Parse and roll a dice expression like '2d6+3', 'd20', 'd100'."""
    expr = expression.strip().lower().replace(" ", "")
    match = _DICE_RE.match(expr)
    if not match:
        return f"无效的骰子表达式：{expression}。格式示例：2d6+3, d20, d100"

    count = int(match.group(1)) if match.group(1) else 1
    sides = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0

    if count < 1 or count > 100:
        return "骰子数量需在 1-100 之间。"
    if sides < 2 or sides > 1000:
        return "骰子面数需在 2-1000 之间。"

    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + modifier

    if count == 1 and modifier == 0:
        return f"d{sides} = {rolls[0]}"

    roll_str = " + ".join(str(r) for r in rolls)
    if modifier > 0:
        return f"({roll_str}) + {modifier} = {total}"
    if modifier < 0:
        return f"({roll_str}) - {abs(modifier)} = {total}"
    return f"({roll_str}) = {total}"


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

def build_system_prompt(
    scenario_title: str,
    scenario_summary: str,
    scenario_tags: list[str],
    recommended_players: str,
    opening_scene: str,
    current_stage: str,
    turn_count: int,
    notes_json: str,
    history_summary: str = "",
) -> str:
    tags_str = " / ".join(scenario_tags) if scenario_tags else "无标签"

    notes: list[str] = json.loads(notes_json or "[]")
    notes_summary = "\n".join(f"- {n}" for n in notes) if notes else "暂无记录"

    history_section = ""
    if history_summary:
        history_section = f"## 历史摘要（上一局）\n{history_summary}"

    return SOLO_SYSTEM_PROMPT.format(
        title=scenario_title,
        summary=scenario_summary or "暂无简介",
        tags=tags_str,
        recommended_players=recommended_players or "未填写",
        opening_scene=opening_scene or "故事即将开始。",
        current_stage=current_stage,
        turn_count=turn_count,
        notes_summary=notes_summary,
        history_section=history_section,
    )


def build_summary_prompt(transcript_json: str) -> str:
    """Build the prompt for LLM to generate a session summary."""
    try:
        history = json.loads(transcript_json or "[]")
    except json.JSONDecodeError:
        history = []

    lines: list[str] = []
    for msg in history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        prefix = "玩家" if role == "user" else "GM"
        lines.append(f"{prefix}：{content}")

    return SUMMARY_PROMPT.format(transcript="\n".join(lines) or "（无对话记录）")
