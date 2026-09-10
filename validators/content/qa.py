"""Content QA v1（蓝图 9.1 子集，计划 M4-T3）：结构 / 字数 / AI 味复检 / 引用一致性。

四项检查全部确定性执行（硬约束 H8）；AI 味复检不信任 draft.humanize 缓存，
而是对当前 markdown 重新运行 skills/content/humanize 检测器。
字数口径复用 core.utils.estimate_word_count（CJK 计 1、西文单词计 1），
与 parser 统计 ContentPackage.word_count 的方式保持一致。

容错契约与其他验证器相同：一次扫描收集全部问题，不抛异常，空列表 = 通过；
research / brief 缺省时跳过对应检查（优雅降级），引用一致性检查需要
research 提供 Source / Fact 注册表。
"""

from __future__ import annotations

import re

from core.artifacts.models import (
    ArticleDraft,
    ContentBrief,
    ResearchResult,
    ValidationIssue,
)
from core.utils import estimate_word_count
from skills.content.humanize.detector import HumanizeRules, analyze_text

_HEADING_LINE_RE = re.compile(r"^#{1,6}[ \t]+\S", re.MULTILINE)

_WORD_COUNT_TOLERANCE_MIN = 20
_WORD_COUNT_TOLERANCE_RATIO = 0.05
_WORD_TARGET_MIN_RATIO = 0.5


def lint_content(
    draft: ArticleDraft,
    research: ResearchResult | None = None,
    brief: ContentBrief | None = None,
    rules: HumanizeRules | None = None,
) -> list[ValidationIssue]:
    """对 ArticleDraft 做 Content Gate 检查（蓝图 9.1 v1 四项），空列表 = 通过。"""
    issues: list[ValidationIssue] = []
    issues.extend(_check_structure(draft))
    issues.extend(_check_word_count(draft, brief))
    issues.extend(_check_ai_flavor(draft, rules))
    issues.extend(_check_citations(draft, research, brief))
    return issues


def _check_structure(draft: ArticleDraft) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not draft.title.strip():
        issues.append(
            ValidationIssue(
                type="structure_incomplete",
                node="draft",
                property="title",
                message="标题为空，Content Gate 要求非空标题。",
            )
        )
    if not draft.markdown.strip():
        issues.append(
            ValidationIssue(
                type="structure_incomplete",
                node="draft",
                property="markdown",
                message="正文为空，无法进入渲染与发布。",
            )
        )
        return issues
    if not _HEADING_LINE_RE.search(draft.markdown):
        issues.append(
            ValidationIssue(
                type="structure_incomplete",
                node="draft",
                property="markdown",
                message="正文缺少 Markdown 标题行（# 至 ######），结构不完整。",
            )
        )
    return issues


def _check_word_count(draft: ArticleDraft, brief: ContentBrief | None) -> list[ValidationIssue]:
    if not draft.markdown.strip():
        return []
    actual = estimate_word_count(draft.markdown)
    tolerance = max(_WORD_COUNT_TOLERANCE_MIN, round(actual * _WORD_COUNT_TOLERANCE_RATIO))
    issues: list[ValidationIssue] = []
    if abs(draft.word_count - actual) > tolerance:
        issues.append(
            ValidationIssue(
                type="word_count_mismatch",
                node="draft",
                property="word_count",
                message=f"声明字数 {draft.word_count}，实际 {actual}，相差超过容差 {tolerance}。",
            )
        )
    if brief is not None and actual < brief.word_target * _WORD_TARGET_MIN_RATIO:
        issues.append(
            ValidationIssue(
                type="word_count_below_target",
                node="draft",
                property="word_count",
                severity="warning",
                message=f"实际字数 {actual}，低于大纲目标 {brief.word_target} 的 50%，内容偏薄。",
            )
        )
    return issues


def _check_ai_flavor(draft: ArticleDraft, rules: HumanizeRules | None) -> list[ValidationIssue]:
    if not draft.markdown.strip():
        return []
    report = analyze_text(draft.markdown, rules=rules)
    return [_ai_flavor_issue(item) for item in report.issues]


def _ai_flavor_issue(item: dict[str, str]) -> ValidationIssue:
    return ValidationIssue(
        type=f"ai_flavor_{item['type']}",
        node="draft",
        property=item.get("evidence", ""),
        severity="error" if item.get("severity") == "error" else "warning",
        message=item.get("message", ""),
    )


def _check_citations(
    draft: ArticleDraft,
    research: ResearchResult | None,
    brief: ContentBrief | None,
) -> list[ValidationIssue]:
    if research is None:
        return []
    issues: list[ValidationIssue] = []
    known_source_ids = {source.source_id for source in research.sources}
    for fact in research.facts:
        for source_id in dict.fromkeys(fact.source_ids):
            if source_id not in known_source_ids:
                issues.append(
                    ValidationIssue(
                        type="unknown_source_ref",
                        node=fact.fact_id,
                        property=source_id,
                        message=f"事实 {fact.fact_id} 引用了不存在的 source_id「{source_id}」。",
                    )
                )
    known_fact_ids = {fact.fact_id for fact in research.facts}
    for fact_id in dict.fromkeys(draft.fact_ids):
        if fact_id not in known_fact_ids:
            issues.append(
                ValidationIssue(
                    type="unknown_fact_ref",
                    node="draft",
                    property=fact_id,
                    message=f"文章引用了不存在的事实「{fact_id}」。",
                )
            )
    if brief is not None:
        for index, section in enumerate(brief.sections, start=1):
            for fact_id in dict.fromkeys(section.fact_ids):
                if fact_id not in known_fact_ids:
                    issues.append(
                        ValidationIssue(
                            type="unknown_fact_ref",
                            node=f"section_{index}",
                            property=fact_id,
                            message=f"大纲第 {index} 节引用了不存在的事实「{fact_id}」。",
                        )
                    )
    return issues
