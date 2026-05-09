# AstrBot TRPG 跑团插件

面向 AstrBot 的 TRPG 桌游剧本管理与单人跑团插件。

## 功能

- **剧本管理**：管理员导入 Markdown 剧本大纲，拆分为多个候选剧本，审核后发布
- **群聊选本**：在群聊中查看已发布剧本列表，绑定当前团的剧本
- **单人跑团**（LLM 主导）：在私聊中开启单人跑团，由 LLM 担任 GM 自由叙事，支持骰子判定、记录板、阶段推进
- **跑团历史**：每次跑团结束后自动生成 LLM 总结，保存历史记录
- **剧本导出**：将剧本导出为格式化的 Markdown 文件
- **WebUI 管理面板**：通过 AstrBot Dashboard 内置页面访问，支持剧本编辑/发布、跑团记录查看、插件配置管理
- **内置剧本**：附带 3 个官方剧本，首次启动自动上架

## 安装

### 从 AstrBot 插件目录安装

1. 将仓库中的 `astrbot_plugin_trpg/` 目录复制到 AstrBot 的插件目录。
2. 在 AstrBot Dashboard 中启用插件，或重启 AstrBot。
3. 在插件配置中填写 `admin_user_ids`，否则导入、发布、重置、导出等管理员命令会被拒绝。
4. 首次启动默认会自动初始化 3 个内置剧本，可通过 `/trpg 剧本列表` 验证。

### 从源码开发

```powershell
python -m pip install -r astrbot_plugin_trpg/requirements.txt
python -m unittest discover -s tests -v
```

## 版本兼容

- `metadata.yaml` 当前声明 `astrbot_version: ">=4.24.2,<5"`。
- 基础命令、SQLite 存储、内置剧本和 LLM Tool 主要依赖 AstrBot 插件/事件/工具接口。
- WebUI 管理面板依赖 AstrBot >= 4.24.2 的插件页面与 `register_web_api` 能力，因此发布元数据按 WebUI 要求收紧到 `>=4.24.2,<5`。
- 如果只使用命令功能且运行在更低版本 AstrBot，需要自行验证兼容性；官方发布包按 WebUI 能力要求声明版本。

## 依赖说明

- `requirements.txt` 显式声明 `quart`，因为 `core/web_api.py` 直接使用 `quart.request/jsonify` 实现 WebUI API。
- 部分 AstrBot 发行环境可能已经内置 `quart`，但插件仍显式声明该依赖，避免独立安装时 WebUI 缺依赖。
- 如果运行环境没有安装 `quart`，插件会跳过 WebUI API 注册，基础命令和 LLM Tool 仍可加载使用。

## 目录结构

- `main.py`：AstrBot 插件入口，负责命令注册、事件适配和权限判断
- `core/parser.py`：Markdown 剧本大纲解析
- `core/store.py`：SQLite 持久化与查询（5 张表）
- `core/service.py`：导入、发布、群会话绑定、LLM 单人会话等业务编排
- `core/solo_mode.py`：纯函数模块（骰子、系统提示词构建）
- `core/tools.py`：4 个 FunctionTool 定义（骰子/记录板/进度/结束会话）
- `core/builtin_scenarios.py`：插件内置剧本包
- `core/web_api.py`：WebUI 后端 API（剧本 CRUD、会话记录、配置管理）
- `pages/admin/`：AstrBot 插件页面（HTML/CSS/JS），通过 Bridge SDK 与后端通信
- `tests/`：核心逻辑单元测试

## 命令

### 管理员命令

| 命令 | 说明 |
|------|------|
| `/trpg 导入` | 进入一次性剧本导入状态，下一条消息粘贴 Markdown |
| `/trpg 草稿列表` | 查看待发布的剧本草稿 |
| `/trpg 发布 <id>` | 发布指定草稿剧本 |
| `/trpg 初始化内置剧本` | 初始化插件内置剧本包 |
| `/trpg 重置当前剧本` | 清空当前群已绑定剧本 |
| `/trpg 导出剧本 <id>` | 导出指定剧本为 Markdown 文件 |

### 所有人可用

