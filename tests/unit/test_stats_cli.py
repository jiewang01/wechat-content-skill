"""scripts/stats.py CLI 测试：进程内调用 + transport 注入（CI 零网络，v0.3 计划 N2-T3/T4）。

覆盖计划 N2-T3 验收：
- 成功：stdout 摘要 + outputs/stats/<date>_article_stats.json 回执（asdict 全量明细）；
- --date 缺省 = 昨日（today 注入口）；--account 选择账号配置；
- 幂等：重复运行覆盖同一回执文件，内容不变；
- 空数据：article_count=0 回执照写；
- 查询失败：61500 → 退出码 1；未来日期 → 预检拦截零网络 → 退出码 1；
- 环境错误：账号配置缺失 / 凭据未设置 → 退出码 2（可行动提示）。
"""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from scripts.stats import main

PAYLOAD = {
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


@pytest.fixture
def stats_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    accounts = tmp_path / "accounts"
    accounts.mkdir()
    (accounts / "default.yaml").write_text(
        "name: default\n"
        "env:\n"
        "  app_id: WECHAT_APP_ID_TEST\n"
        "  app_secret: WECHAT_APP_SECRET_TEST\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WECHAT_APP_ID_TEST", "wx-test-app")
    monkeypatch.setenv("WECHAT_APP_SECRET_TEST", "secret-test")
    return tmp_path


def make_transport(payload=None, *, errcode=None):
    requests: list[httpx.Request] = []
    body = PAYLOAD if payload is None else payload

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/cgi-bin/token":
            return httpx.Response(200, json={"access_token": "TOKEN-1", "expires_in": 7200})
        if errcode is not None:
            return httpx.Response(200, json={"errcode": errcode, "errmsg": "datacube rejected"})
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler), requests


# ---------------------------------------------------------------------------
# 成功路径：回执留档 + 终端摘要
# ---------------------------------------------------------------------------


def test_success_writes_receipt_and_prints_summary(stats_env, capsys):
    transport, requests = make_transport()
    assert main(["--date", "2025-12-01"], transport=transport) == 0

    receipt = stats_env / "outputs" / "stats" / "2025-12-01_article_stats.json"
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["date"] == "2025-12-01"
    assert data["account"] == "default"
    assert data["article_count"] == 1
    assert data["articles"][0]["msgid"] == "200000006_1"
    assert data["articles"][0]["detail_list"][0]["read_user_source"][0] == {
        "type": 99999999,
        "value": 1200,
    }
    assert data["articles"][0]["detail_list"][1]["stat_date"] == "2025-12-02"

    assert json.loads(requests[1].content) == {
        "begin_date": "2025-12-01",
        "end_date": "2025-12-01",
    }

    captured = capsys.readouterr()
    assert "date=2025-12-01 account=default articles=1" in captured.out
    assert "嵌套卡片实战" in captured.out
    assert "阅读=1200" in captured.out
    assert "完读率=42.0%" in captured.out
    assert "合计（发表当日口径）：阅读 1200 · 分享 88 · 在看 40 · 点赞 66" in captured.out
    assert "回执：outputs/stats/2025-12-01_article_stats.json" in captured.out
    assert "OK: 1 articles (date=2025-12-01)" in captured.err


def test_default_date_is_yesterday(stats_env):
    transport, requests = make_transport()
    assert main([], transport=transport, today=datetime.date(2025, 12, 2)) == 0

    receipt = stats_env / "outputs" / "stats" / "2025-12-01_article_stats.json"
    assert receipt.is_file()
    assert json.loads(requests[1].content)["begin_date"] == "2025-12-01"


def test_account_flag_selects_config(stats_env, monkeypatch):
    (stats_env / "accounts" / "team-a.yaml").write_text(
        "name: team-a\n"
        "env:\n"
        "  app_id: WECHAT_APP_ID_TEAM\n"
        "  app_secret: WECHAT_APP_SECRET_TEAM\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("WECHAT_APP_ID_TEAM", "wx-team")
    monkeypatch.setenv("WECHAT_APP_SECRET_TEAM", "secret-team")

    transport, _ = make_transport()
    assert main(["--account", "team-a"], transport=transport,
                today=datetime.date(2025, 12, 2)) == 0

    receipt = stats_env / "outputs" / "stats" / "2025-12-01_article_stats.json"
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["account"] == "team-a"


def test_rerun_overwrites_receipt_idempotently(stats_env):
    transport, _ = make_transport()
    assert main(["--date", "2025-12-01"], transport=transport) == 0
    receipt = stats_env / "outputs" / "stats" / "2025-12-01_article_stats.json"
    first = receipt.read_text(encoding="utf-8")

    assert main(["--date", "2025-12-01"], transport=transport) == 0
    assert receipt.read_text(encoding="utf-8") == first


# ---------------------------------------------------------------------------
# 空数据 / 查询失败 / 预检拦截
# ---------------------------------------------------------------------------


def test_empty_data_writes_zero_receipt(stats_env, capsys):
    transport, _ = make_transport({"list": []})
    assert main(["--date", "2025-12-01"], transport=transport) == 0

    receipt = stats_env / "outputs" / "stats" / "2025-12-01_article_stats.json"
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["article_count"] == 0
    assert data["articles"] == []

    captured = capsys.readouterr()
    assert "articles=0" in captured.out
    assert "当日无群发文章" in captured.out
    assert "OK: 0 articles (date=2025-12-01)" in captured.err


def test_wechat_errcode_exits_1_without_receipt(stats_env, capsys):
    transport, _ = make_transport(errcode=61500)
    assert main(["--date", "2025-12-01"], transport=transport) == 1

    captured = capsys.readouterr()
    assert "日期格式" in captured.err
    assert not (stats_env / "outputs" / "stats" / "2025-12-01_article_stats.json").exists()


def test_future_date_exits_1_zero_network(stats_env, capsys):
    transport, requests = make_transport()
    assert main(["--date", "2099-01-01"], transport=transport) == 1

    captured = capsys.readouterr()
    assert "超出可查询范围" in captured.err
    assert requests == []


# ---------------------------------------------------------------------------
# 环境错误：可行动提示 + 退出码 2
# ---------------------------------------------------------------------------


def test_missing_account_config_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["--date", "2025-12-01"]) == 2

    captured = capsys.readouterr()
    assert "accounts.example.yaml" in captured.err


def test_missing_credentials_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    accounts = tmp_path / "accounts"
    accounts.mkdir()
    (accounts / "default.yaml").write_text(
        "name: default\n"
        "env:\n"
        "  app_id: WECHAT_APP_ID_TEST\n"
        "  app_secret: WECHAT_APP_SECRET_TEST\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("WECHAT_APP_ID_TEST", raising=False)
    monkeypatch.delenv("WECHAT_APP_SECRET_TEST", raising=False)

    assert main(["--date", "2025-12-01"]) == 2

    captured = capsys.readouterr()
    assert "set WECHAT_APP_ID_TEST and WECHAT_APP_SECRET_TEST" in captured.err
