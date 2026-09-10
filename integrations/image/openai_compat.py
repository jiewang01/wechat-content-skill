"""OpenAI 兼容 Images 实现（DALL·E / Flux / Gemini Image 兼容模式通用网关）。

环境变量契约（from_env）：
- IMAGE_API_KEY：必填，Bearer 凭证；
- IMAGE_BASE_URL：默认 https://api.openai.com/v1；
- IMAGE_MODEL：默认 dall-e-3；
- IMAGE_TIMEOUT：默认 60（秒），图片生成耗时显著长于文本。

响应兼容两种形态：{"data": [{"url": ...}]} 或 {"data": [{"b64_json": ...}]}
（后者转 data URI）。测试注入 httpx.MockTransport 离线运行（CI 无网络依赖）。
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from integrations.errors import ProviderError

from .base import ImageAsset

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "dall-e-3"
DEFAULT_TIMEOUT = 60.0
DEFAULT_SIZE = "1024x1024"


class OpenAIImageProvider:
    """走 OpenAI 风格 POST /images/generations 的最小客户端。"""

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
    def from_env(cls, env: Mapping[str, str]) -> OpenAIImageProvider:
        api_key = env.get("IMAGE_API_KEY", "")
        if not api_key:
            raise ProviderError("缺少环境变量 IMAGE_API_KEY（无法构造 Image Provider）")
        return cls(
            api_key=api_key,
            base_url=env.get("IMAGE_BASE_URL", DEFAULT_BASE_URL),
            model=env.get("IMAGE_MODEL", DEFAULT_MODEL),
            timeout=float(env.get("IMAGE_TIMEOUT", str(DEFAULT_TIMEOUT))),
        )

    def generate(self, prompt: str, *, size: str = DEFAULT_SIZE) -> ImageAsset:
        payload: dict = {"model": self._model, "prompt": prompt, "size": size, "n": 1}
        try:
            response = self._client.post("images/generations", json=payload)
        except httpx.HTTPError as exc:
            raise ProviderError(f"图片生成请求失败：{exc}") from exc
        if response.status_code != 200:
            raise ProviderError(f"图片服务返回 HTTP {response.status_code}：{response.text[:200]}")
        try:
            data = response.json()["data"][0]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"图片响应缺少 data 结构：{exc}") from exc
        url = data.get("url") or ""
        b64 = data.get("b64_json") or ""
        if url:
            return ImageAsset(url=url, source="generated", prompt=prompt)
        if b64:
            return ImageAsset(url=f"data:image/png;base64,{b64}", source="generated", prompt=prompt)
        raise ProviderError("图片响应既无 url 也无 b64_json")

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> OpenAIImageProvider:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
