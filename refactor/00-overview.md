# Overview

## 1. 重构背景

`bananabot` 当前已经完成了第一阶段结构整理，顶层目录边界基本稳定：

- `app`
- `runtime`
- `memory`
- `tools`
- `llm`
- `infra`

这一步解决的是“项目结构混乱”的问题，但没有解决更深的一层问题：

当前系统的执行骨架仍然是一个典型的 Assistant 结构：

- 接收用户输入
- 拼接消息列表
- 调用模型
- 如果模型触发工具，则执行工具
- 把工具结果回填给模型
- 直到模型停止

这套结构适合聊天助手，不适合你要的个人 Agent。

## 2. 当前系统的核心限制

如果继续在现有 `LLM ↔ Tool ↔ LLM` 循环上叠功能，后面会稳定撞上这些限制：

1. 没有真正的 `thread / task / turn` 模型
2. 无法优雅支持中断、恢复、审批阻塞
3. 很难挂子 Agent，而不把当前会话搅乱
4. 没有 working memory，只能靠消息和摘要硬撑
5. 工具系统只有“注册与执行”，没有治理能力
6. 事件流更偏 UI 进度，不是 runtime 协议

## 3. 这次重构的目标

这次重构不再只是“优化代码结构”，而是要完成系统身份切换：

从：

- Chat-first assistant runtime

迁移到：

- Task-first local agent runtime

新的系统核心应该是：

- `Thread`
- `TaskRun`
- `Turn`
- `Step`
- `EventEnvelope`
- `WorkingMemory`
- `ToolExecutionPolicy`

## 4. 这次重构不做什么

为了控制范围，这次重构明确不做：

1. 不重做整个顶层目录结构
2. 不改成 LiteLLM 那种模型网关
3. 不一次性做完子 Agent、scheduler、worktree、automation 全量能力
4. 不把所有历史能力都迁成双栈长期并存
5. 不为了未知 provider 再做一层大兼容设计

## 5. 应保留的部分

以下方向保留，不推倒：

- `llm` 作为模型接入层的职责
- `infra` 作为配置、路径、日志的基础设施域
- `tools` 作为独立域存在
- `memory` 作为独立域存在
- `app` 作为统一入口域存在

## 6. 必须重写的部分

以下内容必须视为新系统来做：

1. `runtime/runner`
2. `runtime/events`
3. `runtime/context_builder`
4. `app/service`
5. `memory` 中的 working layer
6. `tools` 的执行与治理层

## 7. 新系统的判断标准

只有满足下面这些，才算真正完成身份切换：

1. 执行核心不再围绕单轮 chat loop 组织
2. 运行时拥有稳定的 `thread/task/turn/step` 状态机
3. 事件协议能支撑 CLI、桌面端、Web 端复用
4. memory 里存在 working memory，而不是只有摘要
5. tools 有权限、审批、规则、审计能力
6. `app/service` 面向 task runtime，而不是只面向聊天
