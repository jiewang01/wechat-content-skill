"""组件 lint（蓝图 9.2）：对语义 Markdown 做容错扫描，收集全部组件级错误。

与 parser 的 fail-fast 语义互补：parser 首错即抛（渲染门直接拦截），
lint 则一次报告全部问题 —— Error Report 需要完整可修复点位列表，
这是 H3（按 node 定向修复）的前提。

检出错误类型（蓝图 9.2 五类 + 语法补充）：
- unknown_component / missing_required_prop / unsupported_attribute /
  invalid_prop_value —— 复用注册表契约（单一事实来源）
- invalid_nesting / unclosed_marker / invalid_card_content / stray_marker /
  invalid_marker_syntax / unclosed_code_block —— 与 parser 同一分类
- theme_component_missing —— 文档使用的组件在主题中未启用或缺样式

v0.3 嵌套：栈式扫描与 parser 同构 —— 顶层组件编号 component_N、子组件
component_N.M；嵌套违例归属父组件报 invalid_nesting（违例行跳过不建子栈，
与 parser 不构建该节点同构）；EOF 时未闭合的每一层全量报告。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.artifacts.models import ValidationIssue
from renderer.ast.parser import ATTR_RE, MARKER_RE, ORDERED_RE, UNORDERED_RE
from renderer.components.registry import (
    MAX_COMPONENT_DEPTH,
    MarkerValidationError,
    get_spec,
    marker_names,
    validate_marker,
)
from renderer.themes import Theme


def _card_content_issues(component_id: str, body: list[tuple[int, str]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for line_no, text in body:
        if not text:
            continue
        if not (UNORDERED_RE.match(text) or ORDERED_RE.match(text)):
            issues.append(
                ValidationIssue(
                    type="invalid_card_content",
                    node=component_id,
                    message=f"第 {line_no} 行：card 组件的正文必须是列表（每行以 - 或 1. 开头）",
                )
            )
    return issues


@dataclass
class _LintMarker:
    """lint 扫描栈中的开放组件；body 只收直接文本行（子组件行入子栈）。"""

    name: str
    cid: str
    line_no: int
    body: list[tuple[int, str]] = field(default_factory=list)
    children_opened: int = 0


def lint_components(semantic_markdown: str, theme: Theme | None = None) -> list[ValidationIssue]:
    """容错扫描语义 Markdown；返回全部组件级错误（不抛异常，空列表 = 通过）。"""
    issues: list[ValidationIssue] = []

    def add(error_type: str, node: str, message: str, prop: str = "") -> None:
        issues.append(ValidationIssue(type=error_type, node=node, property=prop, message=message))

    def check_theme(name: str, cid: str, line_no: int) -> None:
        if theme is None or name not in marker_names():
            return
        if not theme.components_enabled.get(name, False):
            add(
                "theme_component_missing",
                cid,
                f"第 {line_no} 行：主题 {theme.name!r} 未启用组件 {name!r}"
                "（theme.yaml components）",
            )
        elif name not in theme.components:
            add(
                "theme_component_missing",
                cid,
                f"第 {line_no} 行：主题 {theme.name!r} 缺少组件 {name!r} 的样式定义"
                "（components.yaml）",
            )

    def open_child(parent: _LintMarker, name: str, attrs: dict[str, str], line_no: int) -> None:
        """校验子组件并按 registry 契约开栈；违例归属父组件报 invalid_nesting。"""
        parent.children_opened += 1
        cid = f"{parent.cid}.{parent.children_opened}"
        known = True
        try:
            validate_marker(name, attrs)
        except MarkerValidationError as exc:
            add(exc.error_type, cid, f"第 {line_no} 行：{exc}", exc.prop)
            known = name in marker_names()
        spec = get_spec(parent.name)
        if known and spec is not None and name not in spec.allowed_children:
            add(
                "invalid_nesting",
                parent.cid,
                f"第 {line_no} 行：:::{parent.name} 组件内不允许嵌套 :::{name}"
                f"（允许的子组件：{sorted(spec.allowed_children)}）",
            )
            return
        if len(stack) >= MAX_COMPONENT_DEPTH:
            add(
                "invalid_nesting",
                parent.cid,
                f"第 {line_no} 行：组件嵌套深度超过上限 {MAX_COMPONENT_DEPTH}",
            )
            return
        check_theme(name, cid, line_no)
        stack.append(_LintMarker(name=name, cid=cid, line_no=line_no))

    lines = semantic_markdown.split("\n")
    n = len(lines)
    counter = 0
    stack: list[_LintMarker] = []
    in_code = False
    code_line = 0

    i = 0
    while i < n:
        stripped = lines[i].strip()
        line_no = i + 1

        if stack:
            top = stack[-1]
            if stripped == ":::":
                if top.name == "card":
                    issues.extend(_card_content_issues(top.cid, top.body))
                stack.pop()
            else:
                marker = MARKER_RE.match(stripped)
                if marker:
                    attrs = dict(ATTR_RE.findall(marker.group(2)))
                    open_child(top, marker.group(1), attrs, line_no)
                elif stripped.startswith(":::"):
                    add(
                        "invalid_nesting",
                        top.cid,
                        f"第 {line_no} 行：:::{top.name} 组件内不允许嵌套另一个 ::: 标记",
                    )
                else:
                    top.body.append((line_no, stripped))
            i += 1
            continue

        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_line = line_no
            else:
                in_code = False
            i += 1
            continue
        if in_code:
            i += 1
            continue

        if stripped == ":::":
            add("stray_marker", "", f"第 {line_no} 行：未配对的 ::: 结束标记")
            i += 1
            continue

        marker = MARKER_RE.match(stripped)
        if marker:
            name = marker.group(1)
            attrs = dict(ATTR_RE.findall(marker.group(2)))
            counter += 1
            cid = f"component_{counter}"
            try:
                validate_marker(name, attrs)
            except MarkerValidationError as exc:
                add(exc.error_type, cid, f"第 {line_no} 行：{exc}", exc.prop)
            check_theme(name, cid, line_no)
            stack.append(_LintMarker(name=name, cid=cid, line_no=line_no))
            i += 1
            continue

        if stripped.startswith(":::"):
            add(
                "invalid_marker_syntax",
                "",
                f'第 {line_no} 行：{stripped!r} 不是合法的标记行（应为 :::name key="value" 形式）',
            )
            i += 1
            continue

        i += 1

    for comp in stack:
        add(
            "unclosed_marker",
            comp.cid,
            f"第 {comp.line_no} 行开始的 :::{comp.name} 标记未闭合（缺少结束的 :::）",
        )
    if in_code:
        add("unclosed_code_block", "", f"第 {code_line} 行开始的代码块未闭合（缺少结束的 ```）")

    return issues
