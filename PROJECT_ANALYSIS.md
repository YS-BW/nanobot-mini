# nanobot-mini 项目分析文档

> 📅 分析时间：2026-04-14  
> 📦 项目版本：v0.1.0  

---

## 1. 项目概述

**nanobot-mini** 是一个轻量级 AI Agent 框架的最小复刻版，旨在从零构建自己的 AI Agent。它通过调用 LLM（大语言模型）API，结合工具调用（Function Calling）能力，实现了一个能够执行 shell 命令、完成自动化任务的智能代理。

### 核心特性

| 特性 | 说明 |
|------|------|
| 🔌 LLM 集成 | 支持 OpenAI 及兼容 API（可对接本地模型） |
| 🛠️ 工具系统 | 基于 Function Calling 的可扩展工具框架 |
| 💬 会话管理 | 支持多轮对话，自动保存历史 |
| ⚙️ 灵活配置 | 支持 `.env` 文件和环境变量配置 |
| 🖥️ 交互模式 | 支持 CLI 单次调用和交互式对话 |

---

## 2. 技术栈

| 类别 | 技术 |
|------|------|
| 语言 | Python ≥ 3.11 |
| HTTP 客户端 | httpx (异步) |
| 环境管理 | python-dotenv |
| 包管理 | pip / uv |
| API 协议 | OpenAI Chat Completions API |

---

## 3. 项目结构

```
nanobot-mini/
├── .env                        # 环境变量配置
├── pyproject.toml              # 项目元数据与依赖
├── uv.lock                     # uv 锁文件
├── README.md                   # 项目说明
├── PROJECT_ANALYSIS.md         # 📄 本文档
└── nanobot_mini/               # 核心源码
    ├── __init__.py             # 模块导出
    ├── __main__.py             # CLI 入口
    ├── config.py               # 配置管理
    ├── context.py              # Prompt 构建
    ├── llm.py                  # LLM API 调用
    ├── runner.py               # 核心 Agent 循环
    ├── session.py              # 会话管理
    ├── tools.py                # 工具系统
    └── types.py                # 数据类型定义
```

---

## 4. 核心架构

### 4.1 整体流程

```
┌─────────────┐
│  用户输入    │
└──────┬──────┘
       ▼
┌──────────────────┐
│ ContextBuilder   │  构建 system prompt + 历史 + 用户消息
│ build_messages() │
└──────┬───────────┘
       ▼
┌──────────────────┐     ┌─────────────┐
│  AgentRunner     │◄───►│    LLM      │  调用 OpenAI API
│  run()           │     │  chat()     │
└──────┬───────────┘     └─────────────┘
       │                        ▲
       │  tool_calls?           │
       ▼                        │
┌──────────────────┐            │
│  ToolRegistry    │────────────┘
│  execute()       │  执行工具，返回结果
└──────┬───────────┘
       ▼
┌──────────────────┐
│  Session         │  保存对话历史
│  save()          │
└──────────────────┘
```

### 4.2 Agent 循环（Runner）

`AgentRunner.run()` 实现了经典的 **ReAct** 风格循环：

1. 将消息列表发送给 LLM
2. 检查 LLM 返回是否有 `tool_calls`
3. 若有，执行对应工具，将结果追加到消息列表
4. 重复步骤 1-3，直到 LLM 不再调用工具或达到最大迭代次数

```python
while iteration < self.max_iterations:
    response = await self.llm.chat(messages=messages, tools=...)
    if not response.tool_calls:
        return response  # 任务完成
    for tc in response.tool_calls:
        result = await self.registry.execute(tc.name, tc.arguments)
        messages.append({"role": "tool", "content": result})
```

---

## 5. 模块详解

### 5.1 `types.py` — 数据类型

定义了三个核心数据类：

| 类型 | 字段 | 说明 |
|------|------|------|
| `ToolCall` | id, name, arguments | 工具调用请求 |
| `LLMResponse` | content, tool_calls, finish_reason | LLM 返回结果 |
| `ToolResult` | tool_call_id, name, content | 工具执行结果 |

### 5.2 `config.py` — 配置管理

支持从 `.env` 文件或环境变量加载配置：

| 配置项 | 环境变量 | 默认值 |
|--------|----------|--------|
| API 地址 | `BASE_URL` / `MIMO_BASE_URL` | `https://api.openai.com/v1` |
| 模型名称 | `LLM` / `MIMO_LLM` | `gpt-4o` |
| API Key | `API_KEY` / `MIMO_API_KEY` | `""` |
| 工作目录 | `WORKSPACE` | `/tmp/nanobot-mini` |
| 最大迭代 | `MAX_ITERATIONS` | `20` |

### 5.3 `llm.py` — LLM 调用

