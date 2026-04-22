# app 模块设计

## 模块职责

`app` 是整个仓库的应用层。
它负责把界面输入转换成统一任务请求，把 runtime 事件转成上层稳定消费的事件流，并提供 thread 管理、模型切换、compact、状态查看这些高层操作。

当前目录：

- `bootstrap.py`
- `contracts.py`
- `service.py`
- `cli.py`
- `cli_render.py`
- `cli_lists.py`
- `cli_state.py`
- `cli_handlers.py`

## 核心契约

### `TaskRequest`

字段：

- `thread_id`
- `objective`
- `task_run_id`
- `metadata`

含义：一条明确的任务执行请求。

### `TaskResponse`

字段：

- `thread_id`
- `task_run_id`
- `output`
- `finish_reason`
- `status`
- `metadata`

含义：一次任务执行结束后的最终结果。

### `AgentEvent`

字段：

- `type`
- `thread_id`
- `task_run_id`
- `turn_id`
- `step_id`
- `status`
- `message`
- `payload`
- `event_id`
- `timestamp`

含义：上层界面和未来多端统一消费的事件对象。

## `AppService`

`AppService` 是应用层核心。

### 依赖

初始化时依赖：

- `Config`
- `LLMClient`
- `ToolRegistry`
- `ThreadStoreManager`

内部补齐：

- `MemoryStore`
- `FileWorkingMemoryStore`
- `FileRuntimeStateStore`

### 公开能力

- `run_task()`
- `run_task_stream()`
- `create_thread()`
- `get_thread()`
- `list_threads()`
- `clear_thread()`
- `compact_thread()`
- `get_thread_status()`
- `get_banana_info()`
- `list_models()`
- `switch_model()`

### `run_task_stream()` 执行流程

1. 创建本轮 `_TaskExecutionContext`
2. 预写 runtime 根状态
3. 把用户消息追加到当前 thread 当前窗口和完整历史
4. 调用 `build_context()` 组装模型上下文
5. 调用 `AgentRunner.run()` 执行主循环
6. 把新增的 `assistant / tool` 消息回写到 thread
7. 更新 thread/task 两份 working memory
8. 必要时执行 compact
9. 产出最终 `done` 事件

### `_TaskExecutionContext`

它把一次执行需要的四个核心对象绑在一起：

- `TaskRequest`
- `ThreadRef`
- `TaskRun`
- `ThreadStore`

作用很直接：保持应用层、消息存储层和 runtime 身份链一致。

## `bootstrap.py`

`create_app_service()` 是默认装配入口，负责创建默认配置、模型客户端、工具注册表和应用服务。
当前默认内置工具是 `ExecTool`。

## TUI 拆分

当前 TUI 不再把渲染、命令、事件处理、页面状态全部塞进 `cli.py`。
现在按职责拆成四块：

- `cli.py`
  - `BananaTUI` 外壳
  - Textual 组件定义
  - 焦点、按键、输入提交这些交互入口
- `cli_render.py`
  - 纯文本格式化
  - thinking 框、列表项摘要、状态块渲染
- `cli_lists.py`
  - thread / command / model 候选项数据结构
  - 各类 picker 列表项组件
  - 候选数据构建
- `cli_state.py`
  - 纸面正文状态
  - thinking / assistant 增量拼接
  - 正文块重建与收口
- `cli_handlers.py`
  - 内置命令处理
  - 对话事件流消费

## `cli.py`

`BananaTUI` 仍然是当前唯一的用户界面实现，但它现在主要承担的是界面层外壳，而不是业务编排。

### 页面结构

- 上方是一张可滚动纸面
- 下方是输入框
- 命令列表、thread 列表、模型列表都以内联列表方式出现在输入区附近

### 当前交互特征

- assistant 正文流式增长
- reasoning 过程写入固定高度 thinking 区域
- 如果一轮里发生工具调用，最终保留工具摘要框
- 如果没有工具调用，最终只保留 `Thinked`
- 线程、命令、模型列表都支持方向键和回车直接选择

### 当前职责边界

`cli.py` 当前主要保留：

- `compose()` 和组件查询
- picker 的显示/隐藏与选择入口
- 输入提交和全局按键入口
- 调用 `CLICommandHandler` / `CLIConversationHandler`

不再继续承担：

- 命令执行细节
- 事件流到纸面状态的完整投影
- 纸面正文块和 thinking 状态的底层拼接

### 当前内置命令

- `/help`
- `/model`
- `/new`
- `/threads`
- `/status`
- `/compact`
- `/banana`
- `/clear`
- `/exit`

## 当前边界

已经稳定的点：

- 应用层只暴露 task/thread 语义
- TUI 已经直接消费统一事件流
- 模型切换、线程切换、compact、状态查看都在 `AppService` 上统一收口

暂时仍然是应用层负责的点：

- thread 消息落盘
- working memory 回写
- compact 调度
- 最终 `done` 收口事件
