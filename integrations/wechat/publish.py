"""发布 Facade：上层只调 create_draft / release，零感知微信细节（蓝图十三章，M5-T6 / N2-T3）。

出口语义（蓝图十二章「发布不是 Workflow 的唯一出口」）：
- draft_created：微信链路全程成功（封面素材上传 + 草稿箱落位）；
- published：草稿经 freepublish 确认发布成功（release 专用出口，含 article_url）；
- degraded：微信 API 不可用（或无可用封面素材 / 发布未确认成功）→ 本地导出 HTML，人工发布；
- failed：连本地导出都失败（磁盘错误），没有任何 artifact 落地。
非 failed 出口都会落 html_path 本地留档。
"""

from __future__ import annotations

import base64
import re
import time
from pathlib import Path
from urllib.parse import unquote

from core.artifacts.models import PublishResult, WechatDocument
from integrations.errors import ProviderError

from .auth import TokenManager
from .client import WeChatClient
from .draft import DraftService
from .freepublish import FreepublishService
from .media import MediaService

DEFAULT_OUTPUT_DIR = Path("artifacts/wechat")

_MIME_SUFFIX = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}
_DEFAULT_SUFFIX = ".png"


def _slugify(title: str) -> str:
    cleaned = re.sub(r"[^\w]+", "-", title).strip("-")
    return cleaned[:60] or "article"


def _decode_data_uri(uri: str) -> bytes:
    header, _, payload = uri.partition(",")
    if header.endswith(";base64"):
        return base64.b64decode(payload)
    return unquote(payload).encode("utf-8")


def _data_uri_suffix(uri: str) -> str:
    mime = uri[5:].partition(",")[0].removesuffix(";base64")
    return _MIME_SUFFIX.get(mime, _DEFAULT_SUFFIX)


class WeChatPublisher:
    """蓝图十三章 Facade：AuthProvider / MediaService / DraftService 的唯一组合出口。"""

    def __init__(
        self,
        client: WeChatClient,
        tokens: TokenManager,
        *,
        media: MediaService | None = None,
        drafts: DraftService | None = None,
        freepublish: FreepublishService | None = None,
        output_dir: Path = DEFAULT_OUTPUT_DIR,
    ) -> None:
        self._media = media or MediaService(client, tokens)
        self._drafts = drafts or DraftService(client, tokens)
        self._freepublish = freepublish or FreepublishService(client, tokens)
        self._output_dir = Path(output_dir)

    def create_draft(
        self,
        doc: WechatDocument,
        *,
        author: str = "",
        cover_path: str | Path | None = None,
    ) -> PublishResult:
        """把 WechatDocument 落成公众号草稿；微信侧任何失败都降级为本地 HTML 出口。"""
        try:
            html_path = self._export_html(doc)
        except OSError:
            return PublishResult(status="failed")

        cover = self._load_cover(str(cover_path) if cover_path is not None else doc.cover_asset)
        if cover is None:
            return PublishResult(status="degraded", html_path=str(html_path), degraded=True)
        data, filename = cover

        try:
            uploaded = self._media.upload_image(data, filename=filename)
            draft_id = self._drafts.add(
                title=doc.title,
                html=doc.html,
                digest=doc.digest,
                author=author,
                thumb_media_id=uploaded.media_id,
            )
        except ProviderError:
            return PublishResult(status="degraded", html_path=str(html_path), degraded=True)

        return PublishResult(
            status="draft_created",
            media_id=uploaded.media_id,
            draft_id=draft_id,
            html_path=str(html_path),
        )

    def release(
        self,
        draft_id: str,
        *,
        media_id: str = "",
        html_path: str = "",
        max_polls: int = 10,
        poll_interval: float = 1.0,
        sleep=time.sleep,
    ) -> PublishResult:
        """把草稿箱文章正式发布（freepublish 群发）并轮询至终态；绝不抛出。

        只有确认 publish_state=0 才返回 published（含 article_url）；
        提交失败 / 审核失败 / 轮询超时一律返回 degraded——草稿仍在草稿箱，
        可人工发布或再次调用 release（计划 N2-T3，蓝图十二章降级出口）。
        """
        if not draft_id:
            return PublishResult(
                status="degraded",
                media_id=media_id,
                html_path=html_path,
                degraded=True,
                message="缺少草稿 media_id，无法提交发布",
            )
        try:
            publish_id = self._freepublish.submit(draft_id)
            status = self._freepublish.wait(
                publish_id,
                max_polls=max_polls,
                poll_interval=poll_interval,
                sleep=sleep,
            )
        except ProviderError as exc:
            return PublishResult(
                status="degraded",
                media_id=media_id,
                draft_id=draft_id,
                html_path=html_path,
                degraded=True,
                message=str(exc),
            )
        if status.success:
            return PublishResult(
                status="published",
                media_id=media_id,
                draft_id=draft_id,
                publish_id=publish_id,
                article_url=status.article_url,
                html_path=html_path,
                message="发布成功",
            )
        return PublishResult(
            status="degraded",
            media_id=media_id,
            draft_id=draft_id,
            publish_id=publish_id,
            html_path=html_path,
            degraded=True,
            message=status.message,
        )

    def _export_html(self, doc: WechatDocument) -> Path:
        """本地留档：无论微信侧成败，最终 HTML 始终有本地副本。"""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"{_slugify(doc.title)}.html"
        path.write_text(doc.html, encoding="utf-8")
        return path

    def _load_cover(self, ref: str) -> tuple[bytes, str] | None:
        """解析封面引用为 (字节, 文件名)；解析不了返回 None（上层走降级出口）。

        支持本地文件路径与 data URI（b64 图片 / utf8 百分号编码 SVG，
        后者即占位图格式）。远程 http(s) URL 需先由视觉阶段物化为本地文件，
        v0.1 不在 Facade 里下载。
        """
        if not ref:
            return None
        if ref.startswith("data:"):
            return _decode_data_uri(ref), f"cover{_data_uri_suffix(ref)}"
        path = Path(ref)
        if path.is_file():
            try:
                return path.read_bytes(), path.name
            except OSError:
                return None
        return None
