"""access_token 获取、缓存与过期刷新（蓝图十三章 AuthProvider，计划 M5-T4）。

微信 access_token 有效期 7200 秒；提前 refresh_margin（默认 300 秒）刷新，
避免拿到临期 token 调业务接口失败。clock 可注入，单测用假时钟驱动过期
（M5-T4 DoD：token 过期自动刷新有单测）。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from integrations.errors import ProviderError

from .client import WeChatClient

TOKEN_PATH = "cgi-bin/token"
DEFAULT_EXPIRES_IN = 7200.0
DEFAULT_REFRESH_MARGIN = 300.0


class TokenManager:
    """蓝图十三章 AuthProvider 角色：token 的唯一出口，缓存 + 自动续期。"""

    def __init__(
        self,
        client: WeChatClient,
        *,
        app_id: str,
        app_secret: str,
        clock: Callable[[], float] | None = None,
        refresh_margin: float = DEFAULT_REFRESH_MARGIN,
    ) -> None:
        self._client = client
        self._app_id = app_id
        self._app_secret = app_secret
        self._clock = clock or time.monotonic
        self._refresh_margin = refresh_margin
        self._token = ""
        self._expires_at = 0.0

    def get_token(self) -> str:
        """返回有效 token；无缓存或临期（超过有效期减安全边际）时自动刷新。"""
        if self._token and self._clock() < self._expires_at - self._refresh_margin:
            return self._token
        return self._refresh()

    def invalidate(self) -> None:
        """丢弃缓存（业务方收到 40001/42001 时强制下次重取）。"""
        self._token = ""
        self._expires_at = 0.0

    def _refresh(self) -> str:
        data = self._client.get(
            TOKEN_PATH,
            {
                "grant_type": "client_credential",
                "appid": self._app_id,
                "secret": self._app_secret,
            },
        )
        token = data.get("access_token", "")
        if not token:
            raise ProviderError("微信 token 响应缺少 access_token")
        expires_in = data.get("expires_in", DEFAULT_EXPIRES_IN)
        self._token = str(token)
        self._expires_at = self._clock() + float(expires_in)
        return self._token


TOKEN_EXPIRED_CODES = frozenset({40001, 42001})
T = TypeVar("T")


def call_with_token_retry(tokens: TokenManager, call: Callable[[], T]) -> T:
    """执行一次微信调用；命中 40001/42001（token 失效）时废弃缓存并重试一次。"""
    try:
        return call()
    except ProviderError as exc:
        if getattr(exc, "errcode", None) in TOKEN_EXPIRED_CODES:
            tokens.invalidate()
            return call()
        raise
