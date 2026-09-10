"""微信官方 API 最小 HTTP 客户端（蓝图十三章，计划 M5-T4）。

只做三件事：拼 URL、发请求、把失败统一封装成 ProviderError——
- 网络异常 / HTTP 非 200 / 响应非 JSON；
- 微信业务错误（HTTP 200 但 errcode != 0）。

上层（TokenManager / Facade）不接触 httpx 细节。
测试注入 httpx.MockTransport 离线运行（CI 无网络依赖）。
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from integrations.errors import ProviderError

BASE_URL = "https://api.weixin.qq.com"
DEFAULT_TIMEOUT = 10.0


def _parse(response: httpx.Response) -> dict:
    if response.status_code != 200:
        raise ProviderError(f"微信 API 返回 HTTP {response.status_code}：{response.text[:200]}")
    try:
        data = response.json()
    except ValueError as exc:
        raise ProviderError(f"微信 API 响应不是 JSON：{exc}") from exc
    if isinstance(data, dict) and data.get("errcode", 0) != 0:
        errcode = data.get("errcode")
        errmsg = data.get("errmsg", "")
        code = errcode if isinstance(errcode, int) else None
        raise ProviderError(f"微信 API 错误 errcode={errcode}：{errmsg}", errcode=code)
    return data


class WeChatClient:
    """api.weixin.qq.com 的薄封装：GET/POST + 统一错误解析。"""

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            timeout=timeout,
            transport=transport,
        )

    def get(self, path: str, params: Mapping[str, str]) -> dict:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ProviderError(f"微信 API 请求失败：{exc}") from exc
        return _parse(response)

    def post(
        self,
        path: str,
        params: Mapping[str, str] | None = None,
        json: dict | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> dict:
        try:
            response = self._client.post(path, params=params, json=json, files=files)
        except httpx.HTTPError as exc:
            raise ProviderError(f"微信 API 请求失败：{exc}") from exc
        return _parse(response)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> WeChatClient:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
