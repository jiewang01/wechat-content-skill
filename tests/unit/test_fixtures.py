"""tests/fixtures/ 全 Artifact 合法示例的活文档契约（M6-T2，DoD：fixtures 即文档）。

11 份 fixture 讲的是同一个故事：一篇《缓存穿透》示例文章的全链路产物——
research → brief → draft → visual → package → document → report/publish，
外加一轮 publish 门禁攻防三件套（attack / defense / verdict）。

本测试把示例当活文档验证三层契约：
1. 结构：每份 fixture 能被对应 Artifact 模型严格解析（extra=forbid）；
2. 跨引用：fact → source、brief/draft → fact、document → visual 全部闭合；
3. 行为：draft 过真实 Content Gate、package 可渲染且过平台 lint、document 过平台 lint。
fixtures 与真实实现脱钩（字段漂移 / 渲染不兼容 / 黑名单词）时，这里会先红。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.artifacts.models import (
    ARTIFACT_MODELS,
    ArticleDraft,
    ContentBrief,
    ContentPackage,
    ResearchResult,
    VisualPlan,
    WechatDocument,
)
from core.utils import estimate_word_count
from core.workflow.repair import repair_rendered
from renderer.ast.parser import parse
from renderer.html.renderer import HtmlRenderer
from renderer.themes import load_theme
from skills.content.humanize.detector import analyze_text
from validators.content.qa import lint_content
from validators.content.visual import lint_visual
from validators.wechat.gzh import lint_gzh

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
RUN_ID = "run_20260910_001"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 结构契约：每个 Artifact 一份合法示例，严格解析
# ---------------------------------------------------------------------------


def test_every_artifact_has_exactly_one_fixture() -> None:
    on_disk = {p.stem for p in FIXTURES.glob("*.json")}
    assert on_disk == set(ARTIFACT_MODELS)


@pytest.mark.parametrize(("name", "model_cls"), sorted(ARTIFACT_MODELS.items()))
def test_fixture_parses_strictly(name: str, model_cls: type) -> None:
    artifact = model_cls.model_validate(_load(name))
    assert artifact.run_id == RUN_ID


# ---------------------------------------------------------------------------
# 跨引用契约：研究 → 大纲 → 初稿 → 视觉 → 成稿的引用链闭合
# ---------------------------------------------------------------------------


def test_research_fact_references_close() -> None:
    research = ResearchResult.model_validate(_load("research_result"))
    source_ids = {s.source_id for s in research.sources}
    assert source_ids
    for fact in research.facts:
        assert fact.source_ids, f"{fact.fact_id} 缺少来源（H2）"
        assert set(fact.source_ids) <= source_ids


def test_brief_and_draft_cite_only_known_facts() -> None:
    research = ResearchResult.model_validate(_load("research_result"))
    fact_ids = {f.fact_id for f in research.facts}
    brief = ContentBrief.model_validate(_load("content_brief"))
    for section in brief.sections:
        assert set(section.fact_ids) <= fact_ids
    draft = ArticleDraft.model_validate(_load("article_draft"))
    assert set(draft.fact_ids) <= fact_ids


def test_document_uses_visual_assets() -> None:
    visual = VisualPlan.model_validate(_load("visual_plan"))
    doc = WechatDocument.model_validate(_load("wechat_document"))
    assert visual.cover is not None
    assert doc.cover_asset == visual.cover.asset_path
    assert doc.image_assets == [img.asset_path for img in visual.images]
    package = ContentPackage.model_validate(_load("content_package"))
    for image in package.visual.images:
        assert f"![{image.purpose}]({image.asset_path})" in package.semantic_markdown


# ---------------------------------------------------------------------------
# 行为契约：示例产物经得起真实子系统检验
# ---------------------------------------------------------------------------


def test_draft_passes_content_gate() -> None:
    research = ResearchResult.model_validate(_load("research_result"))
    brief = ContentBrief.model_validate(_load("content_brief"))
    draft = ArticleDraft.model_validate(_load("article_draft"))
    issues = lint_content(draft, research, brief)
    assert [i for i in issues if i.severity == "error"] == []
    assert draft.word_count == estimate_word_count(draft.markdown)
    assert draft.humanize is not None
    assert draft.humanize.passed
    assert draft.humanize.humanize_score == analyze_text(draft.markdown).humanize_score


def test_package_passes_visual_gate() -> None:
    # Visual Gate：示例成稿必须自带封面 prompt 与插图 prompt 占位（成品必有图或占位符）
    package = ContentPackage.model_validate(_load("content_package"))
    assert lint_visual(package) == []


def test_package_renders_into_gzh_clean_html() -> None:
    package = ContentPackage.model_validate(_load("content_package"))
    ast = parse(package.semantic_markdown, title=package.title, digest=package.digest)
    renderer = HtmlRenderer(load_theme(package.theme))
    outcome = repair_rendered(ast, renderer)
    html = renderer.wrap_document(outcome.html)
    assert lint_gzh(html) == []


def test_wechat_document_is_gzh_clean() -> None:
    doc = WechatDocument.model_validate(_load("wechat_document"))
    assert lint_gzh(doc.html) == []
    assert doc.size_bytes == len(doc.html.encode("utf-8"))
    assert doc.plain_text.strip()
    assert "<" not in doc.plain_text


# ---------------------------------------------------------------------------
# 攻防三件套（H2 证据 / H3 定向修复 / H4 轮次）
# ---------------------------------------------------------------------------


def test_adversarial_trio_forms_one_round() -> None:
    attack = ARTIFACT_MODELS["attack_report"].model_validate(_load("attack_report"))
    defense = ARTIFACT_MODELS["defense_report"].model_validate(_load("defense_report"))
    verdict = ARTIFACT_MODELS["verdict"].model_validate(_load("verdict"))

    assert attack.gate == defense.gate == verdict.gate
    assert attack.round == defense.round == verdict.round

    attack_ids = {a.attack_id for a in attack.attacks}
    assert attack.attacks, "攻击报告不能为空（H2）"
    for a in attack.attacks:
        assert a.evidence, f"{a.attack_id} 缺少逐字证据（H2）"
    for fix in defense.fixes:
        assert fix.attack_id in attack_ids
        assert fix.scope, f"{fix.attack_id} 缺少修复范围（H3）"

    assert verdict.decision == "PASS"
    assert verdict.unresolved == []


def test_publish_story_is_success() -> None:
    report = ARTIFACT_MODELS["validation_report"].model_validate(_load("validation_report"))
    result = ARTIFACT_MODELS["publish_result"].model_validate(_load("publish_result"))
    assert report.status == "passed"
    assert report.errors == []
    draft = ArticleDraft.model_validate(_load("article_draft"))
    assert report.humanize_score == draft.humanize.humanize_score
    assert result.status == "draft_created"
    assert result.degraded is False
    assert result.draft_id and result.html_path
