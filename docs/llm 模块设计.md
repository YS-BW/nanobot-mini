# llm 模块设计

## 模块定位

`llm` 负责模型接入层，目标是把不同 provider 的 HTTP 调用收敛成统一内部结构。
当前这一层已经完成 provider 收敛，原则很明确：

- 只支持白名单 provider
- 只通过 `models.toml` 声明模型档案
- `.env` 只负责密钥和运行参数
- 所有请求都统一走 `LLMClient`

## 目录结构

- `registry.py`：provider 固定规则、模型能力、模型档案、注册表
- `factory.py`：backend 工厂
- `client.py`：统一调用入口
- `types.py`：统一响应与流式 chunk 结构
- `errors.py`：LLM 层异常
- `smoke.py`：真实 provider smoke 测试工具
- `providers/`
  - `base.py`：provider 协议
  - `openai_compat.py`：OpenAI-compatible backend
  - `dashscope.py`：DashScope backend

## provider 白名单

当前只支持 5 个 provider：

- `dashscope`
- `deepseek`
- `minimax`
- `mimo`
- `local`

不再保留 `legacy` provider，也不再从旧的单模型环境变量回退构造模型。

## 主要对象

当前 `llm` 不再把静态数据拆成 `profiles.py`、`specs.py`、`registry.py` 三层。
这些最基础的数据定义已经全部收回 `registry.py`。

### `ProviderSpec`

表示某个 provider 的固定规则，字段包括：

- `name`
- `backend`
- `api_key_env`
- `default_base_url`
- `chat_path`
- `supports_tools`
- `supports_stream`
- `supports_reasoning`
- `requires_api_key`
- `extra_headers`
- `default_query_params`
- `default_extra_body`

这一层的作用是把“provider 的公共默认行为”从 `models.toml` 中拿出来，避免每个模型条目重复写一遍。

当前内置规则里：

- `dashscope` 走独立 backend
- `deepseek / minimax / mimo / local` 走 `openai_compat`
- `minimax` 默认注入 `reasoning_split = true`
- `local` 默认 `supports_tools = false` 且 `requires_api_key = false`

### `ModelCapabilities`

表示模型能力：

- `supports_stream`
- `supports_tools`
- `supports_reasoning`

runtime 和 TUI 都靠这个结构决定是否启用流式、工具和 reasoning 展示。

### `ModelProfile`

表示单个模型的完整调用档案：

- `alias`
- `provider`
- `model`
- `base_url`
- `api_key`
- `api_key_env`
- `backend`
- `chat_path`
- `headers`
- `query_params`
- `extra_body`
- `capabilities`
- `description`

provider 默认值和模型覆盖值都会收敛到这里。

## 注册表设计

### `ProviderRegistry`

只负责管理 provider 规格，不负责创建 backend。

主要能力：

- `register()`
- `get()`
- `has()`
- `list_specs()`
- `list_names()`

### `ModelRegistry`

只负责管理模型 alias。

主要能力：

- `register()`
- `list_profiles()`
- `get(alias_or_model)`
- `has()`
- `with_default()`

当前会拒绝重复 alias，避免模型切换时出现歧义。

## `LLMClient`

`LLMClient` 是统一调用入口。

初始化现在必须显式传入：

- `model_registry`
- 可选 `provider_factory`
- 可选 `default_model`
- 可选 `timeout_seconds`
- 可选 `max_retries`

不再支持直接通过 `BASE_URL / API_KEY / model` 临时构造单模型客户端。

### `chat()`

执行非流式请求：

1. 从 `ModelRegistry` 解析模型档案
2. 从 `ProviderFactory` 取得 backend
3. 生成 headers 和 payload
4. `POST {base_url}{chat_path}`
5. 解析成 `LLMResponse`

### `chat_stream()`

执行流式请求：

1. 解析模型档案
2. 生成请求
3. 用 SSE 流式读取
4. 解析成 `LLMStreamChunk`

### 重试规则

当前会对这些错误做有限重试：

- `408 / 409 / 429 / 500 / 502 / 503 / 504 / 529`
- `httpx.ConnectError`
- `httpx.ReadTimeout`
- `httpx.WriteTimeout`
- `httpx.RemoteProtocolError`

## backend 设计

### `OpenAICompatProvider`

负责当前大多数 provider：

- 构造 OpenAI-compatible `/chat/completions` 请求
- 统一普通响应解析
- 统一流式 chunk 解析
- 处理 reasoning 字段
- 处理工具调用增量聚合输入
- 处理 `<think>...</think>` 内容抽取

### `DashScopeProvider`

继承 `OpenAICompatProvider`，额外处理 DashScope 的 thinking 参数封装。

当前支持把这些字段收进 `parameters`：

- `enable_thinking`
- `preserve_thinking`
- `thinking_budget`

## 配置入口

### `models.toml`

这是当前唯一的模型注册入口。

负责声明：

- `alias`
- `provider`
- `model`
- `base_url`
- `api_key_env`
- `description`
- `reasoning`
- `supports_tools`
- `supports_stream`
- `extra_body`
- `headers`
- `query_params`

### `.env`

`.env` 现在只负责：

- provider API key
- `DEFAULT_MODEL`
- `CONTEXT_WINDOW`
- `MAX_ITERATIONS`
- compact 阈值

不再作为模型注册入口。

## smoke 验证

`smoke.py` 提供真实 provider 验证工具：

```bash
uv run python -m bananabot.llm.smoke
```

也可以只测某个模型：

```bash
uv run python -m bananabot.llm.smoke --alias qwen3.6-plus
```

默认行为：

- 优先走流式请求
- 发送最小提示词
- 输出每个 alias 的 provider、finish_reason、reasoning 长度和回复预览

## 当前边界

已完成：

- provider 白名单固定
- 配置入口收敛到 `models.toml + .env`
- provider 默认能力和模型覆盖能力已经分层
- 真实 smoke 工具已经进入代码库

当前限制：

- 只覆盖 `/chat/completions` 风格接口
- 还没有更复杂的多模态输入能力
- 还没有 provider 级自动化联调测试，只保留单元测试和手动 smoke
