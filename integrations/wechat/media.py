"""媒体上传：封面换 thumb_media_id、正文图换微信 CDN URL（蓝图十三章 MediaService，计划 M5-T5）。

微信两条上传通道：
- 永久素材 add_material（type=image）：封面用，返回 media_id + url，
  media_id 即 DraftService 需要的 thumb_media_id；
- 正文图 uploadimg：换取可直接内嵌 HTML 的 mmbiz.qpic.cn URL（无 media_id）。

只上传原始字节，不负责下载远程图——远程素材应由视觉阶段先物化为本地文件。
测试注入 httpx.MockTransport 离线运行（M5-T9）。
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from core.artifacts.models import ContentPackage
from integrations.errors import ProviderError

from .auth import TokenManager, call_with_token_retry
from .client import WeChatClient

ADD_MATERIAL_PATH = "cgi-bin/material/add_material"
UPLOADIMG_PATH = "cgi-bin/media/uploadimg"


class UploadedMedia(NamedTuple):
    """一次封面上传的结果：media_id 供 thumb_media_id 使用，url 为微信 CDN 地址。"""

    media_id: str
    url: str


class MediaService:
    """蓝图十三章 MediaService 角色：字节进，media_id / 微信 URL 出。"""

    def __init__(self, client: WeChatClient, tokens: TokenManager) -> None:
        self._client = client
        self._tokens = tokens

    def upload_image(
        self,
        data: bytes,
        *,
        filename: str = "cover.png",
        content_type: str = "image/png",
    ) -> UploadedMedia:
        """上传永久图片素材；封面 thumb_media_id 的唯一来源。"""

        def _do() -> UploadedMedia:
            token = self._tokens.get_token()
            response = self._client.post(
                ADD_MATERIAL_PATH,
                params={"access_token": token, "type": "image"},
                files={"media": (filename, data, content_type)},
            )
            media_id = response.get("media_id", "")
            url = response.get("url", "")
            if not media_id or not url:
                raise ProviderError("微信素材响应缺少 media_id / url")
            return UploadedMedia(media_id=str(media_id), url=str(url))

        return call_with_token_retry(self._tokens, _do)

    def upload_content_image(
        self,
        data: bytes,
        *,
        filename: str = "image.png",
        content_type: str = "image/png",
    ) -> str:
        """上传正文图片，返回可内嵌 HTML 的微信 CDN URL。"""

        def _do() -> str:
            token = self._tokens.get_token()
            response = self._client.post(
                UPLOADIMG_PATH,
                params={"access_token": token},
                files={"media": (filename, data, content_type)},
            )
            url = response.get("url", "")
            if not url:
                raise ProviderError("微信正文图响应缺少 url")
            return str(url)

        return call_with_token_retry(self._tokens, _do)

    def upload_package_cover(self, package: ContentPackage) -> UploadedMedia | None:
        """把 ContentPackage.visual.cover.asset_path 指向的本地封面上传为永久素材。

        上传成功后把 asset_path 原地升级为微信 CDN URL（素材已在微信侧落地），
        并返回 UploadedMedia——media_id 由调用方传给草稿接口当 thumb_media_id。
        无封面（visual.cover 缺失或 asset_path 为空）返回 None，不算错误。
        """
        cover = package.visual.cover
        if cover is None or not cover.asset_path:
            return None
        path = Path(cover.asset_path)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise ProviderError(f"封面文件读取失败：{cover.asset_path}：{exc}") from exc
        uploaded = self.upload_image(data, filename=path.name or "cover.png")
        cover.asset_path = uploaded.url
        return uploaded
