"""visual ↔ 正文一致性校验（prompt-first 配图契约）。

契约：ContentPackage.visual.images 与语义 Markdown 必须一一对应——
- asset_path 为空的插图以 :::figure 占位块呈现（prompt 即五要素生图提示词）；
- asset_path 已回填的插图以 ![purpose](asset) 图片语法呈现。

任何一侧缺失都意味着配图方案与正文脱节：漏插占位块（visual_figure_missing）、
孤儿占位块（figure_orphan）、资产未入文（visual_asset_missing_in_body）。

契约约定：输入文档，输出 list[ValidationIssue]（空列表 = 通过），不抛异常
（与 component / content / html / wechat 层一致），供 Error Report 与门禁消费。
"""

from __future__ import annotations

import re

from core.artifacts.models import ContentPackage, ValidationIssue

_FIGURE_OPEN_RE = re.compile(r"^:::figure\s*$")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")


def _figure_texts(semantic_markdown: str) -> list[tuple[int, str]]:
    """提取 :::figure 占位块，返回 (起始行号, 块内文本)；空块不计。"""
    figures: list[tuple[int, str]] = []
    lines = semantic_markdown.split("\n")
    i = 0
    while i < len(lines):
        if _FIGURE_OPEN_RE.match(lines[i].strip()):
            start = i + 1
            body: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                body.append(lines[i])
                i += 1
            text = "\n".join(body).strip()
            if text:
                figures.append((start, text))
        i += 1
    return figures


def lint_visual_consistency(package: ContentPackage) -> list[ValidationIssue]:
    """校验 visual.images 与正文 figure 占位块 / 图片引用的一致性。"""
    issues: list[ValidationIssue] = []

    def add(error_type: str, node: str, message: str) -> None:
        issues.append(ValidationIssue(type=error_type, node=node, message=message))

    figures = _figure_texts(package.semantic_markdown)
    figure_prompts = {text for _, text in figures}
    referenced_assets = set(_IMAGE_RE.findall(package.semantic_markdown))

    images = package.visual.images if package.visual else []
    pending_prompts = {
        spec.prompt.strip() for spec in images if not spec.asset_path and spec.prompt.strip()
    }
    for index, spec in enumerate(images):
        if spec.asset_path:
            if spec.asset_path not in referenced_assets:
                add(
                    "visual_asset_missing_in_body",
                    f"visual.images[{index}]",
                    f"第 {spec.position} 位插图已回填资产 {spec.asset_path}，"
                    "但正文未出现对应图片引用",
                )
        elif spec.prompt.strip() and spec.prompt.strip() not in figure_prompts:
            add(
                "visual_figure_missing",
                f"visual.images[{index}]",
                f"第 {spec.position} 位插图的 prompt 未以 :::figure 占位块出现在正文",
            )
    for line_no, text in figures:
        if text not in pending_prompts:
            add(
                "figure_orphan",
                f"figure[L{line_no}]",
                "正文 :::figure 占位块没有对应待配图的 visual.images 条目",
            )
    return issues
