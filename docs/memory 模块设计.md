# memory 模块设计

## 模块职责

`memory` 负责消息存储、摘要压缩、长期记忆和结构化短期记忆。
它不负责执行模型循环，但会决定哪些历史和记忆会回到上下文里。

当前目录：

- `thread_store.py`
- `compact_service.py`
- `policy.py`
- `memory_store.py`
- `working_memory.py`
- `context_sources.py`

## `ThreadStore`

`ThreadStore` 是当前 thread 消息目录实现。

核心字段：

- `key`
- `messages`
- `session_path`
- `history_path`
- `summary_path`
- `memory_path`

### 目录文件

单个 thread 默认落在：`~/.bananabot/sessions/<thread_id>/`

包含：

- `session.jsonl`：当前窗口消息
- `history.jsonl`：完整历史
- `summary.jsonl`：compact 摘要
- `MEMORY.md`：thread 长期记忆

### 主要方法

- `add_message()` / `add()` / `add_batch()`
- `save()` / `reload()`
- `clear()`
- `append_history()`
- `append_summary()`
- `get_summary_content()`
- `get_summary_count()`
- `clear_summary()`
- `has_memory()`
- `estimate_tokens()`

## `ThreadStoreManager`

负责：

- 计算 thread 目录路径
- 读取或创建 `ThreadStore`
- 维护缓存
- 列出 threads
- 删除 thread 目录

## `CompactPolicy`

定义 compact 触发条件：

- `context_window`
- `round1_threshold`
- `round2_threshold`
- `keep_count`
- `summary_rollup_count`

## `CompactService`

`CompactService` 只做 compact 和记忆整合。

### 第一轮：窗口裁剪

1. 裁掉旧消息
2. 保留最近 `keep_count` 条
3. 用模型生成一句摘要
4. 追加到 `summary.jsonl`

### 第二轮：摘要整合

1. 读取全部摘要
2. 读取现有 `MEMORY.md`
3. 用模型整合出新的长期记忆
4. 覆盖写回 `MEMORY.md`

## `MemoryStore`

负责项目级长期记忆。

默认路径：

```text
~/.bananabot/projects/<project_hash>/memory/
```

主要能力：

- `get_memory_context()`
- `save_memory()`
- `add_note()`
- `list_notes()`
- `find_banana_md()`

## `WorkingMemory`

`WorkingMemory` 是结构化短期记忆，不保存完整聊天，而是保留后续最可能复用的信息。

核心字段：

- `thread_id`
- `task_run_id`
- `objective`
- `user_intent`
- `summary`
- `current_plan`
- `constraints`
- `pending_actions`
- `open_questions`
- `recent_facts`
- `tool_observations`
- `metadata`

### 存储路径

- thread 级：`<root>/<thread_id>/working-memory.json`
- task 级：`<root>/<thread_id>/tasks/<task_run_id>/working-memory.json`

### 主链写回

当前 `AppService` 每次任务执行完成后都会自动写回：

- thread working memory
- task working memory

## `context_sources.py`

这个文件把不同记忆来源统一成 `ContextSource`，便于 runtime 直接注入模型上下文。

当前优先级：

1. working memory
2. project memory
3. thread `MEMORY.md`
4. thread `summary`

也就是说，长期记忆优先于摘要，摘要只在没有长期记忆时作为回退来源。

## 当前边界

已经稳定的点：

- thread 当前窗口、完整历史、compact 摘要、长期记忆已经分层
- working memory 已经接入主链
- compact 两阶段流程已经能跑通

还会继续增强的点：

- 更结构化的摘要与记忆抽取
- 更细粒度的事实归并
- 更强的长期记忆更新策略
