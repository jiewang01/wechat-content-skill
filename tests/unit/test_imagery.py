"""imagery 单测：确定性配图规划——配额、锚点提取、五要素、主题联动、空资产防护。"""

import pytest

from core.artifacts.models import ContentPackage, ImageSpec
from core.workflow.imagery import (
    ImageryProfile,
    build_brief,
    cover_prompt,
    extract_anchors,
    image_quota,
    plan_visual,
    section_prompt,
)
from core.workflow.pipeline import _insert_images
from renderer.themes import Theme, load_theme

MARKDOWN = """# 文章标题

导语第一段。

## 第一节

**加粗**正文行。

:::note
组件行，不应成为摘要。
:::

## 第二节

普通正文。

## 第三节

收尾正文。
"""


def _package(word_count: int = 500) -> ContentPackage:
    return ContentPackage(
        title="测试文章",
        digest="一句话摘要。第二句被截断。",
        semantic_markdown=MARKDOWN,
        word_count=word_count,
    )


@pytest.fixture()
def orange() -> Theme:
    return load_theme("orange-heart")


@pytest.fixture()
def minimal() -> Theme:
    return load_theme("minimal")


@pytest.mark.parametrize(
    ("words", "expected"),
    [(0, 1), (100, 1), (600, 1), (601, 2), (1200, 2), (1800, 3), (2400, 4), (9600, 4)],
)
def test_image_quota(words: int, expected: int):
    assert image_quota(words) == expected


def test_extract_anchors_skips_title_and_strips_inline():
    anchors = extract_anchors(MARKDOWN)
    assert [a.position for a in anchors] == [1, 2, 3]
    assert [a.title for a in anchors] == ["第一节", "第二节", "第三节"]
    assert anchors[0].summary == "加粗正文行。"
    assert anchors[1].summary == "普通正文。"


def test_extract_anchors_empty_when_single_heading():
    assert extract_anchors("# 只有标题\n\n正文。") == []


def test_cover_prompt_five_elements(orange: Theme):
    profile = ImageryProfile.from_theme(orange)
    prompt = cover_prompt("测试文章", "一句话摘要。第二句。", profile)
    assert prompt.startswith("测试文章——一句话摘要")
    assert "2.35:1" in prompt
    assert "#ef7060" in prompt
    assert prompt.endswith("画面中不出现任何文字、无水印、无 logo。")


def test_cover_prompt_without_digest(orange: Theme):
    profile = ImageryProfile.from_theme(orange)
    assert cover_prompt("标题", "", profile).startswith("标题的概念意象")


def test_section_prompt_five_elements(orange: Theme):
    anchor = extract_anchors(MARKDOWN)[1]
    prompt = section_prompt(anchor, ImageryProfile.from_theme(orange))
    assert "第二节" in prompt and "普通正文。" in prompt
    assert "16:9" in prompt
    assert "#ef7060" in prompt
    assert prompt.endswith("画面中不出现任何文字、无水印、无 logo。")


def test_prompts_self_contained(orange: Theme):
    plan = plan_visual(_package(), orange)
    prompts = [plan.cover.prompt, *[i.prompt for i in plan.images]]
    assert prompts
    for prompt in prompts:
        assert "上文" not in prompt
        assert "前文" not in prompt
        assert "如图" not in prompt


def test_plan_visual_deterministic(orange: Theme):
    first = plan_visual(_package(), orange).model_dump(exclude={"created_at"})
    second = plan_visual(_package(), orange).model_dump(exclude={"created_at"})
    assert first == second


def test_plan_visual_structure(orange: Theme):
    plan = plan_visual(_package(), orange)
    assert plan.cover.style == "editorial"
    assert plan.cover.ratio == "2.35:1"
    assert plan.cover.asset_path == ""
    assert plan.degraded is False
    assert plan.diagrams == []
    assert len(plan.images) == 1  # 500 字 → 1 张
    for spec in plan.images:
        assert spec.purpose == "concept"
        assert spec.asset_path == ""
        assert spec.position >= 2  # 避开第一个锚点（开头由封面承担）


def test_plan_visual_theme_linked(orange: Theme, minimal: Theme):
    orange_plan = plan_visual(_package(), orange)
    minimal_plan = plan_visual(_package(), minimal)
    assert orange_plan.cover.prompt != minimal_plan.cover.prompt
    assert "#ef7060" in orange_plan.cover.prompt
    assert "#111111" in minimal_plan.cover.prompt


def test_profile_default_fallback():
    theme = Theme(name="ghost")
    profile = ImageryProfile.from_theme(theme)
    assert profile.style == "现代扁平概念插画，干净的几何构图与柔和渐变"
    assert profile.primary == "#333333"
    assert profile.negative == "画面中不出现任何文字、无水印、无 logo"


def test_build_brief_structure(orange: Theme):
    brief = build_brief(_package(), orange)
    assert brief.startswith("# 《测试文章》配图方案")
    assert "## 封面（2.35:1 · editorial）" in brief
    assert "```text" in brief
    assert "#ef7060" in brief
    assert "## 使用说明" in brief


def test_insert_images_skips_empty_asset():
    images = [
        ImageSpec(position=1, purpose="concept", prompt="p1", asset_path=""),
        ImageSpec(
            position=2,
            purpose="concept",
            prompt="p2",
            asset_path="https://example.com/a.png",
        ),
    ]
    out = _insert_images(MARKDOWN, images)
    lines = out.split("\n")
    assert lines.count("![concept](https://example.com/a.png)") == 1
    first_section = lines.index("## 第一节")
    assert "![concept](https://example.com/a.png)" not in lines[:first_section]


def test_insert_images_all_empty_returns_original():
    images = [ImageSpec(position=1, purpose="concept", prompt="p", asset_path="")]
    assert _insert_images(MARKDOWN, images) == MARKDOWN