| 命令 | 说明 |
|------|------|
| `/trpg 剧本列表` | 查看已发布剧本列表 |
| `/trpg 选剧本 <id>` | 在群聊中绑定剧本 |
| `/trpg 当前剧本` | 查看当前群已绑定剧本 |
| `/trpg 单人开始 <id>` | 在私聊中开启单人跑团 |
| `/trpg 单人状态` | 查看当前单人跑团状态 |
| `/trpg 单人结束` | 结束单人跑团（自动生成总结） |
| `/trpg 历史` | 查看本会话的跑团历史记录 |

## 内置剧本

插件内置了 3 个可直接使用的剧本：

- **雾港回声**：海港悬疑克苏鲁调查
- **红枫高中的第十三间教室**：校园怪谈推理惊悚
- **星环列车终点站**：太空列车密室悬疑

默认配置下，插件首次启动会自动把这 3 个内置剧本写入数据库并直接发布。如果关闭了自动初始化，管理员可手动执行 `/trpg 初始化内置剧本`。

## 自然语言调用工具

插件通过 `@filter.llm_tool` 注册了 6 个工具，AstrBot 的基础 LLM 可通过自然语言自动调用：

| 工具 | 触发示例 |
|------|---------|
| `trpg_list_scenarios` | "有什么剧本"、"给我看看可选团本" |
| `trpg_select_group_scenario` | "这个群就跑 2 号本"、"帮我们开雾港回声" |
| `trpg_view_group_scenario` | "我们现在跑哪个本"、"当前剧本是什么" |
| `trpg_start_solo_session` | "我想单人跑团"、"私聊带我跑 1 号本" |
| `trpg_view_solo_status` | "我现在跑到哪了"、"单人团状态" |
| `trpg_end_solo_session` | "结束这局"、"我要换个本重开" |

支持按剧本编号或标题匹配（如"雾港回声"或"1"）。

## 单人跑团模式

单人跑团由 LLM 主导，玩家在私聊中直接发送自然语言行动即可。

### 开始跑团

```text
/trpg 剧本列表
/trpg 单人开始 1
```

### 玩家行动示例

- `我先调查房间里最可疑的痕迹`
- `我去找刚才那个目击者继续追问`
- `我决定直接进入灯塔`

### LLM 可调用工具

跑团过程中，LLM 可按需调用以下工具：

| 工具 | 说明 |
|------|------|
| `trpg_roll` | 投掷骰子（支持 d20、2d6+3、d100 等格式） |
| `trpg_notes` | 读写冒险记录板（记录线索、关键信息） |
| `trpg_progress` | 更新或查询剧本阶段（开场/调查/危机/高潮/结局） |
| `trpg_end_session` | 结束当前跑团会话 |

### 会话结束

执行 `/trpg 单人结束` 或 LLM 调用 `trpg_end_session` 工具时：
1. LLM 自动生成一段 100 字以内的跑团总结
2. 总结存入历史记录表
3. 当前会话数据清空
4. 总结自动同步到 AstrBot 基础 LLM 的上下文

**上下文同步**：跑团结束后，用户发的第一条普通消息会触发基础 LLM 自动获知跑团经历。基础 LLM 会在回复中自然提及刚结束的跑团，避免沟通割裂。

下次开同一剧本时，历史摘要会自动注入系统提示词，让 LLM 了解上一局的情况。

### 查看历史

```text
/trpg 历史
```

显示最近 5 局的跑团历史，包含剧本 ID、回合数、最终阶段和总结。

## 导入格式

管理员执行 `/trpg 导入` 后，在下一条消息中直接粘贴 Markdown：

```md
## 剧本：雾港回声
### 简介
暴雨夜的白礁港里，一座废弃灯塔重新亮起。
### 标签
悬疑, 克苏鲁, 调查
### 推荐人数
3-5 人
### 开场设定
玩家在港口躲雨时，发现一艘失踪渔船空无一人地漂回码头。

## 剧本：山路终点
### 简介
一辆旅游大巴误入封闭山道，乘客逐渐发现彼此并不陌生。
```

说明：

- 每个剧本必须以 `## 剧本：标题` 开头
- 支持 `### 简介`、`### 标签`、`### 推荐人数`、`### 开场设定`
- 如果没有填写 `简介`，系统会自动回退到首段描述

## 剧本 Markdown 导出

管理员可将剧本导出为格式化的 Markdown 文件：

```text
/trpg 导出剧本 1
```

