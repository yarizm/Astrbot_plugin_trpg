# AstrBot TRPG 选本插件

这是一个面向 AstrBot 的跑团选本 MVP 插件，支持：

- 管理员通过两步交互导入 Markdown 剧本大纲
- 将一份大纲拆分成多个待审核剧本草稿
- 审核后发布给玩家查看
- 在群聊中把已发布剧本绑定为当前群的激活剧本

## 目录结构

- `main.py`: AstrBot 插件入口，只负责命令注册、事件适配和权限判断
- `core/parser.py`: Markdown 剧本大纲拆分与字段提取
- `core/store.py`: SQLite 持久化与查询
- `core/service.py`: 导入态、发布、群会话绑定等业务编排
- `tests/`: 不依赖 AstrBot 本体的核心单元测试

## 命令

- `/trpg 导入`
- `/trpg 草稿列表`
- `/trpg 发布 <id>`
- `/trpg 剧本列表`
- `/trpg 选剧本 <id>`
- `/trpg 当前剧本`
- `/trpg 重置当前剧本`

## 导入格式

管理员执行 `/trpg 导入` 后，在下一条消息中直接粘贴 Markdown 文本。

```md
## 剧本：雾港回声
### 简介
暴雨夜的封港令背后，藏着一艘从未靠岸的货轮。

### 标签
推理，悬疑，克苏鲁

### 推荐人数
3-5 人

### 开场设定
玩家们在港务局门前避雨时，同时收到一封匿名信。

## 剧本：山路终点
### 简介
一辆旅游大巴误入封闭山道，乘客逐渐发现彼此并不陌生。
```

说明：

- 每个剧本必须以 `## 剧本：标题` 开头
- 支持 `### 简介`、`### 标签`、`### 推荐人数`、`### 开场设定`
- 未填写 `简介` 时，系统会用剧本块中的首段文字代替

## 配置

- `admin_user_ids`: 允许执行管理命令的用户 ID 列表
- `max_import_chars`: 单次导入的最大字符数
- `max_list_size`: 列表命令最多返回多少条剧本
- `db_filename`: SQLite 文件名，保存在插件数据目录

## 开发验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
