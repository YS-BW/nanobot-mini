# infra 模块设计

## 模块定位

`infra` 提供配置、路径、调试日志和 runtime 状态存储这些基础设施能力。
它不负责编排业务，但决定了项目如何读取配置、如何查找文件以及如何落盘运行时状态。

## 目录结构

- `config.py`：运行配置加载
- `paths.py`：默认路径与仓库路径约定
- `logging.py`：调试消息快照
- `runtime_state_store.py`：运行时状态文件仓库

## 配置系统

### `Config`

`Config` 是默认配置入口。

当前负责：

- 读取 `.env`
- 读取 `models.toml`
- 构建 `ProviderRegistry`
- 构建 `ModelRegistry`
- 解析默认模型
- 解析运行参数与全局目录

### 当前配置规则

- `models.toml` 是必需的
- `.env` 不是模型注册入口，只提供密钥和运行参数
- 真正的环境变量优先级高于 `.env`
- 缺少 `models.toml` 会直接报错
- 默认模型如果不可用，会直接报错，不再静默回退

### `ConfigError`

当配置不合法时，`config.py` 会抛出 `ConfigError`。

典型场景：

- 缺少 `models.toml`
- `models.toml` 缺少 `[models]`
- provider 名称不在白名单里
- 默认模型不存在
- 默认模型声明了但因为缺少密钥而不可用

### 初始化结果

当前 `Config` 初始化后会提供：

- `workspace`
- `global_dir`
- `sessions_dir`
- `runtime_state_dir`
- `max_iterations`
- `context_window`
- `compact_threshold_round1`
- `compact_threshold_round2`
- `provider_registry`
- `model_registry`
- `model_alias`
- `base_url`
- `model`
- `api_key`

## 路径约定

`paths.py` 提供：

- `project_root()`
- `default_global_dir()`
- `find_env_file()`
- `find_models_file()`

默认全局目录仍为：`~/.bananabot`

## 调试日志

### `write_debug_messages()`

会把一次真实发送给模型的消息写到当前 thread 目录下的 `debug.json`。

这个文件主要用来排查：

- 系统提示词顺序错误
- memory 注入顺序错误
- compact 摘要污染上下文
- 历史消息脏数据残留

## 运行时状态存储

### `FileRuntimeStateStore`

`runtime_state_store.py` 提供最小文件仓库，实现：

- `save_thread()`
- `save_task_run()`
- `save_turn()`
- `save_step()`
- `append_event()`
- `load_thread()`
- `load_task_run()`
- `load_turn()`
- `load_step()`
- `load_events()`
- `load_runtime_snapshot()`

### 目录结构

```text
runtime-state/
├── threads/<thread_id>.json
├── task_runs/<task_run_id>.json
├── turns/<turn_id>.json
├── steps/<step_id>.json
└── event_log.jsonl
```

## 当前边界

已完成：

- `models.toml + .env` 配置链已经固定
- 配置错误会显式报错
- 路径约定已经固定
- runtime 状态仓库已经可用并有测试覆盖

当前限制：

- runtime state 仍是文件实现，不是数据库实现
- 还没有并发锁和更强的持久化一致性策略
- 调试日志还不是完整 tracing，只是消息快照
