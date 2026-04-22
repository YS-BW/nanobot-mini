# Work Items

## P0

### runtime

- [ ] 定义 `Thread / TaskRun / Turn / Step` 数据结构
- [ ] 定义 `EventEnvelope`
- [ ] 设计 runtime 状态图
- [ ] 重写 `runtime/runner` 为状态机核心
- [ ] 把旧 chat loop 收成兼容适配层

### app/service

- [ ] 定义新的 runtime service 接口
- [ ] 让 `chat_stream()` 走新 task runtime
- [ ] 把会话语义逐步迁到 thread 语义

### memory

- [ ] 新建 `working_memory.py`
- [ ] 定义 working memory 数据模型
- [ ] 重做 `context_builder` 为 `context_engine`
- [ ] 设计 episodic extraction 规则

## P1

### tools

- [ ] 定义 `ToolSpec`
- [ ] 定义 `ToolExecutionRequest / Result`
- [ ] 增加 policy 过滤
- [ ] 增加审批模型
- [ ] 增加审计记录

### persistence

- [ ] 设计 thread/task/turn 的持久化结构
- [ ] 明确 session 文件与未来 state store 的过渡方案
- [ ] 给 event log 设计最小持久化格式

## P2

### runtime extensions

- [ ] 设计 sub-agent 协议
- [ ] 设计 scheduled jobs
- [ ] 设计 recovery / resume
- [ ] 设计 environment abstraction

## 当前建议顺序

1. 冻结 runtime 模型
2. 重写 `app/service` 入口语义
3. 重写 `runtime`
4. 引入 working memory
5. 重做 context engine
6. 升级 tool governance
7. 最后做子 agent 和自动化

## 本轮输出完成定义

本轮文档工作完成，至少满足：

- [x] 有统一文档目录
- [x] 有总览文档
- [x] 有详细重构方案
- [x] 有 phase 计划
- [x] 有代码指导
- [x] 有代码风格规则
- [x] 有执行清单
