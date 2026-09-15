"""Visual Gate 单测：ContentPackage.visual 的强制占位检查（蓝图 ch12 / visual skill 硬规则）。

回归背景（run_20260915_001）：空 VisualPlan（cover=None、images=[]、无任何 prompt）
曾静默通过全部门禁。本文件锁定五条错误规则：
- visual_cover_missing / visual_cover_prompt_missing：封面必填且 prompt 不可为空；
- visual_no_images：正文至少一张插图或图表（配额下限 1）；
- visual_image_prompt_missing：asset 缺失的插图必须能以 :::figure 占位；
- visual_image_position_out_of_range：position 落在锚点范围外会被 insert_images
  静默丢弃（锚点口径：跳过首个标题，1-based）。
"""

from __future__ import annotations

from core.artifacts.models import (
    ContentPackage,
    CoverSpec,
    DiagramSpec,
    ImageSpec,
    VisualPlan,
)
from validators.content import lint_visual

MARKDOWN = """# 手冲咖啡入门

## 冲煮步骤

把水烧到 92 度，闷蒸 30 秒。

## 小结

参数稳定，风味才稳定。
"""


def make_package(visual: VisualPlan, markdown: str = MARKDOWN) -> ContentPackage:
    return ContentPackage(title="手冲咖啡入门", semantic_markdown=markdown, visual=visual)


def make_visual(**overrides) -> VisualPlan:
    defaults = dict(
        cover=CoverSpec(prompt="手冲咖啡器具的扁平概念插画"),
        images=[ImageSpec(position=1, purpose="concept", prompt="注水闷蒸示意插画")],
    )
    defaults.update(overrides)
    return VisualPlan(**defaults)


def issue_types(package: ContentPackage) -> list[str]:
    return [issue.type for issue in lint_visual(package)]


def test_clean_visual_passes():
    assert lint_visual(make_package(make_visual())) == []


def test_missing_cover_rejected():
    types = issue_types(make_package(make_visual(cover=None)))
    assert types == ["visual_cover_missing"]


def test_cover_without_prompt_rejected():
    visual = make_visual(cover=CoverSpec(prompt="   "))
    assert issue_types(make_package(visual)) == ["visual_cover_prompt_missing"]


def test_no_images_and_no_diagrams_rejected():
    visual = make_visual(images=[])
    assert issue_types(make_package(visual)) == ["visual_no_images"]


def test_diagrams_alone_satisfy_image_floor():
    visual = make_visual(
        images=[], diagrams=[DiagramSpec(position=1, type="flowchart", spec="A --> B")]
    )
    assert lint_visual(make_package(visual)) == []


def test_image_without_prompt_rejected():
    visual = make_visual(images=[ImageSpec(position=1, prompt="")])
    assert issue_types(make_package(visual)) == ["visual_image_prompt_missing"]


def test_image_position_beyond_anchors_rejected():
    # 2 个锚点（冲煮步骤 / 小结），position=3 越界 → 插图会被静默丢弃
    visual = make_visual(images=[ImageSpec(position=3, prompt="越界插图")])
    assert issue_types(make_package(visual)) == ["visual_image_position_out_of_range"]


def test_image_without_any_section_anchor_rejected():
    # 正文只有文章标题（0 锚点）：任何 position 都无处安放
    markdown = "# 手冲咖啡入门\n\n把水烧到 92 度。\n"
    visual = make_visual(images=[ImageSpec(position=1, prompt="无处安放的插图")])
    assert issue_types(make_package(visual, markdown)) == ["visual_image_position_out_of_range"]


def test_empty_visual_collects_all_issues_at_once():
    # run_20260915_001 回归：一次扫描同时收集封面缺失 + 无插图，而不是只报第一个
    types = issue_types(make_package(VisualPlan()))
    assert types == ["visual_cover_missing", "visual_no_images"]


def test_issues_carry_error_severity():
    for issue in lint_visual(make_package(VisualPlan())):
        assert issue.severity == "error"
        assert issue.node and issue.property and issue.message
