# nanobot-mini → nanobot 进化清单

> 从 nanobot-mini 接近 nanobot 的完整路线图

---

## 优先级 1：体验增强（收益高，改动小）

### 1.1 [ ] 流式输出
- **描述**: LLM 返回时逐步显示，打字机效果
- **修改文件**: `llm.py`, `runner.py`
- **参考 nanobot**: `runner.py` 中的 `on_content_delta` 回调
- **实现思路**:
  1. `llm.py` 实现 `chat_stream()` 返回 AsyncIterator[str]
  2. `runner.py` 支持 `stream_callback` 参数
  3. `__main__.py` 打印时逐块输出

### 1.2 [ ] 多会话支持
- **描述**: 支持多个独立的 conversation
- **修改文件**: `__main__.py`, `session.py`
- **参考 nanobot**: `session/manager.py`
- **实现思路**:
  1. 根据 session_key 区分不同会话
  2. 支持 `/new` 命令新建会话
  3. 支持 `/sessions` 列出所有会话

---

## 优先级 2：记忆与上下文（核心功能）

### 2.1 [ ] Token 预算与历史截断
- **描述**: 避免上下文超限，自动截断旧消息
- **修改文件**: `runner.py`, `session.py`
- **参考 nanobot**: `runner.py` 中 `_snip_history()` 方法
- **实现思路**:
  1. 用 tiktoken 或简单字符估算 token 数
  2. 超过预算时，从后往前截断消息
  3. 保留 system prompt 和最近 N 条

### 2.2 [ ] 记忆固化（Consolidator 简化版）
- **描述**: 把旧消息总结后存到文件
- **修改文件**: `runner.py`, `session.py`
- **参考 nanobot**: `agent/memory.py` 中 Consolidator
- **实现思路**:
  1. 当历史超长时，调用 LLM 总结
  2. 保存到 `history.jsonl`
  3. 清空 session.messages 中的旧消息

### 2.3 [ ] 长期记忆（SOUL/MEMORY）
- **描述**: 支持 SOUL.md / MEMORY.md 长期记忆
- **修改文件**: `context.py`, `runner.py`
- **参考 nanobot**: `agent/context.py` 中 `build_system_prompt()` 加载 SOUL/MEMORY
- **实现思路**:
  1. `context.py` 加载 `~/.nanobot/workspace/SOUL.md`
  2. 拼到 system prompt 开头
  3. 支持更新 MEMORY.md

---

## 优先级 3：工具系统（可复用 nanobot 代码）

### 3.1 [ ] read_file / write_file 工具
- **描述**: 专门的读写文件工具，更安全
- **新增文件**: `tools/filesystem.py`
- **参考 nanobot**: `agent/tools/filesystem.py`
- **功能**:
  - `read_file(path, offset, limit)` — 读取文件指定行
  - `write_file(path, content)` — 写入文件
  - 内容太长时截断

### 3.2 [ ] grep / glob 工具
- **描述**: 专门的文件搜索工具
- **新增文件**: `tools/search.py`
- **参考 nanobot**: `agent/tools/search.py`
- **功能**:
  - `grep(path, pattern, output_mode)` — 搜索文件内容
  - `glob(pattern, path)` — 按模式匹配文件

### 3.3 [ ] web_search / web_fetch 工具
- **描述**: 让 Agent 能上网搜索
- **新增文件**: `tools/web.py`
- **参考 nanobot**: `agent/tools/web.py`
- **功能**:
  - `web_search(query)` — 搜索网页
  - `web_fetch(url)` — 获取网页内容

### 3.4 [ ] message 工具
- **描述**: 发送消息给用户
- **新增文件**: `tools/message.py`
- **参考 nanobot**: `agent/tools/message.py`
- **功能**: Agent 调用后消息会发到终端

---

## 优先级 4：命令系统

### 4.1 [ ] /new 命令
- **描述**: 开始新会话
- **修改文件**: `__main__.py`
- **参考 nanobot**: `command/builtin.py`

### 4.2 [ ] /exit /quit 命令
- **描述**: 退出程序
- **修改文件**: `__main__.py`

### 4.3 [ ] /status 命令
- **描述**: 显示当前会话状态
- **修改文件**: `__main__.py`

### 4.4 [ ] /help 命令
- **描述**: 显示帮助信息
- **修改文件**: `__main__.py`

---

## 优先级 5：Checkpoint 与恢复

