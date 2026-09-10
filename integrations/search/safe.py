"""降级包装：搜索失败不中断流程，返回 degraded=True 由上层复用既有 sources（蓝图十二章）。

Web Search 挂了 → use existing sources → continue。
本模块是 M5-T2 DoD「断网/超时用例走降级分支」的实现落点。
"""

from __future__ import annotations

import httpx

from integrations.errors import ProviderError

from .base import SearchOutcome, SearchProvider


class SafeSearchProvider:
    """包装任意 SearchProvider：异常转降级结果，绝不把网络/服务错误抛给上层。"""

    def __init__(self, inner: SearchProvider) -> None:
        self._inner = inner

    def search(self, query: str, *, limit: int = 5) -> SearchOutcome:
        try:
            hits = self._inner.search(query, limit=limit)
        except (ProviderError, httpx.HTTPError) as exc:
            return SearchOutcome(hits=[], degraded=True, reason=str(exc))
        return SearchOutcome(hits=list(hits), degraded=False)
