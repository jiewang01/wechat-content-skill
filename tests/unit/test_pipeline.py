"""core/workflow/pipeline.py 单测（M6-T1）：19 状态全链路 + 门禁 + 降级 + 留痕。

覆盖蓝图十一章状态序列与 references/adversarial-constraints.md 的关键契约：
- happy path：INIT → … → DRAFT_CREATED 全链路与全部 Artifact 产出
  （LLM 六段：research → brief → draft → annotate → style → imagery）；
- H2/H6：门禁拒绝时 Attack 携带证据并记入 adversarial_history；
- H4：发布门修复回环 ≤3 轮，轮次耗尽进入 REJECTED 终态；
- 蓝图十二章降级：research / brief / style / imagery 降级、
  annotate 回退原文（不算降级）、draft 不降级；
- H6：checkpoint 恢复（WorkflowRun.resume）保留对抗留痕。

所有外部依赖（LLM / 搜索 / 图片 / 微信发布）以 stub 注入；
mock 文本均避开 humanize rules.yaml 的黑名单短语与配对短语。
"""

from __future__ import annotations

import json

import pytest

from core.artifacts.models import (
    ArticleDraft,
    ContentBrief,
    ContentPackage,
    PublishResult,
    ResearchResult,
    StyleDecision,
    ValidationIssue,
    ValidationReport,
    WechatDocument,
)
from core.state.checkpoint import CheckpointStore
from core.state.machine import WorkflowState
from core.workflow import pipeline
from core.workflow.imagery import strip_figure_blocks
from core.workflow.orchestrator import WorkflowRun
from core.workflow.pipeline import (
    ContentGateError,
    DraftGenerationError,
    PipelineDeps,
    build_pipeline,
)
from integrations.errors import ProviderError
from integrations.image.base import ImageAsset
from integrations.llm.base import LLMResult
from integrations.search.base import SearchHit, SearchOutcome

_IMG_URL = "https://img.example.com/asset.png"
_INTENT = "写一篇讲清缓存穿透的公众号文章"

_DRAFT_MD = (
    "# 缓存穿透的三种解法\n"
    "\n"
    "## 问题是什么\n"
    "\n"
    "缓存穿透指查询一个不存在的键。请求绕过缓存，直接落到数据库。流量一大，数据库先倒下。\n"
    "\n"
    "## 解法一：缓存空值\n"
    "\n"
    "把「键不存在」这个事实写进缓存。空值过期时间设短一点。写入前先校验参数。\n"
    "\n"
    "## 解法二：布隆过滤器\n"
    "\n"
    "在缓存前加一层布隆过滤器。过滤器说不存在的键，直接返回。误判率随数据量上升，要预留容量。\n"
    "\n"
    "## 小结\n"
    "\n"
    "两种解法可以叠加使用。空值兜底冷门键，过滤器挡住大多数恶意查询。\n"
)

_SEMANTIC_MD = (
    "# 缓存穿透的三种解法\n"
    "\n"
    ":::note\n"
    "布隆过滤器能省下九成内存，代价是少量误判。\n"
    ":::\n"
    "\n"
    "## 问题是什么\n"
    "\n"
    "缓存穿透指查询一个不存在的键。请求绕过缓存，直接落到数据库。流量一大，数据库先倒下。\n"
    "\n"
    "## 解法一：缓存空值\n"
    "\n"
    "把「键不存在」这个事实写进缓存。空值过期时间设短一点。写入前先校验参数。\n"
    "\n"
    "## 解法二：布隆过滤器\n"
    "\n"
    "在缓存前加一层布隆过滤器。过滤器说不存在的键，直接返回。误判率随数据量上升，要预留容量。\n"
    "\n"
    "## 小结\n"
    "\n"
    "两种解法可以叠加使用。空值兜底冷门键，过滤器挡住大多数恶意查询。\n"
)

_BAD_MD = (
    "# 缓存穿透入门\n"
    "\n"
    "总而言之，缓存穿透是个需要正视的问题。它会让数据库压力骤增。\n"
    "\n"
    "## 解法\n"
    "\n"
    "布隆过滤器能挡住大部分恶意查询。\n"
)

