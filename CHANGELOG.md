# Changelog

## v0.1.0 - 2026-05-09

### 简介

`astrbot_plugin_trpg` 是面向 AstrBot 的跑团选本 / TRPG 辅助插件，提供剧本导入、发布、群聊选本、私聊单人跑团和 WebUI 管理能力。

### 核心功能

- 剧本导入与管理：支持按约定格式导入 Markdown 剧本大纲，拆分为候选剧本，管理员审核后发布。
- WebUI 可视化管理：通过 AstrBot Dashboard 插件页面查看、编辑、发布和上传剧本。
- 跑团会话记录：保存单人跑团历史、总结、阶段和记录板快照。
- 单人跑团模式：在私聊中由 LLM 担任 GM 推进剧情，并可调用骰子、记录板、阶段推进和结束会话工具。
- 群聊选本：群聊中查看已发布剧本，并绑定当前群正在跑的剧本。
- 配置管理：提供管理员 ID、数据库文件名、导入限制、上传限制、历史记录限制、单人跑团模型等配置项。

### 环境要求

- AstrBot：`>=4.24.2,<5`。
- Python：建议使用 AstrBot 当前支持的 Python 运行环境；CI 使用 Python `3.11`。
- 插件依赖：`requirements.txt` 当前包含 `quart`，用于 WebUI API。

### 安装说明

- 将 `astrbot_plugin_trpg` 文件夹放入 AstrBot 的 `plugins` 目录。
- 重启 AstrBot，并在 Dashboard 插件管理界面启用插件。
- 如手动部署，请按 AstrBot 插件依赖安装方式安装 `requirements.txt` 中的依赖。
- 进入插件配置页面填写 `admin_user_ids` 后，再使用导入、发布、重置、导出等管理员能力。

### 升级与兼容性

- 这是首个公开整理版本，无需执行历史迁移脚本。
- SQLite 数据默认位于 `plugin_data/astrbot_plugin_trpg/trpg.sqlite3`。
- 修改 `db_filename` 后需要重启插件或 AstrBot 才会切换数据库文件，旧数据库不会自动迁移。
- WebUI 依赖 AstrBot `>=4.24.2` 的插件页面能力；低版本 AstrBot 需要自行验证基础命令兼容性。

### 已知限制

- WebUI API 依赖 AstrBot Dashboard 登录态作为访问边界，请不要将 Dashboard 暴露到不可信公网。
- 剧本上传仅支持 UTF-8 编码的 `.md`、`.markdown`、`.txt` 文件。
- 当前不包含角色卡、完整主持人控场、分支存档等完整跑团系统能力。
- README 暂未包含实际截图文件，后续 Release 可补充 WebUI 页面截图。
