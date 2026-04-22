# tools 模块设计

## 模块定位

`tools` 负责把“模型请求调用工具”这件事收敛成当前项目能直接看懂、直接调用的一层。
这一层现在只保留真正跑在主链上的内容，不再保留审批、沙箱、审计、执行器这些空骨架。

## 目录结构

- `base.py`：工具基类
- `specs.py`：工具静态描述
- `registry.py`：工具注册表
- `exec.py`：内置 shell 工具

## 核心对象

### `Tool`

`Tool` 是所有工具的基类，要求子类提供：

- `name`
- `description`
- `parameters`
- `execute()`

此外基类还补了两层能力：

- `spec`
  - 把工具本身映射成统一 `ToolSpec`
- `definition()`
  - 直接返回给模型消费的 function calling 定义

这样 `runner` 不需要知道每个工具的细节，只需要拿工具定义和执行结果。

### `ToolSpec`

`ToolSpec` 是工具的静态描述信息，包含：

- `name`
- `description`
- `parameters`

`ToolSpec.to_definition()` 会生成模型可消费的 function calling 定义。

## `ToolRegistry`

`ToolRegistry` 现在只做四件事：

1. `register()` 注册工具
2. `get()` / `list_tools()` 查询工具
3. `list_specs()` / `get_definitions()` 暴露工具定义
4. `execute(name, arguments)` 直接执行工具并返回 `(result, error)`

这里故意不再包一层 `ToolExecutionRequest / ToolExecutionResult`。
当前 `runner` 的诉求很简单，就是：

- 能列出工具定义给模型
- 能按名字执行工具
- 能拿到字符串结果或错误

## 当前执行链

当前主链路很直接：

1. `runner` 从 `registry.get_definitions()` 取 function calling 定义
2. 模型返回工具调用时，`runner` 调 `registry.execute()`
3. `registry` 找到具体工具并执行
4. 把 `(result, error)` 回写成 `tool` 消息

这条链路的优点是简单、可读、容易测试。

## 内置工具：`ExecTool`

当前默认只注册一个内置工具 `exec`，负责执行 shell 命令。

### 工具定义
- 名称：`exec`
- 描述：执行一条 shell 命令并返回输出
- 参数：
  - `command`
  - `timeout`

### 执行方式

`ExecTool.execute()` 用 `asyncio.create_subprocess_shell()` 在指定工作目录启动命令，并返回：

- `stdout + stderr`
- 最终退出码
- 或超时终止提示

## 当前实现边界

### 已实现
- 工具定义和执行入口已经统一
- `runner` 不再直接绑定某个具体工具实现
- 当前工具层足够支撑 function calling 主链

### 当前限制
- 还没有权限、审批、沙箱、审计这些真正可用的能力
- 当前只内置了 `exec` 一个工具
- 后续要补工具能力时，优先先补真实可用功能，不再先搭空骨架
