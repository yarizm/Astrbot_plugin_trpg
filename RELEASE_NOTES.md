# v0.1.0

## 简介

`astrbot_plugin_trpg` 是一个 AstrBot 跑团选本 / TRPG 辅助插件。它面向需要在群聊中选本、管理剧本，并在私聊中体验单人跑团的用户。

## 主要功能

- 剧本导入与管理：管理员可导入 Markdown 剧本大纲，系统拆分为候选剧本后再发布。
- 群聊选本：群聊中查看已发布剧本，并绑定当前群正在跑的剧本。
- 单人跑团：私聊中开启单人跑团，由 LLM 担任 GM 推进剧情。
- 跑团工具：单人模式下支持骰子、记录板、阶段推进和结束会话工具。
- 跑团记录：会话结束后生成总结，并保存历史记录。
- WebUI 管理：通过 AstrBot Dashboard 插件页面管理剧本、查看跑团记录、调整配置。
- 内置剧本：首次启动可自动初始化 3 个内置剧本。

## 安装要求

- AstrBot：`>=4.24.2,<5`。
- Python：建议使用 AstrBot 当前支持的 Python 运行环境；本仓库 CI 使用 Python `3.11`。
- 依赖：`requirements.txt` 当前包含 `quart`，用于 WebUI API。

## 安装方式

1. 下载或克隆仓库。
2. 将 `astrbot_plugin_trpg` 文件夹放入 AstrBot 的 `plugins` 目录。
3. 按 AstrBot 插件依赖安装方式安装 `requirements.txt` 中的依赖。
4. 重启 AstrBot。
5. 在 AstrBot Dashboard 的插件管理界面启用 `跑团选本助手`。
6. 打开插件配置页面，填写管理员用户 ID。

## 配置说明

- `admin_user_ids`：必填，控制导入、发布、重置、导出等管理员命令权限。
- `db_filename`：SQLite 数据库文件名，修改后需要重启插件或 AstrBot。
- `bootstrap_builtin_scenarios`：是否在首次启动时初始化内置剧本，修改后需要重启插件或 AstrBot。
- `max_import_chars`：聊天命令导入 Markdown 的最大字符数。
- `max_upload_chars`：WebUI 上传 Markdown 的最大字符数。
- `session_history_limit`：WebUI 跑团记录接口最大返回条数。
- `solo_provider_id` / `solo_fallback_provider_id`：单人跑团使用的主模型和备用模型 Provider ID。

## 注意事项

- WebUI 入口位于 AstrBot Dashboard 的插件管理页面。
- WebUI API 依赖 AstrBot Dashboard 登录态作为访问边界，请不要将 Dashboard 暴露到不可信公网。
- 上传剧本仅支持 UTF-8 编码的 `.md`、`.markdown`、`.txt` 文件。
- 默认数据目录为 AstrBot 数据目录下的 `plugin_data/astrbot_plugin_trpg/`。
- 迁移或备份时建议复制整个 `plugin_data/astrbot_plugin_trpg/` 目录。
- 当前版本不包含角色卡、完整主持人控场、分支存档等完整跑团系统能力。

## 验证方式

启用插件后，可按以下方式验证：

1. 在插件配置中填写 `admin_user_ids`。
2. 执行 `/trpg 剧本列表`，确认内置剧本已初始化或已有已发布剧本。
3. 管理员执行 `/trpg 导入` 并粘贴符合格式的 Markdown，确认可生成草稿。
4. 管理员执行 `/trpg 发布 <id>`，确认剧本可发布。
5. 在群聊执行 `/trpg 选剧本 <id>`，确认当前群能绑定剧本。
6. 在私聊执行 `/trpg 单人开始 <id>`，确认单人跑团可启动。

开发验证命令：

```powershell
python -m py_compile astrbot_plugin_trpg/main.py
python -m py_compile astrbot_plugin_trpg/core/web_api.py
python -m unittest discover -s tests -v
ruff check .
```
