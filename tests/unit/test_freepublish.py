"""正式发布（freepublish）单元测试（N2-T5：全部 mock，CI 零网络）。

覆盖计划 N2 四条必需路径：
- 成功：submit → publish_id，get → publish_state=0 → published + article_url；
- errcode 失败：微信业务错误 → ProviderError（服务层）/ degraded（release 层）；
- HTTP 500 降级：API 不可用 → release 返回 degraded，绝不抛出；
- token 40001 重试：submit 首次 token 失效 → 废弃缓存刷新重试恰好一次成功。
"""

from __future__ import annotations

import json

import httpx
import pytest

from integrations.errors import ProviderError
from integrations.wechat import (
    FreepublishService,
    FreepublishStatus,
    TokenManager,
    WeChatClient,
    WeChatPublisher,
)

SUCCESS_GET = {
    "publish_id": "PUB-1",
    "publish_state": 0,
    "article_id": "ART-1",
    "article_detail": {
        "count": 1,
        "item": [{"article_url": "https://mp.weixin.qq.com/s/abc123", "index": 0}],
    },
}
IN_PROGRESS_GET = {"publish_id": "PUB-1", "publish_state": 4}
REVIEW_FAIL_GET = {"publish_id": "PUB-1", "publish_state": 1, "fail_idx": 0}


def make_freepublish(
    *,
    expire_first_submit: bool = False,
    submit_errcode: int | None = None,
    http_status: int | None = None,
    get_payloads: list[dict] | None = None,
):
    """构造挂 MockTransport 的 FreepublishService；get_payloads 依次消费，最后一个循环返回。"""
    requests: list[httpx.Request] = []
    state = {"tokens": 0, "submits": 0, "gets": 0}
    get_queue = list(get_payloads or [SUCCESS_GET])

    def handler(request: httpx.Request) -> httpx.Response:
        if http_status is not None:
            return httpx.Response(http_status, text="server error")
        if request.url.path == "/cgi-bin/token":
            state["tokens"] += 1
            return httpx.Response(
                200, json={"access_token": f"TOKEN-{state['tokens']}", "expires_in": 7200}
            )
        if request.url.path == "/cgi-bin/freepublish/submit":
            state["submits"] += 1
            if expire_first_submit and state["submits"] == 1:
                return httpx.Response(200, json={"errcode": 40001, "errmsg": "invalid credential"})
            if submit_errcode is not None:
                return httpx.Response(
                    200, json={"errcode": submit_errcode, "errmsg": "release rejected"}
                )
            return httpx.Response(200, json={"publish_id": "PUB-1"})
        if request.url.path == "/cgi-bin/freepublish/get":
            state["gets"] += 1
            payload = get_queue.pop(0) if len(get_queue) > 1 else get_queue[0]
            return httpx.Response(200, json=payload)
        return httpx.Response(404, text="not found")

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = WeChatClient(transport=httpx.MockTransport(record))
    tokens = TokenManager(
        client, app_id="wx-test-app", app_secret="secret-test", clock=lambda: 1000.0
    )
    service = FreepublishService(client, tokens)
    publisher = WeChatPublisher(client, tokens)
    return service, publisher, client, requests, state


def _no_sleep(seconds: float) -> None:
    return None


# ---------------------------------------------------------------------------
# FreepublishService：submit / status / wait
# ---------------------------------------------------------------------------


def test_submit_returns_publish_id():
    service, _, client, requests, state = make_freepublish()
    assert service.submit("DRAFT-1") == "PUB-1"
    assert state == {"tokens": 1, "submits": 1, "gets": 0}
    assert [r.url.path for r in requests] == ["/cgi-bin/token", "/cgi-bin/freepublish/submit"]
    assert json.loads(requests[1].content) == {"media_id": "DRAFT-1"}
    client.close()


def test_status_success_extracts_article_url():
    service, _, client, _, _ = make_freepublish()
    status = service.status("PUB-1")
    assert isinstance(status, FreepublishStatus)
    assert status.success is True
    assert status.in_progress is False
    assert status.article_id == "ART-1"
    assert status.article_url == "https://mp.weixin.qq.com/s/abc123"
    assert status.message == "发布成功"
    client.close()


def test_status_maps_failure_and_in_progress_states():
    service, _, client, _, _ = make_freepublish(get_payloads=[REVIEW_FAIL_GET, IN_PROGRESS_GET])
    failed = service.status("PUB-1")
    assert failed.success is False
    assert "审核" in failed.message
    assert "index=0" in failed.message
    assert service.status("PUB-1").in_progress is True
    client.close()


def test_submit_errcode_raises_provider_error():
    service, _, client, _, _ = make_freepublish(submit_errcode=53101)
    with pytest.raises(ProviderError) as exc_info:
        service.submit("DRAFT-1")
    assert exc_info.value.errcode == 53101
    client.close()