_RESEARCH_JSON = json.dumps(
    {
        "facts": [
            {
                "fact_id": "fact_001",
                "claim": "布隆过滤器用固定内存判断键大概率不存在",
                "source_ids": ["src_001"],
            },
            {
                "fact_id": "fact_002",
                "claim": "缓存空值需要设置较短的过期时间",
                "source_ids": ["src_001", "src_002"],
            },
        ],
        "angles": ["从线上事故切入", "对比两档解法的成本"],
    },
    ensure_ascii=False,
)

_BRIEF_JSON = json.dumps(
    {
        "goal": "讲清缓存穿透的成因与两档解法",
        "framework": "tutorial",
        "tone": "平实",
        "sections": [
            {"heading": "问题是什么", "key_points": ["给出定义与后果"], "fact_ids": ["fact_001"]},
            {
                "heading": "两档解法",
                "key_points": ["缓存空值", "布隆过滤器"],
                "fact_ids": ["fact_001", "fact_002"],
            },
        ],
    },
    ensure_ascii=False,
)

_ANNOTATE_JSON = json.dumps({"semantic_markdown": _SEMANTIC_MD}, ensure_ascii=False)

_STYLE_JSON = json.dumps(
    {
        "theme": "default",
        "rationale": "教程框架配中性默认版式，note 组件可用",
        "cover_style": "editorial",
        "rejected": [{"theme": "magazine", "reason": "分栏感与线性教程的阅读路径不符"}],
    },
    ensure_ascii=False,
)

_COVER_PROMPT = (
    "深蓝色数据流动抽象插画，极简矢量风格，横向封面构图（2.35:1），冷色调，"
    "画面中不出现任何文字、无水印、无 logo。"
)

_IMAGERY_JSON = json.dumps(
    {
        "cover_prompt": _COVER_PROMPT,
        "images": [
            {
                "position": 2,
                "purpose": "概念图",
                "prompt": "布隆过滤器与缓存空值两道闸门拦截请求的示意，扁平概念插画，"
                "横构图（16:9），蓝灰色调，画面中不出现任何文字、无水印、无 logo。",
            }
        ],
    },
    ensure_ascii=False,
)

# 全链路 LLM 脚本：research → brief → draft → annotate → style → imagery
_SCRIPT = [_RESEARCH_JSON, _BRIEF_JSON, _DRAFT_MD, _ANNOTATE_JSON, _STYLE_JSON, _IMAGERY_JSON]


class StubLLM:
    """按调用顺序返回预设响应；None 表示该次调用抛 ProviderError（模拟供应商故障）。"""

    def __init__(self, responses: list[str | None]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def complete(self, messages, *, max_tokens=None, temperature=None) -> LLMResult:
        self.calls.append(messages[-1].content)
        if not self._responses:
            raise AssertionError(f"LLM 调用超出预设次数（第 {len(self.calls)} 次）")
        response = self._responses.pop(0)
        if response is None:
            raise ProviderError("stub：LLM 供应商不可用")
        return LLMResult(text=response)


class StubSearch:
    """返回固定 SearchOutcome，模拟 SafeSearchProvider 的降级契约。"""

    def __init__(self, hits: list[SearchHit] | None = None, *, degraded: bool = False) -> None:
        self._outcome = SearchOutcome(hits=hits or [], degraded=degraded)
        self.queries: list[str] = []

    def search(self, query: str, *, limit: int = 5) -> SearchOutcome:
        self.queries.append(query)
        return self._outcome


class StubImage:
    """总是返回固定 URL 的图片资产。"""

    def __init__(self, url: str = _IMG_URL) -> None:
        self._url = url
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, size: str = "1024x1024") -> ImageAsset:
        self.prompts.append(prompt)
        return ImageAsset(url=self._url, source="generated", prompt=prompt)


