# runtime 模块设计

## 模块职责

`runtime` 是当前项目的执行内核。
它负责定义运行时模型、管理状态流转、构建上下文、执行 `LLM -> tool -> LLM` 循环，并持续发出结构化事件。

当前目录：

- `models.py`
- `events.py`
- `coordinator.py`
- `runner.py`
- `context_engine.py`
- `prompts.py`

## 运行时模型

### `ThreadRef`

表示一个 thread：

- `id`
- `title`
- `metadata`
- `created_at`
- `updated_at`

### `TaskRun`

表示 thread 下的一次任务执行：

- `id`
- `thread_id`
- `objective`
- `status`
- `metadata`
- `created_at`
- `updated_at`

### `Turn`

表示一次任务执行中的一轮决策：

- `id`
- `task_run_id`
- `sequence`
- `status`
- `created_at`
- `updated_at`

### `Step`

表示一轮中的原子动作：

- `id`
- `task_run_id`
- `turn_id`
- `kind`
- `sequence`
- `status`
- `payload`
- `created_at`
- `updated_at`

## 事件模型

`events.py` 只定义一个统一事件对象：`EventEnvelope`。

字段：

- `type`
- `status`
- `message`
- `payload`
- `thread_id`
- `task_run_id`
- `turn_id`
- `step_id`
- `event_id`
- `timestamp`

现在 runtime 内部和 app 层之间都只走这一个事件结构，不再存在第二套事件命名。

## `RuntimeCoordinator`

`coordinator.py` 现在直接负责状态推进和事件发射，不再拆一层独立状态机。

职责：

1. 推进 `thread / task_run / turn / step`
2. 生成 `EventEnvelope`
3. 把状态和事件写到 `FileRuntimeStateStore`

当前主要动作：

- `start_task_run()`
- `complete_task_run()`
- `fail_task_run()`
- `start_turn()`
- `complete_turn()`
- `fail_turn()`
- `start_step()`
- `complete_step()`
- `fail_step()`

它是当前 runtime 里唯一负责把状态推进和事件发射绑定在一起的对象。

## `AgentRunner`

`runner.py` 是最核心的执行循环。

### 输入

- `messages`
- `event_callback`
- `thread_id`
- `task_run_id`
- `thread_title`
- `thread_metadata`
- `task_metadata`
- `state_store`

### 核心流程

1. 创建 `RuntimeCoordinator`
2. 开始 `task_run`
3. 开始一个 `turn`
4. 创建 reasoning step
5. 读取 `LLMClient.chat_stream()` 输出的 chunk
6. 增量聚合 reasoning、正文、工具调用
7. 如果模型请求工具，执行工具并把工具消息补回消息列表
8. 如果模型停止调用工具，产出最终 `assistant_message`
9. 完成 `turn` 与 `task_run`

### 事件类型

当前主链里常见事件：

- `task_run_started`
- `turn_started`
- `assistant_thinking`
- `assistant_reasoning_delta`
- `assistant_delta`
- `tool_call_requested`
- `tool_call_started`
- `tool_call_finished`
- `assistant_message`
- `turn_completed`
- `task_run_completed`
- `error`

## 上下文构建

`context_engine.py` 现在只保留函数式入口，不再包一层 `ContextEngine / Request / Result`。

当前对外只提供一个方法：

- `build_context()`

输入参数：

- `workspace`
- `thread_store`
- `thread`
- `task_run`
- `messages`
- `memory_store`
- `working_memory`
- `working_memory_store`
- `system_prompt`
- `extra_system_messages`

返回值：

- 直接返回 `list[dict]`，也就是模型最终要消费的消息列表

### 构建顺序

1. 收集 memory 来源
2. 转成 system 消息注入最前面
3. 注入默认系统提示词
4. 注入附加 system 消息
5. 拼接当前 thread 消息
6. 清理无效历史消息

内部辅助函数：

- `sanitize_messages()`：清理没有正文的 assistant 消息、没有前置 tool_call 的孤立 tool 消息
- `_load_working_memory()`：按 `thread_id / task_run_id` 恢复 working memory
- `_resolve_messages()`：优先取显式传入的消息，否则回退到 `thread_store.messages`
- `_resolve_thread_id()`：统一解析当前上下文对应的 thread 标识

## 当前边界

已经稳定的点：

- 运行时模型已经统一
- runtime 事件已经统一
- 主循环已经能处理 reasoning、正文流、工具调用和最大轮次保护
- runtime 状态已经能持续落盘

后续还会继续增强的点：

- 更细粒度的恢复能力
- 审批与阻塞状态
- 更完整的任务规划与状态更新 step
- 与 skill 的协作
