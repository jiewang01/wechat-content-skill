"""发布数据统计（datacube）单元测试（v0.3 计划 N2-T2/T4：全部 mock，CI 零网络）。

覆盖计划 N2 必需路径：
- 成功：完整 payload → 四级模型（ref_date/msgid → detail_list → read_user_source /
  read_jump_position），请求体 begin = end = date 锁定；
- 空数据：当日无群发 → 空 tuple（{"list": []} 与裸数组两种响应形态）；
- errcode：61500/61501 → ProviderError 语义化消息（errcode 保留）；
- token 40001 重试：首次失效 → 废弃缓存刷新重试恰好一次成功。

另有：日期预检（未来 / 今日 / 格式非法均客户端拦截、零网络请求）、
msgid（msg_data_id_index）拆装、publish_type 语义。
"""

from __future__ import annotations

import datetime
import json
from dataclasses import asdict

import httpx
import pytest

from integrations.errors import ProviderError
from integrations.wechat import (
    ArticleTotalDetail,
    DatacubeService,
    JumpPosition,
    ReadSource,
    TokenManager,
    WeChatClient,
)

ARTICLE_PAYLOAD = {
    "list": [
        {
            "ref_date": "2025-12-01",
            "msgid": "200000006_1",
            "publish_type": 0,
            "title": "嵌套卡片实战",
            "content_url": "https://mp.weixin.qq.com/s/abc123",
            "is_delay": 0,
            "detail_list": [
                {
                    "stat_date": "2025-12-01",
                    "read_user": 1200,
                    "read_user_source": [
                        {"type": 99999999, "value": 1200},
                        {"type": 99999925, "value": 640},
                    ],
                    "share_user": 88,
                    "zaikan_user": 40,
                    "like_user": 66,
                    "comment_count": 12,
                    "collection_user": 25,
                    "praise_money": 500,
                    "read_subscribe_user": 300,
                    "read_delivery_rate": 96.5,
                    "read_finish_rate": 42.0,
                    "read_avg_activetime": 3.5,
                    "read_jump_position": [
                        {"position": 1, "rate": 18.2},
                        {"position": 5, "rate": 9.1},
                    ],
                },
                {
                    "stat_date": "2025-12-02",
                    "read_user": 350,
                    "share_user": 10,
                    "zaikan_user": 5,
                    "like_user": 8,
                    "comment_count": 1,
                    "collection_user": 3,
                    "praise_money": 0,
                    "read_subscribe_user": 60,
                    "read_delivery_rate": 0.0,
                    "read_finish_rate": 0.0,
                    "read_avg_activetime": 0.0,
                },
            ],
        }
    ]
}


def make_datacube(
    *,
    payload: dict | list | None = None,
    errcode: int | None = None,
    expire_first: bool = False,
):
    """构造挂 MockTransport 的 DatacubeService，并记录全部请求与调用计数。"""
    requests: list[httpx.Request] = []
    state = {"tokens": 0, "stats": 0}
    body = ARTICLE_PAYLOAD if payload is None else payload

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/token":
            state["tokens"] += 1
            return httpx.Response(
                200, json={"access_token": f"TOKEN-{state['tokens']}", "expires_in": 7200}
            )
        if request.url.path == "/cgi-bin/datacube/getarticletotaldetail":
            state["stats"] += 1
            if expire_first and state["stats"] == 1:
                return httpx.Response(200, json={"errcode": 40001, "errmsg": "invalid credential"})
            if errcode is not None:
                return httpx.Response(
                    200, json={"errcode": errcode, "errmsg": "datacube rejected"}
                )
            return httpx.Response(200, json=body)
        return httpx.Response(404, text="not found")

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = WeChatClient(transport=httpx.MockTransport(record))
    tokens = TokenManager(
        client, app_id="wx-test-app", app_secret="secret-test", clock=lambda: 1000.0
    )
    return DatacubeService(client, tokens), client, requests, state


# ---------------------------------------------------------------------------
# 成功路径：全量字段解析 + 请求形状
# ---------------------------------------------------------------------------


def test_article_stats_success_parses_full_payload():
    service, client, requests, state = make_datacube()
    articles = service.article_stats("2025-12-01")
    assert state == {"tokens": 1, "stats": 1}
    assert [r.url.path for r in requests] == [
        "/cgi-bin/token",
        "/cgi-bin/datacube/getarticletotaldetail",
    ]
    assert requests[1].url.params["access_token"] == "TOKEN-1"
    assert json.loads(requests[1].content) == {
        "begin_date": "2025-12-01",
        "end_date": "2025-12-01",
    }

    (article,) = articles
    assert isinstance(article, ArticleTotalDetail)
    assert article.ref_date == "2025-12-01"
    assert article.title == "嵌套卡片实战"
    assert article.content_url == "https://mp.weixin.qq.com/s/abc123"
    assert article.notified_subscribers is True
    assert article.is_delay == 0
    assert len(article.detail_list) == 2

    first = article.detail_list[0]
    assert first.stat_date == "2025-12-01"
    assert first.read_user == 1200
    assert first.share_user == 88
    assert first.zaikan_user == 40
    assert first.like_user == 66
    assert first.comment_count == 12
    assert first.collection_user == 25
    assert first.praise_money == 500
    assert first.read_subscribe_user == 300
    assert first.read_delivery_rate == 96.5
    assert first.read_finish_rate == 42.0
    assert first.read_avg_activetime == 3.5
    assert first.read_user_source == (
        ReadSource(type=99999999, value=1200),
        ReadSource(type=99999925, value=640),
    )
    assert first.read_jump_position == (
        JumpPosition(position=1, rate=18.2),
        JumpPosition(position=5, rate=9.1),
    )

    second = article.detail_list[1]
    assert second.read_user == 350
    assert second.read_user_source == ()
    assert second.read_jump_position == ()
    client.close()


