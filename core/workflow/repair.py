"""定向修复循环（蓝图十章，计划 M4-T4）：Render → Validate → ErrorReport → Targeted Repair。

领域模型：修复循环作用于「渲染产物段」而非 AST —— AST 不携带样式，
非法 CSS 只可能出现在渲染后的 HTML 中；HtmlSegment 把每段 HTML 与
node_id 绑定（来自 renderer.render_segments），HTML 层错误据此归属到
节点，这是 H3 节点级定向修复的前提。

修复策略注册表（全部确定性，H8）：
- unsupported_css（受限取值，如 display:grid）→ 替换为回退值
  display:block（公众号网格布局的标准降级路径）
- unsupported_css（白名单外属性，如 position:fixed）→ 删除该声明；
  style 因此为空时连属性一并移除

其余错误类型（forbidden_tag / empty_node / html_structure 等）没有
确定性修复手段 —— 修复它们需要发明内容或猜测意图，超出确定性边界；
这类错误原样保留在最终 ErrorReport 中，由上层决定重写或人工介入。

约束落实：
- H3：只替换 issue.node 对应的段，其余段字节不变
- H4：修复轮数上限 3，max_rounds 越界直接抛 ValueError
- H6：repaired_nodes / rounds / 最终 ValidationReport（即蓝图十章
  ErrorReport，gate="render"）全程留痕
- 无可修复项或策略未命中时提前终止，不做无效空转
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from core.artifacts.models import ValidationIssue, ValidationReport
from renderer.ast.nodes import ContentAST
from renderer.html.renderer import HtmlRenderer
from validators.html.checks import ALLOWED_CSS_PROPS, lint_html

MAX_REPAIR_ROUNDS = 3

Linter = Callable[[str], list[ValidationIssue]]

_FALLBACK_VALUES: dict[str, str] = {"display": "block"}

_STYLE_ATTR_RE = re.compile(
    r"(?P<lead>[ \t]*)(?<![\w-])style[ \t]*=[ \t]*(?P<quote>[\"'])(?P<value>[^\"']*)(?P=quote)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class HtmlSegment:
    """渲染产物段：node_id 与该节点渲染出的 HTML 片段一一对应。"""

    node_id: str
    html: str


@dataclass(frozen=True)
class RepairOutcome:
    """修复循环结果（H6 审计）：最终产物 + ErrorReport + 修复留痕。"""

    segments: list[HtmlSegment]
    html: str
    report: ValidationReport
    rounds: int
    repaired_nodes: list[str]


def _repair_unsupported_css(html: str, issue: ValidationIssue) -> str | None:
    """按 issue.property 修复段内全部匹配声明；无命中返回 None。

    issue.property 形如 "prop:value"（lint_html 的输出格式）。
    一次调用清理段内所有出现（一个组件可含多个内联样式的标签）。
    """
    target = issue.property
    if not target or ":" not in target:
        return None
    prop, _, bad_value = target.partition(":")
    prop = prop.strip().lower()
    bad_value = bad_value.strip()
    if not prop or not bad_value:
        return None

    changed = False

    def _rewrite(match: re.Match[str]) -> str:
        nonlocal changed
        kept: list[str] = []
        touched = False
        for chunk in match.group("value").split(";"):
            decl = chunk.strip()
            if not decl or ":" not in decl:
                continue
            p, _, v = decl.partition(":")
            p, v = p.strip().lower(), v.strip()
            if p == prop and v.lower() == bad_value.lower():
                touched = True
                fallback = _FALLBACK_VALUES.get(p)
                if p in ALLOWED_CSS_PROPS and fallback is not None:
                    kept.append(f"{p}:{fallback}")
                continue
            kept.append(decl)
        if not touched:
            return match.group(0)
        changed = True
        if not kept:
            return ""
        lead = match.group("lead") or " "
        return f'{lead}style="{";".join(kept)};"'

    new_html = _STYLE_ATTR_RE.sub(_rewrite, html)
    return new_html if changed else None


_REPAIR_STRATEGIES: dict[str, Callable[[str, ValidationIssue], str | None]] = {
    "unsupported_css": _repair_unsupported_css,
}


def _validate_segments(segments: list[HtmlSegment], lint: Linter) -> ValidationReport:
    """逐段验证并把错误归属到 node_id（段是归属的唯一事实来源）。"""
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    for segment in segments:
        for issue in lint(segment.html):
            attributed = issue.model_copy(update={"node": segment.node_id})
            if attributed.severity == "error":
                errors.append(attributed)
            else:
                warnings.append(attributed)
    return ValidationReport(
        status="failed" if errors else "passed",
        gate="render",
        errors=errors,
        warnings=warnings,
    )


def repair_document(
    segments: list[HtmlSegment],
    *,
    lint: Linter = lint_html,
    max_rounds: int = MAX_REPAIR_ROUNDS,
) -> RepairOutcome:
    """对带节点归属的渲染段执行修复循环（≤ max_rounds 轮，H4）。"""
    if not 1 <= max_rounds <= MAX_REPAIR_ROUNDS:
        raise ValueError(
            f"max_rounds 必须在 1..{MAX_REPAIR_ROUNDS} 之间（H4 硬约束），当前 {max_rounds}"
        )

    current = [HtmlSegment(node_id=s.node_id, html=s.html) for s in segments]
    index: dict[str, int] = {}
    for position, segment in enumerate(current):
        if segment.node_id in index:
            raise ValueError(f"段 node_id 重复：{segment.node_id}")
        index[segment.node_id] = position

    repaired_nodes: list[str] = []
    rounds = 0
    report = _validate_segments(current, lint)

    while report.status == "failed" and rounds < max_rounds:
        repairable = [
            issue
            for issue in report.errors
            if issue.type in _REPAIR_STRATEGIES and issue.node in index
        ]
        if not repairable:
            break
        progressed = False
        for issue in repairable:
            position = index[issue.node]
            segment = current[position]
            new_html = _REPAIR_STRATEGIES[issue.type](segment.html, issue)
            if new_html is None:
                continue
            current[position] = HtmlSegment(node_id=segment.node_id, html=new_html)
            progressed = True
            if segment.node_id not in repaired_nodes:
                repaired_nodes.append(segment.node_id)
        if not progressed:
            break
        rounds += 1
        report = _validate_segments(current, lint)

    html = "\n".join(segment.html for segment in current)
    return RepairOutcome(
        segments=current,
        html=html,
        report=report,
        rounds=rounds,
        repaired_nodes=repaired_nodes,
    )


def repair_rendered(
    ast: ContentAST,
    renderer: HtmlRenderer | None = None,
    *,
    max_rounds: int = MAX_REPAIR_ROUNDS,
) -> RepairOutcome:
    """渲染并执行修复循环（蓝图十章闭环入口：Render → Validate → Repair → …）。"""
    if renderer is None:
        renderer = HtmlRenderer()
    segments = [
        HtmlSegment(node_id=node_id, html=chunk) for node_id, chunk in renderer.render_segments(ast)
    ]
    return repair_document(segments, max_rounds=max_rounds)
