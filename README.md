# nanobot-mini

> 🤖 轻量级 AI Agent 框架

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![MIT License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

一个精简的 AI Agent 实现，支持 LLM 对话和工具调用，基于 nanobot 思想构建。

## ✨ 特性

- 🔄 **Agent 循环**：LLM ↔ 工具调用的智能循环
- 🛠️ **工具系统**：可扩展的工具注册机制（内置 exec 工具）
- 💬 **会话管理**：多会话支持，JSONL 持久化
- ⚙️ **灵活配置**：.env 文件 + 环境变量
- 🎨 **友好交互**：Rich 终端输出，思考动画
- 🤖 **兼容性强**：支持 OpenAI 兼容 API（Ollama、vLLM、Mimo 等）

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
BASE_URL=https://api.xiaomimimo.com/v1
API_KEY=your-api-key
LLM=mimo-v2-pro
```

### 运行

```bash
# 单次对话
uv run nanobot-mini "你好"

# 交互模式
uv run nanobot-mini
```

## ⚙️ 配置

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `BASE_URL` | `https://api.openai.com/v1` | LLM API 地址 |
| `LLM` | `gpt-4o` | 模型名称 |
| `API_KEY` | `""` | API 密钥 |
| `MAX_ITERATIONS` | `20` | 最大工具调用次数 |

> 工作目录默认为 `~/.nanobot/workspace`，无需配置

## 🏗️ 项目结构

```
nanobot_mini/
├── __init__.py          # 包入口
├── __main__.py          # CLI 入口
├── config.py            # 配置管理
├── context.py           # 系统提示词构建
├── llm.py               # LLM 调用封装
├── runner.py            # Agent 循环
├── session.py           # 会话管理
├── types.py             # 数据类型
├── tools/               # 工具系统
│   ├── __init__.py
│   ├── base.py          # Tool 基类
│   ├── exec.py          # exec 工具
│   └── registry.py      # 工具注册表
```

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
