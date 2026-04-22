# Architecture Plan

## 1. 总体原则

这次重构遵循 4 个原则：

1. 顶层目录保留，核心执行模型重做
2. runtime 是承重墙，优先级最高
3. 所有上层界面都只消费统一 runtime 协议
4. memory 与 tools 必须为 agent runtime 服务，而不是为聊天服务补丁式扩展

## 2. 新的执行骨架

建议引入以下核心对象：

### `Thread`

表示一个持续存在的执行上下文。

职责：

- 聚合多轮任务执行
- 维护长期 thread 状态
- 关联 memory、artifacts、event log

### `TaskRun`

表示一次明确的任务运行实例。

职责：

- 表示某一轮任务执行
- 可中断、可恢复、可审计
- 拥有开始、运行中、等待审批、完成、失败等状态

### `Turn`

表示 task 内的一轮 Agent 决策与执行。

职责：

- 对应一次模型推理周期
- 产出多个 step
- 决定下一步是回复、调用工具、等待、继续规划

### `Step`

表示 turn 内的一次原子动作。

例如：

- reasoning
- tool_call_requested
- tool_call_started
- tool_call_finished
- assistant_message
- approval_required
- state_update

## 3. 新的数据流

目标数据流应为：

1. `app/service` 接收用户请求
2. 解析到目标 `thread`
3. 创建或恢复 `task_run`
4. `runtime` 驱动 `task_run -> turn -> step`
5. `context engine` 组装上下文
6. `llm` 执行推理
7. `tool execution layer` 执行受控工具动作
8. `memory` 更新 working / episodic / project / personal memory
9. 统一通过 `EventEnvelope` 向外发事件

## 4. 统一事件协议

新的 runtime 事件至少应包含：

- `event_id`
- `thread_id`
- `task_run_id`
- `turn_id`
- `step_id`
- `type`
- `status`
- `timestamp`
- `payload`

说明：

- `CLI/TUI` 不应再直接依赖底层对象
- `Web` 和未来桌面端只订阅这一层协议
- 历史恢复、调试日志、任务恢复也以它为准

## 5. 模块保留与重写边界

### 保留并增强

#### `llm`

保留原因：

- provider / backend / profile 的方向已经基本正确
- 当前问题不在模型接入层，而在 runtime 上层

增强方向：

- 与 runtime protocol 更紧密耦合
- 能输出更稳定的 stream / reasoning / tool-call event
- 对 task runtime 提供更明确的能力声明

#### `infra`

保留原因：

- `config / paths / logging` 都是有效基础设施能力

增强方向：

- 增加 runtime state store 配置
- 增加 execution policy 配置
- 增加 environment policy 配置

### 必须重写

#### `runtime`

原因：

- 当前仍然是 chat loop
- 无法承担 thread/task/turn/step 状态模型

新职责：

- task state machine
- event production
- context assembly coordination
- tool orchestration
- memory synchronization

#### `app/service`

原因：

- 当前是 chat orchestrator
- 只能优雅支撑聊天请求，不适合任务型 agent

新职责：

- thread/task runtime service
- 统一 session/thread 入口
- 统一命令与任务操作接口
- 统一事件输出

#### `memory`

原因：

- 当前只有 `session + summary + MEMORY.md`
- 还没有正式的 working memory

新职责：

- working memory
- episodic memory
- project memory
- personal memory
- context budget integration

#### `tools`

原因：

- 当前 registry 太薄
- 不足以承接未来高风险 agent 能力

新职责：

- tool spec
- execution policy
- approval policy
- sandbox policy
- audit log
- environment binding

## 6. 目标目录结构

顶层仍然保持：

```text
bananabot/
├── app/
├── runtime/
├── memory/
├── tools/
├── llm/
└── infra/
```

但内部应向下面演化：

```text
bananabot/runtime/
├── models.py
├── state_machine.py
├── service.py
├── events.py
├── context_engine.py
├── task_store.py
└── coordinator.py
```

```text
bananabot/memory/
├── working_memory.py
├── episodic_memory.py
├── project_memory.py
├── personal_memory.py
├── compaction.py
└── context_sources.py
```

```text
bananabot/tools/
├── specs.py
├── registry.py
├── executor.py
├── policy.py
├── approvals.py
├── sandbox.py
├── audit.py
└── builtins/
```

## 7. 为什么不是继续修补当前 runner

因为继续修补当前 runner，会把这些能力都做成分散补丁：

- 子 agent
- task queue
- resume
- approval wait
- scheduled jobs
- worktree / environment
- context planner

一旦这些能力不是建立在统一状态机上，而是挂在单轮 chat loop 上，后面几乎一定返工。

## 8. 设计合理性判断

这次重构是合理的，因为：

1. 顶层目录已经足够稳定，不需要第二次目录级推倒
2. 当前真正的瓶颈明确是 runtime 执行模型
3. 记忆和工具系统的升级都依赖新的 runtime 骨架
4. 未来 skill、subagent、automation 都要求明确的 task runtime

换句话说：

这次不是为了“更漂亮的架构”而重构，而是为了让未来能力有地方落。