class StubPublisher:
    """记录 create_draft / release 入参并返回固定结果。"""

    def __init__(
        self, status: str = "draft_created", released: PublishResult | None = None
    ) -> None:
        self._status = status
        self._released = released
        self.docs: list[WechatDocument] = []
        self.authors: list[str] = []
        self.cover_paths: list[str | None] = []
        self.release_calls: list[str] = []

    def create_draft(self, doc, *, author: str = "", cover_path=None) -> PublishResult:
        self.docs.append(doc)
        self.authors.append(author)
        self.cover_paths.append(cover_path)
        return PublishResult(status=self._status, draft_id="draft-001", media_id="media-001")

    def release(self, draft_id, *, media_id: str = "", html_path: str = "") -> PublishResult:
        self.release_calls.append(draft_id)
        if self._released is not None:
            return self._released
        return PublishResult(
            status="published",
            draft_id=draft_id,
            media_id=media_id,
            publish_id="pub-001",
            article_url="https://mp.weixin.qq.com/s/stub",
            html_path=html_path,
            message="发布成功",
        )


def _hits() -> list[SearchHit]:
    return [
        SearchHit(url="https://blog.example.com/cache-penetration.html", title="缓存穿透详解"),
        SearchHit(url="https://docs.example.com/bloom-filter.html", title="布隆过滤器入门"),
    ]


def _deps(
    llm: StubLLM,
    search: StubSearch | None = None,
    image: StubImage | None = None,
    publisher: StubPublisher | None = None,
    auto_release: bool = False,
) -> PipelineDeps:
    return PipelineDeps(
        llm=llm,
        search=search if search is not None else StubSearch(_hits()),
        image=image if image is not None else StubImage(),
        publisher=publisher if publisher is not None else StubPublisher(),
        author="测试作者",
        auto_release=auto_release,
    )


def _start(tmp_path, deps: PipelineDeps, intent: str = _INTENT):
    store = CheckpointStore(tmp_path / "runs")
    return build_pipeline(store, deps).start(intent), store


def _only_run_id(store: CheckpointStore) -> str:
    return next(path.name for path in store.base_dir.iterdir() if path.is_dir())


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_happy_path_full_pipeline(tmp_path):
    llm = StubLLM(_SCRIPT)
    search, image, publisher = StubSearch(_hits()), StubImage(), StubPublisher()
    run, _ = _start(tmp_path, _deps(llm, search, image, publisher))

    assert run.state == WorkflowState.DRAFT_CREATED
    assert len(llm.calls) == 6  # research → brief → draft → annotate → style → imagery 各一次
    assert search.queries == [_INTENT]

    research = run.artifact_typed("research_result", ResearchResult)
    assert [fact.fact_id for fact in research.facts] == ["fact_001", "fact_002"]
    assert [source.source_id for source in research.sources] == ["src_001", "src_002"]

    brief = run.artifact_typed("content_brief", ContentBrief)
    assert brief.sections[0].heading == "问题是什么"

    draft = run.artifact_typed("article_draft", ArticleDraft)
    assert draft.title == "缓存穿透的三种解法"
    assert draft.fact_ids == ["fact_001", "fact_002"]

    style = run.artifact_typed("style_decision", StyleDecision)
    assert style.theme == "default"
    assert style.cover_style == "editorial"
    assert style.framework == "tutorial"
    assert style.degraded is False
    assert style.rejected[0].theme == "magazine"  # 否决记录可审计

    package = run.artifact_typed("content_package", ContentPackage)
    assert package.theme == "default"  # 风格决策回写 package.theme
    assert ":::note" in package.semantic_markdown
    assert ":::figure" in package.semantic_markdown  # prompt-first：正文插图是占位块
    body = package.visual.images[0]
    assert body.asset_path == ""
    assert body.prompt in package.semantic_markdown
    cover = package.visual.cover
    assert cover.prompt == _COVER_PROMPT
    assert cover.style == "editorial"
    assert cover.asset_path == _IMG_URL  # 上传阶段按 prompt 兜底生图并回写
    assert package.visual.degraded is False

    doc = run.artifact_typed("wechat_document", WechatDocument)
    assert doc.html and doc.plain_text
    assert body.prompt in doc.html  # figure 占位块渲染为 prompt 文本卡片
    assert doc.cover_asset == ""  # 文档在渲染时定型，早于封面生成
    assert doc.image_assets == [""]

    report = run.artifact_typed("validation_report", ValidationReport)
    assert report.status == "passed"

    result = run.artifact_typed("publish_result", PublishResult)
    assert result.status == "draft_created"

    assert image.prompts == [_COVER_PROMPT]  # 管线内生图仅封面一张
    assert publisher.docs[0].title == "缓存穿透的三种解法"
    assert publisher.authors == ["测试作者"]
    assert publisher.cover_paths == [_IMG_URL]

    gates = [(r.gate, r.verdict.decision) for r in run.checkpoint.adversarial_history]
    assert gates == [
        ("content", "PASS"),  # 内容门（DRAFTED）
        ("content", "PASS"),  # 组件门（ANNOTATED，自渲染前移）
        ("render", "PASS"),
        ("publish", "PASS"),
    ]
    assert run.publish_gate_passed


