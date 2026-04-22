# Code Guide

## 1. 重构期间的总规则

1. 顶层目录不再二次推倒
2. 新功能优先接入新 runtime，不继续堆在旧 runner 上
3. 不允许长期双栈并存
4. 每次改动必须明确属于哪个 phase
5. 任何模块如果需要跨域依赖，必须先说明原因

## 2. 模块职责边界

### `app`

只负责：

- 外部入口
- 请求转发
- 事件消费
- 用户命令层

不负责：

- 执行状态机
- memory 细节
- tool 执行细节
- provider 细节

### `runtime`

只负责：

- task 状态机
- turn/step 编排
- event 产出
- 调度 memory / llm / tools

不负责：

- UI 展示
- provider 适配实现
- 存储层底层细节

### `memory`

只负责：

- working / episodic / project / personal memory
- compaction 与提取
- context source 抽象

不负责：

- UI 展示
- tool 执行
- runtime 状态机

### `tools`

只负责：

- tool spec
- tool registry
- execution policy
- approval / sandbox / audit

不负责：

- task 状态机
- session 组织

## 3. 新对象的命名建议

统一使用下面的领域命名：

- `Thread`
- `TaskRun`
- `Turn`
- `Step`
- `EventEnvelope`
- `WorkingMemory`
- `ToolExecutionRequest`
- `ToolExecutionResult`
- `ApprovalRequest`
- `RuntimeSnapshot`

不要再继续用语义过轻的名字，例如：

- `runner`
- `chunk`
- `message pack`
- `context builder` 但实际上只是 `message joiner`

## 4. 数据流要求

任何从 runtime 往外冒的数据，都应先标准化成统一协议。

禁止：

- UI 直接读取底层存储对象渲染
- TUI 依赖 provider 原始字段
- memory 直接操作 UI 事件结构
- tools 直接写 session 文件

## 5. 文档先行规则

以下改动必须先改文档再改代码：

1. runtime 状态模型变化
2. event protocol 变化
3. tool policy 变化
4. memory source 变化
5. 持久化结构变化

## 6. 禁止事项

1. 不要再向旧 `chat loop` 继续堆复杂能力
2. 不要把 working memory 做成另一份 markdown 摘要
3. 不要把审批逻辑写进单个 tool 实现里
4. 不要把 provider 差异泄漏到 runtime
5. 不要让 TUI 直接消费未经标准化的执行状态

## 7. 测试要求

新增或重构代码必须至少覆盖：

- 状态迁移测试
- 工具审批测试
- context 构建测试
- working memory 测试
- thread/task 恢复测试
- 端到端主链路测试
