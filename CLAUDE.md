# CLAUDE.md

本文件为 Claude Code 在本仓库中工作时提供指引。

## 项目概述

一个 AstrBot 插件（Python），用于 TRPG 桌游剧本管理。管理员可导入 Markdown 剧本大纲并发布，玩家可在群聊中选择剧本或在私聊中运行 LLM 主导的单人跑团。内置 3 个剧本。

## 运行测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

运行单个测试文件：

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_solo_mode -v
```

测试使用 `test_tmp/` 下的临时 SQLite 数据库（已 gitignore），运行后自动清理。测试环境中 `astrbot` 包不可用，因此 `core/tools.py`（依赖 `astrbot.core.agent.tool`）不参与测试导入链。

## 架构

插件采用三层设计：**AstrBot 适配层 → 业务层 → 存储层**。

- [main.py](astrbot_plugin_trpg/main.py) — 插件入口。通过 `@filter.command_group` 和 `@filter.llm_tool` 注册斜杠命令（`/trpg` 命令组）和 LLM 工具。负责权限校验（管理员专属命令、仅私聊/仅群聊）。单人跑团消息在 `on_all_message` 中拦截，通过 `tool_loop_agent` 调用 LLM 主导叙事。跑团结束时通过 `@filter.on_llm_request` 将总结注入基础 LLM 上下文。

- [core/service.py](astrbot_plugin_trpg/core/service.py) — `TrpgService` 编排所有业务逻辑：导入预备/消费、发布、群聊剧本绑定、LLM 驱动的单人会话生命周期。单人跑团通过 `advance_solo_session_llm()` 调用 AstrBot 的 `tool_loop_agent`，让 LLM 自由叙事并按需调用工具。会话结束时通过 `end_solo_session_with_summary()` 单独调用 LLM 生成总结。

- [core/store.py](astrbot_plugin_trpg/core/store.py) — `TrpgStore` 管理 SQLite 持久化。五张表：`outline_imports`、`scenario_candidates`、`group_sessions`、`solo_sessions`、`session_history`。通过 `source_key` 实现内置剧本的幂等播种。支持剧本导出为 Markdown 文件。所有连接使用上下文管理器，出错时自动回滚。

- [core/parser.py](astrbot_plugin_trpg/core/parser.py) — 解析以 `## 剧本：标题` 为分隔符的 Markdown 大纲。提取 `### 简介/标签/推荐人数/开场设定` 各节。输入无效时抛出 `OutlineParseError`。

- [core/solo_mode.py](astrbot_plugin_trpg/core/solo_mode.py) — 纯函数模块，不依赖 `astrbot` 包。包含骰子投掷逻辑（`roll_dice`）、系统提示词构建（`build_system_prompt`）、总结 prompt 构建（`build_summary_prompt`）。可在测试中直接导入。

- [core/tools.py](astrbot_plugin_trpg/core/tools.py) — 4 个 `FunctionTool` 子类，仅供运行时使用（依赖 `astrbot.core.agent.tool`）：`TrpgRollTool`（骰子）、`TrpgNotesTool`（记录板）、`TrpgProgressTool`（阶段进度）、`TrpgEndSessionTool`（结束会话）。通过 `build_solo_tools()` 工厂函数组装。在 `service.py` 中延迟导入，避免测试时的依赖问题。

- [core/builtin_scenarios.py](astrbot_plugin_trpg/core/builtin_scenarios.py) — 包含 3 个内置剧本，以原始 Markdown 字符串常量存储。通过 `source_key` 幂等播种。

## 关键模式

- **LLM 主导的单人跑团**：玩家消息 → 构建系统提示词（剧本+记录板+阶段+历史摘要）→ `tool_loop_agent` 驱动 LLM 自由叙事 + 按需调用 4 个 FunctionTool → 更新会话状态。LLM 自主决定何时骰骰子、何时记录、何时推进阶段。
- **导入预备状态机**：`TrpgService.arm_import()` 存储以 `sender_id::session_key` 为键的 `PendingImport`。该发送者在该会话中的下一条消息即被消费为 Markdown。触发消息本身通过消息 ID 比较被跳过。
- **群聊与单人会话隔离**：群聊会话以 `(platform_name, session_id)` 为键，有 UNIQUE 约束。单人会话使用相同的键方案，但在独立的表中。
- **状态生命周期**：剧本经历 `draft → published → archived`。内置剧本直接进入 `published`。
- **会话历史与总结**：结束单人跑团时，通过 `llm_generate` 单独调用 LLM 生成 100 字以内的总结，存入 `session_history` 表，然后清空 `solo_sessions` 对应记录。下次开同一剧本时，历史摘要会注入系统提示词。
- **剧本 Markdown 可视化**：`export_scenario_markdown()` 将剧本导出为格式化的 `.md` 文件，存储在 `{plugin_data_dir}/scenarios/` 目录下。
- **延迟导入隔离**：`core/tools.py` 依赖 `astrbot` 包，仅在运行时延迟导入（`service.py` 的方法内部 import）。测试链不经过 `tools.py`。

## 配置

定义在 [_conf_schema.json](astrbot_plugin_trpg/_conf_schema.json)。

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `admin_user_ids` | list[string] | [] | 管理员用户 ID 列表 |
| `bootstrap_builtin_scenarios` | bool | true | 启动时自动播种内置剧本 |
| `db_filename` | string | trpg.sqlite3 | SQLite 数据库文件名 |
| `max_import_chars` | int | 20000 | 单次导入最大字符数 |
| `max_list_size` | int | 20 | 列表命令最大返回数 |
| `scenario_export_dir` | string | scenarios | 剧本 MD 导出目录（相对插件数据目录） |
| `solo_max_steps` | int | 10 | 单人跑团 LLM agent 每轮最大工具调用步数 |
| `solo_system_prompt_override` | string | "" | 自定义单人跑团系统提示词（为空则使用内置默认） |

## 依赖

- `astrbot.api` — AstrBot 框架（命令、事件、LLM 工具、日志）。要求 AstrBot >=4.16,<5。
- `astrbot.core.agent.tool` — FunctionTool / ToolSet，用于定义 LLM 可调用的工具。
- 无其他外部依赖（requirements.txt 为空）。
