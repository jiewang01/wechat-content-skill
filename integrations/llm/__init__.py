"""LLM 集成层：环境变量选择供应商（蓝图十八章⑤，计划 M5-T1）。

    LLM_PROVIDER=openai_compat（默认）→ OpenAI 兼容网关
                                           （OpenAI / Qwen / DeepSeek / Gemini 兼容模式）

切换供应商只需改环境变量，核心 Workflow 不感知（DoD）。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from integrations.errors import ProviderError

from .base import LLMMessage, LLMProvider, LLMResult
from .openai_compat import OpenAICompatProvider

__all__ = [
    "LLMMessage",
    "LLMProvider",
    "LLMResult",
    "OpenAICompatProvider",
    "ProviderError",
    "load_llm_provider",
]

_REGISTRY: dict[str, Callable[[Mapping[str, str]], LLMProvider]] = {
    "openai_compat": OpenAICompatProvider.from_env,
}


def load_llm_provider(env: Mapping[str, str] | None = None) -> LLMProvider:
    """按 LLM_PROVIDER 环境变量构造 Provider；未知名称或缺凭证抛 ProviderError。"""
    env = os.environ if env is None else env
    name = env.get("LLM_PROVIDER", "openai_compat")
    constructor = _REGISTRY.get(name)
    if constructor is None:
        options = "、".join(sorted(_REGISTRY))
        raise ProviderError(f"未知 LLM_PROVIDER：{name}（可选：{options}）")
    return constructor(env)
