"""三级降级链：生成失败 → 图片搜索 → 确定性占位图（蓝图十二章，计划 M5-T3）。

    Image generation unavailable → use image search → continue

占位图为 data URI SVG：离线确定性生成（同 prompt 同图），
最差情况下流程仍可继续，绝不把网络/服务错误抛给上层。
"""

from __future__ import annotations

from html import escape
from urllib.parse import quote

from integrations.errors import ProviderError
from integrations.search import SafeSearchProvider, SearchProvider

from .base import ImageAsset, ImageProvider

_PLACEHOLDER_REASON = "图片生成与搜索均不可用，已使用占位图"


def _placeholder_url(prompt: str, size: str) -> str:
    """确定性占位图：data URI SVG，离线生成，同 prompt + size 同 URL。"""
    try:
        width_text, _, height_text = size.lower().partition("x")
        width, height = str(int(width_text)), str(int(height_text))
    except ValueError:
        width, height = "1024", "1024"
    text = escape((prompt or "图片").strip()[:24] or "图片")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" fill="#f2f2f2"/>'
        f'<text x="50%" y="50%" fill="#999999" font-family="sans-serif" font-size="28" '
        f'text-anchor="middle" dominant-baseline="middle">{text}</text>'
        f"</svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg)


class FallbackImageProvider:
    """组合生成与搜索：一级失败自动降级，任何情况都有兜底出口。

    - 第一级 generator.generate(prompt)：抛 ProviderError 即降级；
    - 第二级 searcher.search(query)：复用 Search 集成层，SafeSearchProvider
      包装后失败/空结果都进入第三级；
    - 第三级占位图：确定性 data URI SVG，永不失败。
    """

    def __init__(
        self,
        generator: ImageProvider | None,
        searcher: SearchProvider | None = None,
    ) -> None:
        self._generator = generator
        self._searcher = SafeSearchProvider(searcher) if searcher is not None else None

    def generate(self, prompt: str, *, size: str = "1024x1024") -> ImageAsset:
        """ImageProvider 契约入口：管线经此走完整三级降级链。"""
        return self.get_image(prompt, size=size)

    def get_image(
        self,
        prompt: str,
        *,
        query: str | None = None,
        size: str = "1024x1024",
    ) -> ImageAsset:
        """获取一张图片：生成 → 搜索 → 占位图，永不抛网络/服务错误。"""
        if self._generator is not None:
            try:
                return self._generator.generate(prompt, size=size)
            except ProviderError:
                pass
        if self._searcher is not None:
            outcome = self._searcher.search(query or prompt, limit=1)
            if not outcome.degraded and outcome.hits:
                hit = outcome.hits[0]
                title = hit.title or hit.url
                return ImageAsset(
                    url=hit.url, source="search", prompt=prompt, reason=f"图片搜索命中：{title}"
                )
        return ImageAsset(
            url=_placeholder_url(prompt, size),
            source="placeholder",
            prompt=prompt,
            reason=_PLACEHOLDER_REASON,
        )
