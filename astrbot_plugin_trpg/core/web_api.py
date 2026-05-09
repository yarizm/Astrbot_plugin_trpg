from __future__ import annotations

import logging
from pathlib import Path

from quart import jsonify, request

from .parser import OutlineParseError, parse_scenario_outline
from .service import TrpgService
from .store import TrpgStore

logger = logging.getLogger("astrbot")

_SENSITIVE_CONFIG_KEYS = frozenset({
    "solo_provider_id", "solo_fallback_provider_id", "admin_user_ids",
})


def _json_ok(data=None, message: str = ""):
    return jsonify({"status": "ok", "data": data, "message": message})


def _json_error(message: str, code: int = 400):
    resp = jsonify({"status": "error", "data": None, "message": message})
    resp.status_code = code
    return resp


class TrpgWebApi:
    """Web API handlers for the TRPG plugin admin UI.

    These routes are registered through AstrBot's Dashboard plugin page API.
    AstrBot Dashboard authentication is expected to be the access boundary.
    """

    def __init__(
        self,
        service: TrpgService,
        store: TrpgStore,
        plugin_config: dict,
        plugin_data_dir: Path,
        conf_schema: dict,
    ):
        self.service = service
        self.store = store
        self.plugin_config = plugin_config
        self.plugin_data_dir = plugin_data_dir
        self.conf_schema = conf_schema

    def _scenario_to_dict(self, s) -> dict:
        return {
            "id": s.id,
            "title": s.title,
            "summary": s.summary,
            "tags": s.tags,
            "tag_list": s.tag_list,
            "recommended_players": s.recommended_players,
            "opening_scene": s.opening_scene,
            "raw_markdown": s.raw_markdown,
            "status": s.status,
            "created_at": s.created_at,
            "published_at": s.published_at,
        }

    def _history_to_dict(self, h) -> dict:
        return {
            "id": h.id,
            "platform_name": h.platform_name,
            "session_id": h.session_id,
            "scenario_id": h.scenario_id,
            "user_id": h.user_id,
            "turn_count": h.turn_count,
            "summary": h.summary,
            "notes_snapshot": h.notes_snapshot,
            "final_stage": h.final_stage,
            "started_at": h.started_at,
            "ended_at": h.ended_at,
        }

    def _session_to_dict(self, s) -> dict:
        return {
            "platform_name": s.platform_name,
            "session_id": s.session_id,
            "user_id": s.user_id,
            "scenario_id": s.scenario_id,
            "scenario_title": s.scenario_title,
            "scenario_summary": s.scenario_summary,
            "turn_count": s.turn_count,
            "current_stage": s.current_stage,
            "notes_json": s.notes_json,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        }

    def _config_int(self, key: str, default: int, minimum: int = 1, maximum: int | None = None) -> int:
        try:
            value = int(self.plugin_config.get(key, default) or default)
        except (TypeError, ValueError):
            value = default
        value = max(minimum, value)
        if maximum is not None:
            value = min(value, maximum)
        return value

    def _max_upload_chars(self) -> int:
        return self._config_int("max_upload_chars", 200_000, minimum=1_000, maximum=2_000_000)

    def _session_history_limit(self) -> int:
        return self._config_int("session_history_limit", 100, minimum=1, maximum=1_000)

    # --- Scenario endpoints ---

    async def get_scenarios(self, **kwargs):
        try:
            status = request.args.get("status", "").strip()
            limit = int(request.args.get("limit", "100"))
            if status:
                scenarios = self.service.store.list_scenarios(status, limit)
            else:
                scenarios = self.service.store.list_scenarios_all(limit)
            return _json_ok([self._scenario_to_dict(s) for s in scenarios])
        except Exception as e:
            logger.error("TRPG web get_scenarios error: %s", e)
            return _json_error(str(e))

    async def get_scenario(self, **kwargs):
        try:
            scenario_id = int(kwargs.get("id", 0))
            scenario = self.service.store.get_scenario(scenario_id)
            if not scenario:
                return _json_error("剧本不存在", 404)
            return _json_ok(self._scenario_to_dict(scenario))
        except Exception as e:
            logger.error("TRPG web get_scenario error: %s", e)
            return _json_error(str(e))

    async def update_scenario(self, **kwargs):
        try:
            scenario_id = int(kwargs.get("id", 0))
            data = await request.get_json()
            if not data:
                return _json_error("请求体为空")

            title = str(data.get("title", "")).strip()
            raw_markdown = str(data.get("raw_markdown", "")).strip()
            if not title:
                return _json_error("剧本标题不能为空")
            if not raw_markdown:
                return _json_error("剧本内容不能为空")

            scenario = self.service.store.update_scenario_content(
                scenario_id=scenario_id,
                title=title,
                summary=str(data.get("summary", "")).strip(),
                tags=str(data.get("tags", "")).strip(),
                recommended_players=str(data.get("recommended_players", "")).strip(),
                opening_scene=str(data.get("opening_scene", "")).strip(),
                raw_markdown=raw_markdown,
            )
            if not scenario:
                return _json_error("剧本不存在", 404)
            return _json_ok(self._scenario_to_dict(scenario), "保存成功")
        except Exception as e:
            logger.error("TRPG web update_scenario error: %s", e)
            return _json_error(str(e))

    async def publish_scenario(self, **kwargs):
        try:
            scenario_id = int(kwargs.get("id", 0))
            scenario = self.service.publish_scenario(scenario_id)
            if not scenario:
                return _json_error("剧本不存在或发布失败", 404)
            return _json_ok(self._scenario_to_dict(scenario), "发布成功")
        except Exception as e:
            logger.error("TRPG web publish_scenario error: %s", e)
            return _json_error(str(e))

    async def upload_scenario(self, **kwargs):
        try:
            files = await request.files
            field = files.get("file")
            if not field:
                return _json_error("未上传文件")

            filename = field.filename or "upload.md"
            if not filename.lower().endswith((".md", ".markdown", ".txt")):
                return _json_error("仅支持 .md / .markdown / .txt 文件")

            content_bytes = field.read()
            max_upload_chars = self._max_upload_chars()
            if len(content_bytes) > max_upload_chars * 4:
                return _json_error(f"文件过大（最多约 {max_upload_chars} 个 UTF-8 字符）")

            try:
                markdown_text = content_bytes.decode("utf-8").strip()
            except UnicodeDecodeError:
                return _json_error("文件编码错误：请上传 UTF-8 编码的 Markdown / 文本文件")
            if not markdown_text:
                return _json_error("文件内容为空")
            if len(markdown_text) > max_upload_chars:
                return _json_error(f"文件内容过长（最多 {max_upload_chars} 个字符）")

            created = self.service.store.create_import_with_scenarios(
                source_markdown=markdown_text,
                imported_by="webui",
                imported_session="webui",
                scenarios=parse_scenario_outline(markdown_text),
            )
            if not created:
                return _json_error("未能从 Markdown 中解析出任何剧本，请检查格式")

            return _json_ok(
                [self._scenario_to_dict(s) for s in created],
                f"成功导入 {len(created)} 个剧本",
            )
        except OutlineParseError as e:
            return _json_error(f"解析失败: {e}")
        except Exception as e:
            logger.error("TRPG web upload_scenario error: %s", e)
            return _json_error(str(e))

    # --- Session history endpoints ---

    async def get_sessions(self, **kwargs):
        try:
            history = self.service.store.list_all_session_history(limit=self._session_history_limit())
            active = self.service.store.list_active_sessions()

            seen = set()
            session_summaries = []
            for h in history:
                key = (h.platform_name, h.session_id)
                if key not in seen:
                    seen.add(key)
                    session_summaries.append({
                        "platform_name": h.platform_name,
                        "session_id": h.session_id,
                        "history_count": sum(
                            1 for x in history
                            if x.platform_name == h.platform_name
                            and x.session_id == h.session_id
                        ),
                    })

            return _json_ok({
                "active_sessions": [self._session_to_dict(s) for s in active],
                "history_sessions": session_summaries,
                "total_history_count": len(history),
            })
        except Exception as e:
            logger.error("TRPG web get_sessions error: %s", e)
            return _json_error(str(e))

    async def get_session_detail(self, **kwargs):
        try:
            platform = kwargs.get("platform", "")
            session_id = kwargs.get("session_id", "")
            if not platform or not session_id:
                return _json_error("缺少 platform 或 session_id")

            history = self.service.store.list_session_history(
                platform, session_id, limit=self._session_history_limit(),
            )
            return _json_ok([self._history_to_dict(h) for h in history])
        except Exception as e:
            logger.error("TRPG web get_session_detail error: %s", e)
            return _json_error(str(e))

    # --- Config endpoints ---

    async def get_config(self, **kwargs):
        try:
            config_data = {}
            for key, schema in self.conf_schema.items():
                value = self.plugin_config.get(key, schema.get("default"))
                display_value = "***" if key in _SENSITIVE_CONFIG_KEYS and value else value
                config_data[key] = {
                    "value": display_value,
                    "type": schema.get("type", "string"),
                    "description": schema.get("description", ""),
                    "default": schema.get("default"),
                    "sensitive": key in _SENSITIVE_CONFIG_KEYS,
                }
            return _json_ok(config_data)
        except Exception as e:
            logger.error("TRPG web get_config error: %s", e)
            return _json_error(str(e))

    async def save_config(self, **kwargs):
        try:
            data = await request.get_json()
            if not data or not isinstance(data, dict):
                return _json_error("请求体格式错误")

            errors = []
            for key, value in data.items():
                if key not in self.conf_schema:
                    continue
                schema = self.conf_schema[key]
                expected_type = schema.get("type", "string")

                if key in _SENSITIVE_CONFIG_KEYS and value == "***":
                    continue

                try:
                    if expected_type == "int":
                        value = int(value)
                    elif expected_type == "bool":
                        if isinstance(value, str):
                            value = value.lower() in ("true", "1", "yes")
                        else:
                            value = bool(value)
                    elif expected_type == "list":
                        if isinstance(value, str):
                            value = [v.strip() for v in value.split(",") if v.strip()]
                        elif not isinstance(value, list):
                            errors.append(f"{key}: 需要列表类型")
                            continue
                    elif expected_type == "string":
                        value = str(value)
                except (ValueError, TypeError) as e:
                    errors.append(f"{key}: 类型转换失败 - {e}")
                    continue

                self.plugin_config[key] = value

            if errors:
                return _json_error("校验失败: " + "; ".join(errors))

            # Persist to disk
            try:
                self.plugin_config.save_config()
            except Exception as e:
                logger.warning("TRPG config save to disk failed: %s", e)

            return _json_ok(None, "配置已保存（部分配置需要重启插件生效）")
        except Exception as e:
            logger.error("TRPG web save_config error: %s", e)
            return _json_error(str(e))