导出的文件保存在 `{插件数据目录}/scenarios/` 下，文件名格式为 `{id}_{标题}.md`。

## 数据存储、备份与迁移

- SQLite 数据库默认位于 AstrBot 数据目录下的 `plugin_data/astrbot_plugin_trpg/trpg.sqlite3`。
- 剧本导出文件默认位于 `plugin_data/astrbot_plugin_trpg/scenarios/`。
- 迁移到新 AstrBot 实例时，复制整个 `plugin_data/astrbot_plugin_trpg/` 目录即可保留剧本、群聊选本、单人会话和历史记录。
- 备份前建议先停止 AstrBot，或至少确认没有正在进行的 WebUI 保存、导入、发布和单人跑团写入。
- 修改 `db_filename` 后需要重启插件才会切换数据库文件；旧数据库不会自动迁移。

## WebUI 管理面板

插件内置 WebUI 管理面板，通过 AstrBot Dashboard 的插件详情页进入（要求 AstrBot >= 4.24.2）。

> 截图占位：发布 Release 时建议补充 Dashboard 插件页面入口、剧本列表、编辑页、跑团记录页和配置页截图。

功能：
- **剧本管理**：查看、编辑、发布剧本，支持拖拽上传 Markdown 文件导入
- **跑团记录**：查看进行中的会话和历史跑团记录
- **插件配置**：在线修改插件配置项，敏感配置需确认后保存

技术说明：
- 前端通过 AstrBot Bridge SDK（`window.AstrBotPluginPage`）与后端通信
- 后端 API 在 `core/web_api.py` 中实现，通过 `register_web_api` 注册到 AstrBot 路由系统
- 前端页面位于 `pages/admin/`，由 AstrBot 内置页面系统自动托管
- WebUI API 的访问边界依赖 AstrBot Dashboard 登录态和插件页面路由保护；请不要将 Dashboard 暴露到不可信公网。
- WebUI 中剧本编辑、发布、上传、配置读取/保存和跑团记录查看均按 Dashboard 管理页面能力处理，不再额外读取聊天平台的 `admin_user_ids`。
- 上传接口仅接受 UTF-8 编码的 `.md`、`.markdown`、`.txt` 文件，扩展名大小写不敏感，大小由 `max_upload_chars` 控制。

## 管理员权限

- 聊天命令中的导入、发布、重置和导出依赖 `admin_user_ids`。
- `admin_user_ids` 应填写平台上可从 `event.get_sender_id()` 获取到的用户 ID 字符串。
- `admin_user_ids` 在 WebUI 配置接口中会被视为敏感配置并以 `***` 掩码展示；保存时保留 `***` 表示不修改原值。
- WebUI 页面本身依赖 AstrBot Dashboard 认证，适合由 AstrBot 管理员使用。

## 配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `admin_user_ids` | list | [] | 管理员用户 ID 列表 |
| `bootstrap_builtin_scenarios` | bool | true | 启动时自动初始化内置剧本 |
| `db_filename` | string | trpg.sqlite3 | SQLite 数据文件名 |
| `max_import_chars` | int | 20000 | 单次导入最大字符数 |
| `max_upload_chars` | int | 200000 | WebUI 上传 Markdown 最大字符数 |
| `max_list_size` | int | 20 | 列表命令最大返回数 |
| `session_history_limit` | int | 100 | WebUI 跑团记录接口最大返回数 |
| `scenario_export_dir` | string | scenarios | 剧本 MD 导出目录 |
| `solo_max_steps` | int | 10 | 单人跑团每轮最大工具调用步数 |
| `solo_system_prompt_override` | string | "" | 自定义单人跑团系统提示词 |
| `solo_provider_id` | string | "" | 单人跑团使用的 LLM 模型 Provider ID，为空则使用 AstrBot 当前会话的默认模型 |
| `solo_fallback_provider_id` | string | "" | 单人跑团备用 LLM 模型 Provider ID，主模型失败时自动切换，为空则不使用备用模型 |

## 开发验证

```powershell
python -m py_compile astrbot_plugin_trpg/main.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
ruff check .
```

GitHub Actions 会在推送和 PR 时执行 `ruff check .`、`python -m py_compile astrbot_plugin_trpg/main.py` 和 `python -m unittest discover -s tests -v`。
