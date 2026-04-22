# bananabot TODO

> 这份文件只保留当前有效执行清单。以后项目推进以这份 TODO 为准，不再口头扩阶段、不再把新需求塞回阶段 1。

## 执行规则

1. 一次只推进一个阶段。
2. 阶段 1 已冻结，不再继续扩写新内容。
3. 每个任务的完成必须同时满足：代码、文档、测试三项同步。
4. 新需求默认进入阶段 2 或阶段 3，除非它是阶段 1 的明确 bug 修复。
5. 不允许为了补一个功能，再次推倒整体结构。

---

## 阶段 1：结构重构

状态：`已完成并冻结`

目标：

- 固定项目目录结构
- 固定核心模块边界
- 固定统一服务接口
- 固定统一运行时数据结构
- 不在这一阶段扩展新业务能力

已完成内容：

- [x] `app/`
  - 统一应用入口、服务编排、TUI
  - 固定 `TaskRequest / TaskResponse / AgentEvent`
- [x] `runtime/`
  - 固定 `thread / task_run / turn / step`
  - 固定统一事件模型 `EventEnvelope`
  - 固定主循环、上下文、提示词边界
- [x] `memory/`
  - 固定 `ThreadStore / CompactService / WorkingMemory`
  - 收敛 thread 当前窗口、history、summary、MEMORY
- [x] `llm/`
  - 固定模型档案、provider 注册、client、types 分层
- [x] `tools/`
  - 固定工具目录结构、注册表、最小执行链
- [x] `infra/`
  - 固定配置、路径、日志、runtime state store
- [x] 文档
  - `docs/` 改为只描述当前实现
  - `README.md`、`AGENTS.md`、`TODO.md` 同步收敛
- [x] 预留设计清理
  - 删除未进入主链的空骨架和薄封装
  - 避免继续并行维护“当前实现”和“未来设想”两套结构
- [x] 测试
  - 建立阶段 1 回归测试
  - 建立 runtime 契约测试
  - 建立 runtime 状态存储测试

阶段 1 完成定义：

- [x] 目录结构不再反复改名
- [x] 核心模块边界已经明确
- [x] 对外主接口已经统一
- [x] 当前功能已经迁入新结构
- [x] 代码、文档、测试能够同步工作

阶段 1 不再做的事：

- [x] 不新增桌面端 / Web 端
- [x] 不新增 skill 系统
- [x] 不新增恢复系统
- [x] 不新增复杂权限与审批流
- [x] 不再做第二次整体推倒重构

---

## 阶段 2：核心模块增强

状态：`当前进行阶段`

目标：

- 在阶段 1 固定骨架上继续增强能力
- 所有改动只允许在既有结构内扩展
- 不允许再用“顺手重构”把阶段拖爆

### P0

- [x] `llm` provider 收敛
  - 明确白名单 provider
  - 收敛模型配置入口
  - 明确每个 provider 的请求参数、thinking 参数、tool 能力
  - 完成 `/model` 切换后的真实调用验证

- [ ] `tools` 核心能力补全
  - 在现有最小执行链上补真实可用工具集
  - 至少补 `filesystem`
  - 补工具权限判定、审计落盘、输出裁剪
  - 让 runtime 正式走统一工具执行链

- [ ] `memory` 主链增强
  - 优化 compact 触发规则
  - 完善 working memory 写回字段
  - 明确 project memory、thread memory、summary 的注入优先级
  - 避免 history、summary、memory 三份内容互相污染

- [ ] `runtime` 状态增强
  - 继续细化 turn / step 生命周期
  - 统一 reasoning、assistant、tool 三类事件的收口行为
  - 为后续 resume / approval 预留稳定状态位

### P1

- [ ] `app` 多端预留增强
  - 明确 TUI、桌面端、Web 端共用的服务接口
  - 把界面专属逻辑继续留在 `app/cli.py`
  - 避免把 UI 状态写回 runtime 内核

- [ ] `tests` 补强
  - 扩大 provider 回归测试
  - 增加多轮 thread 测试
  - 增加 compact / working memory 联动测试
  - 增加工具执行链测试

- [ ] `docs` 跟随更新
  - 代码变更必须同步 `docs/`
  - 模块文档只写当前实现，不写历史方案

### P2

- [ ] `skills`
  - 设计 skill 的目录结构、加载方式、上下文注入点
  - 明确 skill 和 tool、prompt、memory 的边界

- [ ] `security`
  - 细化权限模型
  - 增加审批节点
  - 增加更明确的执行审计

- [ ] `resume / recovery`
  - 增加中断恢复
  - 增加 checkpoint 设计
  - 明确从 runtime state 恢复执行的条件

---

## 阶段 3：客户端扩展

状态：`未开始`

目标：

- 在阶段 2 稳定之后接入更多客户端
- 不改核心执行链，只做客户端适配

### P0

- [ ] Web 端
  - 基于 `AppService` 和统一事件流接入

- [ ] 桌面端
  - 基于 `AppService` 和统一事件流接入

### P1

- [ ] API 层
  - 提供明确的请求、事件流、状态查询接口

---

## 当前执行顺序

以后默认按这个顺序推进，不再跳着做：

1. `llm` provider 收敛
2. `tools` 核心能力补全
3. `memory` 主链增强
4. `runtime` 状态增强
5. `app` 多端预留增强
6. `tests` 补强
7. `docs` 同步
8. `skills`
9. `security`
10. `resume / recovery`
11. `web / desktop / api`

---

## 完成标准

一个 TODO 项只有在下面四件事都完成后，才能打勾：

- [ ] 代码已经合入当前主线
- [ ] 对应模块文档已经更新
- [ ] 至少有一条自动化测试覆盖
- [ ] 没有把不属于当前阶段的内容顺手带进来
