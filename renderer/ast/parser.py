"""语义 Markdown → ContentAST 解析器（确定性，支持往返序列化）。

块级节点 id 为 node_N，语义组件节点 id 为 component_N —— 修复循环据此定位（H3）。
`>` 块引用解析为 QuoteNode；序列化时统一规范化为 :::quote 标记形式。

标记语法常量（MARKER_RE / ATTR_RE / 列表正则）公开导出：
组件 lint 复用同一份语法定义，保证 lint 与 parser 永不漂移。
"""

from __future__ import annotations

import re

from core.utils import estimate_word_count
from renderer.ast.nodes import (
    AnyASTNode,
    CalloutNode,
    CardNode,
    CodeNode,
    ContentAST,
    HeadingNode,
    HrNode,
    ImageNode,
    ListNode,
    NoteNode,
    ParagraphNode,
    QuoteNode,
)
from renderer.components.registry import MarkerValidationError, validate_marker


class ParseError(ValueError):
    """解析失败；error_type 供修复循环与 lint 分类。"""

    def __init__(self, error_type: str, message: str, line: int = 0):
        super().__init__(message)
        self.error_type = error_type
        self.line = line


MARKER_RE = re.compile(r"^:::(\w+)((?:\s+\w+=\"[^\"]*\")*)\s*$")
ATTR_RE = re.compile(r"(\w+)=\"([^\"]*)\"")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
UNORDERED_RE = re.compile(r"^[-*+]\s+(.*)$")
ORDERED_RE = re.compile(r"^\d+(?:[.]\s+|[、)]\s*)(.+)$")
_IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_HR_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$")
_QUOTE_PREFIX_RE = re.compile(r"^>\s?(.*)$")


def _parse_card_items(body_lines: list[str], line: int) -> list[str]:
    items: list[str] = []
    for raw in body_lines:
        s = raw.strip()
        if not s:
            continue
        m = UNORDERED_RE.match(s) or ORDERED_RE.match(s)
        if not m:
            raise ParseError(
                "invalid_card_content",
                "card 组件的正文必须是列表（每行以 - 或 1. 开头）",
                line,
            )
        items.append(m.group(1).strip())
    return items


def _is_block_boundary(s: str) -> bool:
    return bool(
        not s
        or s.startswith("```")
        or s.startswith(":::")
        or s.startswith(">")
        or _HEADING_RE.match(s)
        or _HR_RE.match(s)
        or _IMAGE_RE.match(s)
        or UNORDERED_RE.match(s)
        or ORDERED_RE.match(s)
    )


