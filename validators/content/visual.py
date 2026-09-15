"""Visual Gate：ContentPackage.visual 的「成品必有图或占位符」强制检查。

对应 skills/visual/SKILL.md 的硬规则与 visual/references/visual-checklist.md：
- 恰好一份封面规格，且封面 prompt 必填（asset 缺失时 prompt 是占位与再生成的唯一依据）；
- 每张插图 prompt 必填：asset_path 为空的插图必须能以 :::figure 占位块呈现；
- 正文至少一张插图或图表（imagery 配额下限 1，确定性兜底永不产出空方案）；
- 插图 position 必须落在正文锚点范围内，否则插图会静默丢失。

与其他验证器同契约：一次扫描收集全部问题，不抛异常，空列表 = 通过。
锚点口径与 core.workflow.imagery.insert_images 一致（跳过首个标题，1-based）。
"""

from __future__ import annotations

import re

from core.artifacts.models import ContentPackage, ValidationIssue

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def _anchor_count(markdown: str) -> int:
    headings = [line for line in markdown.split("\n") if _HEADING_RE.match(line.strip())]
    return max(len(headings) - 1, 0)


def lint_visual(package: ContentPackage) -> list[ValidationIssue]:
    """对 ContentPackage.visual 做强制检查（gate=content），空列表 = 通过。"""
    issues: list[ValidationIssue] = []
    visual = package.visual
    cover = visual.cover
    if cover is None:
        issues.append(
            ValidationIssue(
                type="visual_cover_missing",
                node="visual",
                property="cover",
                message="缺少封面规格：成品必有图或占位符，封面 prompt 不可为空。",
            )
        )
    elif not cover.prompt.strip():
        issues.append(
            ValidationIssue(
                type="visual_cover_prompt_missing",
                node="visual",
                property="cover.prompt",
                message="封面 prompt 为空，无法生图也无法回填封面资产。",
            )
        )
    if not visual.images and not visual.diagrams:
        issues.append(
            ValidationIssue(
                type="visual_no_images",
                node="visual",
                property="images",
                message="正文没有任何插图或图表：成品必有图或占位符（配额下限 1 张）。",
            )
        )
    anchors = _anchor_count(package.semantic_markdown)
    for index, spec in enumerate(visual.images, start=1):
        if not spec.prompt.strip():
            issues.append(
                ValidationIssue(
                    type="visual_image_prompt_missing",
                    node=f"image_{index}",
                    property="prompt",
                    message=(
                        f"第 {index} 张插图（position={spec.position}）缺少生图 prompt，"
                        "既无法渲染也无法以 :::figure 占位。"
                    ),
                )
            )
        if anchors == 0 or spec.position > anchors:
            issues.append(
                ValidationIssue(
                    type="visual_image_position_out_of_range",
                    node=f"image_{index}",
                    property="position",
                    message=(
                        f"第 {index} 张插图 position={spec.position} 不在正文锚点范围内"
                        f"（可用锚点 {anchors} 个），插图会静默丢失。"
                    ),
                )
            )
    return issues
