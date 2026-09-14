"""语义 Markdown → ContentAST 解析器（确定性，支持往返序列化）。

块级节点 id 为 node_N，语义组件节点 id 为 component_N，嵌套子组件为 component_N.M
（M 为容器内子组件序号）—— 修复循环据此定位（H3）。
`>` 块引用解析为 QuoteNode；序列化时统一规范化为 :::quote 标记形式。

嵌套由 registry 契约驱动：仅 allowed_children 中的组件可作子组件（v0.3 仅 card
可嵌 note/quote/callout），深度上限 MAX_COMPONENT_DEPTH；违例报 invalid_nesting。

标记语法常量（MARKER_RE / ATTR_RE / 列表正则）公开导出：
组件 lint 复用同一份语法定义，保证 lint 与 parser 永不漂移。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.utils import estimate_word_count
from renderer.ast.nodes import (
    AnyASTNode,
    CalloutNode,
    CardItem,
    CardNode,
    CodeNode,
    ContentAST,
    FigureNode,
    HeadingNode,
    HrNode,
    ImageNode,
    ListNode,
    NoteNode,
    ParagraphNode,
    QuoteNode,
)
from renderer.components.registry import (
    MAX_COMPONENT_DEPTH,
    ComponentSpec,
    MarkerValidationError,
    validate_marker,
)


class ParseError(ValueError):
    """解析失败；error_type 供修复循环与 lint 分类。"""

    def __init__(self, error_type: str, message: str, line: int = 0):
        super().__init__(message)
        self.error_type = error_type
        self.line = line


@dataclass
class _OpenMarker:
    """解析栈中的开放组件：entries 按文档顺序混排原文行与已闭合的子节点。"""

    name: str
    attrs: dict[str, str]
    spec: ComponentSpec
    node_id: str
    entries: list[CardItem] = field(default_factory=list)
    children_opened: int = 0


MARKER_RE = re.compile(r"^:::(\w+)((?:\s+\w+=\"[^\"]*\")*)\s*$")
ATTR_RE = re.compile(r"(\w+)=\"([^\"]*)\"")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
UNORDERED_RE = re.compile(r"^[-*+]\s+(.*)$")
ORDERED_RE = re.compile(r"^\d+(?:[.]\s+|[、)]\s*)(.+)$")
_IMAGE_RE = re.compile(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$")
_HR_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$")
_QUOTE_PREFIX_RE = re.compile(r"^>\s?(.*)$")


def _parse_card_items(entries: list[CardItem], line: int) -> list[CardItem]:
    items: list[CardItem] = []
    for entry in entries:
        if isinstance(entry, str):
            s = entry.strip()
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
        else:
            items.append(entry)
    return items


def _build_component(comp: _OpenMarker, close_line: int) -> AnyASTNode:
    body = "\n".join(e for e in comp.entries if isinstance(e, str)).strip()
    if comp.name == "note":
        return NoteNode(node_id=comp.node_id, text=body)
    if comp.name == "quote":
        return QuoteNode(node_id=comp.node_id, text=body, cite=comp.attrs.get("cite", ""))
    if comp.name == "callout":
        return CalloutNode(
            node_id=comp.node_id,
            variant=comp.attrs.get("type", "info"),
            title=comp.attrs.get("title", ""),
            text=body,
        )
    if comp.name == "figure":
        return FigureNode(node_id=comp.node_id, prompt=body)
    return CardNode(
        node_id=comp.node_id,
        title=comp.attrs.get("title", ""),
        items=_parse_card_items(comp.entries, close_line),
        footer=comp.attrs.get("footer", ""),
    )


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

    open_stack: list[_OpenMarker] = []

    def open_component(name: str, attrs: dict[str, str], spec: ComponentSpec) -> None:
        if open_stack:
            parent = open_stack[-1]
            if name not in parent.spec.allowed_children:
                raise ParseError(
                    "invalid_nesting",
                    f":::{parent.name} 组件内不允许嵌套 :::{name}"
                    f"（允许的子组件：{sorted(parent.spec.allowed_children)}）",
                    i + 1,
                )
            if len(open_stack) >= MAX_COMPONENT_DEPTH:
                raise ParseError(
                    "invalid_nesting",
                    f"组件嵌套深度超过上限 {MAX_COMPONENT_DEPTH}",
                    i + 1,
                )
            parent.children_opened += 1
            node_id = f"{parent.node_id}.{parent.children_opened}"
        else:
            node_id = next_component_id()
        open_stack.append(_OpenMarker(name=name, attrs=attrs, spec=spec, node_id=node_id))

    def close_component() -> None:
        comp = open_stack.pop()
        node = _build_component(comp, i)
        if open_stack:
            open_stack[-1].entries.append(node)
        else:
            nodes.append(node)

    def try_open_marker() -> bool:
        marker = MARKER_RE.match(stripped)
        if not marker:
            return False
        name = marker.group(1)
        attrs = dict(ATTR_RE.findall(marker.group(2)))
        try:
            spec = validate_marker(name, attrs)
        except MarkerValidationError as exc:
            raise ParseError(exc.error_type, str(exc), i + 1) from exc
        open_component(name, attrs, spec)
        return True

    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()

        if open_stack:
            if not stripped:
                open_stack[-1].entries.append("")
                i += 1
                continue
            if stripped == ":::":
                i += 1
                close_component()
                continue
            if try_open_marker():
                i += 1
                continue
            if stripped.startswith(":::"):
                raise ParseError(
                    "invalid_nesting",
                    f":::{open_stack[-1].name} 组件内不允许嵌套另一个 ::: 标记",
                    i + 1,
                )
            open_stack[-1].entries.append(stripped)
            i += 1
            continue

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

        if try_open_marker():
            i += 1
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

    if open_stack:
        unclosed = open_stack[-1]
        raise ParseError(
            "unclosed_marker", f":::{unclosed.name} 标记未闭合（缺少结束的 :::）", i
        )

    texts: list[str] = []
    for node in nodes:
        if node.type in {"heading", "paragraph", "quote", "note", "callout", "code"}:
            texts.append(node.text)
        elif node.type == "card":
            texts.append(node.title)
            for item in node.items:
                texts.append(item if isinstance(item, str) else item.text)
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


def _component_block(node: NoteNode | QuoteNode | CalloutNode) -> str:
    if node.type == "quote":
        cite = f' cite="{_escape_attr(node.cite)}"' if node.cite else ""
        return f":::quote{cite}\n{node.text}\n:::"
    if node.type == "note":
        return f":::note\n{node.text}\n:::"
    attrs = f'type="{node.variant}"'
    if node.title:
        attrs += f' title="{_escape_attr(node.title)}"'
    return f":::callout {attrs}\n{node.text}\n:::"


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
            blocks.append(_component_block(node))
        elif kind == "note":
            blocks.append(_component_block(node))
        elif kind == "callout":
            blocks.append(_component_block(node))
        elif kind == "card":
            attrs = ""
            if node.title:
                attrs += f' title="{_escape_attr(node.title)}"'
            if node.footer:
                attrs += f' footer="{_escape_attr(node.footer)}"'
            parts: list[str] = []
            for item in node.items:
                if isinstance(item, str):
                    parts.append(f"- {item}")
                else:
                    parts.append(_component_block(item))
            blocks.append(f":::card{attrs}\n" + "\n".join(parts) + "\n:::")
        elif kind == "figure":
            blocks.append(f":::figure\n{node.prompt}\n:::")
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
