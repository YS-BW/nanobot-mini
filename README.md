# 🍌 BananaBot

> 可配置的 AI Agent 框架，支持长对话上下文管理

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

一个模块化的 AI Agent 实现，支持工具调用、会话管理和智能上下文压缩。

## ✨ 特性

- 🔄 **Agent 循环**：LLM ↔ 工具调用的智能循环
- 🛠️ **工具系统**：可扩展的注册机制（内置 exec 工具）
- 💬 **会话管理**：多会话支持，JSONL 持久化
- 🧠 **上下文压缩**：自动 compact，长对话无忧
- ⚙️ **灵活配置**：.env 文件 + 环境变量
- 🎨 **友好交互**：Rich 终端输出，滚动进度框
- 🤖 **兼容性强**：支持 OpenAI 兼容 API（Ollama、vLLM、阿里、Claude 等）

## 🏗️ 核心架构

```
┌─────────────────────────────────────────────────────────┐
│                      Agent Runner                       │
│  ┌─────────┐    ┌─────────┐    ┌─────────────────┐    │
│  │   LLM   │◄──►│ Registry│◄──►│ Tool Execution  │    │
│  └─────────┘    └─────────┘    └─────────────────┘    │
│       ▲                                               │
│       │ messages                                       │
│  ┌────┴─────┐    ┌──────────────┐                   │
│  │ Context   │───►│   Session    │                   │
│  │ Builder   │    │ (compact)    │                   │
│  └───────────┘    └──────────────┘                   │
└─────────────────────────────────────────────────────────┘
```

**关键模块**：
- `runner.py` — Agent 循环核心，LLM ↔ 工具调用
- `context.py` — 上下文构建，system prompt + session 拼接
- `session.py` — 会话管理，自动 compact 机制
- `tools/` — 可扩展工具注册系统

## 📦 安装

```bash
git clone <your-repo-url>
cd nanobot-mini
uv sync
```

## 🚀 快速开始

### 配置

创建 `.env` 文件：

```bash
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
API_KEY=your-api-key
LLM=qwen-plus
```

### 运行

```bash
# 单次对话
uv run nanobot-mini "帮我执行 ls -la"

# 交互模式
uv run nanobot-mini
```

## ⚙️ 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `BASE_URL` | `https://api.openai.com/v1` | LLM API 地址 |
| `LLM` | `gpt-4o` | 模型名称 |
| `API_KEY` | `""` | API 密钥 |
| `CONTEXT_WINDOW` | `128000` | 上下文窗口大小 |
| `COMPACT_THRESHOLD_ROUND1` | `0.70` | 第一轮 compact 阈值 |
| `MAX_ITERATIONS` | `20` | 最大工具调用次数 |

## 🧠 上下文管理

BananaBot 采用**分层记忆**策略：

```
session.jsonl    ← 当前会话（可被 compact 裁切）
history.jsonl    ← 完整存档（append-only）
summary.jsonl    ← 第一轮 compact 摘要（累积）
MEMORY.md        ← 第二轮 compact 长期记忆
```

**Compact 流程**：
1. session 超过阈值 → 裁切到 history，生成 1 条 summary
2. 累积 25 条 summary → 整合到 MEMORY.md
3. memory 替代 summary 注入上下文

## 🔌 扩展工具

继承 `Tool` 基类创建自定义工具：

```python
from nanobot_mini.tools import Tool

class MyTool(Tool):
    name = "my_tool"
    description = "我的自定义工具"

    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "查询内容"},
        },
        "required": ["query"],
    }

    async def execute(self, query: str, **kwargs) -> str:
        return f"处理结果: {query}"
```

## 📊 技术栈

- **语言**: Python 3.11+
- **HTTP**: httpx (异步)
- **终端**: Rich
- **配置**: python-dotenv
- **架构**: Agent 循环模式

## 📄 许可证

[MIT License](LICENSE)