def test_submit_missing_publish_id_raises():
    requests_holder: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_holder.append(request)
        if request.url.path == "/cgi-bin/token":
            return httpx.Response(200, json={"access_token": "TOKEN-1", "expires_in": 7200})
        if request.url.path == "/cgi-bin/freepublish/submit":
            return httpx.Response(200, json={"errcode": 0})
        return httpx.Response(404, text="not found")

    client = WeChatClient(transport=httpx.MockTransport(handler))
    tokens = TokenManager(
        client, app_id="wx-test-app", app_secret="secret-test", clock=lambda: 1000.0
    )
    with pytest.raises(ProviderError, match="publish_id"):
        FreepublishService(client, tokens).submit("DRAFT-1")
    client.close()


def test_token_expiry_during_submit_retries_once():
    service, _, client, requests, state = make_freepublish(expire_first_submit=True)
    assert service.submit("DRAFT-1") == "PUB-1"
    assert state == {"tokens": 2, "submits": 2, "gets": 0}
    assert [r.url.path for r in requests] == [
        "/cgi-bin/token",
        "/cgi-bin/freepublish/submit",
        "/cgi-bin/token",
        "/cgi-bin/freepublish/submit",
    ]
    assert requests[3].url.params["access_token"] == "TOKEN-2"
    client.close()


def test_wait_polls_until_terminal():
    service, _, client, _, state = make_freepublish(
        get_payloads=[IN_PROGRESS_GET, IN_PROGRESS_GET, SUCCESS_GET]
    )
    sleeps: list[float] = []
    status = service.wait("PUB-1", max_polls=10, poll_interval=1.5, sleep=sleeps.append)
    assert status.success is True
    assert state["gets"] == 3
    assert sleeps == [1.5, 1.5]
    client.close()


def test_wait_returns_immediately_when_terminal():
    service, _, client, _, state = make_freepublish(get_payloads=[SUCCESS_GET])
    sleeps: list[float] = []
    status = service.wait("PUB-1", max_polls=5, sleep=sleeps.append)
    assert status.success is True
    assert state["gets"] == 1
    assert sleeps == []
    client.close()


def test_wait_timeout_keeps_in_progress_status():
    service, _, client, _, state = make_freepublish(get_payloads=[IN_PROGRESS_GET])
    status = service.wait("PUB-1", max_polls=2, poll_interval=0.0, sleep=_no_sleep)
    assert status.in_progress is True
    assert state["gets"] == 3  # 首查 + 2 次轮询
    client.close()


# ---------------------------------------------------------------------------
# WeChatPublisher.release()：四条必需路径
# ---------------------------------------------------------------------------


def test_release_success_returns_published(tmp_path):
    _, publisher, client, requests, state = make_freepublish()
    result = publisher.release(
        "DRAFT-1",
        media_id="MEDIA-1",
        html_path=str(tmp_path / "x.html"),
        sleep=_no_sleep,
    )
    assert result.status == "published"
    assert result.publish_id == "PUB-1"
    assert result.article_url == "https://mp.weixin.qq.com/s/abc123"
    assert result.draft_id == "DRAFT-1"
    assert result.media_id == "MEDIA-1"
    assert result.html_path == str(tmp_path / "x.html")
    assert result.degraded is False
    assert result.message == "发布成功"
    assert state == {"tokens": 1, "submits": 1, "gets": 1}
    assert [r.url.path for r in requests] == [
        "/cgi-bin/token",
        "/cgi-bin/freepublish/submit",
        "/cgi-bin/freepublish/get",
    ]
    client.close()


def test_release_errcode_failure_degrades_never_raises():
    _, publisher, client, _, _ = make_freepublish(submit_errcode=53101)
    result = publisher.release("DRAFT-1", media_id="MEDIA-1", html_path="out/x.html")
    assert result.status == "degraded"
    assert result.degraded is True
    assert result.draft_id == "DRAFT-1"
    assert result.publish_id == ""
    assert "errcode=53101" in result.message
    client.close()


def test_release_http_500_degrades():
    _, publisher, client, _, _ = make_freepublish(http_status=500)
    result = publisher.release("DRAFT-1", html_path="out/x.html")
    assert result.status == "degraded"
    assert result.degraded is True
    assert result.draft_id == "DRAFT-1"
    assert "HTTP 500" in result.message
    client.close()


def test_release_review_failure_degrades_with_state_message():
    _, publisher, client, _, _ = make_freepublish(get_payloads=[REVIEW_FAIL_GET])
    result = publisher.release("DRAFT-1", sleep=_no_sleep)
    assert result.status == "degraded"
    assert result.degraded is True
    assert result.publish_id == "PUB-1"
    assert "审核" in result.message
    client.close()


def test_release_poll_timeout_degrades():
    _, publisher, client, _, _ = make_freepublish(get_payloads=[IN_PROGRESS_GET])
    result = publisher.release("DRAFT-1", max_polls=2, poll_interval=0.0, sleep=_no_sleep)
    assert result.status == "degraded"
    assert result.degraded is True
    assert result.publish_id == "PUB-1"
    assert "发布中" in result.message
    client.close()


def test_release_without_draft_id_degrades_without_api_call():
    _, publisher, client, requests, state = make_freepublish()
    result = publisher.release("")
    assert result.status == "degraded"
    assert result.degraded is True
    assert "缺少草稿" in result.message
    assert requests == []
    assert state == {"tokens": 0, "submits": 0, "gets": 0}
    client.close()
