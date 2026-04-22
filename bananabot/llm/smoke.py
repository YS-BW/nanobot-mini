"""Provider smoke 测试工具。"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from ..infra import Config
from .client import LLMClient


@dataclass(slots=True)
class SmokeResult:
    """单个模型 smoke 结果。"""

    alias: str
    provider: str
    model: str
    streamed: bool
    ok: bool
    finish_reason: str | None = None
    content_preview: str = ""
    reasoning_chars: int = 0
    error: str | None = None


def _preview(text: str, limit: int = 80) -> str:
    compact = " ".join(part.strip() for part in text.splitlines() if part.strip())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}…"


async def smoke_alias(client: LLMClient, alias: str, prompt: str, *, prefer_stream: bool = True) -> SmokeResult:
    """对单个 alias 做一次最小真实请求。"""

    profile = client.model_registry.get(alias)
    streamed = prefer_stream and profile.capabilities.supports_stream
    try:
        if streamed:
            content_parts: list[str] = []
            reasoning_parts: list[str] = []
            finish_reason: str | None = None
            async for chunk in client.chat_stream(
                messages=[{"role": "user", "content": prompt}],
                model=alias,
            ):
                if chunk.reasoning_content:
                    reasoning_parts.append(chunk.reasoning_content)
                if chunk.content:
                    content_parts.append(chunk.content)
                if chunk.finish_reason is not None:
                    finish_reason = chunk.finish_reason

            return SmokeResult(
                alias=profile.alias,
                provider=profile.provider,
                model=profile.model,
                streamed=True,
                ok=True,
                finish_reason=finish_reason or "stop",
                content_preview=_preview("".join(content_parts)),
                reasoning_chars=len("".join(reasoning_parts)),
            )

        response = await client.chat(
            messages=[{"role": "user", "content": prompt}],
            model=alias,
        )
        return SmokeResult(
            alias=profile.alias,
            provider=profile.provider,
            model=profile.model,
            streamed=False,
            ok=True,
            finish_reason=response.finish_reason,
            content_preview=_preview(response.content or ""),
            reasoning_chars=len(response.reasoning_content or ""),
        )
    except Exception as exc:  # pragma: no cover - 依赖真实 provider
        return SmokeResult(
            alias=profile.alias,
            provider=profile.provider,
            model=profile.model,
            streamed=streamed,
            ok=False,
            error=str(exc),
        )


async def run_smoke(aliases: list[str] | None = None, *, prompt: str, prefer_stream: bool = True) -> list[SmokeResult]:
    """对当前配置的模型做 smoke 测试。"""

    config = Config.from_env()
    client = LLMClient(model_registry=config.model_registry, default_model=config.model_alias)
    target_aliases = aliases or [profile.alias for profile in client.list_models()]
    results: list[SmokeResult] = []
    for alias in target_aliases:
        results.append(await smoke_alias(client, alias, prompt, prefer_stream=prefer_stream))
    return results


async def _amain() -> int:
    parser = argparse.ArgumentParser(description="Smoke test configured LLM providers")
    parser.add_argument("--alias", action="append", dest="aliases", help="只测试指定 alias，可重复传入")
    parser.add_argument(
        "--prompt",
        default="请只回复 OK，不要输出其他内容。",
        help="用于 smoke 的最小提示词",
    )
    parser.add_argument("--no-stream", action="store_true", help="关闭流式 smoke，强制走非流式请求")
    args = parser.parse_args()

    results = await run_smoke(args.aliases, prompt=args.prompt, prefer_stream=not args.no_stream)
    has_error = False
    for result in results:
        mode = "stream" if result.streamed else "oneshot"
        if result.ok:
            print(
                f"[ok] {result.alias} | {result.provider} | {mode} | "
                f"finish={result.finish_reason} | reason_chars={result.reasoning_chars} | "
                f"preview={result.content_preview or '<empty>'}"
            )
            continue

        has_error = True
        print(f"[error] {result.alias} | {result.provider} | {mode} | {result.error}")

    return 1 if has_error else 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