def parse(semantic_markdown: str, *, title: str = "", digest: str = "") -> ContentAST:
    """把语义 Markdown 解析为 ContentAST；非法输入抛 ParseError / MarkerValidationError。"""
    lines = semantic_markdown.split("\n")
    nodes: list[AnyASTNode] = []
    counters = {"block": 0, "component": 0}

    def next_block_id() -> str:
        counters["block"] += 1
        return f"node_{counters['block']}"

    def next_component_id() -> str:
        counters["component"] += 1
        return f"component_{counters['component']}"

    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith("```"):
            language = stripped[3:].strip()
            i += 1
            code_lines: list[str] = []
            closed = False
            while i < n:
                if lines[i].strip().startswith("```"):
                    closed = True
                    i += 1
                    break
                code_lines.append(lines[i])
                i += 1
            if not closed:
                raise ParseError("unclosed_code_block", "代码块未闭合（缺少结束的 ```）", i)
            nodes.append(
                CodeNode(node_id=next_block_id(), language=language, text="\n".join(code_lines))
            )
            continue

        marker = MARKER_RE.match(stripped)
        if marker:
            name = marker.group(1)
            attrs = dict(ATTR_RE.findall(marker.group(2)))
            try:
                validate_marker(name, attrs)
            except MarkerValidationError as exc:
                raise ParseError(exc.error_type, str(exc), i + 1) from exc
            body_lines: list[str] = []
            i += 1
            closed = False
            while i < n:
                inner = lines[i].strip()
                if inner.startswith(":::"):
                    if inner == ":::":
                        closed = True
                        i += 1
                        break
                    raise ParseError(
                        "invalid_nesting", f":::{name} 组件内不允许嵌套另一个 ::: 标记", i + 1
                    )
                body_lines.append(inner)
                i += 1
            if not closed:
                raise ParseError("unclosed_marker", f":::{name} 标记未闭合（缺少结束的 :::）", i)
            body = "\n".join(body_lines).strip()
            cid = next_component_id()
            if name == "note":
                nodes.append(NoteNode(node_id=cid, text=body))
            elif name == "quote":
                nodes.append(QuoteNode(node_id=cid, text=body, cite=attrs.get("cite", "")))
            elif name == "callout":
                nodes.append(
                    CalloutNode(
                        node_id=cid,
                        variant=attrs.get("type", "info"),
                        title=attrs.get("title", ""),
                        text=body,
                    )
                )
            else:
                items = _parse_card_items(body_lines, i)
                nodes.append(
                    CardNode(
                        node_id=cid,
                        title=attrs.get("title", ""),
                        items=items,
                        footer=attrs.get("footer", ""),
                    )
                )
            continue

        if stripped.startswith(":::"):
            if stripped == ":::":
                raise ParseError(
                    "stray_marker", "未配对的 ::: 结束标记（前面没有对应的开始标记）", i + 1
                )
            raise ParseError(
                "invalid_marker_syntax",
                f'{stripped!r} 不是合法的标记行（应为 :::name key="value" 形式）',
                i + 1,
            )

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                m = _QUOTE_PREFIX_RE.match(lines[i].strip())
                quote_lines.append(m.group(1) if m else "")
                i += 1
            text = "\n".join(quote_lines).strip()
            if text:
                nodes.append(QuoteNode(node_id=next_block_id(), text=text))
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            nodes.append(
                HeadingNode(
                    node_id=next_block_id(),
                    level=len(heading.group(1)),
                    text=heading.group(2).strip(),
                )
            )
            i += 1
            continue

        if _HR_RE.match(stripped):
            nodes.append(HrNode(node_id=next_block_id()))
            i += 1
            continue

        image = _IMAGE_RE.match(stripped)
        if image:
            nodes.append(ImageNode(node_id=next_block_id(), src=image.group(2), alt=image.group(1)))
            i += 1
            continue

        unordered = UNORDERED_RE.match(stripped)
        ordered = ORDERED_RE.match(stripped) if not unordered else None
        if unordered or ordered:
            is_ordered = bool(ordered)
            pattern = ORDERED_RE if is_ordered else UNORDERED_RE
            items: list[str] = []
            j = i
            while j < n:
                s = lines[j].strip()
                if not s:
                    k = j + 1
                    while k < n and not lines[k].strip():
                        k += 1
                    if k < n and pattern.match(lines[k].strip()):
                        j = k
                        continue
                    break
                m = pattern.match(s)
                if not m:
                    break
                items.append(m.group(1).strip())
                j += 1
            nodes.append(ListNode(node_id=next_block_id(), ordered=is_ordered, items=items))
            i = j
            continue

        para_lines: list[str] = []
        j = i
        while j < n and not _is_block_boundary(lines[j].strip()):
            para_lines.append(lines[j].strip())
            j += 1
        nodes.append(ParagraphNode(node_id=next_block_id(), text="\n".join(para_lines)))
        i = j

    texts: list[str] = []
    for node in nodes:
        if node.type in {"heading", "paragraph", "quote", "note", "callout", "code"}:
            texts.append(node.text)
        elif node.type == "card":
            texts.append(node.title)
            texts.extend(node.items)
            texts.append(node.footer)
        elif node.type == "list":
            texts.extend(node.items)
        elif node.type == "image":
            texts.append(node.alt)

    return ContentAST(
        title=title,
        digest=digest,
        nodes=nodes,
        word_count=estimate_word_count("\n".join(texts)),
    )


def _escape_attr(value: str) -> str:
    return value.replace('"', "'")


def serialize(ast: ContentAST) -> str:
    """把 ContentAST 序列化回语义 Markdown；引用统一输出 :::quote 规范形式。"""
    blocks: list[str] = []
    for node in ast.nodes:
        kind = node.type
        if kind == "heading":
            blocks.append(f"{'#' * node.level} {node.text}")
        elif kind == "paragraph":
            blocks.append(node.text)
        elif kind == "quote":
            cite = f' cite="{_escape_attr(node.cite)}"' if node.cite else ""
            blocks.append(f":::quote{cite}\n{node.text}\n:::")
        elif kind == "note":
            blocks.append(f":::note\n{node.text}\n:::")
        elif kind == "callout":
            attrs = f'type="{node.variant}"'
            if node.title:
                attrs += f' title="{_escape_attr(node.title)}"'
            blocks.append(f":::callout {attrs}\n{node.text}\n:::")
        elif kind == "card":
            attrs = ""
            if node.title:
                attrs += f' title="{_escape_attr(node.title)}"'
            if node.footer:
                attrs += f' footer="{_escape_attr(node.footer)}"'
            item_lines = [f"- {item}" for item in node.items]
            blocks.append(f":::card{attrs}\n" + "\n".join(item_lines) + "\n:::")
        elif kind == "image":
            blocks.append(f"![{node.alt}]({node.src})")
        elif kind == "code":
            blocks.append(f"```{node.language}\n{node.text}\n```")
        elif kind == "list":
            if node.ordered:
                blocks.append("\n".join(f"{idx}. {item}" for idx, item in enumerate(node.items, 1)))
            else:
                blocks.append("\n".join(f"- {item}" for item in node.items))
        elif kind == "hr":
            blocks.append("---")
    return "\n\n".join(blocks)
