from __future__ import annotations

from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .core import (
    GroupSessionExistsError,
    OutlineParseError,
    STATUS_PUBLISHED,
    SoloSessionExistsError,
    TrpgService,
    TrpgStore,
)


PLUGIN_NAME = "astrbot_plugin_trpg"


@register(PLUGIN_NAME, "YARIZM", "TRPG 选本 MVP 插件", "0.1.0")
class TrpgPlugin(Star):
    """导入 Markdown 剧本大纲，审核发布剧本，并在群内绑定当前选本。"""

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.store = TrpgStore(self._resolve_db_path())
        self.service = TrpgService(self.store)
        self._last_session_summaries: dict[tuple[str, str, str], str] = {}
        self._bootstrap_builtin_scenarios()

    async def initialize(self) -> None:
        """Called when plugin is activated. Registers Web API routes for Plugin Pages."""
        import json

        from .core.web_api import TrpgWebApi

        plugin_data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        conf_schema = self._load_conf_schema()
        web_api = TrpgWebApi(
            service=self.service,
            store=self.store,
            plugin_config=self.config,
            plugin_data_dir=plugin_data_dir,
            conf_schema=conf_schema,
        )

        prefix = f"/{PLUGIN_NAME}"
        routes = [
            (f"{prefix}/trpg/web/scenarios", web_api.get_scenarios, ["GET"], "获取剧本列表"),
            (f"{prefix}/trpg/web/scenarios/<id>", web_api.get_scenario, ["GET"], "获取剧本详情"),
            (f"{prefix}/trpg/web/scenarios/<id>", web_api.update_scenario, ["POST"], "更新剧本"),
            (f"{prefix}/trpg/web/scenarios/<id>/publish", web_api.publish_scenario, ["POST"], "发布剧本"),
            (f"{prefix}/trpg/web/scenarios/upload", web_api.upload_scenario, ["POST"], "上传剧本"),
            (f"{prefix}/trpg/web/sessions", web_api.get_sessions, ["GET"], "获取跑团记录"),
            (f"{prefix}/trpg/web/sessions/<platform>/<session_id>", web_api.get_session_detail, ["GET"], "获取会话详情"),
            (f"{prefix}/trpg/web/config", web_api.get_config, ["GET"], "获取配置"),
            (f"{prefix}/trpg/web/config", web_api.save_config, ["POST"], "保存配置"),
        ]

        for route, handler, methods, desc in routes:
            self.context.register_web_api(route, handler, methods, desc)

        logger.info("TRPG WebUI API routes registered (%d routes)", len(routes))

    @staticmethod
    def _load_conf_schema() -> dict:
        import json
        schema_path = Path(__file__).parent / "_conf_schema.json"
        try:
            return json.loads(schema_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("TRPG: failed to load conf schema: %s", exc)
            return {}

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

    @trpg.command("初始化内置剧本")
    async def init_builtin_scenarios(self, event: AstrMessageEvent):
        """初始化插件内置剧本包"""
        permission_error = self._admin_error(event)
        if permission_error:
            yield event.plain_result(permission_error)
            return

        created = self.service.seed_builtin_scenarios(
            imported_by=event.get_sender_id(),
            imported_session=event.get_session_id(),
        )
        if not created:
            yield event.plain_result("内置剧本已经初始化过了，无需重复导入。")
            return

        logger.info("TRPG builtin scenarios initialized by=%s count=%s", event.get_sender_id(), len(created))
        yield event.plain_result(
            f"已初始化 {len(created)} 个内置剧本，并自动上架。\n"
            f"包括：{self.service.preview_titles(created)}"
        )

    @trpg.command("剧本列表")
    async def list_scenarios(self, event: AstrMessageEvent):
        """查看已发布剧本列表"""
        scenarios = self.service.list_published(self._max_list_size())
        if not scenarios:
            yield event.plain_result("当前还没有已发布的剧本。请联系管理员执行 `/trpg 初始化内置剧本`，或手动导入并发布。")
            return

        yield event.plain_result(self.service.format_scenario_list("可选剧本列表", scenarios))

    @trpg.command("单人开始")
    async def start_solo_mode(self, event: AstrMessageEvent, scenario_id: int):
        """在私聊中开启单人跑团模式"""
        private_error = self._private_only_error(event)
        if private_error:
            yield event.plain_result(private_error)
            return

        try:
            _, opening = self.service.start_solo_session(
                platform_name=event.get_platform_name(),
                session_id=event.get_session_id(),
                user_id=event.get_sender_id(),
                scenario_id=scenario_id,
            )
        except ValueError as exc:
            yield event.plain_result(str(exc))
            return
        except SoloSessionExistsError:
            current = self.service.get_solo_session(event.get_platform_name(), event.get_session_id())
            if current:
                yield event.plain_result(
                    f"你已经在单人模式中：[{current.scenario_id}] {current.scenario_title}\n"
                    "如需更换，请先执行 `/trpg 单人结束`。"
                )
            else:
                yield event.plain_result("当前已经存在一个单人剧本会话，请先结束后再重新开始。")
            return

        logger.info(
            "TRPG solo session started: platform=%s session=%s scenario=%s",
            event.get_platform_name(),
            event.get_session_id(),
            scenario_id,
        )
        yield event.plain_result(opening)

    @trpg.command("单人状态")
    async def solo_status(self, event: AstrMessageEvent):
        """查看当前私聊单人跑团状态"""
        private_error = self._private_only_error(event)
        if private_error:
            yield event.plain_result(private_error)
            return

        session = self.service.get_solo_session(event.get_platform_name(), event.get_session_id())
        if not session:
            yield event.plain_result(
                "你当前还没有开始单人跑团。\n"
                "先执行 `/trpg 剧本列表` 看可选剧本，再用 `/trpg 单人开始 <id>` 开始。"
            )
            return

        yield event.plain_result(self.service.format_solo_status(session))

    @trpg.command("单人结束")
    async def end_solo_mode(self, event: AstrMessageEvent):
        """结束当前私聊单人跑团，生成跑团总结"""
        private_error = self._private_only_error(event)
        if private_error:
            yield event.plain_result(private_error)
            return

        session = self.service.get_solo_session(event.get_platform_name(), event.get_session_id())
        if not session:
            yield event.plain_result("当前没有正在进行的单人跑团，无需结束。")
            return

        try:
            provider_id = await self._resolve_solo_provider_id(event)
            fallback_id = self._solo_fallback_provider_id()
            result = await self.service.end_solo_session_with_summary(
                context=self.context,
                event=event,
                provider_id=provider_id,
                platform_name=event.get_platform_name(),
                session_id=event.get_session_id(),
                fallback_provider_id=fallback_id,
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("TRPG solo session end failed: %s", exc)
            yield event.plain_result("生成跑团总结时出错，已强制结束。你可以重新开始。")
            self.service.reset_solo_session(event.get_platform_name(), event.get_session_id())
            return

        logger.info(
            "TRPG solo session ended: platform=%s session=%s",
            event.get_platform_name(),
            event.get_session_id(),
        )
        self._remember_session_summary(event, result)
        yield event.plain_result(result)

    @filter.on_llm_request()
    async def inject_trpg_context(self, event: AstrMessageEvent, req: ProviderRequest):
        summary_key = self._session_summary_key(event)
        summary = self._last_session_summaries.pop(summary_key, None)
        if not summary:
            return
        req.system_prompt = (
            f"{req.system_prompt or ''}\n\n"
            f"[跑团上下文]\n"
            f"该用户刚刚完成了一局单人跑团，以下是跑团总结：\n"
            f"{summary}\n"
            f"请在回复中自然地提及这段经历，让用户感受到连续性。\n"
        )

    @filter.llm_tool(name="trpg_list_scenarios")
    async def llm_list_scenarios(self, event: AstrMessageEvent):
        """List available TRPG scenarios.
        Use when the user wants to see available scenarios, choose a scenario, or asks what scenarios are available.
        Common requests: 有什么剧本, 剧本列表, 给我看看可选团本, 我能开哪个本, 列一下跑团选项.
        """
        return self._tool_list_scenarios()

    @filter.llm_tool(name="trpg_select_group_scenario")
    async def llm_select_group_scenario(self, event: AstrMessageEvent, scenario_ref: str):
        """Bind a scenario to the current group chat.
        Use when the user wants to select a scenario for the group to play.
        Common requests: 这个群就跑 2 号本, 帮我们开雾港回声, 当前团选 1 号剧本.
        Only use in group chat, not in private chat.
        Args:
            scenario_ref(string): Scenario ID or title, e.g. 1 or 雾港回声.
        """
        return self._tool_select_group_scenario(event, scenario_ref)

    @filter.llm_tool(name="trpg_view_group_scenario")
    async def llm_view_group_scenario(self, event: AstrMessageEvent):
        """View the currently bound scenario for this group chat.
        Use when the user wants to know which scenario is currently selected for the group.
        Common requests: 我们现在跑哪个本, 当前剧本是什么, 看一下这个群的团本.
        Only use in group chat.
        """
        return self._tool_view_group_scenario(event)

    @filter.llm_tool(name="trpg_start_solo_session")
    async def llm_start_solo_session(self, event: AstrMessageEvent, scenario_ref: str):
        """Start a solo TRPG session in private chat.
        Use when the user wants to play a solo TRPG adventure with the bot as GM.
        Common requests: 我想单人跑团, 私聊带我跑 1 号本, 帮我开一个单人剧本.
        Only use in private chat, not in group chat.
        Args:
            scenario_ref(string): Scenario ID or title, e.g. 1 or 雾港回声.
        """
        return self._tool_start_solo_session(event, scenario_ref)

    @filter.llm_tool(name="trpg_view_solo_status")
    async def llm_view_solo_status(self, event: AstrMessageEvent):
        """View current solo TRPG session status.
        Use when the user wants to check their solo session progress, current scenario, or session state.
        Common requests: 我现在跑到哪了, 单人团状态, 看看我当前的剧本.
        Only use in private chat.
        """
        return self._tool_view_solo_status(event)

    @filter.llm_tool(name="trpg_end_solo_session")
    async def llm_end_solo_session(self, event: AstrMessageEvent):
        """End the current solo TRPG session and generate a summary.
        Use when the user wants to end their solo adventure, restart, or clear the current solo session.
        Common requests: 结束这局, 单人模式先停掉, 我要换个本重开.
        Only use in private chat.
        """
        return await self._tool_end_solo_session(event)

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

    @trpg.command("历史")
    async def session_history(self, event: AstrMessageEvent):
        """查看本会话的跑团历史记录"""
        private_error = self._private_only_error(event)
        if private_error:
            yield event.plain_result(private_error)
            return

        history = self.service.list_session_history(
            event.get_platform_name(), event.get_session_id(), limit=5,
        )
        if not history:
            yield event.plain_result("还没有跑团历史记录。完成一局跑团后会自动生成。")
            return

        lines = ["最近的跑团历史：\n"]
        for i, record in enumerate(history, 1):
            lines.append(
                f"--- 第 {i} 局 ---\n"
                f"剧本 ID：{record.scenario_id}\n"
                f"回合数：{record.turn_count}\n"
                f"最终阶段：{record.final_stage}\n"
                f"结束时间：{record.ended_at}\n"
                f"总结：{record.summary}"
            )
        yield event.plain_result("\n".join(lines))

    @trpg.command("导出剧本")
    async def export_scenario(self, event: AstrMessageEvent, scenario_id: int):
        """导出指定剧本为 Markdown 文件"""
        permission_error = self._admin_error(event)
        if permission_error:
            yield event.plain_result(permission_error)
            return

        export_dir = self._scenario_export_dir()
        filepath = self.service.export_scenario_markdown(scenario_id, export_dir)
        if not filepath:
            yield event.plain_result(f"未找到编号为 {scenario_id} 的剧本。")
            return

        logger.info("TRPG scenario exported: id=%s path=%s", scenario_id, filepath)
        yield event.plain_result(f"已导出剧本到：{filepath}")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        message_text = (event.message_str or "").strip()
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
            if not event.is_private_chat():
                return
            if not message_text or message_text.startswith("/"):
                return

            # Check for active solo session
            session = self.service.get_solo_session(event.get_platform_name(), event.get_session_id())
            if not session:
                return

            try:
                provider_id = await self._resolve_solo_provider_id(event)
                fallback_id = self._solo_fallback_provider_id()
                solo_reply = await self.service.advance_solo_session_llm(
                    context=self.context,
                    event=event,
                    provider_id=provider_id,
                    platform_name=event.get_platform_name(),
                    session_id=event.get_session_id(),
                    player_message=message_text,
                    max_steps=self._solo_max_steps(),
                    system_prompt_override=self._solo_system_prompt_override(),
                    fallback_provider_id=fallback_id,
                )
            except Exception as exc:  # pragma: no cover
                logger.exception("TRPG solo mode failed unexpectedly: %s", exc)
                event.stop_event()
                yield event.plain_result("单人跑团推进失败，请稍后重试，或先执行 `/trpg 单人结束` 后重新开始。")
                return

            if solo_reply is None:
                return

            self._remember_session_summary(event, solo_reply)
            event.stop_event()
            yield event.plain_result(solo_reply)
            return

        logger.info("TRPG outline imported by=%s count=%s", event.get_sender_id(), len(created))
        event.stop_event()
        yield event.plain_result(
            f"导入成功，已生成 {len(created)} 个待审核剧本草稿。\n"
            f"示例标题：{self.service.preview_titles(created)}\n"
            "请使用 /trpg 草稿列表 查看，并通过 /trpg 发布 <id> 上架。"
        )

    def _resolve_db_path(self) -> Path:
        plugin_data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        db_filename = str(self.config.get("db_filename", "trpg.sqlite3") or "trpg.sqlite3")
        return plugin_data_dir / db_filename

    def _tool_list_scenarios(self) -> str:
        scenarios = self.service.list_published(self._max_list_size())
        if not scenarios:
            return "当前还没有已发布的剧本。请联系管理员先初始化内置剧本或导入并发布。"
        return self.service.format_scenario_list("可选剧本列表", scenarios)

    def _tool_select_group_scenario(self, event: AstrMessageEvent, scenario_ref: str | int) -> str:
        group_error = self._group_only_error(event)
        if group_error:
            return group_error

        existing = self.service.get_group_selection(event.get_platform_name(), event.message_obj.session_id)
        if existing:
            return (
                f"当前群已经绑定剧本：[{existing.scenario_id}] {existing.scenario_title}。\n"
                "如果需要更换，请先让管理员重置当前剧本。"
            )

        scenario_to_select = self.service.resolve_published_scenario(scenario_ref)
        if not scenario_to_select:
            return f"未找到可用剧本：{scenario_ref}。可以先查看可选剧本列表。"

        try:
            scenario = self.service.select_group_scenario(
                platform_name=event.get_platform_name(),
                session_id=event.message_obj.session_id,
                scenario_id=scenario_to_select.id,
                selected_by=event.get_sender_id(),
            )
        except ValueError as exc:
            return str(exc)
        except GroupSessionExistsError:
            return "当前群已经有选定剧本，请先重置后再重新选择。"

        return f"已为当前群绑定剧本：[{scenario.id}] {scenario.title}\n简介：{scenario.summary or '暂无简介'}"

    def _tool_view_group_scenario(self, event: AstrMessageEvent) -> str:
        group_error = self._group_only_error(event)
        if group_error:
            return group_error

        selection = self.service.get_group_selection(event.get_platform_name(), event.message_obj.session_id)
        if not selection:
            return "当前群还没有绑定剧本。可以先查看可选剧本列表，再决定跑哪个本。"
        return (
            f"当前剧本：[{selection.scenario_id}] {selection.scenario_title}\n"
            f"简介：{selection.scenario_summary or '暂无简介'}\n"
            f"选择人：{selection.selected_by}\n"
            f"选择时间：{selection.selected_at}"
        )

    def _tool_start_solo_session(self, event: AstrMessageEvent, scenario_ref: str | int) -> str:
        private_error = self._private_only_error(event)
        if private_error:
            return private_error

        scenario_to_start = self.service.resolve_published_scenario(scenario_ref)
        if not scenario_to_start:
            return f"未找到可用剧本：{scenario_ref}。可以先查看可选剧本列表。"

        try:
            _, opening = self.service.start_solo_session(
                platform_name=event.get_platform_name(),
                session_id=event.get_session_id(),
                user_id=event.get_sender_id(),
                scenario_id=scenario_to_start.id,
            )
        except ValueError as exc:
            return str(exc)
        except SoloSessionExistsError:
            current = self.service.get_solo_session(event.get_platform_name(), event.get_session_id())
            if current:
                return (
                    f"你已经在单人模式中：[{current.scenario_id}] {current.scenario_title}\n"
                    "如需更换，请先结束当前单人跑团。"
                )
            return "当前已经存在一个单人剧本会话，请先结束后再重新开始。"

        return opening

    def _tool_view_solo_status(self, event: AstrMessageEvent) -> str:
        private_error = self._private_only_error(event)
        if private_error:
            return private_error

        session = self.service.get_solo_session(event.get_platform_name(), event.get_session_id())
        if not session:
            return "你当前还没有开始单人跑团。可以先看剧本列表，再让我帮你开始。"
        return self.service.format_solo_status(session)

    async def _tool_end_solo_session(self, event: AstrMessageEvent) -> str:
        private_error = self._private_only_error(event)
        if private_error:
            return private_error

        session = self.service.get_solo_session(event.get_platform_name(), event.get_session_id())
        if not session:
            return "当前没有正在进行的单人跑团，无需结束。"

        try:
            provider_id = await self._resolve_solo_provider_id(event)
            fallback_id = self._solo_fallback_provider_id()
            result = await self.service.end_solo_session_with_summary(
                context=self.context,
                event=event,
                provider_id=provider_id,
                platform_name=event.get_platform_name(),
                session_id=event.get_session_id(),
                fallback_provider_id=fallback_id,
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("TRPG solo session end tool failed: %s", exc)
            self.service.reset_solo_session(event.get_platform_name(), event.get_session_id())
            return "生成总结时出错，已强制结束。你可以重新选择剧本再开始。"

        self._remember_session_summary(event, result)
        return result

    def _bootstrap_builtin_scenarios(self) -> None:
        if not self._bootstrap_builtin_enabled():
            return

        try:
            created = self.service.seed_builtin_scenarios(
                imported_by="plugin-bootstrap",
                imported_session="builtin",
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("TRPG builtin scenario bootstrap failed: %s", exc)
            return

        if created:
            logger.info("TRPG builtin scenarios bootstrapped: count=%s", len(created))

    def _admin_error(self, event: AstrMessageEvent) -> str | None:
        if event.get_sender_id() in self._admin_user_ids():
            return None
        return "你没有管理员权限。请让配置在 `admin_user_ids` 里的管理员执行该命令。"

    @staticmethod
    def _private_only_error(event: AstrMessageEvent) -> str | None:
        if not event.is_private_chat():
            return "该命令仅支持在和机器人的私聊中使用。"
        return None

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

    def _bootstrap_builtin_enabled(self) -> bool:
        value = self.config.get("bootstrap_builtin_scenarios", True)
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "off"}
        return bool(value)

    def _solo_max_steps(self) -> int:
        value = int(self.config.get("solo_max_steps", 10) or 10)
        return max(1, min(value, 30))

    def _solo_system_prompt_override(self) -> str:
        return str(self.config.get("solo_system_prompt_override", "") or "").strip()

    def _solo_provider_id(self) -> str:
        return str(self.config.get("solo_provider_id", "") or "").strip()

    def _solo_fallback_provider_id(self) -> str:
        return str(self.config.get("solo_fallback_provider_id", "") or "").strip()

    async def _resolve_solo_provider_id(self, event: AstrMessageEvent) -> str:
        configured = self._solo_provider_id()
        if configured:
            return configured
        return await self.context.get_current_chat_provider_id(umo=event.unified_msg_origin)

    @staticmethod
    def _session_summary_key(event: AstrMessageEvent) -> tuple[str, str, str]:
        return (
            event.get_platform_name(),
            event.get_session_id(),
            event.get_sender_id(),
        )

    def _remember_session_summary(self, event: AstrMessageEvent, result: str) -> None:
        marker = "总结："
        if marker not in result:
            return
        summary = result.split(marker, 1)[1].strip()
        if not summary:
            return
        self._last_session_summaries[self._session_summary_key(event)] = summary

    def _scenario_export_dir(self) -> Path:
        plugin_data_dir = Path(get_astrbot_data_path()) / "plugin_data" / PLUGIN_NAME
        subdir = str(self.config.get("scenario_export_dir", "scenarios") or "scenarios")
        return plugin_data_dir / subdir
