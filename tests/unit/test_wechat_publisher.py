"""发布 Facade 单测（蓝图十二章/十三章，计划 M5-T6）。

- 三出口语义：draft_created / degraded（无封面或微信 API 失败）/ failed（本地导出失败）；
- 请求编排：token → add_material → draft/add，上层零感知 access_token / media_id 细节（T6 DoD）；
- 封面解析：显式 cover_path 优先于 doc.cover_asset，支持本地文件与 data URI（b64 图片 / utf8 SVG）；
- 本地留档：非 failed 出口均落 html_path；标题转 slug（中文保留、纯符号回退 article）。
全部经 httpx.MockTransport 离线运行，不触网（H6 / M5-T9）。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from urllib.parse import quote

import httpx

from core.artifacts.models import WechatDocument
from integrations.wechat import TokenManager, WeChatClient, WeChatPublisher

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-cover-data"
COVER_URL = "https://mmbiz.qpic.cn/mmbiz_png/cover.png"


def make_publisher(
    output_dir: Path,
    *,
    add_material_error: int | None = None,
    draft_error: int | None = None,
    draft_payload: dict | None = None,
) -> tuple[WeChatPublisher, list[httpx.Request], dict, WeChatClient]:
    requests: list[httpx.Request] = []
    state = {"tokens": 0, "drafts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/token":
            state["tokens"] += 1
            return httpx.Response(
                200, json={"access_token": f"TOKEN-{state['tokens']}", "expires_in": 7200}
            )
        if request.url.path == "/cgi-bin/material/add_material":
            if add_material_error is not None:
                return httpx.Response(
                    200, json={"errcode": add_material_error, "errmsg": "api error"}
                )
            return httpx.Response(200, json={"media_id": "MEDIA-1", "url": COVER_URL})
        if request.url.path == "/cgi-bin/draft/add":
            state["drafts"] += 1
            if draft_error is not None:
                return httpx.Response(200, json={"errcode": draft_error, "errmsg": "api error"})
            body = draft_payload if draft_payload is not None else {"media_id": "DRAFT-1"}
            return httpx.Response(200, json=body)
        return httpx.Response(404, text="not found")

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = WeChatClient(transport=httpx.MockTransport(record))
    tokens = TokenManager(
        client, app_id="wx-test-app", app_secret="secret-test", clock=lambda: 1000.0
    )
    publisher = WeChatPublisher(client, tokens, output_dir=output_dir)
    return publisher, requests, state, client


def make_doc(**overrides) -> WechatDocument:
    fields = {
        "title": "手冲咖啡完整指南",
        "digest": "三段式冲煮法",
        "html": '<section style="margin:0"><p>正文</p></section>',
        "cover_asset": "",
    }
    fields.update(overrides)
    return WechatDocument(**fields)


def write_cover(tmp_path: Path) -> Path:
    path = tmp_path / "cover.png"
    path.write_bytes(PNG_BYTES)
    return path


def test_create_draft_success_with_explicit_cover_path(tmp_path: Path):
    out = tmp_path / "out"
    publisher, requests, state, client = make_publisher(out)
    cover = write_cover(tmp_path)
    doc = make_doc()
    result = publisher.create_draft(doc, author="老王", cover_path=cover)
    assert result.status == "draft_created"
    assert result.media_id == "MEDIA-1"
    assert result.draft_id == "DRAFT-1"
    assert result.degraded is False
    assert state == {"tokens": 1, "drafts": 1}
    assert [r.url.path for r in requests] == [
        "/cgi-bin/token",
        "/cgi-bin/material/add_material",
        "/cgi-bin/draft/add",
    ]
    upload = requests[1]
    assert upload.url.params["access_token"] == "TOKEN-1"
    assert upload.url.params["type"] == "image"
    assert PNG_BYTES in upload.content
    article = json.loads(requests[2].content)["articles"][0]
    assert article["title"] == doc.title
    assert article["author"] == "老王"
    assert article["digest"] == doc.digest
    assert article["content"] == doc.html
    assert article["thumb_media_id"] == "MEDIA-1"
    assert article["show_cover_pic"] == 0
    exported = Path(result.html_path)
    assert exported.parent == out
    assert exported.name == "手冲咖啡完整指南.html"
    assert exported.read_text(encoding="utf-8-sig") == doc.html
    client.close()


def test_create_draft_uses_doc_cover_asset_when_no_explicit_path(tmp_path: Path):
    publisher, requests, _, client = make_publisher(tmp_path / "out")
    cover = write_cover(tmp_path)
    result = publisher.create_draft(make_doc(cover_asset=str(cover)))
    assert result.status == "draft_created"
    assert PNG_BYTES in requests[1].content
    client.close()


def test_create_draft_author_defaults_to_empty(tmp_path: Path):
    publisher, requests, _, client = make_publisher(tmp_path / "out")
    cover = write_cover(tmp_path)
    result = publisher.create_draft(make_doc(cover_asset=str(cover)))
    assert result.status == "draft_created"
    article = json.loads(requests[2].content)["articles"][0]
    assert article["author"] == ""
    client.close()


def test_create_draft_base64_data_uri_cover(tmp_path: Path):
    publisher, requests, _, client = make_publisher(tmp_path / "out")
    encoded = base64.b64encode(PNG_BYTES).decode("ascii")
    doc = make_doc(cover_asset=f"data:image/png;base64,{encoded}")
    result = publisher.create_draft(doc)
    assert result.status == "draft_created"
    upload = requests[1]
    assert b"cover.png" in upload.content
    assert PNG_BYTES in upload.content
    client.close()


def test_create_draft_svg_data_uri_cover(tmp_path: Path):
    publisher, requests, _, client = make_publisher(tmp_path / "out")
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"></svg>'
    doc = make_doc(cover_asset="data:image/svg+xml," + quote(svg))
    result = publisher.create_draft(doc)
    assert result.status == "draft_created"
    upload = requests[1]
    assert b"cover.svg" in upload.content
    assert svg.encode("utf-8") in upload.content
    client.close()


def test_create_draft_without_cover_degrades_without_any_request(tmp_path: Path):
    publisher, requests, _, client = make_publisher(tmp_path / "out")
    doc = make_doc()
    result = publisher.create_draft(doc)
    assert result.status == "degraded"
    assert result.degraded is True
    assert result.media_id == ""
    assert result.draft_id == ""
    assert requests == []
    assert Path(result.html_path).read_text(encoding="utf-8-sig") == doc.html
    client.close()


def test_create_draft_remote_cover_url_degrades(tmp_path: Path):
    publisher, requests, _, client = make_publisher(tmp_path / "out")
    result = publisher.create_draft(make_doc(cover_asset="https://example.com/cover.png"))
    assert result.status == "degraded"
    assert result.degraded is True
    assert requests == []
    client.close()


def test_create_draft_upload_failure_degrades(tmp_path: Path):
    publisher, _, state, client = make_publisher(tmp_path / "out", add_material_error=45009)
    cover = write_cover(tmp_path)
    doc = make_doc(cover_asset=str(cover))
    result = publisher.create_draft(doc)
    assert result.status == "degraded"
    assert result.degraded is True
    assert result.draft_id == ""
    assert state["drafts"] == 0
    assert Path(result.html_path).read_text(encoding="utf-8-sig") == doc.html
    client.close()


def test_create_draft_draft_api_failure_degrades(tmp_path: Path):
    publisher, _, state, client = make_publisher(tmp_path / "out", draft_error=45009)
    cover = write_cover(tmp_path)
    doc = make_doc(cover_asset=str(cover))
    result = publisher.create_draft(doc)
    assert result.status == "degraded"
    assert result.degraded is True
    assert state["drafts"] == 1
    assert Path(result.html_path).read_text(encoding="utf-8-sig") == doc.html
    client.close()


def test_create_draft_draft_response_missing_media_id_degrades(tmp_path: Path):
    publisher, _, state, client = make_publisher(tmp_path / "out", draft_payload={"foo": "bar"})
    cover = write_cover(tmp_path)
    result = publisher.create_draft(make_doc(cover_asset=str(cover)))
    assert result.status == "degraded"
    assert state["drafts"] == 1
    client.close()


def test_create_draft_export_failure_returns_failed(tmp_path: Path):
    blocker = tmp_path / "blocker"
    blocker.write_text("占位文件，阻挡 mkdir", encoding="utf-8")
    publisher, requests, _, client = make_publisher(blocker / "out")
    result = publisher.create_draft(make_doc())
    assert result.status == "failed"
    assert result.html_path == ""
    assert result.media_id == ""
    assert result.draft_id == ""
    assert requests == []
    client.close()


def test_export_slug_keeps_chinese_words(tmp_path: Path):
    publisher, _, _, client = make_publisher(tmp_path / "out")
    result = publisher.create_draft(make_doc(title="手冲咖啡 完整指南"))
    assert result.html_path.endswith("手冲咖啡-完整指南.html")
    client.close()


def test_export_slug_symbol_only_title_falls_back_to_article(tmp_path: Path):
    publisher, _, _, client = make_publisher(tmp_path / "out")
    result = publisher.create_draft(make_doc(title="？！？！？"))
    assert result.html_path.endswith("article.html")
    client.close()
