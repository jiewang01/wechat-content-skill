"""HTML 通用检查（蓝图 9.3 之 HTML 侧）：标签 / 属性 / 结构 / CSS 白名单 / 空节点。

公众号仅支持受限 HTML 子集：标签 ⊆ {section, span, strong, em, img}，
样式必须全部内联（禁止 <style>/<link>），CSS 属性 ⊆ 渲染器白名单。

ALLOWED_CSS_PROPS 与 renderer/html/renderer.py 实际发射的属性保持同步
（单测锚定：渲染器产出零误报），保证默认管线全绿 ——
这是 H5（不过 PASS 不发布）与 H8（确定性验证器优先）的前提。

与组件 lint 相同的容错契约：一次扫描收集全部问题，不抛异常，空列表 = 通过。
"""

from __future__ import annotations

from html.parser import HTMLParser

from core.artifacts.models import ValidationIssue

ALLOWED_TAGS = frozenset({"section", "span", "strong", "em", "img"})
STYLE_TAGS = frozenset({"style", "link"})
ALLOWED_ATTRS = frozenset({"style", "src", "alt"})

ALLOWED_CSS_PROPS = frozenset(
    {
        "color",
        "font-size",
        "font-weight",
        "font-family",
        "line-height",
        "letter-spacing",
        "text-align",
        "margin-top",
        "margin-bottom",
        "background",
        "border",
        "border-left",
        "border-bottom",
        "border-radius",
        "padding",
        "padding-left",
        "padding-right",
        "padding-top",
        "padding-bottom",
        "display",
        "width",
        "max-width",
        "height",
        "white-space",
        "word-break",
    }
)

RESTRICTED_CSS_VALUES: dict[str, frozenset[str]] = {
    "display": frozenset({"block", "inline", "inline-block"}),
}

_EMPTY_NODE_EXEMPT_TAGS = frozenset(
    {
        "style",
        "link",
        "script",
        "iframe",
        "embed",
        "object",
        "video",
        "audio",
    }
)

_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


class _OpenTag:
    __slots__ = ("tag", "has_content", "line")

    def __init__(self, tag: str, line: int) -> None:
        self.tag = tag
        self.has_content = False
        self.line = line


def _style_declarations(style_value: str) -> list[tuple[str, str]]:
    declarations: list[tuple[str, str]] = []
    for chunk in style_value.split(";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        prop, _, value = chunk.partition(":")
        declarations.append((prop.strip().lower(), value.strip()))
    return declarations


class _HtmlAuditor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.issues: list[ValidationIssue] = []
        self.stack: list[_OpenTag] = []

    def _add(self, error_type: str, message: str, prop: str = "") -> None:
        self.issues.append(
            ValidationIssue(type=error_type, node="", property=prop, message=message)
        )

    def _audit_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        line = self.getpos()[0]
        if tag in STYLE_TAGS:
            self._add(
                "style_block",
                f"第 {line} 行：禁止 <{tag}> —— 公众号样式必须全部内联（style 属性）",
            )
        elif tag not in ALLOWED_TAGS:
            allowed = "/".join(sorted(ALLOWED_TAGS))
            self._add(
                "forbidden_tag",
                f"第 {line} 行：不允许的标签 <{tag}>（允许：{allowed}）",
            )
        style_value = ""
        for name, value in attrs:
            if name not in ALLOWED_ATTRS:
                self._add(
                    "disallowed_attribute",
                    f"第 {line} 行：标签 <{tag}> 不允许属性 {name!r}（允许：style/src/alt）",
                    prop=name,
                )
            if name == "style" and value:
                style_value = value
        if style_value:
            for prop, value in _style_declarations(style_value):
                if prop not in ALLOWED_CSS_PROPS:
                    self._add(
                        "unsupported_css",
                        f"第 {line} 行：标签 <{tag}> 的样式不支持 {prop}:{value}",
                        prop=f"{prop}:{value}",
                    )
                elif (
                    prop in RESTRICTED_CSS_VALUES
                    and value.lower() not in RESTRICTED_CSS_VALUES[prop]
                ):
                    self._add(
                        "unsupported_css",
                        f"第 {line} 行：标签 <{tag}> 的 {prop}:{value} 取值不被公众号支持",
                        prop=f"{prop}:{value}",
                    )

    def _mark_content(self) -> None:
        if self.stack:
            self.stack[-1].has_content = True

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._audit_tag(tag, attrs)
        if tag in _VOID_TAGS:
            self._mark_content()
            return
        self._mark_content()
        self.stack.append(_OpenTag(tag, self.getpos()[0]))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._audit_tag(tag, attrs)
        if tag in _VOID_TAGS:
            self._mark_content()
        elif tag not in _EMPTY_NODE_EXEMPT_TAGS:
            self._add(
                "empty_node",
                f"第 {self.getpos()[0]} 行：<{tag}/> 是空节点（无文本、无子元素）",
            )

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            return
        line = self.getpos()[0]
        if not self.stack:
            self._add("html_structure", f"第 {line} 行：多余的结束标签 </{tag}>")
            return
        if self.stack[-1].tag == tag:
            node = self.stack.pop()
            if not node.has_content and node.tag not in _EMPTY_NODE_EXEMPT_TAGS:
                self._add(
                    "empty_node",
                    f"第 {node.line} 行：<{node.tag}> 是空节点（无文本、无子元素）",
                )
            return
        for idx in range(len(self.stack) - 1, -1, -1):
            if self.stack[idx].tag == tag:
                unclosed = [open_tag.tag for open_tag in self.stack[idx + 1 :]]
                self._add(
                    "html_structure",
                    f"第 {line} 行：</{tag}> 之前有 {len(unclosed)} 个标签未闭合："
                    + "/".join(unclosed),
                )
                del self.stack[idx:]
                return
        self._add(
            "html_structure",
            f"第 {line} 行：多余的结束标签 </{tag}>（当前无对应的开始标签）",
        )

    def handle_data(self, data: str) -> None:
        if data:
            self._mark_content()

    def finish(self) -> None:
        if self.stack:
            unclosed = [open_tag.tag for open_tag in self.stack]
            self._add(
                "html_structure",
                f"文档结束时仍有 {len(unclosed)} 个标签未闭合：" + "/".join(unclosed),
            )
            self.stack.clear()


def lint_html(html: str) -> list[ValidationIssue]:
    """容错扫描公众号 HTML；返回全部 HTML 层问题（不抛异常，空列表 = 通过）。"""
    auditor = _HtmlAuditor()
    try:
        auditor.feed(html)
        auditor.close()
    except Exception:
        return [
            ValidationIssue(
                type="html_structure",
                node="",
                property="",
                message="HTML 解析失败（语法严重非法）",
            )
        ]
    auditor.finish()
    return auditor.issues
