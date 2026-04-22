# Agent Roles

## 总控角色

### `architect-coordinator`

职责：

- 维护总设计口径
- 冻结共享协议
- 审核跨模块边界
- 合并并发 agent 的产出

写入范围：

- `refactor/`
- `AGENTS.md`
- 跨模块共享契约

## 执行角色

### `runtime-core`

职责：

- 重写 `runtime` 状态机
- 落地 `Thread / TaskRun / Turn / Step`
- 定义和实现统一运行时事件协议

写入范围：

- `bananabot/runtime/`

### `memory-engine`

职责：

- 引入 `working memory`
- 重做 context engine
- 设计和实现 episodic/project/personal memory 的过渡层

写入范围：

- `bananabot/memory/`
- 允许少量触达 `bananabot/runtime/context_*`

### `tool-governance`

职责：

- 把工具系统升级为执行治理层
- 引入 `ToolSpec / Policy / Approval / Audit / Sandbox`

写入范围：

- `bananabot/tools/`

### `app-interface`

职责：

- 改 `app/service`
- 让 CLI/TUI 消费新 runtime 事件协议
- 维持用户入口可用

写入范围：

- `bananabot/app/`

### `state-and-test`

职责：

- 设计 task/thread 持久化骨架
- 补状态机测试、恢复测试、端到端测试

写入范围：

- `tests/`
- 少量 `bananabot/infra/`
- 少量未来 `task_store/state_store`

## 并发规则

1. 共享协议只允许总控先定稿
2. 各 agent 只改自己的 ownership 范围
3. 跨域变更先记录到 `refactor/`
4. 不允许并行修改同一核心文件
5. 合并前必须跑回归测试
