"""Content QA v1 单测：结构 / 字数 / AI 味复检 / 引用一致性（蓝图 9.1，计划 M4-T3）。

净化用例的 markdown 均避开 rules.yaml 全部触发条件
（黑话 / 关联句式 / 超长句 / 超长段 / 5-gram 重复），保证零误报基线可信。
"""

from __future__ import annotations

from core.artifacts.models import (
    ArticleDraft,
    BriefSection,
    ContentBrief,
    Fact,
    ResearchResult,
    Source,
)
from core.utils import estimate_word_count
from validators.content import lint_content

CLEAN_MARKDOWN = """# 手冲咖啡入门

## 冲煮步骤

把水烧到 92 度。
磨豆 20 克。
闷蒸 30 秒。

## 小结
"""

LONG_MARKDOWN = """# 手冲咖啡入门指南

## 器具准备

滤纸、电子秤、手冲壶，三样即可开工。
预算有限时，先买滤杯。
磨豆机可以稍后再添置。

## 冲煮参数

水温 92 度。
粉水比 1 比 15。
闷蒸 30 秒，之后分两段注水。

## 风味调整

水流快，萃取偏浅，口感偏酸。
水温高，萃取偏深，口感偏苦。
偏酸就调细研磨，偏苦就降低水温。

## 记录与复盘

每次记录参数与口感。
连续三次验证，再改下一个变量。
"""

LONG_SENTENCE = (
    "我们把水温、粉水比、研磨粗细、注水节奏、滤杯形状、豆子烘焙度、"
    "水质软硬这七个变量逐个讲清楚，剩下的时间留给读者自己动手练习。"
)


def make_draft(**overrides) -> ArticleDraft:
    markdown = overrides.pop("markdown", CLEAN_MARKDOWN)
    defaults = dict(
        title="手冲咖啡入门",
        markdown=markdown,
        word_count=estimate_word_count(markdown),
    )
    defaults.update(overrides)
    return ArticleDraft(**defaults)


def make_research() -> ResearchResult:
    return ResearchResult(
        topic="手冲咖啡",
        sources=[Source(source_id="src_001", title="咖啡冲煮手册")],
        facts=[Fact(fact_id="fact_001", claim="水温建议 92 度", source_ids=["src_001"])],
    )


def make_brief() -> ContentBrief:
    return ContentBrief(
        topic="手冲咖啡",
        framework="tutorial",
        word_target=200,
        sections=[BriefSection(heading="冲煮步骤", fact_ids=["fact_001"])],
    )


def test_clean_draft_passes():
    assert lint_content(make_draft()) == []


def test_full_context_clean_passes():
    draft = make_draft(markdown=LONG_MARKDOWN, fact_ids=["fact_001"])
    assert lint_content(draft, research=make_research(), brief=make_brief()) == []


def test_empty_title():
    issues = lint_content(make_draft(title=""))
    assert [i.type for i in issues] == ["structure_incomplete"]
    assert issues[0].property == "title"


def test_whitespace_title():
    issues = lint_content(make_draft(title="   "))
    assert [i.type for i in issues] == ["structure_incomplete"]
    assert issues[0].property == "title"


def test_empty_markdown_reports_single_issue():
    issues = lint_content(make_draft(markdown=""))
    assert [i.type for i in issues] == ["structure_incomplete"]
    assert issues[0].property == "markdown"


def test_markdown_without_heading():
    draft = make_draft(markdown="正文没有标题层级。\n第二段也没有。")
    issues = lint_content(draft)
    assert [i.type for i in issues] == ["structure_incomplete"]
    assert issues[0].property == "markdown"
    assert "标题" in issues[0].message


def test_word_count_mismatch_beyond_tolerance():
    actual = estimate_word_count(CLEAN_MARKDOWN)
    issues = lint_content(make_draft(word_count=actual + 100))
    assert [i.type for i in issues] == ["word_count_mismatch"]
    assert issues[0].severity == "error"
    assert issues[0].property == "word_count"


def test_word_count_within_tolerance_passes():
    actual = estimate_word_count(CLEAN_MARKDOWN)
    assert lint_content(make_draft(word_count=actual + 15)) == []


def test_word_count_below_half_target_warns():
    issues = lint_content(make_draft(), brief=make_brief())
    assert [i.type for i in issues] == ["word_count_below_target"]
    assert issues[0].severity == "warning"


def test_word_count_meeting_half_target_no_warning():
    draft = make_draft(markdown=LONG_MARKDOWN)
    assert lint_content(draft, brief=make_brief()) == []


def test_ai_flavor_blacklist_phrase():
    draft = make_draft(markdown="# 标题\n\n首先，我们要热身。\n")
    issues = lint_content(draft)
    assert [i.type for i in issues] == ["ai_flavor_blacklist_phrase"]
    assert issues[0].severity == "error"
    assert issues[0].node == "draft"
    assert issues[0].property == "首先，"


def test_ai_flavor_paired_phrase():
    draft = make_draft(markdown="# 标题\n\n随着移动互联网的发展，工具变多了。\n")
    issues = lint_content(draft)
    assert [i.type for i in issues] == ["ai_flavor_paired_phrase"]
    assert issues[0].severity == "error"
    assert "随着" in issues[0].property


def test_ai_flavor_long_sentence_warning():
    draft = make_draft(markdown=f"# 标题\n\n{LONG_SENTENCE}\n")
    issues = lint_content(draft)
    assert [i.type for i in issues] == ["ai_flavor_long_sentence"]
    assert issues[0].severity == "warning"


def test_dod_nonexistent_source_id_intercepted():
    research = make_research()
    research.facts[0].source_ids.append("src_999")
    issues = lint_content(make_draft(), research=research)
    assert [i.type for i in issues] == ["unknown_source_ref"]
    assert issues[0].node == "fact_001"
    assert issues[0].property == "src_999"
    assert issues[0].severity == "error"


def test_unknown_fact_ref_in_draft():
    draft = make_draft(fact_ids=["fact_001", "fact_999"])
    issues = lint_content(draft, research=make_research())
    assert [i.type for i in issues] == ["unknown_fact_ref"]
    assert issues[0].node == "draft"
    assert issues[0].property == "fact_999"


def test_unknown_fact_ref_in_brief_section():
    brief = make_brief()
    brief.sections[0].fact_ids.append("fact_888")
    draft = make_draft(markdown=LONG_MARKDOWN)
    issues = lint_content(draft, research=make_research(), brief=brief)
    assert [i.type for i in issues] == ["unknown_fact_ref"]
    assert issues[0].node == "section_1"
    assert issues[0].property == "fact_888"


def test_duplicate_unknown_fact_ref_reported_once():
    draft = make_draft(fact_ids=["fact_999", "fact_999"])
    issues = lint_content(draft, research=make_research())
    assert len(issues) == 1


def test_missing_research_skips_citation_checks():
    draft = make_draft(fact_ids=["fact_999"])
    assert lint_content(draft) == []


def test_multiple_issues_collected_in_one_pass():
    research = make_research()
    research.facts[0].source_ids.append("src_999")
    draft = make_draft(title="", word_count=999_999)
    issues = lint_content(draft, research=research)
    assert {i.type for i in issues} == {
        "structure_incomplete",
        "word_count_mismatch",
        "unknown_source_ref",
    }
