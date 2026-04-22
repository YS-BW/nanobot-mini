# AGENTS.md

本文件定义当前仓库的协作规则，只保留仍然有效的项目约束。

## 项目定位

- 项目名：`bananabot`
- 当前形态：CLI AI 助手原型
- 目标形态：统一支撑 CLI、桌面端、Web 端的 AI 助手内核
- 当前阶段：第一阶段结构重构已完成，当前按第二阶段任务推进

## 当前有效文档

当前文档分两层：

1. [README.md](/Users/lixinlv/bananabot/README.md)
2. [TODO.md](/Users/lixinlv/bananabot/TODO.md)
3. `docs/`
   - [00-仓库总览.md](/Users/lixinlv/bananabot/docs/00-仓库总览.md)
   - [app 模块设计.md](/Users/lixinlv/bananabot/docs/app%20模块设计.md)
   - [runtime 模块设计.md](/Users/lixinlv/bananabot/docs/runtime%20模块设计.md)
   - [memory 模块设计.md](/Users/lixinlv/bananabot/docs/memory%20模块设计.md)
   - [tools 模块设计.md](/Users/lixinlv/bananabot/docs/tools%20模块设计.md)
   - [llm 模块设计.md](/Users/lixinlv/bananabot/docs/llm%20模块设计.md)
   - [infra 模块设计.md](/Users/lixinlv/bananabot/docs/infra%20模块设计.md)
   - [测试与状态存储设计.md](/Users/lixinlv/bananabot/docs/测试与状态存储设计.md)
4. `refactor/`
   - 重构方案、共享契约、工作拆分与迁移材料

`docs/` 只描述当前实现；`refactor/` 只描述重构过程和迁移方案。

## 协作原则

1. 第一阶段已经完成，后续不再做第二次完整推倒式重构。
2. 第二阶段所有实现都必须在既定结构边界内推进。
3. 以后默认严格按 [TODO.md](/Users/lixinlv/bananabot/TODO.md) 推进，不再脱离 TODO 口头扩阶段或临时改执行顺序。
4. 如果新增任务不在 TODO 中，先更新 TODO，再开始实现。
5. 所有实现与文档必须围绕同一套目标结构，不允许并行维护两套口径。
6. 涉及 `memory`、`tools`、`runtime`、`app/service` 的改动，必须先看对应设计文档再改代码。
7. 变更如果触及统一接口或统一数据结构，必须先更新设计文档。

## 当前目标结构

当前目标结构以 [00-仓库总览.md](/Users/lixinlv/bananabot/docs/00-仓库总览.md) 为准，核心分层固定为：

- `app`
- `runtime`
- `memory`
- `llm`
- `tools`
- `infra`

## 文档规则

1. 一个主题只保留一份主文档。
2. 分析类临时文档不长期保留。
3. 如果某份文档已经被新文档覆盖，应直接删除，不再保留“历史参考”。
4. 变更当前实现时，先改 `docs/`，再改代码。
5. 变更重构路线、阶段边界或共享契约时，改 `refactor/`。

## 变更顺序

1. 先确认 [TODO.md](/Users/lixinlv/bananabot/TODO.md) 中的当前阶段和当前任务
2. 如有必要，先更新 TODO
3. 再改结构文档
4. 再改代码
5. 最后更新 README

## 最低验证要求

每次结构或核心逻辑变更后，至少验证：

1. `uv run bananabot` 可以启动
2. 单次对话可以返回 assistant 内容
3. 工具调用可以正常回写 `tool` 消息
4. `/status` 正常
5. `/compact` 正常
