# 🍌 bananabot

一个面向终端的 AI Agent 项目。
当前已经完成第一阶段结构收束，主线设计是统一 `thread / task_run / turn / step` 运行时，加上可落盘的消息存储、working memory、compact 和记忆整合。

> 现在的目标不是做一个能跑通 demo 的聊天壳子，而是做一个后面能继续接 TUI、桌面端、Web 端的 Agent 内核。

## ✨ 当前能力

- 💬 多轮 thread 对话
- 🌊 正文流式输出
- 🧠 reasoning 事件流与 thinking 展示
- 🔧 工具调用循环
- 💾 thread 消息持久化
- 🗜️ compact 摘要压缩
- 📌 project memory + working memory 注入
- 🧵 结构化运行时状态落盘
- 🖥️ Textual TUI 交互界面
- 🔁 模型列表与 `/model` 快速切换

## 🧱 仓库结构

```text
bananabot/
├── bananabot/
│   ├── app/      # 应用入口、服务编排、TUI、统一契约
│   ├── runtime/  # 运行时模型、事件、状态推进、主循环、上下文
│   ├── memory/   # thread 存储、compact、长期记忆、working memory
│   ├── llm/      # 模型档案、provider 规则、HTTP 请求
│   ├── tools/    # 工具抽象、注册表、内置工具
│   └── infra/    # 配置、路径、日志、状态存储
├── docs/         # 当前实现文档
├── refactor/     # 重构规则、计划、协作文档
├── tests/        # 回归测试与契约测试
├── AGENTS.md
├── TODO.md
└── models.toml
```

## 🚀 启动

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置模型

准备 `.env` 和 `models.toml`。

最少需要：

```env
DEFAULT_MODEL=qwen3.6-plus
DASHSCOPE_API_KEY=your_key
DEEPSEEK_API_KEY=your_key
MINIMAX_API_KEY=your_key
MIMO_API_KEY=your_key
LOCAL_OMLX_API_KEY=your_key
```

`models.toml` 负责声明模型档案，`.env` 只负责密钥和运行参数。

当前内置 provider 白名单：`dashscope / deepseek / minimax / mimo / local`。

### 3. 启动交互模式

```bash
uv run bananabot
```

如果已经安装到本地环境：

```bash
bananabot
```

### 4. 单次执行

```bash
uv run bananabot "帮我分析当前目录"
```

### 5. Provider smoke 验证

```bash
uv run python -m bananabot.llm.smoke
```

只验证某个模型：

```bash
uv run python -m bananabot.llm.smoke --alias qwen3.6-plus
```

## 🖥️ TUI 命令

- `/help`：显示命令列表
- `/model`：打开模型切换列表
- `/new`：创建新 thread
- `/threads`：打开 thread 列表
- `/status`：查看当前 thread 状态
- `/compact`：压缩当前 thread
- `/banana`：查看全局 / 项目 BANANA 指令
- `/clear`：清空当前窗口消息
- `/exit`：退出

常用快捷键：

- `Enter`：发送 / 选择
- `Esc`：回到输入框
- `Ctrl+L`：清理当前屏幕上的临时过程
- `Ctrl+R`：从磁盘重载当前 thread

## 🔄 主执行链路

1. `app/bootstrap.py` 组装 `Config`、`LLMClient`、`ToolRegistry`、`ThreadStoreManager`
2. `app/service.py` 接收 `TaskRequest`
3. 用户消息写入当前 thread 窗口和历史日志
4. `runtime/context_engine.py` 组装模型上下文
5. `runtime/runner.py` 执行 `LLM -> tool -> LLM` 循环
6. `runtime/coordinator.py` 推进 `thread / task_run / turn / step`
7. `infra/runtime_state_store.py` 持续写 runtime 状态与事件日志
8. `memory/working_memory.py` 回写 thread/task working memory
9. `memory/compact_service.py` 按阈值压缩旧消息
10. `app/cli.py` 消费统一事件流并渲染 TUI

## 🧾 对外契约

当前公共请求/响应模型已经统一为：

- `TaskRequest`
- `TaskResponse`
- `AgentEvent`

当前公共服务入口：

- `AppService.run_task()`
- `AppService.run_task_stream()`
- `AppService.get_thread_status()`
- `AppService.list_threads()`
- `AppService.switch_model()`

## 💾 存储结构

默认目录在 `~/.bananabot/`。

### thread 消息目录

```text
~/.bananabot/sessions/<thread_id>/
├── session.jsonl
├── history.jsonl
├── summary.jsonl
└── MEMORY.md
```

含义：

- `session.jsonl`：当前短期窗口
- `history.jsonl`：完整历史
- `summary.jsonl`：compact 摘要
- `MEMORY.md`：thread 长期记忆

### runtime 状态目录

```text
~/.bananabot/runtime-state/
├── threads/
├── task_runs/
├── turns/
├── steps/
└── event_log.jsonl
```

## 🧪 测试

运行全量测试：

```bash
uv run python -m unittest
```

快速检查：

```bash
uv run python -m compileall bananabot tests
```

## 📚 文档

- [仓库总览](docs/00-仓库总览.md)
- [app 模块设计](docs/app%20模块设计.md)
- [runtime 模块设计](docs/runtime%20模块设计.md)
- [memory 模块设计](docs/memory%20模块设计.md)
- [测试与状态存储设计](docs/测试与状态存储设计.md)
- [TODO](TODO.md)
- [重构文档目录](refactor/)

## 🛣️ 接下来

当前仓库已经完成第一阶段的大结构收口。后续重点是：

- 扩展工具体系
- 继续升级 provider 和模型调度
- 加入 skill 机制
- 补桌面端 / Web 端入口
- 完善恢复、审批、安全和端到端测试
