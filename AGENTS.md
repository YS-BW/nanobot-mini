# AGENTS.md

本文件定义当前仓库的协作规则，只保留仍然有效的项目约束。

## 项目定位

- 项目名：`bananabot`
- 当前形态：CLI AI 助手原型
- 目标形态：统一支撑 CLI、桌面端、Web 端的 AI 助手内核
- 当前阶段：第一阶段结构重构已完成，进入第二阶段前的稳定期

## 当前有效文档

以下文档是当前唯一有效文档源：

1. [README.md](/Users/lixinlv/bananabot/README.md)
2. [TODO.md](/Users/lixinlv/bananabot/TODO.md)
3. [项目结构重构方案.md](/Users/lixinlv/bananabot/docs/项目结构重构方案.md)
4. [记忆与上下文压缩系统设计.md](/Users/lixinlv/bananabot/docs/记忆与上下文压缩系统设计.md)

除以上文档外，不再保留旧分析文档、重复说明文档、历史临时方案文档。

## 协作原则

1. 第一阶段已经完成，后续不再做第二次完整推倒式重构。
2. 第二阶段所有实现都必须在既定结构边界内推进。
3. 所有实现与文档必须围绕同一套目标结构，不允许并行维护两套口径。
4. 涉及 `memory`、`tools`、`runtime`、`app/service` 的改动，必须先看对应设计文档再改代码。
5. 变更如果触及统一接口或统一数据结构，必须先更新设计文档。

## 当前目标结构

当前目标结构以 [项目结构重构方案.md](/Users/lixinlv/bananabot/docs/项目结构重构方案.md) 为准，核心分层固定为：

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
4. 变更结构方案时，先改设计文档，再改代码。

## 变更顺序

1. 先改结构文档
2. 再改 TODO
3. 再改代码
4. 最后更新 README

## 最低验证要求

每次结构或核心逻辑变更后，至少验证：

1. `uv run bananabot` 可以启动
2. 单次对话可以返回 assistant 内容
3. 工具调用可以正常回写 `tool` 消息
4. `/status` 正常
5. `/compact` 正常
