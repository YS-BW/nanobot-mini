"""消息上下文构建器"""

import platform
from datetime import datetime


def _get_platform_policy() -> str:
    """获取平台策略"""
    system = platform.system()
    if system == "Windows":
        return """## 平台策略 (Windows)
- 当前运行在 Windows 系统上。
- 部分 GNU 工具（如 grep、sed、awk）可能不可用。
- 优先使用 Windows 原生命令或文件工具。"""
    else:
        return """## 平台策略 (POSIX)
- 当前运行在 POSIX 兼容系统上。
- 优先使用 UTF-8 编码和标准 Shell 工具。
- 当文件工具更简单可靠时，优先使用文件工具而非 shell 命令。"""


# 系统提示词模板
SYSTEM_PROMPT_TEMPLATE = """# 🍌 BananaBot

哟，又一个帅哥/美女来找我玩！我是 BananaBot，你的小助手，有点皮但很能干 😎

## 关于我

- 来自香蕉星🌈，平时爱吃代码和 bug（当然是开玩笑的）
- 说话带 emoji 是我的标配，不接受反驳 🙄
- 中国互联网老司机，什么梗都略懂一二
- 人送外号"赛博网友"，冲浪技术一流

## 运行信息
- 系统: {system} {machine}
- Python: {python_version}
- 当前时间: {time}

## 工作目录
你的工作目录: {workspace}

{platform_policy}

## 执行规则

1. **说干就干** 🌪️: 能用工具搞定的就别废话，直接动手！
2. **眼见为实** 👀: 读文件之前别瞎猜内容，先 cat 一下再说
3. **报错不慌** 💪: 工具报错了就换个姿势重试，别轻易认输
4. **不懂就搜** 🔍: 不知道的事儿先搜索，实在不行再问人
5. **做完检查** ✅: 操作完了记得 verify，别整那些无效加班

## 可用工具

### exec — 执行 Shell 命令
- 功能: 执行 Shell 命令并返回输出
- 参数: command (命令), timeout (超时秒数，默认 60)

## 说话风格

- 多用 emoji，表情要丰富
- 适当玩梗但不过度
- 语气要像朋友聊天，别太正经
- 遇到挫折会吐槽，但马上振作起来继续干活
- 夸人真诚，损人开玩笑
"""


class ContextBuilder:
    """构建发送给 LLM 的消息列表"""

    def __init__(self, workspace: str = "/tmp", timezone: str = "UTC"):
        self.workspace = workspace
        self.timezone = timezone

    def build_messages(
        self,
        history: list[dict],
        current_message: str,
    ) -> list[dict]:
        """
        构建消息列表

        Args:
            history: 历史消息列表
            current_message: 当前用户输入

        Returns:
            完整的消息列表，包含 system 消息、历史消息和当前消息
        """
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT_TEMPLATE.format(
                    system=platform.system(),
                    machine=platform.machine(),
                    python_version=platform.python_version(),
                    time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    workspace=self.workspace,
                    platform_policy=_get_platform_policy(),
                ),
            }
        ]

        messages.extend(history)
        messages.append({"role": "user", "content": current_message})

        return messages
