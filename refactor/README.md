# Bananabot Refactor Docs

这组文档用于管理 `bananabot` 下一轮核心重构。

目标不是继续修补当前“聊天 + 工具循环”实现，而是把项目迁移为一个更接近 Codex / Nanobot 的本地优先 Agent Runtime。

## 文档索引

1. `00-overview.md`
   - 为什么要重构
   - 这次重构的边界
   - 当前系统与目标系统的差异

2. `01-architecture-plan.md`
   - 总体重构方案
   - 模块保留与重写边界
   - 新执行骨架与数据模型

3. `02-runtime-migration-plan.md`
   - `Phase 0 ~ Phase 3` 迁移计划
   - 每个阶段的目标、产物、风险、退出条件

4. `03-code-guide.md`
   - 重构期间的代码组织规则
   - 模块职责、命名、数据流、禁止事项

5. `04-code-style.md`
   - 重构期间统一代码风格与注释规范

6. `05-work-items.md`
   - 可直接执行的工作清单
   - 当前优先级与建议顺序

7. `06-agent-roles.md`
   - 并发重构的 agent 角色、ownership 与协作规则

8. `07-shared-contracts.md`
   - 并发重构期间冻结的共享对象与事件契约

## 当前结论

这次重构的核心判断：

- 保留顶层模块域：`app / runtime / memory / tools / llm / infra`
- 推倒重写 `runtime` 执行骨架
- 把 `app/service` 从 chat orchestrator 改成 task runtime service
- 把 `memory` 从 `session + summary` 升级为带 `working memory` 的结构
- 把 `tools` 从 registry 升级为带治理能力的执行层

## 阅读顺序

建议按下面顺序阅读：

1. `00-overview.md`
2. `01-architecture-plan.md`
3. `02-runtime-migration-plan.md`
4. `03-code-guide.md`
5. `05-work-items.md`
