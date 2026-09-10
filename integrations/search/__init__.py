"""Search 集成层：环境变量选择供应商 + 降级包装（蓝图十二章，计划 M5-T2）。

    SEARCH_PROVIDER=tavily（默认）→ Tavily Web Search

断网 / 超时 / 限流时 SafeSearchProvider 返回 degraded=True，
上层复用既有 sources 继续流程（Workflow 不因外网故障中断）。
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from integrations.errors import ProviderError

from .base import SearchHit, SearchOutcome, SearchProvider
from .safe import SafeSearchProvider
from .tavily import TavilySearchProvider

__all__ = [
    "ProviderError",
    "SafeSearchProvider",
    "SearchHit",
    "SearchOutcome",
    "SearchProvider",
    "TavilySearchProvider",
    "load_safe_search_provider",
    "load_search_provider",
]

_REGISTRY: dict[str, Callable[[Mapping[str, str]], SearchProvider]] = {
    "tavily": TavilySearchProvider.from_env,
}


def load_search_provider(env: Mapping[str, str] | None = None) -> SearchProvider:
    """按 SEARCH_PROVIDER 环境变量构造 Provider；未知名称或缺凭证抛 ProviderError。"""
    env = os.environ if env is None else env
    name = env.get("SEARCH_PROVIDER", "tavily")
    constructor = _REGISTRY.get(name)
    if constructor is None:
        options = "、".join(sorted(_REGISTRY))
        raise ProviderError(f"未知 SEARCH_PROVIDER：{name}（可选：{options}）")
    return constructor(env)


def load_safe_search_provider(env: Mapping[str, str] | None = None) -> SafeSearchProvider:
    """带降级包装的搜索入口：上层直接消费 SearchOutcome，无需 try/except。"""
    return SafeSearchProvider(load_search_provider(env))