# ---------------------------------------------------------------------------
# auto_release（N2-T4：DRAFT_CREATED → 条件推进 PUBLISHED）
# ---------------------------------------------------------------------------


def test_auto_release_advances_to_published(tmp_path):
    llm = StubLLM(_SCRIPT)
    publisher = StubPublisher()
    run, _ = _start(tmp_path, _deps(llm, publisher=publisher, auto_release=True))

    assert run.state == WorkflowState.PUBLISHED
    assert publisher.release_calls == ["draft-001"]
    result = run.artifact_typed("publish_result", PublishResult)
    assert result.status == "published"
    assert result.publish_id == "pub-001"
    assert result.article_url == "https://mp.weixin.qq.com/s/stub"
    assert result.draft_id == "draft-001"
    assert result.media_id == "media-001"


def test_auto_release_degraded_stays_draft_created(tmp_path):
    llm = StubLLM(_SCRIPT)
    released = PublishResult(
        status="degraded",
        draft_id="draft-001",
        degraded=True,
        message="微信 API 请求失败",
    )
    publisher = StubPublisher(released=released)
    run, _ = _start(tmp_path, _deps(llm, publisher=publisher, auto_release=True))

    assert run.state == WorkflowState.DRAFT_CREATED
    assert publisher.release_calls == ["draft-001"]
    result = run.artifact_typed("publish_result", PublishResult)
    assert result.status == "degraded"
    assert result.degraded is True


def test_auto_release_skipped_when_draft_not_created(tmp_path):
    llm = StubLLM(_SCRIPT)
    publisher = StubPublisher(status="degraded")
    run, _ = _start(tmp_path, _deps(llm, publisher=publisher, auto_release=True))

    assert run.state == WorkflowState.DRAFT_CREATED
    assert publisher.release_calls == []  # 没有草稿句柄，绝不调用 release
    result = run.artifact_typed("publish_result", PublishResult)
    assert result.status == "degraded"


# ---------------------------------------------------------------------------
# content gate（H2 证据 / DRAFTED 中断）
# ---------------------------------------------------------------------------


def test_content_gate_blacklist_stops_at_drafted(tmp_path):
    llm = StubLLM([_RESEARCH_JSON, _BRIEF_JSON, _BAD_MD])
    store = CheckpointStore(tmp_path / "runs")
    with pytest.raises(ContentGateError) as exc_info:
        build_pipeline(store, _deps(llm)).start("缓存穿透科普")

    # DRAFTED 无通往 REJECTED 的转移：异常中断，checkpoint 保留现场
    checkpoint = store.load_checkpoint(_only_run_id(store))
    assert checkpoint.state == WorkflowState.DRAFTED
    assert "article_draft" in checkpoint.artifacts

    rounds = [r for r in checkpoint.adversarial_history if r.gate == "content"]
    assert len(rounds) == 1
    assert rounds[0].verdict.decision == "REJECT"
    assert rounds[0].attack_report.attacks  # H2：攻击必须携带证据
    assert rounds[0].attack_report.attacks[0].category == "ai_flavor_blacklist_phrase"
    assert any("blacklist" in issue.type for issue in exc_info.value.issues)


# ---------------------------------------------------------------------------
# publish gate 修复回环（H4 ≤3 轮）
# ---------------------------------------------------------------------------


