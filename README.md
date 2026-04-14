# nanobot-mini

> 🤖 轻量级 AI Agent 框架 — 从零构建自己的 AI 助手

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/YS-BW/nanobot-mini)](https://github.com/YS-BW/nanobot-mini/stargazers)

一个精简的 AI Agent 实现，支持 LLM 对话和工具调用，代码仅 ~500 行。

## ✨ 特性

- 🔄 **Agent 循环**：LLM ↔ 工具调用的智能循环
- 🛠️ **工具系统**：可扩展的工具注册机制
- 💬 **会话管理**：支持多会话上下文
- ⚙️ **灵活配置**：支持 .env 文件和环境变量
- 🚀 **本地模型**：轻松对接 Ollama、vLLM 等本地部署

## 📦 安装

```bash
git clone https://github.com/YS-BW/nanobot-mini.git
cd nanobot-mini
pip install -e .
```

## 🚀 快速开始

### 使用 OpenAI

```bash
export API_KEY="sk-your-key-here"
export LLM="gpt-4o"

python -m nanobot_mini "你好"
python -m nanobot_mini "帮我执行: ls -la /tmp"
python -m nanobot_mini "帮我找一下 /tmp 下的所有 .txt 文件"
```

### 使用本地模型

创建 `.env` 文件：
```bash
BASE_URL=http://127.0.0.1:8000/v1
LLM=gemma-4-e4b-it-4bit
API_KEY=
```

然后运行：
```bash
python -m nanobot_mini "你好"
```

## ⚙️ 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `BASE_URL` | `https://api.openai.com/v1` | LLM API 地址 |
| `LLM` | `gpt-4o` | 使用的模型名称 |
| `API_KEY` | `""` | API 密钥（本地部署可留空） |
| `WORKSPACE` | `/tmp/nanobot-mini` | 工作目录 |
| `MAX_ITERATIONS` | `20` | 最大工具调用次数 |

## 🏗️ 项目结构

```
nanobot_mini/
├── __main__.py      # 🚀 CLI 入口（508 行）
├── runner.py        # ⭐ 核心 Agent 循环
├── llm.py          # 📡 OpenAI API 调用
├── tools.py        # 🔧 工具注册表 + ExecTool
├── context.py       # 💬 Prompt 构建
├── session.py       # 📂 会话管理
├── config.py        # ⚙️ 配置管理
└── types.py        # 📋 数据类型定义
```

## 🔄 核心流程

```
用户输入
    ↓
build_messages() 构建消息列表
    ↓
┌─────────────────────────┐
│    AgentRunner.run()    │
│         ↓               │
│    LLM.chat()          │
│         ↓               │
│    工具调用 ←→ 执行      │
│         ↓               │
│    继续循环或返回        │
└─────────────────────────┘
    ↓
返回结果 + 保存会话
```

## 🔌 扩展工具

继承 `Tool` 基类创建自定义工具：

```python
from nanobot_mini import Tool, ToolRegistry

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

    async def execute(self, query: str, **_) -> str:
        return f"处理结果: {query}"

# 注册工具
registry = ToolRegistry()
registry.register(MyTool())
```

## 📊 技术栈

- **语言**: Python 3.11+
- **HTTP**: httpx (异步)
- **配置**: python-dotenv
- **架构**: Agent 循环模式

## 📈 代码统计

| 模块 | 行数 | 职责 |
|------|------|------|
| `tools.py` | 102 | 工具系统 + ExecTool |
| `__main__.py` | 88 | CLI 入口 |
| `llm.py` | 93 | LLM 调用封装 |
| `runner.py` | 58 | Agent 循环 |
| **总计** | **508** | **完整 Agent 框架** |

## 🎯 适用场景

- ✅ 学习 AI Agent 原理
- ✅ 快速原型开发
- ✅ 本地模型测试
- ✅ 简单任务自动化

## 📄 许可证

[MIT License](LICENSE) © 2026 YS-BW

---

⭐ 如果觉得有用，请给个 Star！
