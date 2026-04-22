# Shared Contracts

这份文档只描述并发重构期间必须共享的核心契约。

## 1. Runtime Identity

### `thread_id`

- 表示一个持续存在的执行上下文
- 作用域高于单次用户输入
- 后续 resume、automation、sub-agent 都依赖它

### `task_run_id`

- 表示 thread 内的一次任务运行
- 用户每次主动发起任务，通常生成一个新的 `task_run`
- 自动化任务和普通聊天任务都要落到这里

### `turn_id`

- 表示 task 内的一轮 agent 决策
- 一个 turn 内允许产生多个 step

### `step_id`

- 表示 turn 内的一次原子动作
- 它是审计、恢复、调试的最小粒度

## 2. Runtime Status

### `TaskRunStatus`

当前冻结为：

- `pending`
- `running`
- `waiting_approval`
- `blocked`
- `completed`
- `failed`
- `cancelled`

### `TurnStatus`

当前冻结为：

- `pending`
- `running`
- `completed`
- `failed`

### `StepStatus`

当前冻结为：

- `pending`
- `running`
- `completed`
- `failed`
- `skipped`

## 3. Step Kinds

当前冻结为：

- `user_message`
- `reasoning`
- `tool_call_requested`
- `tool_call_started`
- `tool_call_finished`
- `assistant_message`
- `approval_required`
- `state_update`

如果后续要新增 step kind，必须先改文档，再改代码。

## 4. Event Envelope

所有 runtime 内部事件最终都要收敛为：

- `event_id`
- `thread_id`
- `task_run_id`
- `turn_id`
- `step_id`
- `type`
- `status`
- `timestamp`
- `payload`

兼容约束：

- 短期内允许继续通过 `message` 显示进度文本
- 短期内允许通过 `data` 兼容旧读取路径
- 新逻辑必须优先写入 `payload`

## 5. Ownership Boundaries

### runtime-core

- 拥有 `runtime/`
- 不负责改 `app/` 的展示语义

### memory-engine

- 拥有 `memory/`
- 只能消费 runtime 共享对象，不得重定义 `thread/task/turn/step`

### tool-governance

- 拥有 `tools/`
- 只能通过 `ToolExecutionRequest / Result` 与 runtime 对接

### app-interface

- 拥有 `app/`
- 只能消费 runtime 协议，不得另起一套事件结构

### state-and-test

- 拥有 `tests/`
- 可以验证共享契约，但不重新定义契约

## 6. Current Rule

当前最重要的一条规则：

不要再围绕 `chat(messages)` 扩展能力，所有新能力都要向 `thread/task/turn/step` 靠拢。
