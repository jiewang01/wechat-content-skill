"""OpenAI 兼容 Chat Completions 实现（Qwen / DeepSeek / Gemini 兼容模式通用网关）。

环境变量契约（from_env）：
    LLM_API_KEY    必填，缺失抛 ProviderError；
    LLM_BASE_URL   默认 https://api.openai.com/v1（自有网关可覆盖）；
    LLM_MODEL      默认 gpt-4o-mini；
    LLM_TIMEOUT    默认 30 秒。

测试注入 httpx.MockTransport 离线运行（CI 无网络依赖）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import httpx

from integrations.errors import ProviderError

from .base import LLMMessage, LLMResult

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT = 30.0


class OpenAICompatProvider:
    """走 OpenAI 风格 POST /chat/completions 的最小客户端。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            transport=transport,
        )

    @property
    def model(self) -> str:
        return self._model

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> OpenAICompatProvider:
        api_key = env.get("LLM_API_KEY", "")
        if not api_key:
            raise ProviderError("缺少环境变量 LLM_API_KEY（无法构造 LLM Provider）")
        return cls(
            api_key=api_key,
            base_url=env.get("LLM_BASE_URL", DEFAULT_BASE_URL),
            model=env.get("LLM_MODEL", DEFAULT_MODEL),
            timeout=float(env.get("LLM_TIMEOUT", str(DEFAULT_TIMEOUT))),
        )

    def complete(
        self,
        messages: Sequence[LLMMessage],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        payload: dict = {
            "model": self._model,
            "messages": [message.model_dump() for message in messages],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        try:
            response = self._client.post("chat/completions", json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError(f"LLM 请求失败：{exc}") from exc
        if response.status_code != 200:
            raise ProviderError(f"LLM 服务返回 HTTP {response.status_code}：{response.text[:200]}")
        try:
            data = response.json()
            choice = data["choices"][0]
            return LLMResult(
                text=choice["message"]["content"],
                model=data.get("model", self._model),
                finish_reason=choice.get("finish_reason", ""),
            )
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"LLM 响应缺少 choices 结构：{exc}") from exc

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenAICompatProvider:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
