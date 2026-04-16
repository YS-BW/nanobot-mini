# BananaBot 开发指南

> nanobot-mini 项目开发规范和架构说明

---

## 核心原则

### 设计优先级

1. **正确性** — 功能必须正确工作
2. **简洁** — 最少的代码实现最清晰的设计
3. **可维护** — 代码应该易于理解和修改
4. **性能** — 在以上都满足后再考虑优化

### 模块化原则

- 每个模块职责单一，边界清晰
- 模块间通过接口交互，不暴露内部实现
- 避免循环依赖
- 使用依赖注入解耦

### 低耦合实现

```
✅ 好：context.py 只依赖 Session 接口，不知道具体存储
❌ 坏：直接在 context 里操作 session.jsonl 文件
```

### 可扩展设计

- 工具系统：注册制，开闭原则（对扩展开放，对修改关闭）
- 会话存储：分层设计，compact 机制可替换
- LLM 调用：接口隔离，不同模型可替换

---

## 开发规范

### 模块依赖（严格遵守）

```
__main__.py     # CLI 入口，协调各模块
├── config.py    # 配置，无依赖
├── llm.py       # LLM 调用，无依赖
├── runner.py    # Agent 循环，依赖 llm, tools
├── context.py   # 上下文构建，依赖 session, memory
├── session.py   # 会话管理，无依赖
├── memory.py    # 记忆管理，无依赖
└── tools/      # 工具系统
    ├── base.py      # Tool 基类
    ├── registry.py  # 注册表
    └── *.py        # 具体工具实现
```

**依赖方向**：CLI → 业务逻辑 → 基础设施
**禁止**：业务逻辑反向依赖 CLI

### 文件命名

| 类型 | 规范 | 示例 |
|------|------|------|
| 类名 | PascalCase | `SessionManager` |
| 公有方法 | snake_case | `build_messages` |
| 私有方法 | `_snake_case` | `_load_summary` |
| 常量 | `UPPER_SNAKE_CASE` | `SYSTEM_PROMPT_TEMPLATE` |
| 实例变量 | `snake_case` | `session_path` |
| 配置变量 | `snake_case` | `context_window` |

### 函数设计

```python
# ✅ 好：单一职责，参数明确，返回简单
def estimate_tokens(text: str) -> int:
    """估算文本 token 数量"""
    return len(text) // 4

# ❌ 坏：多个职责，隐式依赖，副作用
def process_and_save(session, config, also_update_history=False):
    ...
```

### 注释规范

**必须注释的情况**：
- 业务逻辑分支（if/else 的原因）
- 非显而易见的算法
- 与调用方约定的接口契约
- 设计决策的理由

**注释写法**：
```python
# 为什么这么做，而不是更简单的方案
if context_window > 100000:
    # 超大窗口需要分段处理，避免单次请求超时
    chunks = split_into_chunks(messages, chunk_size)
```

**不写注释**：
- 代码本身已经清晰的逻辑
- 显而易见的 getter/setter
- 自解释的变量名

### 避免冗余设计

```python
# ❌ 冗余：抽象过度，为未来可能的扩展预留
class BaseSession(ABC):
    @abstractmethod
    def save(self): ...
    @abstractmethod
    def load(self): ...
    @abstractmethod
    def backup(self): ...

class FileSession(BaseSession):
    ...

class MemorySession(BaseSession):  # 永远用不到

# ✅ 好：只在需要时抽象
class Session:
    def save(self): ...
    # 如果将来需要多种实现，再抽象
```

### 最小修改原则

修改一个模块时：
1. 只改必须改的部分
2. 不为"将来可能用不到"的功能改代码
3. 不修改已经正常工作的接口签名
4. 不添加未来可能需要的参数

```python
# ❌ 坏：添加无用参数
def build_messages(history, current_message, session=None, unused_param=None):

# ✅ 好：只加需要的参数
def build_messages(history, current_message, session=None):
```

### 自我推翻验证

每次修改代码时，先问：

1. **这个修改是否引入不必要的复杂度？**
2. **有没有更简单的实现方式？**
3. **删除这段代码会破坏什么？**
4. **这个抽象在什么场景下会被用到？**
5. **能不能用更少的代码实现同样的功能？**

```python
# 推翻示例：原来的设计
class CompactManager:
    def should_compact(self, session) -> bool: ...
    def do_compact_round1(self, session) -> None: ...
    def do_compact_round2(self, session) -> None: ...
    def estimate_tokens(self, session) -> int: ...

# 推翻后：这些方法本来就是 Session 的职责
class Session:
    def should_compact(self, threshold: float) -> bool: ...
    def compact(self) -> list[dict]: ...
    def estimate_tokens(self) -> int: ...
```

---

## 会话存储架构

### 存储结构

```
~/.bananabot/sessions/<session_name>/
├── session.jsonl    # 当前会话，可被 compact 裁切
├── history.jsonl     # 已被 compact 的历史（append-only，不用于上下文）
├── summary.jsonl     # compact 摘要累积（用于第二轮）
└── MEMORY.md        # 第二轮 compact 整合的长期记忆
```

### Compact 触发规则

| 阶段 | 触发条件 | 操作 |
|------|----------|------|
| 第一轮 | session tokens > context_window * 0.70 | 裁切到 20 条，写入 history + summary |
| 第二轮 | summary tokens > context_window * 0.85 | 整合到 MEMORY.md，清空 summary |

### 上下文构建顺序

`build_messages()` 按序拼接：
1. BANANA.md（全局 + 项目）
2. MEMORY.md（长期记忆）
3. 系统提示词 + summary.jsonl（在系统提示词里）
4. session.messages（最近消息）
5. 当前用户消息

**关键**：history.jsonl 不用于上下文，仅作备份。

---

## 文档规范

### docs/ 目录

```
docs/
├── 记忆与上下文压缩系统设计.md   # 核心功能设计
└── <功能名>.md                  # 其他功能设计
```

### 文档内容要求

每个设计文档必须包含：
1. **问题**：要解决什么问题
2. **方案**：为什么用这个方案而不是其他的
3. **实现**：关键代码和流程
4. **验证**：如何验证正确性

---

## 测试验证

```bash
# 清理后测试
rm -rf ~/.bananabot/sessions/cli:default

# 验证会话累积
nanobot-mini "第一次"
nanobot-mini "第二次"
cat ~/.bananabot/sessions/cli:default/session.jsonl | wc -l  # 应该线性增长

# 验证 compact
# 添加足够多内容触发 compact，检查：
# - session.jsonl 消息数减少
# - history.jsonl 有内容
# - summary.jsonl 有摘要
```

---

## 代码审查清单

提交前自问：

- [ ] 这个修改是否只改最少的代码？
- [ ] 新代码是否比原来更简洁？
- [ ] 是否有删除无用代码？
- [ ] 是否有引入不必要的抽象？
- [ ] 注释是否解释"为什么"而不是"是什么"？
- [ ] 模块依赖是否仍然单向？
- [ ] 能否用更少代码实现？
