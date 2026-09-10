"""Search Provider 单测（蓝图十二章，计划 M5-T2）。

全部注入 httpx.MockTransport / 内桩离线运行（CI 无网络依赖）：
- Tavily：请求形状（URL / Bearer / query / max_results）与命中解析；
- 错误封装：HTTP 非 200 / 网络异常 / 响应缺结构 → 统一 ProviderError；
- 降级（M5-T2 DoD）：SafeSearchProvider 把失败转 degraded=True，
  上层复用既有 sources 继续，绝不向上抛网络错误。
"""

from __future__ import annotations

import json

import httpx
import pytest

from integrations.errors import ProviderError
from integrations.search import (
    SafeSearchProvider,
    SearchHit,
    SearchOutcome,
    TavilySearchProvider,
    load_search_provider,
)

TAVILY_BODY = {
    "results": [
        {"title": "手冲咖啡参数指南", "url": "https://a.test/1", "content": "水温 92 度。"},
        {"title": "闷蒸的作用", "url": "https://a.test/2", "content": "释放二氧化碳。"},
    ]
}


def make_search(handler) -> tuple[TavilySearchProvider, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    provider = TavilySearchProvider(api_key="tv-test", transport=httpx.MockTransport(record))
    return provider, requests


class _FakeProvider:
    def __init__(self, hits=None, error=None):
        self._hits = hits or []
        self._error = error

    def search(self, query: str, *, limit: int = 5):
        if self._error is not None:
            raise self._error
        return self._hits


def test_tavily_sends_query_and_parses_hits():
    provider, requests = make_search(lambda request: httpx.Response(200, json=TAVILY_BODY))
    hits = provider.search("手冲咖啡 水温")
    assert str(requests[0].url) == "https://api.tavily.com/search"
    assert requests[0].headers["Authorization"] == "Bearer tv-test"
    payload = json.loads(requests[0].content)
    assert payload == {"query": "手冲咖啡 水温", "max_results": 5}
    assert hits == [
        SearchHit(url="https://a.test/1", title="手冲咖啡参数指南", snippet="水温 92 度。"),
        SearchHit(url="https://a.test/2", title="闷蒸的作用", snippet="释放二氧化碳。"),
    ]
    provider.close()


def test_tavily_limit_passthrough():
    provider, requests = make_search(lambda request: httpx.Response(200, json=TAVILY_BODY))
    provider.search("手冲咖啡", limit=3)
    payload = json.loads(requests[0].content)
    assert payload["max_results"] == 3
    provider.close()


def test_tavily_http_error_wrapped_as_provider_error():
    provider, _ = make_search(lambda request: httpx.Response(403, text="forbidden"))
    with pytest.raises(ProviderError, match="403"):
        provider.search("手冲咖啡")
    provider.close()


def test_tavily_network_error_wrapped_as_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure", request=request)

    provider, _ = make_search(handler)
    with pytest.raises(ProviderError, match="请求失败"):
        provider.search("手冲咖啡")
    provider.close()


def test_tavily_malformed_response_wrapped_as_provider_error():
    provider, _ = make_search(lambda request: httpx.Response(200, json={"error": "x"}))
    with pytest.raises(ProviderError, match="results"):
        provider.search("手冲咖啡")
    provider.close()


def test_safe_search_success_passthrough():
    hits = [SearchHit(url="https://a.test/1", title="指南")]
    outcome = SafeSearchProvider(_FakeProvider(hits=hits)).search("手冲咖啡")
    assert outcome == SearchOutcome(hits=hits, degraded=False, reason="")


def test_safe_search_degrades_on_provider_error():
    inner = _FakeProvider(error=ProviderError("搜索服务限流"))
    outcome = SafeSearchProvider(inner).search("手冲咖啡")
    assert outcome.hits == []
    assert outcome.degraded is True
    assert "限流" in outcome.reason


def test_safe_search_degrades_on_raw_httpx_error():
    inner = _FakeProvider(error=httpx.ConnectError("connection refused"))
    outcome = SafeSearchProvider(inner).search("手冲咖啡")
    assert outcome.degraded is True
    assert outcome.reason


def test_load_search_provider_selects_by_env():
    provider = load_search_provider({"SEARCH_PROVIDER": "tavily", "TAVILY_API_KEY": "tv"})
    assert isinstance(provider, TavilySearchProvider)
    provider.close()


def test_load_search_provider_missing_api_key():
    with pytest.raises(ProviderError, match="TAVILY_API_KEY"):
        load_search_provider({})


def test_load_search_provider_unknown_name():
    with pytest.raises(ProviderError, match="未知 SEARCH_PROVIDER"):
        load_search_provider({"SEARCH_PROVIDER": "nope", "TAVILY_API_KEY": "tv"})
