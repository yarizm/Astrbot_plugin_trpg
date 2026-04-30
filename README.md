# 跑团选本助手 / AstrBot TRPG Plugin

一个用于 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的 TRPG 选本辅助插件。

插件支持导入 Markdown 剧本大纲、管理员审核发布候选剧本、在群聊中绑定当前剧本，并提供一个轻量级的私聊单人跑团模式。

## 功能特性

- **Markdown 剧本导入**：管理员可一次性粘贴 Markdown 剧本大纲，插件会自动解析为候选剧本草稿。
- **草稿审核与发布**：导入后的剧本默认进入草稿列表，管理员确认后再发布上架。
- **内置剧本初始化**：首次启动可自动导入插件内置剧本包，也可由管理员手动触发初始化。
- **群聊选本绑定**：群聊中可从已发布剧本列表中选择当前剧本，避免重复绑定。
- **私聊单人跑团**：用户可在私聊中选择剧本，进入单人跑团模式，直接发送行动描述推进剧情。
- **SQLite 本地存储**：剧本、群聊选本状态、单人跑团记录会保存到 AstrBot 插件数据目录下。

## 兼容性

插件元信息声明的兼容范围：

```yaml
astrbot_version: ">=4.16,<5"
```

Python 版本以当前 AstrBot 运行环境为准。插件本身目前不依赖第三方 Python 包。

## 安装方式

将本仓库放入 AstrBot 的插件目录，或通过 AstrBot 插件管理方式安装。

示例：

```bash
git clone https://github.com/yarizm/Astrbot_plugin_trpg.git
```

仓库中的插件主体目录为：

```text
Astrbot_plugin_trpg/
```

安装后重启 AstrBot，并在插件管理中启用本插件。

## 配置项

插件配置定义在 `Astrbot_plugin_trpg/_conf_schema.json` 中。

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `admin_user_ids` | list[string] | `[]` | 允许执行导入、发布、重置等管理命令的用户 ID 列表。 |
| `max_import_chars` | int | `20000` | 单次导入允许的最大 Markdown 字符数。 |
| `max_list_size` | int | `20` | 列表命令单次最多返回多少条剧本。 |
| `db_filename` | string | `trpg.sqlite3` | SQLite 数据库文件名。 |
| `bootstrap_builtin_scenarios` | bool | `true` | 插件启动时是否自动初始化内置剧本包。 |

> 注意：`admin_user_ids` 默认是空列表。安装后请先配置管理员用户 ID，否则无法执行导入、发布、重置等管理命令。

## 命令说明

所有命令均以 `/trpg` 开头。

### 剧本导入与发布

| 命令 | 权限 | 说明 |
| --- | --- | --- |
| `/trpg 导入` | 管理员 | 进入一次性剧本导入状态。下一条消息需要直接粘贴 Markdown 剧本大纲。 |
| `/trpg 草稿列表` | 管理员 | 查看待发布剧本草稿。 |
| `/trpg 发布 <剧本ID>` | 管理员 | 发布指定草稿剧本。 |
| `/trpg 初始化内置剧本` | 管理员 | 初始化插件内置剧本包。 |

### 群聊选本

| 命令 | 权限 | 说明 |
| --- | --- | --- |
| `/trpg 剧本列表` | 所有人 | 查看已发布剧本列表。 |
| `/trpg 选剧本 <剧本ID>` | 群聊成员 | 为当前群绑定一个已发布剧本。 |
| `/trpg 当前剧本` | 群聊成员 | 查看当前群已绑定剧本。 |
| `/trpg 重置当前剧本` | 管理员 | 清空当前群已绑定剧本。 |

### 私聊单人跑团

| 命令 | 权限 | 说明 |
| --- | --- | --- |
| `/trpg 单人开始 <剧本ID>` | 私聊用户 | 在私聊中开启单人跑团模式。 |
| `/trpg 单人状态` | 私聊用户 | 查看当前私聊单人跑团状态。 |
| `/trpg 单人结束` | 私聊用户 | 结束当前私聊单人跑团。 |

单人跑团开始后，用户可以在私聊中直接发送行动描述、调查、交涉、移动、战斗或推理内容，插件会根据当前剧本和历史记录生成下一步主持人回复。

## Markdown 剧本大纲格式

导入时请使用以下格式：

```markdown
## 剧本：雾港回声

### 简介
一座被暴雨封锁的港口城市中，玩家需要调查一场离奇失踪事件。

### 标签
推理, 克苏鲁, 都市怪谈

### 推荐人数
3-5 人

### 开场设定
玩家在暴雨夜抵达港口旅店，却发现本应接应他们的人已经失踪。
```

一次消息中可以包含多个剧本，只要每个剧本都以 `## 剧本：标题` 开头：

```markdown
## 剧本：雾港回声
...

## 剧本：旧校舍的第十三级台阶
...
```

插件会识别以下小节：

- `### 简介`
- `### 标签`
- `### 推荐人数`
- `### 开场设定`

如果缺少简介，插件会尝试从正文或开场设定中提取摘要。

## 数据存储

插件使用 SQLite 保存数据，默认数据库文件名为：

```text
trpg.sqlite3
```

实际路径位于 AstrBot 数据目录下的插件数据目录：

```text
<astrbot_data_path>/plugin_data/astrbot_plugin_trpg/trpg.sqlite3
```

数据库中保存：

- 导入的 Markdown 原文
- 候选剧本与发布状态
- 群聊当前绑定剧本
- 私聊单人跑团会话与最近对话记录

## 项目结构

```text
Astrbot_plugin_trpg/
├── __init__.py
├── main.py                 # AstrBot 插件入口与命令定义
├── metadata.yaml           # 插件元信息
├── _conf_schema.json       # 插件配置 schema
├── requirements.txt        # 依赖声明，目前无第三方依赖
└── core/
    ├── __init__.py
    ├── parser.py           # Markdown 剧本大纲解析
    ├── service.py          # 剧本导入、发布、选本与单人模式业务逻辑
    ├── store.py            # SQLite 存储层
    ├── solo_mode.py        # 单人跑团回复生成逻辑
    └── builtin_scenarios.py
```

## 开发说明

### 编译检查

```bash
python -m compileall -q Astrbot_plugin_trpg
```

### 建议的本地检查

如需增加代码风格检查和测试，可安装：

```bash
pip install ruff pytest
```

然后运行：

```bash
ruff check Astrbot_plugin_trpg
pytest -q
```

## 注意事项

- 管理命令依赖 `admin_user_ids`，请在启用插件后优先配置管理员。
- 单次导入文本长度受 `max_import_chars` 限制，超长剧本建议拆分导入。
- 群聊同一时间只能绑定一个剧本。如需更换，请先由管理员执行 `/trpg 重置当前剧本`。
- 私聊单人跑团同一会话同一时间只能进行一个剧本。如需更换，请先执行 `/trpg 单人结束`。
- 插件当前的单人跑团模式是轻量规则生成，不依赖外部 LLM。

## License

本仓库暂未声明许可证。如需公开分发，建议补充 `LICENSE` 文件。