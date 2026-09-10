"""LLM Provider 单测（蓝图十八章⑤，计划 M5-T1）。

全部注入 httpx.MockTransport 离线运行（CI 无网络依赖，M5-T9 前置约束）：
- 请求形状：base_url 拼接 / Bearer 头 / 消息序列化 / 可选参数只在显式给出时透传；
- 错误封装：HTTP 非 200 / 网络异常 / 响应缺结构 → 统一 ProviderError；
- 工厂：环境变量选择供应商 / 默认 openai_compat / 未知名称 / 缺 API key。
"""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import ValidationError

from integrations.llm import (
    LLMMessage,
    LLMResult,
    OpenAICompatProvider,
    ProviderError,
    load_llm_provider,
)

MESSAGES = [
    LLMMessage(role="system", content="你是公众号写手"),
    LLMMessage(role="user", content="写一篇手冲咖啡入门"),
]

OK_BODY = {
    "model": "test-model",
    "choices": [{"message": {"role": "assistant", "content": "正文内容"}, "finish_reason": "stop"}],
}


def make_provider(handler) -> tuple[OpenAICompatProvider, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    provider = OpenAICompatProvider(
        api_key="sk-test",
        base_url="https://llm.test/v1",
        model="test-model",
        transport=httpx.MockTransport(record),
    )
    return provider, requests


def test_llm_message_rejects_unknown_role():
    with pytest.raises(ValidationError):
        LLMMessage(role="tool", content="x")


def test_complete_sends_standard_chat_completion_request():
    provider, requests = make_provider(lambda request: httpx.Response(200, json=OK_BODY))
    result = provider.complete(MESSAGES)
    assert str(requests[0].url) == "https://llm.test/v1/chat/completions"
    assert requests[0].headers["Authorization"] == "Bearer sk-test"
    payload = json.loads(requests[0].content)
    assert payload["model"] == "test-model"
    assert payload["messages"] == [
        {"role": "system", "content": "你是公众号写手"},
        {"role": "user", "content": "写一篇手冲咖啡入门"},
    ]
    assert "max_tokens" not in payload
    assert "temperature" not in payload
    assert result == LLMResult(text="正文内容", model="test-model", finish_reason="stop")
    provider.close()


def test_complete_passes_optional_params_when_given():
    provider, requests = make_provider(lambda request: httpx.Response(200, json=OK_BODY))
    provider.complete(MESSAGES, max_tokens=256, temperature=0.3)
    payload = json.loads(requests[0].content)
    assert payload["max_tokens"] == 256
    assert payload["temperature"] == 0.3
    provider.close()


def test_http_error_wrapped_as_provider_error():
    provider, _ = make_provider(lambda request: httpx.Response(500, text="server boom"))
    with pytest.raises(ProviderError, match="500"):
        provider.complete(MESSAGES)
    provider.close()


def test_network_error_wrapped_as_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider, _ = make_provider(handler)
    with pytest.raises(ProviderError, match="请求失败"):
        provider.complete(MESSAGES)
    provider.close()


def test_malformed_response_wrapped_as_provider_error():
    provider, _ = make_provider(lambda request: httpx.Response(200, json={"choices": []}))
    with pytest.raises(ProviderError, match="choices"):
        provider.complete(MESSAGES)
    provider.close()


def test_load_llm_provider_selects_by_env():
    provider = load_llm_provider(
        {
            "LLM_PROVIDER": "openai_compat",
            "LLM_API_KEY": "sk-env",
            "LLM_BASE_URL": "https://qwen.test/v1",
            "LLM_MODEL": "qwen-max",
        }
    )
    assert isinstance(provider, OpenAICompatProvider)
    assert provider.model == "qwen-max"
    provider.close()


def test_load_llm_provider_defaults_to_openai_compat():
    provider = load_llm_provider({"LLM_API_KEY": "sk-env"})
    assert isinstance(provider, OpenAICompatProvider)
    assert provider.model == "gpt-4o-mini"
    provider.close()


def test_load_llm_provider_unknown_name():
    with pytest.raises(ProviderError, match="未知 LLM_PROVIDER"):
        load_llm_provider({"LLM_PROVIDER": "nope", "LLM_API_KEY": "k"})


def test_load_llm_provider_missing_api_key():
    with pytest.raises(ProviderError, match="LLM_API_KEY"):
        load_llm_provider({})
