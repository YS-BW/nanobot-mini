# 🍌 nanobot-mini

一个轻量但完整的 AI Assistant / Agent CLI 项目。  
当前以终端形态运行，已经具备 `LLM ↔ 工具调用 ↔ 会话持久化 ↔ compact ↔ 长期记忆` 的完整闭环，并完成了第一阶段结构重构。

> 目标不是做一个只能跑 demo 的脚手架，而是做一个后续可以继续扩展到 CLI、桌面端、Web 端的统一 Agent 内核。

---

## ✨ 项目概览

`nanobot-mini` 当前已经具备这些核心能力：

- 💬 多轮对话与多会话管理
- 🧠 上下文构建、会话压缩、长期记忆整合
- 🔧 `LLM ↔ Tool` 运行时主循环
- 🌊 流式输出，支持正文增量和思考过程事件
- 🖥️ 可交互的 TUI 终端界面
- 📦 清晰的模块分层：`app / runtime / llm / memory / tools / infra`
- 🔌 面向未来多端的统一服务接口与统一事件结构

当前阶段的重点已经从“能不能跑”切换到“怎么持续扩展、怎么保持结构稳定”。

---

## 🗂️ 项目状态

### ✅ 已完成

- 第一阶段结构重构
- 统一应用服务接口
- 统一运行时事件流
- 会话持久化与历史记录
- compact 摘要压缩
- MEMORY 长期记忆整合
- OpenAI 兼容模型接入
- TUI 交互界面与流式正文展示
- 基础回归测试

### 🚧 当前重点

- 扩展更多工具能力
- 升级记忆与上下文裁剪策略
- 继续打磨统一事件流，支撑 Web / Desktop
- 完善 provider、恢复、安全与测试体系

📌 完整执行清单见 [TODO.md](TODO.md)

---

## 🧱 当前架构

```text
nanobot_mini/
├── __main__.py
├── app/
├── runtime/
├── llm/
├── memory/
├── tools/
└── infra/
```

### `app/`

- 🚪 应用入口
- 🧩 依赖组装
- 📡 统一请求 / 响应 / 事件契约
- 🧠 顶层服务编排
- 🖥️ CLI / TUI 界面

### `runtime/`

- 🔁 Agent 主循环
- 🧵 运行时事件
- 🧱 上下文构建
- 📝 提示词组织

### `llm/`

- 🌐 模型请求发送
- 📥 响应解析
- 🌊 流式 chunk 结构
- ❗ 异常语义封装

### `memory/`

- 💾 session / history / summary 持久化
- 🧠 MEMORY 长期记忆
- 🗜️ compact 压缩服务
- 📚 记忆源查找与加载

### `tools/`

- 🧰 工具抽象基类
- 🗂️ 工具注册表
- ⚙️ 内置工具实现

### `infra/`

- ⚙️ 配置加载
- 🪵 调试日志
- 📁 路径与运行环境规则

---

## 🔄 主执行链路

一次完整对话的大致流程：

1. `nanobot_mini/__main__.py` 启动程序
2. `app/bootstrap.py` 组装 `Config / LLM / ToolRegistry / SessionManager`
3. `app/service.py` 接收统一 `ChatRequest`
4. `runtime/context_builder.py` 构建上下文
5. `runtime/runner.py` 执行 `LLM ↔ Tool` 循环
6. `memory/session_store.py` 写回 `session.jsonl / history.jsonl`
7. `memory/compact_service.py` 按策略执行 compact
8. `app/cli.py` / 未来 Web / Desktop 消费统一事件流

---

## 🖥️ 运行方式

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

最少需要配置：

```bash
BASE_URL=...
API_KEY=...
LLM=...
```

### 3. 启动交互模式

```bash
uv run nanobot-mini
```

如果已经做过全局安装，也可以直接：

```bash
nanobot-mini
```

### 4. 单次执行

```bash
uv run nanobot-mini "帮我分析一下当前目录"
```

---

## 🧭 TUI 体验

当前 TUI 支持：

- 📜 可滚动会话纸面
- 🌊 assistant 正文流式输出
- 🧠 thinking 展示与收敛
- 🔧 工具调用摘要展示
- ⌨️ 持续交互输入

常用操作：

- `Enter` 发送
- `Esc` 聚焦输入框
- `Ctrl+L` 清理当前屏幕临时过程
- `Ctrl+R` 重载当前会话
- 鼠标滚轮查看历史

---

## 🛠️ 内置命令

交互模式支持：

- `/new`：开启新会话
- `/session <name>`：切换会话
- `/clear`：清空当前会话窗口
- `/sessions`：列出所有会话
- `/status`：查看当前状态
- `/compact`：强制执行压缩
- `/banana`：查看全局 / 项目指令文件
- `/help`：显示帮助
- `/exit`：退出程序

---

## 💾 会话与记忆

当前会话目录下通常会包含：

- `session.jsonl`：当前短期窗口消息
- `history.jsonl`：完整历史记录
- `summary.jsonl`：compact 摘要结果
- `MEMORY.md`：长期记忆

这套分层的意义是：

- `session` 负责当前上下文窗口
- `history` 保留完整历史
- `summary` 负责阶段性压缩
- `MEMORY` 负责长期沉淀

这也是当前项目后续继续扩展记忆系统的基础。

---

## 🌊 流式输出与事件流

项目现在已经支持统一事件流：

- `assistant_delta`
- `assistant_reasoning_delta`
- `tool_call_started`
- `tool_call_finished`
- `assistant_message`
- `done`
- `error`

其中最重要的统一入口在：

- `AppService.chat()`
- `AppService.chat_stream()`

这意味着后续 CLI、Web、桌面端都可以尽量复用同一套运行时，而不是每个端自己再写一套 Agent 流程。

---

## 🧪 测试

当前基础回归测试可直接运行：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

测试覆盖的重点包括：

- ✅ assistant / user 持久化
- ✅ 工具调用链路
- ✅ 流式 delta
- ✅ reasoning 事件
- ✅ compact 基础行为
- ✅ context 构建优先级
- ✅ TUI 基础交互

---

## 📚 文档索引

- 📌 [AGENTS.md](AGENTS.md)
  - 协作规则、任务边界、变更原则
- 🗺️ [TODO.md](TODO.md)
  - 当前执行清单与阶段路线图
- 🧱 [docs/项目结构重构方案.md](docs/项目结构重构方案.md)
  - 第一阶段结构重构方案与阶段边界
- 🧠 [docs/记忆与上下文压缩系统设计.md](docs/记忆与上下文压缩系统设计.md)
  - 记忆与上下文压缩设计

---

## 🚀 未来方向

接下来的演进重点不是再次推倒重构，而是在已经固定的结构上继续扩展：

- 🔧 更多工具：filesystem / search / web / 安全控制
- 🧠 更强记忆：token 预算、working memory、compact 策略升级
- 🌐 多端复用：Web / Desktop / API
- 🛡️ 安全能力：命令拦截、权限边界、行为审计
- ♻️ 恢复能力：checkpoint / resume / recovery
- 🧪 更完整的测试体系

路线和优先级以 [TODO.md](TODO.md) 为准。

---

## 🤝 协作说明

如果你要继续在这个项目上开发，建议先读：

1. [AGENTS.md](AGENTS.md)
2. [TODO.md](TODO.md)
3. `docs/` 里的对应设计文档

这个项目现在最值钱的不是某一个函数，而是已经稳定下来的模块边界和统一接口。后续扩展尽量沿着现有骨架推进，不要再把结构搞回一锅粥。
