"""Image Provider 单测（蓝图十二章/十八章⑤，计划 M5-T3）。

全部离线运行（CI 无网络依赖，M5-T9 前置约束）：
- 生成实现：请求形状 / b64 响应 / 三类错误封装（httpx.MockTransport 注入）；
- 三级降级链（DoD 集成测试）：生成成功 → 搜索降级 → 占位图兜底；
- 工厂：环境变量选择 / 默认 / 未知名称 / 缺 key / 降级工厂永不抛错。
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from integrations.errors import ProviderError
from integrations.image import (
    FallbackImageProvider,
    ImageAsset,
    OpenAIImageProvider,
    load_fallback_image_provider,
    load_image_provider,
)
from integrations.search import SearchHit

PROMPT = "手冲咖啡俯拍示意图"

OK_BODY = {"created": 1700, "data": [{"url": "https://cdn.test/generated.png"}]}


def make_image_provider(handler) -> tuple[OpenAIImageProvider, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    provider = OpenAIImageProvider(
        api_key="sk-img",
        base_url="https://img.test/v1",
        model="test-image-model",
        transport=httpx.MockTransport(record),
    )
    return provider, requests


class _StubGenerator:
    def __init__(self, asset: ImageAsset) -> None:
        self.asset = asset

    def generate(self, prompt: str, *, size: str = "1024x1024") -> ImageAsset:
        return self.asset


class _FailingGenerator:
    def generate(self, prompt: str, *, size: str = "1024x1024") -> ImageAsset:
        raise ProviderError("图片服务返回 HTTP 503：overloaded")


class _StubSearcher:
    def __init__(self, hits=None, error=None):
        self.hits = hits or []
        self.error = error
        self.queries: list[tuple[str, int]] = []

    def search(self, query: str, *, limit: int = 5) -> list[SearchHit]:
        self.queries.append((query, limit))
        if self.error is not None:
            raise self.error
        return self.hits


def test_image_asset_rejects_unknown_source():
    with pytest.raises(ValidationError):
        ImageAsset(url="https://cdn.test/a.png", source="magic")


def test_generate_sends_standard_images_request():
    provider, requests = make_image_provider(lambda request: httpx.Response(200, json=OK_BODY))
    result = provider.generate(PROMPT)
    assert str(requests[0].url) == "https://img.test/v1/images/generations"
    assert requests[0].headers["Authorization"] == "Bearer sk-img"
    payload = json.loads(requests[0].content)
    assert payload == {
        "model": "test-image-model",
        "prompt": PROMPT,
        "size": "1024x1024",
        "n": 1,
    }
    assert result == ImageAsset(
        url="https://cdn.test/generated.png", source="generated", prompt=PROMPT
    )
    provider.close()


def test_generate_custom_size_passthrough():
    provider, requests = make_image_provider(lambda request: httpx.Response(200, json=OK_BODY))
    provider.generate(PROMPT, size="1792x1024")
    payload = json.loads(requests[0].content)
    assert payload["size"] == "1792x1024"
    provider.close()


def test_generate_supports_b64_json_response():
    body = {"data": [{"b64_json": "aGVsbG8="}]}
    provider, _ = make_image_provider(lambda request: httpx.Response(200, json=body))
    result = provider.generate(PROMPT)
    assert result.url == "data:image/png;base64,aGVsbG8="
    assert result.source == "generated"
    provider.close()


def test_generate_rejects_payload_without_url_or_b64():
    provider, _ = make_image_provider(lambda request: httpx.Response(200, json={"data": [{}]}))
    with pytest.raises(ProviderError, match="b64_json"):
        provider.generate(PROMPT)
    provider.close()


def test_http_error_wrapped_as_provider_error():
    provider, _ = make_image_provider(lambda request: httpx.Response(429, text="rate limited"))
    with pytest.raises(ProviderError, match="429"):
        provider.generate(PROMPT)
    provider.close()


def test_network_error_wrapped_as_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider, _ = make_image_provider(handler)
    with pytest.raises(ProviderError, match="请求失败"):
        provider.generate(PROMPT)
    provider.close()


def test_malformed_response_wrapped_as_provider_error():
    provider, _ = make_image_provider(lambda request: httpx.Response(200, json={"data": []}))
    with pytest.raises(ProviderError, match="data"):
        provider.generate(PROMPT)
    provider.close()


def test_load_image_provider_selects_by_env():
    provider = load_image_provider(
        {
            "IMAGE_PROVIDER": "openai_compat",
            "IMAGE_API_KEY": "sk-env",
            "IMAGE_BASE_URL": "https://flux.test/v1",
            "IMAGE_MODEL": "flux-pro",
        }
    )
    assert isinstance(provider, OpenAIImageProvider)
    assert provider.model == "flux-pro"
    provider.close()


def test_load_image_provider_defaults_to_openai_compat():
    provider = load_image_provider({"IMAGE_API_KEY": "sk-env"})
    assert isinstance(provider, OpenAIImageProvider)
    assert provider.model == "dall-e-3"
    provider.close()


def test_load_image_provider_unknown_name():
    with pytest.raises(ProviderError, match="未知 IMAGE_PROVIDER"):
        load_image_provider({"IMAGE_PROVIDER": "nope", "IMAGE_API_KEY": "k"})


def test_load_image_provider_missing_api_key():
    with pytest.raises(ProviderError, match="IMAGE_API_KEY"):
        load_image_provider({})


def test_fallback_prefers_generation():
    generated = ImageAsset(url="https://cdn.test/gen.png", source="generated", prompt=PROMPT)
    searcher = _StubSearcher(hits=[SearchHit(url="https://cdn.test/s.jpg", title="命中")])
    provider = FallbackImageProvider(_StubGenerator(generated), searcher)
    asset = provider.get_image(PROMPT)
    assert asset is generated
    assert searcher.queries == []


def test_fallback_uses_search_when_generation_fails():
    searcher = _StubSearcher(hits=[SearchHit(url="https://cdn.test/a.jpg", title="手冲咖啡插图")])
    provider = FallbackImageProvider(_FailingGenerator(), searcher)
    asset = provider.get_image(PROMPT)
    assert asset.source == "search"
    assert asset.url == "https://cdn.test/a.jpg"
    assert asset.prompt == PROMPT
    assert "手冲咖啡插图" in asset.reason
    assert searcher.queries == [(PROMPT, 1)]


def test_fallback_search_uses_custom_query():
    searcher = _StubSearcher(hits=[SearchHit(url="https://cdn.test/b.jpg", title="配图")])
    provider = FallbackImageProvider(_FailingGenerator(), searcher)
    provider.get_image("pour-over coffee top view", query="手冲咖啡 配图")
    assert searcher.queries == [("手冲咖啡 配图", 1)]


def test_fallback_placeholder_when_search_provider_error():
    searcher = _StubSearcher(error=ProviderError("搜索服务返回 HTTP 429：限流"))
    provider = FallbackImageProvider(_FailingGenerator(), searcher)
    asset = provider.get_image(PROMPT)
    assert asset.source == "placeholder"
    assert asset.url.startswith("data:image/svg+xml")


def test_fallback_placeholder_when_search_network_fails():
    searcher = _StubSearcher(error=httpx.ConnectError("搜索服务不可用"))
    provider = FallbackImageProvider(_FailingGenerator(), searcher)
    asset = provider.get_image(PROMPT)
    assert asset.source == "placeholder"
    assert "均不可用" in asset.reason


def test_fallback_placeholder_when_search_empty():
    searcher = _StubSearcher(hits=[])
    provider = FallbackImageProvider(_FailingGenerator(), searcher)
    asset = provider.get_image(PROMPT)
    assert asset.source == "placeholder"


def test_fallback_search_without_generator():
    searcher = _StubSearcher(hits=[SearchHit(url="https://cdn.test/c.jpg", title="配图")])
    provider = FallbackImageProvider(None, searcher)
    asset = provider.get_image(PROMPT)
    assert asset.source == "search"
    assert asset.url == "https://cdn.test/c.jpg"


def test_fallback_placeholder_is_deterministic():
    provider = FallbackImageProvider(None)
    first = provider.get_image("手冲咖啡", size="512x512")
    second = provider.get_image("手冲咖啡", size="512x512")
    other = provider.get_image("意式浓缩", size="512x512")
    assert first.url == second.url
    assert first.url != other.url
    assert first.url.startswith("data:image/svg+xml")


def test_load_fallback_image_provider_never_raises():
    provider = load_fallback_image_provider({})
    asset = provider.get_image("手冲咖啡封面")
    assert asset.source == "placeholder"
    assert asset.url.startswith("data:image/svg+xml")