def test_publish_gate_repair_loop_recovers(tmp_path, monkeypatch):
    llm = StubLLM(_SCRIPT)
    calls = {"count": 0}
    fake_issues = [
        ValidationIssue(type="img_src_insecure", node="img", property="src", message="占位平台问题")
    ]

    def fake_lint_gzh(html, *, max_bytes=None):
        calls["count"] += 1
        return fake_issues if calls["count"] == 1 else []

    monkeypatch.setattr(pipeline, "lint_gzh", fake_lint_gzh)
    run, _ = _start(tmp_path, _deps(llm))

    assert run.state == WorkflowState.DRAFT_CREATED
    publish_rounds = [
        (r.round, r.verdict.decision)
        for r in run.checkpoint.adversarial_history
        if r.gate == "publish"
    ]
    assert publish_rounds == [(1, "REPAIR"), (2, "REPAIR"), (3, "PASS")]
    assert calls["count"] == 4  # Judge 首审 + Defender 修前检查 + 修后自检 + Judge 终审
    assert run.publish_gate_passed


def test_publish_rounds_exhausted_rejects(tmp_path, monkeypatch):
    # 第 1、4 次 lint 出错：两轮攻防修复成功后 Judge 第 3 轮再攻击 → 轮次耗尽
    llm = StubLLM(_SCRIPT)
    publisher = StubPublisher()
    calls = {"count": 0}
    fake_issues = [ValidationIssue(type="img_src_insecure", node="img", message="占位平台问题")]

    def fake_lint_gzh(html, *, max_bytes=None):
        calls["count"] += 1
        return fake_issues if calls["count"] in (1, 4) else []

    monkeypatch.setattr(pipeline, "lint_gzh", fake_lint_gzh)
    run, _ = _start(tmp_path, _deps(llm, publisher=publisher))

    assert run.state == WorkflowState.REJECTED  # H4：修复轮次耗尽
    publish_rounds = [
        (r.round, r.verdict.decision)
        for r in run.checkpoint.adversarial_history
        if r.gate == "publish"
    ]
    assert publish_rounds == [(1, "REPAIR"), (2, "REPAIR"), (3, "REPAIR"), (3, "REJECT")]
    assert not run.publish_gate_passed
    assert publisher.docs == []  # 未过发布门，不触达微信侧


def test_publish_repair_fails_rejects(tmp_path, monkeypatch):
    # 第 1、3 次 lint 出错：Defender 修复后自检仍不干净 → 直接 REJECT，不浪费剩余轮次
    llm = StubLLM(_SCRIPT)
    publisher = StubPublisher()
    calls = {"count": 0}
    fake_issues = [ValidationIssue(type="img_src_insecure", node="img", message="占位平台问题")]

    def fake_lint_gzh(html, *, max_bytes=None):
        calls["count"] += 1
        return fake_issues if calls["count"] in (1, 3) else []

    monkeypatch.setattr(pipeline, "lint_gzh", fake_lint_gzh)
    run, _ = _start(tmp_path, _deps(llm, publisher=publisher))

    assert run.state == WorkflowState.REJECTED
    publish_rounds = [
        (r.round, r.verdict.decision)
        for r in run.checkpoint.adversarial_history
        if r.gate == "publish"
    ]
    assert publish_rounds == [(1, "REPAIR"), (2, "REJECT")]
    assert publisher.docs == []


# ---------------------------------------------------------------------------
# 多级降级（蓝图十二章）
# ---------------------------------------------------------------------------