### 5.1 [ ] 运行中 Checkpoint 保存
- **描述**: 工具执行时定期保存状态
- **修改文件**: `runner.py`
- **参考 nanobot**: `runner.py` 中 `checkpoint_callback`

### 5.2 [ ] 中断后恢复
- **描述**: 重启时恢复未完成的操作
- **修改文件**: `runner.py`, `session.py`
- **参考 nanobot**: `agent/loop.py` 中 `_restore_runtime_checkpoint()`

---

## 优先级 6：多渠道接入（生产级功能）

### 6.1 [ ] HTTP API Server
- **描述**: 暴露 OpenAI 兼容 API
- **新增文件**: `api.py`
- **参考 nanobot**: `api/server.py`
- **端点**:
  - `POST /v1/chat/completions` — 对话
  - `GET /health` — 健康检查
  - `GET /v1/models` — 模型列表

### 6.2 [ ] WeChat 渠道（可选）
- **描述**: 接入微信
- **新增文件**: `channels/weixin.py`
- **参考 nanobot**: `channels/weixin.py`
- **说明**: 需要微信 API 权限

### 6.3 [ ] Telegram 渠道（可选）
- **描述**: 接入 Telegram
- **新增文件**: `channels/telegram.py`
- **参考 nanobot**: `channels/telegram.py`

---

## 优先级 7：安全与生产

### 7.1 [ ] SSRF 防护
- **描述**: 防止 Agent 访问内网
- **修改文件**: `tools/web.py`
- **参考 nanobot**: `security/network.py`

### 7.2 [ ] 沙箱隔离（bwrap）
- **描述**: 限制 exec 只能访问 workspace
- **修改文件**: `tools.py`
- **参考 nanobot**: `agent/tools/sandbox.py`

### 7.3 [ ] 危险命令拦截
- **描述**: 防止 `rm -rf /` 等破坏性命令
- **修改文件**: `tools.py`
- **参考 nanobot**: `agent/tools/shell.py` 中 `deny_patterns`

---

## 优先级 8：Skill 系统（进阶）

### 8.1 [ ] Skill 加载器
- **描述**: 加载 Markdown 格式的技能
- **新增文件**: `skills.py`
- **参考 nanobot**: `agent/skills.py`

### 8.2 [ ] Skill 注册机制
- **描述**: LLM 能选择激活特定技能
- **修改文件**: `context.py`

---

## 实现顺序建议

```
第一阶段（1-2天）: 体验增强
  1.1 流式输出
  1.2 多会话支持

第二阶段（2-3天）: 记忆系统
  2.1 Token 预算截断
  2.2 记忆固化
  2.3 长期记忆

第三阶段（3-4天）: 工具完善
  3.1 read_file / write_file
  3.2 grep / glob
  3.3 web_search / web_fetch

第四阶段（2-3天）: 命令 + Checkpoint
  4.1 基础命令
  5.1-5.2 Checkpoint

第五阶段（长期）: 渠道 + 安全
  6.1 HTTP API
  7.1-7.3 安全增强
```

---

## 各文件最终目标结构

```
nanobot_mini/
├── __main__.py      # CLI 入口 + 命令解析
├── runner.py        # Agent 循环 + Checkpoint
├── llm.py          # LLM 调用 + 流式
├── tools.py        # 工具注册表
├── tools/
│   ├── __init__.py
│   ├── exec.py     # Shell 执行
│   ├── filesystem.py # 文件读写
│   ├── search.py    # grep / glob
│   ├── web.py      # web_search / fetch
│   └── message.py  # 发送消息
├── context.py       # Prompt 构建 + SOUL/MEMORY
├── session.py       # 会话管理 + 历史截断
├── config.py        # 配置
├── types.py        # 数据类型
├── skills.py       # Skill 加载
├── api.py          # HTTP API（可选）
├── channels/       # 渠道（可选）
│   ├── __init__.py
│   └── weixin.py
└── security/      # 安全（可选）
    └── network.py
```

---

## 复用 nanobot 代码的方法

```bash
# 把 nanobot 的工具直接复制过来改造
cp ../nanobot/nanobot/agent/tools/filesystem.py nanobot_mini/tools/filesystem.py
cp ../nanobot/nanobot/agent/tools/search.py nanobot_mini/tools/search.py
cp ../nanobot/nanobot/agent/tools/web.py nanobot_mini/tools/web.py
```

复制后：
1. 删掉 nanobot 特有的依赖（如 `from nanobot.utils.helpers`）
2. 简化参数验证
3. 去掉 channel 相关的逻辑
4. 保留核心执行逻辑
