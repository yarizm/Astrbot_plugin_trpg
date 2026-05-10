from __future__ import annotations

import re
from dataclasses import dataclass


SCENARIO_HEADER_RE = re.compile(r"(?m)^##\s*剧本：\s*(.+?)\s*$")
SECTION_HEADER_RE = re.compile(r"(?m)^###\s*(简介|标签|推荐人数|开场设定)\s*$")


class OutlineParseError(ValueError):
    """Raised when an imported outline cannot be split into valid scenarios."""


@dataclass(slots=True)
class ParsedScenario:
    title: str
    summary: str
    tags: list[str]
    recommended_players: str
    opening_scene: str
    raw_markdown: str


def parse_scenario_outline(markdown_text: str) -> list[ParsedScenario]:
    """Parse a Markdown outline into multiple draft scenarios."""
    normalized = (markdown_text or "").strip()
    if not normalized:
        raise OutlineParseError("导入内容为空，请粘贴 Markdown 剧本大纲。")

    matches = list(SCENARIO_HEADER_RE.finditer(normalized))
    if not matches:
        raise OutlineParseError("未找到任何 `## 剧本：标题` 段落，无法拆分剧本。")

    scenarios: list[ParsedScenario] = []
    for index, match in enumerate(matches):
        block_start = match.start()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        block = normalized[block_start:block_end].strip()
        title = _clean_text(match.group(1))
        if not title:
            raise OutlineParseError("存在空标题剧本，请检查 `## 剧本：` 标题。")

        body = normalized[match.end():block_end].strip()
        preamble, sections = _extract_sections(body)
        opening_scene = _clean_block(sections.get("开场设定", ""))
        summary = _resolve_summary(sections.get("简介", ""), preamble, opening_scene)
        tags = _parse_tags(sections.get("标签", ""))
        recommended_players = _clean_block(sections.get("推荐人数", ""))

        scenarios.append(
            ParsedScenario(
                title=title,
                summary=summary,
                tags=tags,
                recommended_players=recommended_players,
                opening_scene=opening_scene,
                raw_markdown=block,
            )
        )

    return scenarios


def _extract_sections(body: str) -> tuple[str, dict[str, str]]:
    matches = list(SECTION_HEADER_RE.finditer(body))
    if not matches:
        return body.strip(), {}

    preamble = body[: matches[0].start()].strip()
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group(1)] = body[start:end].strip()

    return preamble, sections


def _resolve_summary(summary_section: str, preamble: str, opening_scene: str) -> str:
    explicit_summary = _clean_block(summary_section)
    if explicit_summary:
        return explicit_summary

    first_paragraph = _first_paragraph(preamble)
    if first_paragraph:
        return first_paragraph

    if opening_scene:
        return _truncate(opening_scene, 120)

    return ""


def _first_paragraph(text: str) -> str:
    for paragraph in re.split(r"\n\s*\n", text.strip()):
        cleaned = _clean_text(paragraph)
        if cleaned:
            return cleaned
    return ""


def _parse_tags(text: str) -> list[str]:
    if not text.strip():
        return []

    raw_items = re.split(r"[,，、\n]+", text)
    tags: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        cleaned = _clean_text(raw_item)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            tags.append(cleaned)
    return tags


def _clean_block(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines).strip()


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _truncate(text: str, limit: int) -> str:
    compact = _clean_text(text)
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"
