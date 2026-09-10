"""微信 client / auth / 多账号配置单测（蓝图十三章/十四章，计划 M5-T4/T7）。

- client：GET/POST 形状 / errcode 业务错误 / HTTP / 网络 / 非 JSON 五类封装；
- auth：token 获取 / 缓存命中 / 假时钟驱动的过期自动刷新（M5-T4 DoD）/ invalidate；
- accounts.example.yaml：只引用环境变量，配置中 grep 不到真实密钥（M5-T7 DoD）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import pytest
import yaml

from integrations.errors import ProviderError
from integrations.wechat import TokenManager, WeChatClient

REPO = Path(__file__).resolve().parent.parent.parent

TOKEN_BODY = {"access_token": "TOKEN-1", "expires_in": 7200}


def make_client(handler) -> tuple[WeChatClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = WeChatClient(transport=httpx.MockTransport(record))
    return client, requests


def make_clock(start: float = 0.0):
    state = {"now": start}

    def advance(seconds: float) -> None:
        state["now"] += seconds

    return (lambda: state["now"]), advance


def make_manager(handler):
    clock, advance = make_clock()
    client, requests = make_client(handler)
    manager = TokenManager(
        client,
        app_id="wx-test-app",
        app_secret="secret-test",
        clock=clock,
    )
    return manager, requests, advance, client


def test_get_sends_params_and_parses_json():
    client, requests = make_client(lambda request: httpx.Response(200, json={"ok": 1}))
    data = client.get("cgi-bin/token", {"grant_type": "client_credential"})
    assert data == {"ok": 1}
    assert requests[0].url.path == "/cgi-bin/token"
    assert requests[0].url.params["grant_type"] == "client_credential"
    client.close()


def test_get_errcode_response_raises_provider_error():
    body = {"errcode": 45009, "errmsg": "reach max api daily quota"}
    client, _ = make_client(lambda request: httpx.Response(200, json=body))
    with pytest.raises(ProviderError, match="45009"):
        client.get("cgi-bin/token", {"grant_type": "client_credential"})
    client.close()


def test_post_sends_json_body_and_query():
    client, requests = make_client(lambda request: httpx.Response(200, json={"media_id": "MID"}))
    data = client.post(
        "cgi-bin/draft/add", params={"access_token": "T"}, json={"title": "手冲咖啡"}
    )
    assert data == {"media_id": "MID"}
    assert requests[0].url.params["access_token"] == "T"
    assert json.loads(requests[0].content) == {"title": "手冲咖啡"}
    client.close()


def test_http_error_wrapped_as_provider_error():
    client, _ = make_client(lambda request: httpx.Response(502, text="bad gateway"))
    with pytest.raises(ProviderError, match="502"):
        client.get("cgi-bin/token", {"grant_type": "client_credential"})
    client.close()


def test_network_error_wrapped_as_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client, _ = make_client(handler)
    with pytest.raises(ProviderError, match="请求失败"):
        client.get("cgi-bin/token", {"grant_type": "client_credential"})
    client.close()


def test_non_json_response_wrapped_as_provider_error():
    client, _ = make_client(lambda request: httpx.Response(200, text="Gateway Timeout"))
    with pytest.raises(ProviderError, match="JSON"):
        client.get("cgi-bin/token", {"grant_type": "client_credential"})
    client.close()


def test_get_token_fetches_from_wechat_endpoint():
    manager, requests, _, client = make_manager(
        lambda request: httpx.Response(200, json=TOKEN_BODY)
    )
    assert manager.get_token() == "TOKEN-1"
    assert requests[0].url.path == "/cgi-bin/token"
    assert requests[0].url.params["grant_type"] == "client_credential"
    assert requests[0].url.params["appid"] == "wx-test-app"
    assert requests[0].url.params["secret"] == "secret-test"
    client.close()


def test_get_token_caches_within_lifetime():
    manager, requests, advance, client = make_manager(
        lambda request: httpx.Response(200, json=TOKEN_BODY)
    )
    assert manager.get_token() == "TOKEN-1"
    advance(6000)
    assert manager.get_token() == "TOKEN-1"
    assert len(requests) == 1
    client.close()


def test_get_token_cached_just_before_refresh_point():
    manager, requests, advance, client = make_manager(
        lambda request: httpx.Response(200, json=TOKEN_BODY)
    )
    manager.get_token()
    advance(6899)
    assert manager.get_token() == "TOKEN-1"
    assert len(requests) == 1
    client.close()


def test_get_token_refreshes_after_expiry():
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(
            200, json={"access_token": f"TOKEN-{counter['n']}", "expires_in": 7200}
        )

    manager, requests, advance, client = make_manager(handler)
    assert manager.get_token() == "TOKEN-1"
    advance(7000)
    assert manager.get_token() == "TOKEN-2"
    assert len(requests) == 2
    client.close()


def test_get_token_refresh_error_wrapped():
    body = {"errcode": 40013, "errmsg": "invalid appid"}
    manager, _, _, client = make_manager(lambda request: httpx.Response(200, json=body))
    with pytest.raises(ProviderError, match="40013"):
        manager.get_token()
    client.close()


def test_get_token_missing_token_raises():
    manager, _, _, client = make_manager(
        lambda request: httpx.Response(200, json={"expires_in": 7200})
    )
    with pytest.raises(ProviderError, match="access_token"):
        manager.get_token()
    client.close()


def test_invalidate_forces_refresh():
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(
            200, json={"access_token": f"TOKEN-{counter['n']}", "expires_in": 7200}
        )

    manager, requests, _, client = make_manager(handler)
    assert manager.get_token() == "TOKEN-1"
    manager.invalidate()
    assert manager.get_token() == "TOKEN-2"
    assert len(requests) == 2
    client.close()


def test_accounts_example_references_env_vars_only():
    raw = (REPO / "accounts" / "accounts.example.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    assert data["name"] == "Tech Account"
    env = data["env"]
    assert set(env) == {"app_id", "app_secret"}
    for key, value in env.items():
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", value), f"{key} 必须是环境变量引用：{value}"
