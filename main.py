from __future__ import annotations

from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from core import (
    GroupSessionExistsError,
    OutlineParseError,
    STATUS_PUBLISHED,
    TrpgService,
    TrpgStore,
)


PLUGIN_NAME = "astrbot_plugin_trpg"


@register(PLUGIN_NAME, "YARIZM", "TRPG 选本 MVP 插件", "0.1.0")
class TrpgPlugin(Star):
    """导入 Markdown 剧本大纲，审核发布剧本，并在群内绑定当前选本。"""

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.store = TrpgStore(self._resolve_db_path())
        self.service = TrpgService(self.store)

    @filter.command_group("trpg")
    def trpg(self):
        """跑团选本命令组"""
        pass

    @trpg.command("导入")
    async def import_outline(self, event: AstrMessageEvent):
        """进入一次性剧本导入状态"""
        permission_error = self._admin_error(event)
        if permission_error:
            yield event.plain_result(permission_error)
            return

        self.service.arm_import(
            sender_id=event.get_sender_id(),
            session_key=event.get_session_id(),
            trigger_message_id=str(event.message_obj.message_id),
        )
        logger.info("TRPG import armed for user=%s session=%s", event.get_sender_id(), event.get_session_id())
        yield event.plain_result(
            "请在下一条消息中直接粘贴 Markdown 剧本大纲。\n"
            "格式示例：\n"
            "## 剧本：雾港回声\n"
            "### 简介\n"
            "一句话简介\n"
            "### 标签\n"
            "推理, 克苏鲁\n"
            "### 推荐人数\n"
            "3-5 人\n"
            "### 开场设定\n"
            "玩家在暴雨夜抵达港口。"
        )

    @trpg.command("草稿列表")
    async def draft_list(self, event: AstrMessageEvent):
        """查看待发布剧本草稿"""
        permission_error = self._admin_error(event)
        if permission_error:
            yield event.plain_result(permission_error)
            return

        drafts = self.service.list_drafts(self._max_list_size())
        if not drafts:
            yield event.plain_result("当前没有待发布的剧本草稿。")
            return

        yield event.plain_result(self.service.format_scenario_list("待发布剧本草稿", drafts))

    @trpg.command("发布")
    async def publish_scenario(self, event: AstrMessageEvent, scenario_id: int):
        """发布指定草稿剧本"""
        permission_error = self._admin_error(event)
        if permission_error:
            yield event.plain_result(permission_error)
            return

        scenario = self.service.publish_scenario(scenario_id)
        if not scenario:
            yield event.plain_result(f"未找到编号为 {scenario_id} 的剧本。")
            return
        if scenario.status != STATUS_PUBLISHED:
            yield event.plain_result(f"剧本 {scenario_id} 发布失败，请稍后重试。")
            return

        logger.info("TRPG scenario published: id=%s title=%s", scenario.id, scenario.title)
        yield event.plain_result(f"已发布剧本：[{scenario.id}] {scenario.title}")

    @trpg.command("剧本列表")
    async def list_scenarios(self, event: AstrMessageEvent):
        """查看已发布剧本列表"""
        scenarios = self.service.list_published(self._max_list_size())
        if not scenarios:
            yield event.plain_result("当前还没有已发布的剧本。请稍后再来，或联系管理员先导入并发布。")
            return

        yield event.plain_result(self.service.format_scenario_list("可选剧本列表", scenarios))

    @trpg.command("选剧本")
    async def select_scenario(self, event: AstrMessageEvent, scenario_id: int):
        """在当前群会话绑定一个已发布剧本"""
        group_error = self._group_only_error(event)
        if group_error:
            yield event.plain_result(group_error)
            return

        existing = self.service.get_group_selection(event.get_platform_name(), event.message_obj.session_id)
        if existing:
            yield event.plain_result(
                f"当前群已绑定剧本：[{existing.scenario_id}] {existing.scenario_title}。\n"
                "如需更换，请让管理员先执行 /trpg 重置当前剧本。"
            )
            return

        try:
            scenario = self.service.select_group_scenario(
                platform_name=event.get_platform_name(),
                session_id=event.message_obj.session_id,
                scenario_id=scenario_id,
                selected_by=event.get_sender_id(),
            )
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return
        except GroupSessionExistsError:
            yield event.plain_result("当前群已经有选定剧本，请先让管理员重置当前剧本。")
            return

        logger.info(
            "TRPG scenario selected: platform=%s session=%s scenario=%s",
            event.get_platform_name(),
            event.message_obj.session_id,
            scenario.id,
        )
        yield event.plain_result(
            f"已为当前群绑定剧本：[{scenario.id}] {scenario.title}\n"
            f"简介：{scenario.summary or '暂无简介'}"
        )

    @trpg.command("当前剧本")
    async def current_scenario(self, event: AstrMessageEvent):
        """查看当前群已绑定剧本"""
        group_error = self._group_only_error(event)
        if group_error:
            yield event.plain_result(group_error)
            return

        selection = self.service.get_group_selection(event.get_platform_name(), event.message_obj.session_id)
        if not selection:
            yield event.plain_result("当前群还没有绑定剧本。可先执行 /trpg 剧本列表 查看候选。")
            return

        yield event.plain_result(
            f"当前剧本：[{selection.scenario_id}] {selection.scenario_title}\n"
            f"简介：{selection.scenario_summary or '暂无简介'}\n"
            f"选择人：{selection.selected_by}\n"
            f"选择时间：{selection.selected_at}"
        )

    @trpg.command("重置当前剧本")
    async def reset_current_scenario(self, event: AstrMessageEvent):
        """清空当前群已绑定剧本"""
        permission_error = self._admin_error(event)
        if permission_error:
            yield event.plain_result(permission_error)
            return

        group_error = self._group_only_error(event)
        if group_error:
            yield event.plain_result(group_error)
            return

        removed = self.service.reset_group_session(event.get_platform_name(), event.message_obj.session_id)
        if not removed:
            yield event.plain_result("当前群没有已绑定剧本，无需重置。")
            return

        logger.info(
            "TRPG group session reset: platform=%s session=%s",
            event.get_platform_name(),
            event.message_obj.session_id,
        )
        yield event.plain_result("已重置当前群剧本绑定，现在可以重新选剧本。")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        try:
            created = self.service.consume_import(
                sender_id=event.get_sender_id(),
                session_key=event.get_session_id(),
                message_id=str(event.message_obj.message_id),
                markdown_text=event.message_str or "",
                imported_by=event.get_sender_id(),
                imported_session=event.get_session_id(),
                max_chars=self._max_import_chars(),
            )
        except OutlineParseError as exc:
            event.stop_event()
            yield event.plain_result(f"导入失败：{exc}")
            return
        except Exception as exc:  # pragma: no cover
            logger.exception("TRPG import failed unexpectedly: %s", exc)
            event.stop_event()
            yield event.plain_result("导入失败：保存剧本时发生异常，请查看日志。")
            return

        if created is None:
            return

        logger.info("TRPG outline imported by=%s count=%s", event.get_sender_id(), len(created))
        event.stop_event()
        yield event.plain_result(
            f"导入成功，已生成 {len(created)} 个待审核剧本草稿。\n"
            f"示例标题：{self.service.preview_titles(created)}\n"
            "请使用 /trpg 草稿列表 查看，并通过 /trpg 发布 <id> 上架。"
        )

    def _resolve_db_path(self) -> Path:
        plugin_data_dir = get_astrbot_data_path() / "plugin_data" / PLUGIN_NAME
        db_filename = str(self.config.get("db_filename", "trpg.sqlite3") or "trpg.sqlite3")
        return plugin_data_dir / db_filename

    def _admin_error(self, event: AstrMessageEvent) -> str | None:
        if event.get_sender_id() in self._admin_user_ids():
            return None
        return "你没有管理员权限。请让配置在 `admin_user_ids` 里的管理员执行该命令。"

    @staticmethod
    def _group_only_error(event: AstrMessageEvent) -> str | None:
        if event.is_private_chat():
            return "该命令仅支持在群聊中使用。"
        return None

    def _admin_user_ids(self) -> set[str]:
        configured = self.config.get("admin_user_ids", [])
        return {str(item).strip() for item in configured if str(item).strip()}

    def _max_import_chars(self) -> int:
        value = int(self.config.get("max_import_chars", 20000) or 20000)
        return max(1000, value)

    def _max_list_size(self) -> int:
        value = int(self.config.get("max_list_size", 20) or 20)
        return max(1, value)
