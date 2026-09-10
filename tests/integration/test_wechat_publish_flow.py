"""微信发布链路集成测试（M5-T9：全部 mock，CI 零网络依赖）。

组合 TokenManager + MediaService + DraftService + WeChatPublisher 走完整链路：
- 成功链路：封面素材上传 → media_id 作 thumb_media_id → 草稿落位 → 本地 HTML 留档；
- ContentPackage 封面链：upload_package_cover 写回 CDN URL，media_id 直通草稿（T5→T6 衔接）；
- token 中途失效（40001）：自动废弃缓存刷新重试恰好一次，链路无感恢复；
- 微信 API 全面不可用（HTTP 500）：降级出口，本地 HTML 收尾（蓝图十二章 DoD / T8）。
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from core.artifacts.models import ContentPackage, CoverSpec, VisualPlan, WechatDocument
from integrations.wechat import (
    DraftService,
    MediaService,
    TokenManager,
    WeChatClient,
    WeChatPublisher,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-cover-data"


def make_wechat_api(
    *,
    api_status: int | None = None,
    expire_first_upload: bool = False,
    media_id: str = "MEDIA-1",
) -> tuple[WeChatClient, TokenManager, list[httpx.Request], dict]:
    requests: list[httpx.Request] = []
    state = {"tokens": 0, "uploads": 0, "drafts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if api_status is not None:
            return httpx.Response(api_status, text="server error")
        if request.url.path == "/cgi-bin/token":
            state["tokens"] += 1
            return httpx.Response(
                200, json={"access_token": f"TOKEN-{state['tokens']}", "expires_in": 7200}
            )
        if request.url.path == "/cgi-bin/material/add_material":
            state["uploads"] += 1
            if expire_first_upload and state["uploads"] == 1:
                return httpx.Response(200, json={"errcode": 40001, "errmsg": "invalid credential"})
            return httpx.Response(
                200, json={"media_id": media_id, "url": f"https://mmbiz.qpic.cn/{media_id}.png"}
            )
        if request.url.path == "/cgi-bin/media/uploadimg":
            return httpx.Response(200, json={"url": "https://mmbiz.qpic.cn/mmbiz_png/body.png"})
        if request.url.path == "/cgi-bin/draft/add":
            state["drafts"] += 1
            return httpx.Response(200, json={"media_id": "DRAFT-1"})
        return httpx.Response(404, text="not found")

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = WeChatClient(transport=httpx.MockTransport(record))
    tokens = TokenManager(
        client, app_id="wx-test-app", app_secret="secret-test", clock=lambda: 1000.0
    )
    return client, tokens, requests, state


def make_publisher(client: WeChatClient, tokens: TokenManager, output_dir: Path) -> WeChatPublisher:
    return WeChatPublisher(
        client,
        tokens,
        media=MediaService(client, tokens),
        drafts=DraftService(client, tokens),
        output_dir=output_dir,
    )


def write_cover(tmp_path: Path) -> Path:
    path = tmp_path / "cover.png"
    path.write_bytes(PNG_BYTES)
    return path


def make_doc(**overrides) -> WechatDocument:
    fields = {
        "title": "手冲咖啡完整指南",
        "digest": "三段式冲煮法",
        "html": '<section style="margin:0"><p>正文</p></section>',
        "cover_asset": "",
    }
    fields.update(overrides)
    return WechatDocument(**fields)


def test_full_flow_creates_draft_and_keeps_local_copy(tmp_path: Path):
    cover = write_cover(tmp_path)
    client, tokens, requests, state = make_wechat_api()
    publisher = make_publisher(client, tokens, tmp_path / "out")
    doc = make_doc()
    result = publisher.create_draft(doc, author="老王", cover_path=cover)
    assert result.status == "draft_created"
    assert result.media_id == "MEDIA-1"
    assert result.draft_id == "DRAFT-1"
    assert result.degraded is False
    assert state == {"tokens": 1, "uploads": 1, "drafts": 1}
    assert [r.url.path for r in requests] == [
        "/cgi-bin/token",
        "/cgi-bin/material/add_material",
        "/cgi-bin/draft/add",
    ]
    article = json.loads(requests[2].content)["articles"][0]
    assert article["thumb_media_id"] == "MEDIA-1"
    assert article["author"] == "老王"
    assert Path(result.html_path).read_text(encoding="utf-8") == doc.html
    client.close()


def test_package_cover_media_id_feeds_draft_thumb(tmp_path: Path):
    cover = write_cover(tmp_path)
    client, tokens, requests, state = make_wechat_api(media_id="MEDIA-9")
    media = MediaService(client, tokens)
    drafts = DraftService(client, tokens)
    package = ContentPackage(
        title="手冲咖啡指南",
        semantic_markdown="正文",
        visual=VisualPlan(cover=CoverSpec(asset_path=str(cover))),
    )
    uploaded = media.upload_package_cover(package)
    assert uploaded is not None
    assert uploaded.media_id == "MEDIA-9"
    assert package.visual.cover is not None
    assert package.visual.cover.asset_path == "https://mmbiz.qpic.cn/MEDIA-9.png"
    draft_id = drafts.add(
        title=package.title,
        html='<section style="margin:0"><p>正文</p></section>',
        thumb_media_id=uploaded.media_id,
    )
    assert draft_id == "DRAFT-1"
    assert state == {"tokens": 1, "uploads": 1, "drafts": 1}
    article = json.loads(requests[-1].content)["articles"][0]
    assert article["thumb_media_id"] == "MEDIA-9"
    client.close()


def test_token_expiry_mid_flow_recovers_invisibly(tmp_path: Path):
    cover = write_cover(tmp_path)
    client, tokens, requests, state = make_wechat_api(expire_first_upload=True)
    publisher = make_publisher(client, tokens, tmp_path / "out")
    result = publisher.create_draft(make_doc(), cover_path=cover)
    assert result.status == "draft_created"
    assert result.media_id == "MEDIA-1"
    assert state == {"tokens": 2, "uploads": 2, "drafts": 1}
    assert [r.url.path for r in requests] == [
        "/cgi-bin/token",
        "/cgi-bin/material/add_material",
        "/cgi-bin/token",
        "/cgi-bin/material/add_material",
        "/cgi-bin/draft/add",
    ]
    assert requests[3].url.params["access_token"] == "TOKEN-2"
    client.close()


def test_wechat_outage_ends_with_local_html(tmp_path: Path):
    cover = write_cover(tmp_path)
    client, tokens, _, state = make_wechat_api(api_status=500)
    publisher = make_publisher(client, tokens, tmp_path / "out")
    doc = make_doc()
    result = publisher.create_draft(doc, cover_path=cover)
    assert result.status == "degraded"
    assert result.degraded is True
    assert result.draft_id == ""
    assert state["drafts"] == 0
    assert Path(result.html_path).read_text(encoding="utf-8") == doc.html
    client.close()


def test_content_image_url_ready_for_embedding(tmp_path: Path):
    client, tokens, requests, _ = make_wechat_api()
    media = MediaService(client, tokens)
    url = media.upload_content_image(PNG_BYTES)
    assert url == "https://mmbiz.qpic.cn/mmbiz_png/body.png"
    publisher = make_publisher(client, tokens, tmp_path / "out")
    cover = write_cover(tmp_path)
    doc = make_doc(html=f'<section style="margin:0"><p><img src="{url}" /></p></section>')
    result = publisher.create_draft(doc, cover_path=cover)
    assert result.status == "draft_created"
    article = json.loads(requests[-1].content)["articles"][0]
    assert url in article["content"]
    client.close()