def test_graceful_degradation_research_brief_annotate_style_imagery(tmp_path):
    # research / brief / annotate / style / imagery 五次 LLM 故障，仅 draft 成功 → 降级后仍走完全程
    llm = StubLLM([None, None, _DRAFT_MD, None, None, None])
    image = StubImage(url="http://img.example.com/insecure.png")  # 非 https 封面 URL
    publisher = StubPublisher()
    run, _ = _start(tmp_path, _deps(llm, image=image, publisher=publisher))

    assert run.state == WorkflowState.DRAFT_CREATED
    assert len(llm.calls) == 6  # 降级不省调用：六段 LLM 全部尝试

    research = run.artifact_typed("research_result", ResearchResult)
    assert research.sources and research.facts == [] and research.angles == []
    assert research.degraded is False  # 搜索本身成功，仅 LLM 提炼降级

    brief = run.artifact_typed("content_brief", ContentBrief)
    assert [s.heading for s in brief.sections] == ["背景与问题", "核心原理", "实践要点"]

    draft = run.artifact_typed("article_draft", ArticleDraft)
    assert draft.fact_ids == []  # 无 facts → 无引用

    # annotate 降级 → 回退原文（不算降级）；style 降级 → 框架决策表（tutorial → default）
    style = run.artifact_typed("style_decision", StyleDecision)
    assert style.theme == "default"
    assert style.degraded is True
    assert style.rejected == []
    package = run.artifact_typed("content_package", ContentPackage)
    assert package.theme == "default"

    # imagery 降级 → 确定性模板：1 张插图（quota=1，锚点候选 2/3/4 取中间 → position 3）
    assert len(package.visual.images) == 1
    fallback_spec = package.visual.images[0]
    assert fallback_spec.purpose == "concept"
    assert fallback_spec.asset_path == ""
    assert fallback_spec.prompt.endswith("画面中不出现任何文字、无水印、无 logo。")
    # 原文直出 + figure 占位块（主题启用 figure，成品必有图或 prompt 占位符）
    assert strip_figure_blocks(package.semantic_markdown) == draft.markdown
    assert ":::figure" in package.semantic_markdown
    assert fallback_spec.prompt in package.semantic_markdown
    assert package.visual.degraded is True
    assert "![概念图]" not in package.semantic_markdown

    # 封面上传时兜底生图；非 https URL 原样交给 publisher 裁决
    assert len(image.prompts) == 1
    assert image.prompts[0].endswith("画面中不出现任何文字、无水印、无 logo。")
    assert package.visual.cover.asset_path == "http://img.example.com/insecure.png"
    assert publisher.cover_paths == ["http://img.example.com/insecure.png"]


def test_draft_llm_failure_raises_without_degradation(tmp_path):
    llm = StubLLM([_RESEARCH_JSON, _BRIEF_JSON, None])
    store = CheckpointStore(tmp_path / "runs")
    with pytest.raises(DraftGenerationError):
        build_pipeline(store, _deps(llm)).start("缓存穿透科普")

    checkpoint = store.load_checkpoint(_only_run_id(store))
    assert checkpoint.state == WorkflowState.DRAFTING  # 正文不可伪造，不做降级
    assert {"research_result", "content_brief"} <= set(checkpoint.artifacts)
    assert "article_draft" not in checkpoint.artifacts


def test_search_degraded_skips_research_llm(tmp_path):
    llm = StubLLM([_BRIEF_JSON, _DRAFT_MD, _ANNOTATE_JSON, _STYLE_JSON, _IMAGERY_JSON])
    search = StubSearch([], degraded=True)
    run, _ = _start(tmp_path, _deps(llm, search=search))

    assert run.state == WorkflowState.DRAFT_CREATED
    research = run.artifact_typed("research_result", ResearchResult)
    assert research.degraded is True
    assert research.sources == [] and research.facts == []
    assert len(llm.calls) == 5  # 无搜索来源时跳过 research 阶段的 LLM 调用
    brief = run.artifact_typed("content_brief", ContentBrief)
    assert all(section.fact_ids == [] for section in brief.sections)


# ---------------------------------------------------------------------------
# resume（H6 留痕随 checkpoint 恢复）
# ---------------------------------------------------------------------------


def test_resume_restores_checkpoint_and_history(tmp_path):
    llm = StubLLM([_RESEARCH_JSON, _BRIEF_JSON, _BAD_MD])
    store = CheckpointStore(tmp_path / "runs")
    with pytest.raises(ContentGateError):
        build_pipeline(store, _deps(llm)).start("缓存穿透科普")

    run = WorkflowRun.resume(_only_run_id(store), store)
    assert run.state == WorkflowState.DRAFTED
    assert run.checkpoint.adversarial_history  # H6：对抗留痕随 checkpoint 恢复
    assert run.artifact_typed("article_draft", ArticleDraft).title == "缓存穿透入门"
