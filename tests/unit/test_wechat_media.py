"""媒体上传单测（蓝图十三章 MediaService，计划 M5-T5）。

- upload_image：multipart 形状 / 缺 media_id / 缺 url / 业务错误码不重试；
- upload_content_image：正文图换 CDN URL（不携带 type 参数）；
- upload_package_cover：本地封面 → media_id + 微信 CDN URL 写回 ContentPackage（M5-T5 DoD）；
- token 失效（40001/42001）：废弃缓存后定向重试恰好一次。
全部经 httpx.MockTransport 离线运行（H6 / M5-T9）。
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from core.artifacts.models import ContentPackage, CoverSpec, VisualPlan
from integrations.errors import ProviderError
from integrations.wechat import MediaService, TokenManager, WeChatClient

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-cover-data"
COVER_URL = "https://mmbiz.qpic.cn/mmbiz_png/cover.png"
BODY_URL = "https://mmbiz.qpic.cn/mmbiz_png/body.png"


def make_service(
    *,
    add_material: dict | None = None,
    uploadimg: dict | None = None,
    fail_first_upload_with: int | None = None,
) -> tuple[MediaService, list[httpx.Request], dict, WeChatClient]:
    requests: list[httpx.Request] = []
    state = {"tokens": 0, "uploads": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/cgi-bin/token":
            state["tokens"] += 1
            return httpx.Response(
                200, json={"access_token": f"TOKEN-{state['tokens']}", "expires_in": 7200}
            )
        if request.url.path == "/cgi-bin/material/add_material":
            state["uploads"] += 1
            if fail_first_upload_with is not None and state["uploads"] == 1:
                return httpx.Response(
                    200, json={"errcode": fail_first_upload_with, "errmsg": "api error"}
                )
            body = add_material or {"media_id": "MEDIA-1", "url": COVER_URL}
            return httpx.Response(200, json=body)
        if request.url.path == "/cgi-bin/media/uploadimg":
            return httpx.Response(200, json=uploadimg or {"url": BODY_URL})
        return httpx.Response(404, text="not found")

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = WeChatClient(transport=httpx.MockTransport(record))
    tokens = TokenManager(
        client, app_id="wx-test-app", app_secret="secret-test", clock=lambda: 1000.0
    )
    service = MediaService(client, tokens)
    return service, requests, state, client


def make_package(asset_path: str) -> ContentPackage:
    return ContentPackage(
        title="手冲咖啡指南",
        semantic_markdown="正文",
        visual=VisualPlan(cover=CoverSpec(asset_path=asset_path)),
    )


def test_upload_image_sends_multipart_with_type_and_token():
    service, requests, _, client = make_service()
    uploaded = service.upload_image(PNG_BYTES)
    assert uploaded.media_id == "MEDIA-1"
    assert uploaded.url == COVER_URL
    request = requests[-1]
    assert request.url.path == "/cgi-bin/material/add_material"
    assert request.url.params["type"] == "image"
    assert request.url.params["access_token"] == "TOKEN-1"
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b"cover.png" in request.content
    assert PNG_BYTES in request.content
    client.close()


def test_upload_image_missing_media_id_raises():
    service, _, _, client = make_service(add_material={"url": COVER_URL})
    with pytest.raises(ProviderError, match="media_id"):
        service.upload_image(PNG_BYTES)
    client.close()


def test_upload_image_missing_url_raises():
    service, _, _, client = make_service(add_material={"media_id": "MEDIA-1"})
    with pytest.raises(ProviderError, match="url"):
        service.upload_image(PNG_BYTES)
    client.close()


def test_upload_image_business_error_not_retried():
    service, requests, state, client = make_service(fail_first_upload_with=45009)
    with pytest.raises(ProviderError, match="45009") as excinfo:
        service.upload_image(PNG_BYTES)
    assert excinfo.value.errcode == 45009
    assert state["uploads"] == 1
    assert state["tokens"] == 1
    assert len(requests) == 2
    client.close()


def test_upload_content_image_returns_url_without_type_param():
    service, requests, _, client = make_service()
    url = service.upload_content_image(PNG_BYTES)
    assert url == BODY_URL
    request = requests[-1]
    assert request.url.path == "/cgi-bin/media/uploadimg"
    assert "type" not in request.url.params
    assert request.url.params["access_token"] == "TOKEN-1"
    assert request.headers["content-type"].startswith("multipart/form-data")
    assert b"image.png" in request.content
    assert PNG_BYTES in request.content
    client.close()


def test_upload_content_image_missing_url_raises():
    service, _, _, client = make_service(uploadimg={"media_id": "X"})
    with pytest.raises(ProviderError, match="url"):
        service.upload_content_image(PNG_BYTES)
    client.close()


def test_upload_package_cover_writes_back_cdn_url(tmp_path: Path):
    cover = tmp_path / "cover.png"
    cover.write_bytes(PNG_BYTES)
    service, _, _, client = make_service()
    package = make_package(str(cover))
    uploaded = service.upload_package_cover(package)
    assert uploaded is not None
    assert uploaded.media_id == "MEDIA-1"
    assert package.visual.cover is not None
    assert package.visual.cover.asset_path == COVER_URL
    client.close()


def test_upload_package_cover_without_cover_returns_none():
    service, requests, _, client = make_service()
    package = ContentPackage(title="无封面", semantic_markdown="正文", visual=VisualPlan())
    assert service.upload_package_cover(package) is None
    assert requests == []
    client.close()


def test_upload_package_cover_empty_asset_path_returns_none():
    service, requests, _, client = make_service()
    package = make_package("")
    assert service.upload_package_cover(package) is None
    assert requests == []
    client.close()


def test_upload_package_cover_missing_file_raises(tmp_path: Path):
    service, _, _, client = make_service()
    package = make_package(str(tmp_path / "missing.png"))
    with pytest.raises(ProviderError, match="封面文件读取失败"):
        service.upload_package_cover(package)
    client.close()


@pytest.mark.parametrize("code", [40001, 42001])
def test_upload_image_retries_once_on_expired_token(code):
    service, requests, state, client = make_service(fail_first_upload_with=code)
    uploaded = service.upload_image(PNG_BYTES)
    assert uploaded.media_id == "MEDIA-1"
    assert state["uploads"] == 2
    assert state["tokens"] == 2
    assert [r.url.path for r in requests] == [
        "/cgi-bin/token",
        "/cgi-bin/material/add_material",
        "/cgi-bin/token",
        "/cgi-bin/material/add_material",
    ]
    assert requests[3].url.params["access_token"] == "TOKEN-2"
    client.close()
