# nanobot-mini TODO

> 当前只保留有效执行清单，不再保留旧路线图和历史优先级列表。

## 阶段 1：结构重构

目标：

- 彻底重构项目结构
- 固定核心模块边界
- 固定统一服务接口和统一数据结构
- 不新增当前项目未实现的业务能力

### P0

- [x] `tools`
  - 清理 `nanobot_mini/tools.py` 与 `nanobot_mini/tools/` 冲突
  - 固定 `tools/` 为唯一工具入口

- [x] `app`
  - 把 CLI、命令解析、交互渲染、依赖组装从 `__main__.py` 拆到 `app/`
  - 保留薄 `__main__.py`

- [x] `runtime`
  - 把 `runner`、`context`、`prompts`、运行时事件收敛到 `runtime/`
  - 拆开 prompt 与上下文装配

- [x] `llm`
  - 拆开请求发送、响应解析、错误语义

- [x] `memory`
  - 把 `session/store.py`、`session/compact.py`、`memory.py` 收敛到统一 `memory/`
  - 固定 `session_store / compact_service / memory_store / policy`

- [x] `app/service`
  - 固定统一应用服务接口
  - 固定统一请求/响应/事件结构

### P1

- [x] `infra`
  - 把配置、日志、路径规则下沉到 `infra/`

- [x] 文档同步
  - 结构落地后同步 `README.md`
  - 保持 `AGENTS.md`、`TODO.md`、设计文档与代码一致

### 阶段 1 完成定义

- [x] 目录结构稳定
- [x] 模块边界稳定
- [x] 当前已有能力全部迁移完成
- [x] 不再保留历史结构冲突
- [x] 为第二阶段预留统一接口和统一数据结构

## 阶段 2：模块扩展与优化

目标：

- 在第一阶段确定的骨架上扩展能力
- 不再推倒整体结构

### P0

- [ ] `tools`
  - 增加 `filesystem`
  - 增加 `search`
  - 增加 `web`
  - 增加权限、审计、安全控制

- [ ] `memory`
  - 升级 token 预算
  - 升级 compact 策略
  - 引入结构化 working memory
  - 统一项目级与会话级记忆来源

- [ ] `app/service`
  - 完善统一事件流
  - 支撑 CLI、桌面端、Web 端共用运行时

### P1

- [ ] `llm`
  - provider 适配
  - retry / timeout / stream 完善

- [ ] `runtime`
  - 优化 runner 状态流
  - 优化上下文注入与裁剪策略

- [ ] `clients`
  - Web 端接入
  - 桌面端接入
  - API 层接入

### P2

- [ ] `security`
  - 命令拦截
  - 沙箱策略
  - 行为审计

- [ ] `recovery`
  - checkpoint
  - 运行恢复

- [ ] `tests`
  - 建立结构重构后的回归体系

## 模块优先级

阶段 1：

1. `tools`
2. `app`
3. `runtime`
4. `llm`
5. `memory`
6. `infra`

阶段 2：

1. `tools`
2. `memory`
3. `app/service`
4. `llm`
5. `runtime`
6. `clients`
7. `security`
8. `recovery`
9. `tests`
