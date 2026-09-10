"""Tavily Web Search 实现（POST https://api.tavily.com/search）。

环境变量契约（from_env）：
    TAVILY_API_KEY   必填，缺失抛 ProviderError；
    TAVILY_TIMEOUT   默认 20 秒。

测试注入 httpx.MockTransport 离线运行（CI 无网络依赖）。
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from integrations.errors import ProviderError

from .base import SearchHit

API_URL = "https://api.tavily.com/search"
DEFAULT_TIMEOUT = 20.0


class TavilySearchProvider:
    def __init__(
        self,
        *,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> TavilySearchProvider:
        api_key = env.get("TAVILY_API_KEY", "")
        if not api_key:
            raise ProviderError("缺少环境变量 TAVILY_API_KEY（无法构造 Search Provider）")
        return cls(api_key=api_key, timeout=float(env.get("TAVILY_TIMEOUT", str(DEFAULT_TIMEOUT))))

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        try:
            response = self._client.post(API_URL, json={"query": query, "max_results": limit})
        except httpx.HTTPError as exc:
            raise ProviderError(f"搜索请求失败：{exc}") from exc
        if response.status_code != 200:
            raise ProviderError(f"搜索服务返回 HTTP {response.status_code}：{response.text[:200]}")
        try:
            results = response.json()["results"]
            return [
                SearchHit(
                    url=item["url"],
                    title=item.get("title", ""),
                    snippet=item.get("content", ""),
                )
                for item in results
            ]
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(f"搜索响应缺少 results 结构：{exc}") from exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TavilySearchProvider:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
