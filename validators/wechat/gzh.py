"""微信公众号平台约束检查（蓝图 9.3 之 GZH 侧）：图片 / 外部资源 / HTML 体积。

蓝图 9.3 九项检查的平台侧五项落在本模块：
- broken_image：图片缺少 src（地址为空）
- insecure_image_url：图片地址必须 https://（且应为已上传素材域名）
- missing_image_dimensions：图片 style 必须声明 width（防止横向溢出）
- external_resource：<script>/<iframe> 等引用标签 + style 中的 url()
- html_too_large：UTF-8 字节数超过上限（公众号正文约 1MB）

其余四项（HTML 结构 / 内联 / CSS 白名单 / 空节点）见 validators/html/checks.py，
两层可经 validators.validate_wechat_html 组合为蓝图 9.3 的完整九项。
"""

from __future__ import annotations

from html.parser import HTMLParser

from core.artifacts.models import ValidationIssue

DEFAULT_MAX_HTML_BYTES = 1_000_000

EXTERNAL_RESOURCE_TAGS = frozenset(
    {
        "script",
        "iframe",
        "embed",
        "object",
        "video",
        "audio",
        "source",
        "track",
        "link",
    }
)


class _GzhAuditor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.issues: list[ValidationIssue] = []

    def _add(self, error_type: str, message: str, prop: str = "") -> None:
        self.issues.append(
            ValidationIssue(type=error_type, node="", property=prop, message=message)
        )

    def _audit_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        if tag in EXTERNAL_RESOURCE_TAGS:
            self._add(
                "external_resource",
                f"第 {line} 行：<{tag}> 引用外部资源，公众号正文不允许",
            )
        style_value = ""
        for name, value in attrs:
            if name == "style" and value:
                style_value = value
        if style_value and "url(" in style_value.replace(" ", "").lower():
            self._add(
                "external_resource",
                f"第 {line} 行：style 中的 url() 引用外部资源，公众号不允许",
            )
        if tag != "img":
            return
        src = ""
        for name, value in attrs:
            if name == "src" and value:
                src = value
        if not src:
            self._add("broken_image", f"第 {line} 行：图片缺少 src（地址为空）")
        elif not src.startswith("https://"):
            self._add(
                "insecure_image_url",
                f"第 {line} 行：图片地址必须以 https:// 开头（应为微信素材域名）",
                prop=src,
            )
        width_declared = any(
            prop.strip().lower() == "width" for prop, _ in _style_props(style_value)
        )
        if not width_declared:
            self._add(
                "missing_image_dimensions",
                f"第 {line} 行：图片 style 缺少 width 声明（避免横向溢出）",
            )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._audit_tag(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._audit_tag(tag, attrs)


def _style_props(style_value: str) -> list[tuple[str, str]]:
    props: list[tuple[str, str]] = []
    for chunk in style_value.split(";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        prop, _, value = chunk.partition(":")
        props.append((prop, value))
    return props


def lint_gzh(html: str, *, max_bytes: int | None = None) -> list[ValidationIssue]:
    """容错扫描公众号平台约束；返回全部问题（不抛异常，空列表 = 通过）。

    max_bytes 缺省 1MB（DEFAULT_MAX_HTML_BYTES），可传入更小值便于测试。
    """
    limit = DEFAULT_MAX_HTML_BYTES if max_bytes is None else max_bytes
    issues: list[ValidationIssue] = []
    size = len(html.encode("utf-8"))
    if size > limit:
        issues.append(
            ValidationIssue(
                type="html_too_large",
                node="",
                property="",
                message=f"HTML 体积 {size} 字节超过上限 {limit} 字节（公众号正文约限 1MB）",
            )
        )
    auditor = _GzhAuditor()
    try:
        auditor.feed(html)
        auditor.close()
    except Exception:
        return issues
    issues.extend(auditor.issues)
    return issues
