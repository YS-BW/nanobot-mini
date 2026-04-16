# BananaBot 进化清单

> 从 nanobot-mini 接近 nanobot 的完整路线图

---

## 优先级 1：体验增强

### 1.1 [x] 流式输出
- **描述**: LLM 返回时逐步显示，打字机效果
- **修改文件**: `llm.py`, `runner.py`
- **状态**: 基础实现已完成（非真正 API 流式）

### 1.2 [x] 多会话支持
- **描述**: 支持多个独立的 conversation
- **修改文件**: `__main__.py`, `session.py`
- **状态**: ✅ `/new`, `/sessions`, `/session <name>` 已实现

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

### 2.2 [x] 会话压缩（compact）
- **描述**: 第一轮 compact，session → history.jsonl + summary.jsonl
- **修改文件**: `session.py`, `context.py`, `__main__.py`, `config.py`
- **状态**: ✅ 已实现
  - Session 目录结构：`~/.bananabot/sessions/<session_id>/`
  - `/compact` 命令：第一轮 compact
  - `session.compact()`：裁剪消息
  - `session.append_history()`：追加到 history.jsonl
  - `session.append_summary()`：追加到 summary.jsonl
  - Context 加载 summary.jsonl 和 session.jsonl
  - `/status` 显示会话统计

### 2.3 [x] 长期记忆（MEMORY/BANANA）
- **描述**: 支持 MEMORY.md 长期记忆和 BANANA.md 指令
- **修改文件**: `memory.py`, `context.py`, `__main__.py`
- **状态**: ✅ 已实现
  - `MemoryStore` 类：项目隔离记忆存储
  - `BANANA.md` 支持：全局 + 项目级
  - `/banana` 命令：查看全局/项目指令

### 2.4 [ ] 第二轮 compact（summary → MEMORY.md）
- **描述**: summary.jsonl 超过阈值时，二次 compact 生成 MEMORY.md
- **修改文件**: `session.py`, `context.py`
- **实现思路**:
  1. 检测 summary.jsonl 累积超过 `context_window * 0.85`
  2. 调用 LLM 整合 summary → MEMORY.md
  3. 清空 summary.jsonl
  4. 触发时机：summary 过长 或 手动 `/compact`

### 2.5 [ ] 自动 compact 触发
- **描述**: 超过阈值时自动触发第一轮 compact
- **修改文件**: `runner.py`, `session.py`
- **实现思路**:
  1. 在 `chat_once` 或 `runner.run()` 前检测 token
  2. 超过 `context_window * 0.70` 自动触发 compact
  3. 保留手动 `/compact` 命令

---

## 优先级 3：工具系统

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

### 4.1 [x] /new 命令
- **状态**: ✅ 已实现

### 4.2 [x] /exit /quit 命令
- **状态**: ✅ 已实现

### 4.3 [x] /status 命令
- **状态**: ✅ 已实现

### 4.4 [x] /help 命令
- **状态**: ✅ 已实现

### 4.5 [x] /session <name> 命令
- **描述**: 切换到指定会话
- **状态**: ✅ 已实现

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

## 优先级 6：安全与生产

### 6.1 [ ] 危险命令拦截
- **描述**: 防止 `rm -rf /` 等破坏性命令
- **修改文件**: `tools/exec.py`
- **参考 nanobot**: `agent/tools/shell.py` 中 `deny_patterns`
- **功能**:
  - 拦截 `rm -rf`, `format`, `dd`, `shutdown` 等危险命令
  - 可配置白名单

### 6.2 [ ] SSRF 防护
- **描述**: 防止 Agent 访问内网
- **修改文件**: `tools/web.py`
- **参考 nanobot**: `security/network.py`

### 6.3 [ ] 沙箱隔离（bwrap）
- **描述**: 限制 exec 只能访问 workspace
- **修改文件**: `tools/exec.py`
- **参考 nanobot**: `agent/tools/sandbox.py`

---

## 优先级 7：HTTP API

### 7.1 [ ] HTTP API Server
- **描述**: 暴露 OpenAI 兼容 API
- **新增文件**: `api.py`
- **参考 nanobot**: `api/server.py`
- **端点**:
  - `POST /v1/chat/completions` — 对话
  - `GET /health` — 健康检查
  - `GET /v1/models` — 模型列表

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

## 优先级 9：多渠道接入（可选项，放最后）

### 9.1 [ ] WeChat 渠道
- **描述**: 接入微信
- **新增文件**: `channels/weixin.py`
- **参考 nanobot**: `channels/weixin.py`
- **说明**: 需要微信 API 权限

### 9.2 [ ] Telegram 渠道
- **描述**: 接入 Telegram
- **新增文件**: `channels/telegram.py`
- **参考 nanobot**: `channels/telegram.py`

---

## 实现顺序建议

```
第一阶段（进行中）: 体验增强
  ✅ 1.1 流式输出
  ✅ 1.2 多会话支持

第二阶段（下一步）: 记忆系统
  2.1 Token 预算截断
  2.2 记忆固化
  2.3 长期记忆

第三阶段: 工具完善
  3.1 read_file / write_file
  3.2 grep / glob
  3.3 web_search / web_fetch

第四阶段: 命令 + Checkpoint
  5.1-5.2 Checkpoint

第五阶段: 安全
  6.1 危险命令拦截
  6.2 SSRF 防护
  6.3 沙箱隔离

第六阶段: HTTP API + Skill
  7.1 HTTP API
  8.1-8.2 Skill 系统

最后: 渠道（可选项）
  9.1-9.2 WeChat / Telegram
```

---

## 各文件最终目标结构

```
nanobot_mini/
├── __main__.py          # CLI 入口 + 命令解析
├── runner.py            # Agent 循环 + Checkpoint
├── llm.py               # LLM 调用 + 流式
├── context.py           # Prompt 构建 + SOUL/MEMORY
├── session.py           # 会话管理 + 历史截断
├── config.py           # 配置
├── types.py            # 数据类型
├── tools/              # 工具系统
│   ├── __init__.py
│   ├── base.py        # Tool 基类
│   ├── exec.py        # Shell 执行
│   ├── filesystem.py  # 文件读写
│   ├── search.py       # grep / glob
│   ├── web.py         # web_search / fetch
│   └── message.py     # 发送消息
├── skills.py           # Skill 加载
├── api.py              # HTTP API
└── channels/          # 渠道（可选）
    ├── __init__.py
    ├── weixin.py
    └── telegram.py
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