封装了 OpenAI Chat Completions API：

- **`chat()`**：同步调用，返回 `LLMResponse`
- **`chat_stream()`**：流式调用，返回 `AsyncIterator[str]`

支持任意兼容 OpenAI API 的服务（如本地部署的 Ollama、vLLM 等）。

### 5.4 `tools.py` — 工具系统

采用 **抽象基类 + 注册表** 模式：

```
Tool (ABC)
  ├── name: str
  ├── description: str
  ├── parameters: dict
  └── execute(**kwargs) -> str

ToolRegistry
  ├── register(tool)
  ├── get(name) -> Tool
  ├── get_definitions() -> list[dict]   # OpenAI function calling 格式
  └── execute(name, args) -> (result, error)
```

内置工具：

| 工具 | 功能 |
|------|------|
| `ExecTool` | 执行 shell 命令，支持超时控制 |

### 5.5 `context.py` — Prompt 构建

构建发送给 LLM 的消息列表：

```
[system]  → System Prompt（包含时间、工作目录）
[history] → 历史对话记录
[user]    → 当前用户输入
```

System Prompt 指示 LLM：
- 是一个有帮助的 AI 助手
- 可以使用 `exec` 工具执行命令
- 不确定时可以尝试执行看看结果

### 5.6 `session.py` — 会话管理

- **`Session`**：单个会话，管理消息列表，支持持久化到 JSON 文件
- **`SessionManager`**：会话管理器，按 key 缓存和加载会话

会话文件存储在 `{workspace}/sessions/{key}.jsonl`。

### 5.7 `runner.py` — Agent 运行器

核心的 LLM↔工具循环控制器，实现了 Agent 的推理-行动循环。

### 5.8 `__main__.py` — CLI 入口

支持两种运行模式：

| 模式 | 命令 | 说明 |
|------|------|------|
| 单次模式 | `python -m nanobot_mini "问题"` | 执行一次对话后退出 |
| 交互模式 | `python -m nanobot_mini` | 进入 REPL 循环输入 |

---

## 6. 依赖分析

### 6.1 外部依赖

| 包名 | 用途 |
|------|------|
| `httpx ≥ 0.25.0` | 异步 HTTP 客户端，用于调用 LLM API |
| `python-dotenv ≥ 1.0.0` | 加载 `.env` 环境变量文件 |

### 6.2 模块依赖关系

```
__main__.py
  ├── config.py      → dotenv, os
  ├── llm.py         → httpx, json
  ├── tools.py       → asyncio
  ├── context.py     → datetime
  ├── session.py     → json, pathlib, datetime
  ├── runner.py      → llm.py, tools.py, types.py
  └── types.py       → dataclasses
```

---

## 7. 扩展指南

### 7.1 添加新工具

继承 `Tool` 基类并注册即可：

```python
from nanobot_mini import Tool, ToolRegistry

class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web for information"
    
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["query"],
    }
    
    async def execute(self, query: str, **_) -> str:
        # 实现搜索逻辑
        return f"Search results for: {query}"

# 注册
registry.register(WebSearchTool())
```

### 7.2 对接本地模型

在 `.env` 中配置：

```bash
BASE_URL=http://127.0.0.1:8000/v1
LLM=qwen2.5-72b
API_KEY=
```

---

## 8. 优缺点分析

### ✅ 优点

- **轻量简洁**：核心代码不足 300 行，易于理解和修改
- **架构清晰**：模块职责分明，遵循单一职责原则
- **高度可扩展**：工具系统采用抽象基类，扩展新工具非常简单
- **异步设计**：基于 asyncio，性能良好
- **配置灵活**：支持多种 LLM 后端，可对接本地模型

### ⚠️ 待改进

- **仅支持一个工具**：目前只内置了 `exec` 工具，缺少文件操作、网络请求等常用工具
- **无对话摘要**：历史记录过长时可能导致 token 超限
- **缺少错误恢复**：工具执行失败时仅返回错误信息，无重试机制
- **无流式输出**：交互模式下未使用 `chat_stream`，响应体验可以优化
- **安全性**：`exec` 工具可执行任意命令，生产环境需要沙箱限制

---

## 9. 总结

nanobot-mini 是一个优秀的 AI Agent 学习项目，它用最精简的代码实现了一个完整的 Agent 框架核心：

1. **LLM 集成** → 通过 OpenAI API 与大模型对话
2. **工具调用** → 通过 Function Calling 让 LLM 使用工具
3. **循环控制** → Agent 循环直到任务完成
4. **会话管理** → 支持多轮对话上下文

这个项目非常适合作为学习 AI Agent 开发的入门参考，也可以作为构建更复杂 Agent 系统的基础框架。

---

*文档生成完毕 ✨*