def test_article_stats_asdict_directly_json_serializable():
    service, client, _, _ = make_datacube()
    (article,) = service.article_stats("2025-12-01")
    data = asdict(article)
    text = json.dumps(data, ensure_ascii=False)
    assert "嵌套卡片实战" in text
    assert data["detail_list"][0]["read_user_source"][0] == {"type": 99999999, "value": 1200}
    assert data["detail_list"][0]["read_jump_position"][1] == {"position": 5, "rate": 9.1}
    client.close()


def test_bare_list_response_shape_also_parsed():
    service, client, _, _ = make_datacube(payload=ARTICLE_PAYLOAD["list"])
    (article,) = service.article_stats("2025-12-01")
    assert article.msgid == "200000006_1"
    assert len(article.detail_list) == 2
    client.close()


# ---------------------------------------------------------------------------
# 空数据 / errcode / token 失效重试
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", [{"list": []}, []], ids=["empty-list-key", "bare-empty"])
def test_article_stats_empty_data_returns_empty_tuple(payload):
    service, client, _, state = make_datacube(payload=payload)
    assert service.article_stats("2025-12-01") == ()
    assert state == {"tokens": 1, "stats": 1}
    client.close()


@pytest.mark.parametrize("errcode,fragment", [(61500, "日期格式"), (61501, "日期范围")])
def test_article_stats_errcode_semantic_provider_error(errcode, fragment):
    service, client, _, _ = make_datacube(errcode=errcode)
    with pytest.raises(ProviderError) as exc_info:
        service.article_stats("2025-12-01")
    assert exc_info.value.errcode == errcode
    assert fragment in str(exc_info.value)
    assert "date=2025-12-01" in str(exc_info.value)
    client.close()


def test_token_expiry_during_stats_retries_once():
    service, client, requests, state = make_datacube(expire_first=True)
    articles = service.article_stats("2025-12-01")
    assert len(articles) == 1
    assert state == {"tokens": 2, "stats": 2}
    assert [r.url.path for r in requests] == [
        "/cgi-bin/token",
        "/cgi-bin/datacube/getarticletotaldetail",
        "/cgi-bin/token",
        "/cgi-bin/datacube/getarticletotaldetail",
    ]
    assert requests[3].url.params["access_token"] == "TOKEN-2"
    client.close()


# ---------------------------------------------------------------------------
# 日期客户端预检：零网络请求
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("date", ["2099-01-01", "2100-12-31"])
def test_future_date_rejected_client_side(date):
    service, client, requests, state = make_datacube()
    with pytest.raises(ProviderError, match="昨日"):
        service.article_stats(date)
    assert requests == []
    assert state == {"tokens": 0, "stats": 0}
    client.close()


def test_today_and_tomorrow_rejected_client_side():
    service, client, requests, state = make_datacube()
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    with pytest.raises(ProviderError, match="昨日"):
        service.article_stats(today.isoformat())
    with pytest.raises(ProviderError, match="昨日"):
        service.article_stats(tomorrow.isoformat())
    assert requests == []
    assert state == {"tokens": 0, "stats": 0}
    client.close()


@pytest.mark.parametrize(
    "date",
    ["2025/12/01", "20251201", "2025-12-1", "25-12-01", "not-a-date", ""],
)
def test_invalid_date_format_rejected_client_side(date):
    service, client, requests, state = make_datacube()
    with pytest.raises(ProviderError, match="日期格式"):
        service.article_stats(date)
    assert requests == []
    assert state == {"tokens": 0, "stats": 0}
    client.close()


def test_data_start_date_is_queryable_boundary_constant():
    from integrations.wechat.datacube import DATA_START_DATE

    assert DATA_START_DATE == datetime.date(2025, 11, 1)


# ---------------------------------------------------------------------------
# msgid（msg_data_id_index）拆装与 publish_type 语义
# ---------------------------------------------------------------------------


def test_msgid_parses_msg_data_id_and_index():
    service, client, _, _ = make_datacube()
    (article,) = service.article_stats("2025-12-01")
    assert article.msgid == "200000006_1"
    assert article.msg_data_id == "200000006"
    assert article.msg_index == 1
    client.close()


def test_msgid_variants_default_to_head_article():
    head = ArticleTotalDetail(
        ref_date="2025-12-01", msgid="200000006", title="头条", content_url=""
    )
    assert head.msg_data_id == "200000006"
    assert head.msg_index == 1

    tail = ArticleTotalDetail(
        ref_date="2025-12-01", msgid="200000006_3", title="第三条", content_url=""
    )
    assert tail.msg_data_id == "200000006"
    assert tail.msg_index == 3

    broken = ArticleTotalDetail(
        ref_date="2025-12-01", msgid="200000006_x", title="坏下标", content_url=""
    )
    assert broken.msg_data_id == "200000006"
    assert broken.msg_index == 1


def test_publish_type_semantics():
    notified = ArticleTotalDetail(
        ref_date="d", msgid="m_1", title="t", content_url="", publish_type=0
    )
    silent = ArticleTotalDetail(
        ref_date="d", msgid="m_1", title="t", content_url="", publish_type=1
    )
    assert notified.notified_subscribers is True
    assert silent.notified_subscribers is False
