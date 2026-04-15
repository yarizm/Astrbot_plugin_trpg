from __future__ import annotations

import re
from dataclasses import dataclass

from .store import ScenarioRecord, SoloSessionView


@dataclass(slots=True)
class SoloTurnResult:
    reply: str
    stage_label: str
    action_label: str


def build_solo_opening(scenario: ScenarioRecord) -> str:
    suggestions = " / ".join(_default_options(scenario, "探索"))
    opening_scene = scenario.opening_scene or scenario.summary or "故事即将开始。"
    return (
        f"单人跑团已开始：《{scenario.title}》\n"
        f"简介：{scenario.summary or '暂无简介'}\n"
        f"开场：{opening_scene}\n\n"
        "接下来你可以直接像玩家一样描述行动、提问、调查、交涉或冒险。\n"
        f"你现在可以尝试：{suggestions}"
    )


def build_solo_turn(
    scenario: ScenarioRecord,
    session: SoloSessionView,
    player_message: str,
) -> SoloTurnResult:
    turn_no = session.turn_count + 1
    stage_label = _stage_label(turn_no)
    action_label = _action_label(player_message)
    outcome_label = _outcome_label(player_message, turn_no)
    scene_detail = _pick_scene_detail(scenario)
    consequence = _consequence_text(stage_label, action_label, outcome_label, scene_detail, player_message)
    clue = _clue_text(scenario, stage_label, action_label)
    tension = _tension_text(stage_label, scenario)
    options = " / ".join(_default_options(scenario, action_label))

    reply = (
        f"主持人：{outcome_label}。{consequence}\n\n"
        f"阶段：{stage_label}\n"
        f"线索：{clue}\n"
        f"氛围：{tension}\n\n"
        f"你现在可以：{options}"
    )
    return SoloTurnResult(reply=reply, stage_label=stage_label, action_label=action_label)


def _stage_label(turn_no: int) -> str:
    if turn_no <= 2:
        return "开场"
    if turn_no <= 4:
        return "调查"
    if turn_no <= 6:
        return "危机"
    return "摊牌"


def _action_label(player_message: str) -> str:
    text = (player_message or "").lower()
    keyword_groups = {
        "调查": ["调查", "查看", "搜索", "观察", "线索", "look", "search", "inspect"],
        "交涉": ["交谈", "询问", "说服", "套话", "talk", "ask", "persuade"],
        "移动": ["前往", "进入", "跟上", "出发", "go", "enter", "move"],
        "对抗": ["攻击", "战斗", "反击", "制服", "attack", "fight"],
        "推理": ["推测", "回忆", "分析", "思考", "think", "analyze"],
    }
    for label, words in keyword_groups.items():
        if any(word in text for word in words):
            return label
    return "探索"


def _outcome_label(player_message: str, turn_no: int) -> str:
    score = (sum(ord(char) for char in player_message) + turn_no * 17) % 100
    if score >= 72:
        return "你的行动取得了明显进展"
    if score >= 34:
        return "你的行动有所收获，但伴随着新的压力"
    return "你的行动触发了意料之外的变化"


def _pick_scene_detail(scenario: ScenarioRecord) -> str:
    headings = re.findall(r"(?m)^###\s*(.+?)\s*$", scenario.raw_markdown or "")
    extras = [item for item in headings if item not in {"简介", "标签", "推荐人数", "开场设定"}]
    if extras:
        return extras[0]
    if scenario.tag_list:
        return scenario.tag_list[0]
    return "未知异象"


def _consequence_text(
    stage_label: str,
    action_label: str,
    outcome_label: str,
    scene_detail: str,
    player_message: str,
) -> str:
    compact_action = _compact(player_message)
    if action_label == "调查":
        return f"你围绕“{scene_detail}”仔细排查，逐渐把零散细节拼成一条新的时间线。与你刚才提到的“{compact_action}”相关的痕迹，说明事情没有表面那么简单。"
    if action_label == "交涉":
        return f"对方被你的试探撬开了一点口风，但神情依旧紧绷。关于“{scene_detail}”的说法出现了前后不一致的地方，而你刚才的“{compact_action}”显然让某个隐情浮出了水面。"
    if action_label == "移动":
        return f"你推进到了新的地点，周围环境开始主动回应你的出现。和“{scene_detail}”有关的异常在这里更明显，而你刚才决定“{compact_action}”也让风险同步升高。"
    if action_label == "对抗":
        return f"局势一下子变得尖锐起来。你以“{compact_action}”强行撕开局面，逼得暗处的力量提早现身，和“{scene_detail}”有关的威胁也露出了轮廓。"
    if action_label == "推理":
        return f"你把前面的片段重新串联，发现“{scene_detail}”并不是孤立事件。随着你进一步“{compact_action}”，先前看似无关的矛盾开始互相印证。"
    return f"你沿着自己的直觉继续推进，“{scene_detail}”开始从背景变成真正的关键点。你刚才选择“{compact_action}”，让故事进入了更主动的一步。"


def _clue_text(scenario: ScenarioRecord, stage_label: str, action_label: str) -> str:
    if stage_label == "开场":
        return f"最先浮现的是与《{scenario.title}》主线直接相关的异样征兆，说明开场设定本身就藏着被忽视的信息。"
    if stage_label == "调查":
        return f"你确认当前线索与“{action_label}”方向是有效的，剧本中的核心矛盾已经开始主动暴露。"
    if stage_label == "危机":
        return f"线索不再只是信息，而是会改变局势的筹码。你意识到再拖延一步，代价就会落到自己身上。"
    return f"所有线索都在逼近真相。现在最重要的不是继续收集，而是决定你准备承担什么代价。"


def _tension_text(stage_label: str, scenario: ScenarioRecord) -> str:
    if stage_label == "开场":
        return f"{scenario.title} 的世界观仍在试探你，危险感还很克制，但每个细节都在暗示更大的异常。"
    if stage_label == "调查":
        return "局势开始收束，信息密度明显上升，你已经能感觉到某种看不见的倒计时。"
    if stage_label == "危机":
        return "你已经站在风暴中央。继续行动会逼近真相，但任何犹豫都可能让局面失控。"
    return "故事来到摊牌前夜，所有隐藏后果都在向你逼近。"


def _default_options(scenario: ScenarioRecord, action_label: str) -> list[str]:
    if action_label == "调查":
        return ["继续深挖线索", "换一个地点调查", "找关键 NPC 对质"]
    if action_label == "交涉":
        return ["追问刚才的漏洞", "换个身份试探", "暂时离开再观察"]
    if action_label == "移动":
        return ["谨慎探索周围", "直接进入核心地点", "先布置退路"]
    if action_label == "对抗":
        return ["强行压制局势", "边退边观察", "寻找环境优势"]
    if action_label == "推理":
        return ["复盘已有线索", "验证一个关键猜想", "把矛盾点公开化"]
    if scenario.tag_list:
        return [f"顺着“{scenario.tag_list[0]}”继续推进", "先搜集更多情报", "主动触发新的剧情点"]
    return ["继续推进", "换个角度调查", "主动制造突破口"]


def _compact(text: str, limit: int = 24) -> str:
    collapsed = re.sub(r"\s+", " ", text or "").strip()
    if len(collapsed) <= limit:
        return collapsed or "继续行动"
    return collapsed[: limit - 1].rstrip() + "…"
