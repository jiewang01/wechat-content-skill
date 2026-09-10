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
"""

from __future__ import annotations

from core.artifacts.models import ValidationIssue
from renderer.ast.parser import ATTR_RE, MARKER_RE, ORDERED_RE, UNORDERED_RE
from renderer.components.registry import MarkerValidationError, marker_names, validate_marker
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


def lint_components(semantic_markdown: str, theme: Theme | None = None) -> list[ValidationIssue]:
    """容错扫描语义 Markdown；返回全部组件级错误（不抛异常，空列表 = 通过）。"""
    issues: list[ValidationIssue] = []

    def add(error_type: str, node: str, message: str, prop: str = "") -> None:
        issues.append(ValidationIssue(type=error_type, node=node, property=prop, message=message))

    lines = semantic_markdown.split("\n")
    n = len(lines)
    counter = 0
    open_name = ""
    open_id = ""
    open_line = 0
    body: list[tuple[int, str]] = []
    in_code = False
    code_line = 0

    i = 0
    while i < n:
        stripped = lines[i].strip()
        line_no = i + 1

        if open_id:
            if stripped == ":::":
                if open_name == "card":
                    issues.extend(_card_content_issues(open_id, body))
                open_id = ""
            elif stripped.startswith(":::"):
                add(
                    "invalid_nesting",
                    open_id,
                    f"第 {line_no} 行：:::{open_name} 组件内不允许嵌套另一个 ::: 标记",
                )
            else:
                body.append((line_no, stripped))
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
            if theme is not None and name in marker_names():
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
            open_name, open_id, open_line, body = name, cid, line_no, []
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

    if open_id:
        add(
            "unclosed_marker",
            open_id,
            f"第 {open_line} 行开始的 :::{open_name} 标记未闭合（缺少结束的 :::）",
        )
    if in_code:
        add("unclosed_code_block", "", f"第 {code_line} 行开始的代码块未闭合（缺少结束的 ```）")

    return issues
