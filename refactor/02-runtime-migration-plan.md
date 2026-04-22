# Runtime Migration Plan

## Phase 0

### 目标

冻结目标系统模型，先统一语言和数据结构。

### 产物

- `Thread / TaskRun / Turn / Step` 数据结构定义
- `EventEnvelope` 协议定义
- runtime 状态图
- 模块保留与重写边界清单
- 旧能力兼容边界说明

### 风险

- 文档写得太大，落不下去
- 不明确“先不做什么”，会让 Phase 1 无法开始

### 退出条件

- 团队对新骨架有一致理解
- 能明确回答“哪些模块保留，哪些必须重写”

## Phase 1

### 目标

落地新的 runtime 骨架，但先不引入子 Agent、scheduler、worktree。

### 产物

- 新 runtime 状态机
- 新 `app/service` 入口
- 新 event protocol
- thread/task/turn 的基础持久化
- 旧 chat 接口的最小兼容适配

### 风险

- 旧接口与新 runtime 双栈并存导致状态不一致
- 事件协议不稳定会影响 CLI/TUI 和后续 Web

### 退出条件

- 用户请求已经可以走 `thread -> task_run -> turn`
- 现有 CLI/TUI 可以消费新事件协议
- 基础工具调用仍然正常工作

## Phase 2

### 目标

完成 agent 关键能力迁移：上下文、记忆、工具治理。

### 产物

- `working memory`
- 新 `context engine`
- compact + episodic 提取机制
- 工具权限模型
- 审批与审计机制
- 初版环境抽象

### 风险

- working memory 被做成另一份 summary
- 工具治理做得过轻，后面仍然不安全
- context engine 如果继续只是拼消息，会导致这轮重构失效

### 退出条件

- context 构建不再只依赖 `session.messages`
- tools 可以按 policy 过滤和审批
- memory 已具备 working layer

## Phase 3

### 目标

在新 runtime 上叠高级 agent 能力。

### 产物

- sub-agent orchestration
- scheduled jobs / heartbeat jobs
- thread resume / recovery
- environment isolation
- 对外 runtime control interface

### 风险

- 子 Agent 没有 write ownership 会制造混乱
- 自动化任务与普通对话混用 thread 模型会造成状态污染
- environment 没有隔离会让多任务运行变得危险

### 退出条件

- 新 runtime 支持受控 delegation
- 支持任务恢复和计划性执行
- 支持更复杂的 agent 生命周期

## 顺序原则

必须遵守下面的顺序：

1. 先 state model
2. 再 runtime service
3. 再 context + memory
4. 再 tool governance
5. 最后才是 subagent / automation

如果顺序反过来，后面基本必返工。
