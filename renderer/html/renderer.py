"""确定性 HTML 渲染器：ContentAST → 公众号兼容 HTML 片段。

设计要点（与渲染门校验一一对应）：
- 仅使用安全标签：section / span / strong / em / img
- 仅内联样式；绝不输出 <style>/<script>、class 或 id
- 标题默认不渲染进正文（include_title=False）：公众号标题栏单独展示
- 代码块用 white-space:pre-wrap 保留换行，不依赖 <br>
- hr 渲染为带背景色的 1px section（携带背景样式，空节点校验据此豁免）
- 链接降级为「文本（URL）」纯文本形式
"""

from __future__ import annotations

import html
import re

from renderer.ast.nodes import AnyASTNode, CardItem, ContentAST
from renderer.themes import Theme, load_theme

_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"\*\*([^*\n]+)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")


def _px(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{value}px"
    return str(value)


def _css(pairs: list[tuple[str, object]]) -> str:
    parts = [f"{k}:{v}" for k, v in pairs if v is not None and v != ""]
    return ";".join(parts) + ";" if parts else ""


def _to_plain(text: str) -> str:
    text = _LINK_RE.sub(r"\1", text)
    text = text.replace("**", "").replace("`", "")
    return _ITALIC_RE.sub(r"\1", text)


class HtmlRenderer:
    """主题驱动的渲染器；同一 AST 换主题即换视觉，无需改动代码。"""

    def __init__(self, theme: Theme | None = None):
        self.theme = theme if theme is not None else load_theme("default")

    def render_segments(self, ast: ContentAST) -> list[tuple[str, str]]:
        """逐节点渲染为 (node_id, html) 段列表。

        修复循环据此把 HTML 层错误归属到具体节点并做定向修复（H3）；
        render() 复用同一来源，保证归属与最终输出永不漂移。
        """
        segments: list[tuple[str, str]] = []
        for node in ast.nodes:
            chunk = self._render_node(node)
            if chunk:
                segments.append((node.node_id, chunk))
        return segments

    def render(self, ast: ContentAST, *, include_title: bool = False) -> str:
        """渲染为公众号 HTML 片段；include_title=True 时在顶部加一级标题。"""
        parts: list[str] = []
        if include_title and ast.title:
            parts.append(self._heading_html(ast.title, 1))
        parts.extend(chunk for _, chunk in self.render_segments(ast))
        return self.wrap_document("\n".join(parts))

    def wrap_document(self, body: str) -> str:
        """为主题正文包上根容器；render() 的外壳，供修复循环后重组完整文档。"""
        spec = self._typ("body")
        root_css = _css(
            [
                ("font-size", _px(spec.get("font_size", 16))),
                ("line-height", spec.get("line_height", 1.75)),
                ("color", spec.get("color", "#333333")),
                ("font-family", spec.get("font_family")),
                ("word-break", spec.get("word_break", "break-word")),
                ("letter-spacing", spec.get("letter_spacing")),
                ("text-align", spec.get("text_align")),
            ]
        )
        return f'<section style="{root_css}">\n{body}\n</section>'

    def render_plain_text(self, ast: ContentAST) -> str:
        """渲染为纯文本（去除行内标记），用于摘要与降级导出。"""
        parts = [self._plain_block(node) for node in ast.nodes]
        return _to_plain("\n\n".join(p for p in parts if p and p.strip()))

    def _plain_block(self, node: AnyASTNode) -> str:
        """单节点 → 纯文本；card 的节点条目递归展开（嵌套子组件并入父块）。"""
        kind = node.type
        if kind in {"heading", "paragraph", "note", "code"}:
            return node.text
        if kind == "quote":
            return node.text + (f"\n—— {node.cite}" if node.cite else "")
        if kind == "callout":
            return (f"{node.title}\n" if node.title else "") + node.text
        if kind == "card":
            lines = [node.title]
            for item in node.items:
                if isinstance(item, str):
                    lines.append(f"- {item}")
                else:
                    lines.append(self._plain_block(item))
            lines.append(node.footer)
            return "\n".join(line for line in lines if line)
        if kind == "image":
            return node.alt
        if kind == "list":
            return "\n".join(node.items)
        return ""

    def _typ(self, key: str) -> dict:
        return self.theme.typography.get(key) or {}

    def _comp(self, key: str) -> dict:
        return self.theme.components.get(key) or {}

    def _inline(self, text: str) -> str:
        if not text:
            return ""
        out = html.escape(text, quote=False)
        out = _LINK_RE.sub(r"\1（\2）", out)
        ci = self._typ("code_inline")
        code_css = _css(
            [
                ("font-family", ci.get("font_family")),
                ("font-size", "0.9em"),
                ("color", ci.get("color")),
                ("background", ci.get("background")),
                (
                    "padding",
                    f"{_px(ci.get('padding_v', 2))} {_px(ci.get('padding_h', 4))}",
                ),
                ("border-radius", _px(ci.get("border_radius", 3))),
            ]
        )
        out = _CODE_RE.sub(lambda m: f'<span style="{code_css}">{m.group(1)}</span>', out)
        strong_css = _css([("color", self._typ("strong").get("color"))])
        if strong_css:
            out = _BOLD_RE.sub(
                lambda m: f'<strong style="{strong_css}">{m.group(1)}</strong>', out
            )
        else:
            out = _BOLD_RE.sub(r"<strong>\1</strong>", out)
        out = _ITALIC_RE.sub(r"<em>\1</em>", out)
        return out

    def _heading_html(self, text: str, level: int) -> str:
        key = "h1" if level == 1 else "h2" if level == 2 else "h3"
        spec = self._typ(key)
        css = _css(
            [
                ("font-size", _px(spec.get("font_size", 17))),
                ("font-weight", spec.get("font_weight", 600)),
                ("color", spec.get("color", "#333333")),
                ("line-height", spec.get("line_height", 1.4)),
                ("margin-top", _px(spec.get("margin_top", 18))),
                ("margin-bottom", _px(spec.get("margin_bottom", 10))),
                ("text-align", spec.get("text_align")),
                ("letter-spacing", spec.get("letter_spacing")),
                ("background", spec.get("background")),
                ("border-left", spec.get("border_left")),
                ("padding", spec.get("padding")),
                ("padding-left", spec.get("padding_left")),
                ("padding-top", spec.get("padding_top")),
                ("padding-bottom", spec.get("padding_bottom")),
                ("border-bottom", spec.get("border_bottom")),
                ("border-radius", spec.get("border_radius")),
            ]
        )
        return f'<section style="{css}">{self._inline(text)}</section>'

    def _render_node(self, node: AnyASTNode) -> str:
        kind = node.type
        if kind == "heading":
            return self._heading_html(node.text, node.level)
        if kind == "paragraph":
            if not node.text.strip():
                return ""
            p = self._typ("paragraph")
            css = _css(
                [
                    ("margin-top", _px(p.get("margin_top", 10))),
                    ("margin-bottom", _px(p.get("margin_bottom", 10))),
                ]
            )
            return f'<section style="{css}">{self._inline(node.text)}</section>'
        if kind == "quote":
            return self._quote_html(node.text, node.cite)
        if kind == "note":
            return self._note_html(node.text)
        if kind == "callout":
            return self._callout_html(node.variant, node.title, node.text)
        if kind == "card":
            return self._card_html(node.title, node.items, node.footer)
        if kind == "image":
            return self._image_html(node.src, node.alt)
        if kind == "code":
            return self._code_html(node.language, node.text)
        if kind == "list":
            return self._list_html(node.ordered, node.items)
        return self._hr_html()

    def _quote_html(self, text: str, cite: str) -> str:
        if not text.strip():
            return ""
        q = self._comp("quote")
        outer = _css(
            [
                ("background", q.get("background")),
                ("border-left", q.get("border_left")),
                ("border-radius", _px(q.get("border_radius", 4))),
                ("padding", _px(q.get("padding", 12))),
                ("margin-top", _px(q.get("margin_top", 16))),
                ("margin-bottom", _px(q.get("margin_bottom", 16))),
            ]
        )
        text_css = _css(
            [
                ("font-size", _px(q.get("font_size", 15))),
                ("color", q.get("text_color", "#555555")),
                ("line-height", 1.7),
            ]
        )
        inner = [f'<span style="{text_css}">{self._inline(text)}</span>']
        if cite:
            cite_css = _css(
                [
                    ("display", "block"),
                    ("margin-top", "6px"),
                    ("font-size", _px(q.get("cite_size", 13))),
                    ("color", q.get("cite_color", "#888888")),
                ]
            )
            inner.append(f'<span style="{cite_css}">—— {self._inline(cite)}</span>')
        return f'<section style="{outer}">\n' + "\n".join(inner) + "\n</section>"

    def _note_html(self, text: str) -> str:
        if not text.strip():
            return ""
        n = self._comp("note")
        css = _css(
            [
                ("background", n.get("background")),
                ("border-left", n.get("border_left")),
                ("border-radius", _px(n.get("border_radius", 4))),
                ("padding", _px(n.get("padding", 12))),
                ("margin-top", _px(n.get("margin_top", 16))),
                ("margin-bottom", _px(n.get("margin_bottom", 16))),
                ("font-size", _px(n.get("font_size", 15))),
                ("color", n.get("text_color", "#4a5568")),
                ("line-height", 1.7),
            ]
        )
        return f'<section style="{css}">{self._inline(text)}</section>'

    def _callout_html(self, variant: str, title: str, text: str) -> str:
        if not text.strip() and not title.strip():
            return ""
        base = self._comp("callout").get("base") or {}
        var = (self._comp("callout").get("variants") or {}).get(variant) or {}
        outer = _css(
            [
                ("background", var.get("background")),
                ("border-left", var.get("border_left")),
                ("border-radius", _px(base.get("border_radius", 4))),
                ("padding", _px(base.get("padding", 12))),
                ("margin-top", _px(base.get("margin_top", 16))),
                ("margin-bottom", _px(base.get("margin_bottom", 16))),
            ]
        )
        parts: list[str] = []
        if title:
            title_css = _css(
                [
                    ("display", "block"),
                    ("margin-bottom", "6px"),
                    ("font-size", _px(base.get("font_size", 15))),
                    ("color", var.get("title_color")),
                ]
            )
            parts.append(f'<strong style="{title_css}">{self._inline(title)}</strong>')
        if text:
            text_css = _css(
                [
                    ("font-size", _px(base.get("font_size", 15))),
                    ("color", var.get("text_color", "#4a5568")),
                    ("line-height", 1.7),
                ]
            )
            parts.append(f'<span style="{text_css}">{self._inline(text)}</span>')
        return f'<section style="{outer}">\n' + "\n".join(parts) + "\n</section>"

    def _card_html(self, title: str, items: list[CardItem], footer: str) -> str:
        if not title and not items and not footer:
            return ""
        c = self._comp("card")
        outer = _css(
            [
                ("border", c.get("border")),
                ("border-radius", _px(c.get("border_radius", 8))),
                ("padding", _px(c.get("padding", 14))),
                ("margin-top", _px(c.get("margin_top", 16))),
                ("margin-bottom", _px(c.get("margin_bottom", 16))),
                ("background", c.get("background")),
            ]
        )
        parts: list[str] = []
        if title:
            title_css = _css(
                [
                    ("display", "block"),
                    ("font-size", _px(c.get("title_size", 16))),
                    ("font-weight", c.get("title_weight", 600)),
                    ("color", c.get("title_color")),
                    ("margin-bottom", "8px"),
                ]
            )
            parts.append(f'<strong style="{title_css}">{self._inline(title)}</strong>')
        marker_css = _css([("color", c.get("item_marker_color"))])
        item_css = _css(
            [
                ("font-size", _px(c.get("item_size", 15))),
                ("color", c.get("item_color", "#4a5568")),
            ]
        )
        item_margin = c.get("item_margin", 6)
        child_margin = c.get("child_margin", item_margin)
        for item in items:
            if isinstance(item, str):
                if not item.strip():
                    continue
                row_css = _css(
                    [
                        ("margin-top", _px(item_margin)),
                        ("margin-bottom", _px(item_margin)),
                    ]
                )
                parts.append(
                    f'<section style="{row_css}">'
                    f'<span style="{marker_css}">•</span>'
                    f'<span style="{item_css}"> {self._inline(item)}</span></section>'
                )
                continue
            block = self._render_node(item)
            if not block:
                continue
            row_css = _css(
                [
                    ("margin-top", _px(child_margin)),
                    ("margin-bottom", _px(child_margin)),
                ]
            )
            parts.append(f'<section style="{row_css}">\n{block}\n</section>')
        if footer:
            footer_css = _css(
                [
                    ("display", "block"),
                    ("margin-top", "10px"),
                    ("font-size", _px(c.get("footer_size", 13))),
                    ("color", c.get("footer_color", "#999999")),
                ]
            )
            parts.append(f'<span style="{footer_css}">{self._inline(footer)}</span>')
        return f'<section style="{outer}">\n' + "\n".join(parts) + "\n</section>"

    def _image_html(self, src: str, alt: str) -> str:
        spec = self._typ("image")
        css = _css(
            [
                ("width", spec.get("width", "100%")),
                ("max-width", spec.get("max_width", "100%")),
                ("margin-top", _px(spec.get("margin_top", 16))),
                ("margin-bottom", _px(spec.get("margin_bottom", 16))),
            ]
        )
        safe_src = html.escape(src, quote=True)
        safe_alt = html.escape(alt, quote=True)
        return f'<img src="{safe_src}" alt="{safe_alt}" style="{css}" />'

    def _code_html(self, language: str, text: str) -> str:
        if not text.strip() and not language:
            return ""
        cb = self._typ("code_block")
        css = _css(
            [
                ("background", cb.get("background")),
                ("color", cb.get("color", "#333333")),
                ("font-family", cb.get("font_family")),
                ("font-size", _px(cb.get("font_size", 14))),
                ("line-height", cb.get("line_height", 1.6)),
                ("padding", _px(cb.get("padding", 12))),
                ("border-radius", _px(cb.get("border_radius", 4))),
                ("white-space", cb.get("white_space", "pre-wrap")),
            ]
        )
        parts: list[str] = []
        if language:
            label_css = _css([("display", "block"), ("font-size", "12px"), ("color", "#888888")])
            parts.append(f'<span style="{label_css}">{html.escape(language)}</span>')
        if text:
            parts.append(html.escape(text))
        return f'<section style="{css}">\n' + "\n".join(parts) + "\n</section>"

    def _list_html(self, ordered: bool, items: list[str]) -> str:
        if not items:
            return ""
        spec = self._typ("list")
        indent = _px(spec.get("indent", 16))
        marker_color = spec.get("marker_color", "#07c160")
        item_margin = spec.get("item_margin", 6)
        parts: list[str] = []
        for idx, item in enumerate(items, 1):
            if not item.strip():
                continue
            marker = f"{idx}." if ordered else "•"
            row_css = _css(
                [
                    ("padding-left", indent),
                    ("margin-top", _px(item_margin)),
                    ("margin-bottom", _px(item_margin)),
                ]
            )
            marker_css = _css([("color", marker_color)])
            parts.append(
                f'<section style="{row_css}">'
                f'<span style="{marker_css}">{marker}</span>'
                f" {self._inline(item)}</section>"
            )
        return "\n".join(parts)

    def _hr_html(self) -> str:
        hr = self._comp("hr")
        css = _css(
            [
                ("height", "1px"),
                ("background", hr.get("color", "#e0e0e0")),
                ("margin-top", _px(hr.get("margin_top", 20))),
                ("margin-bottom", _px(hr.get("margin_bottom", 20))),
                ("font-size", "0"),
                ("line-height", "0"),
            ]
        )
        return f'<section style="{css}"> </section>'
