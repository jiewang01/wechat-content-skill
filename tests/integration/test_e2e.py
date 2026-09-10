"""离线端到端测试（M6-T3）：一句话意图 → 公众号草稿，全程零网络。

DoD（v0.1-implementation-plan.md M6-T3）：
- 一句话输入 → 校验通过的 WechatDocument；
- mock 草稿创建（httpx.MockTransport 模拟微信 API，请求序列与请求体可断言）。

与 tests/unit/test_pipeline.py 的分工：
- unit 层以 StubPublisher 验证阶段编排与门禁语义；
- 本文件注入 M5 的真实 WeChatPublisher（仅 HTTP 传输层 mock），
  缝合「管线 → Facade → 微信 API 契约」全链路；
- LLM 四段响应全部取自 tests/fixtures 的《缓存穿透》故事线（fixtures 即文档），
  并把产出 artifact 与 fixtures 逐字锚定（标题/正文/字数/去 AI 味得分/事实清单）；
- 校验环节用真实 lint_components / lint_gzh，不做任何 mock。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

from core.artifacts.models import (
    ArticleDraft,
    ContentPackage,
    PublishResult,
    ResearchResult,
    ValidationReport,
    WechatDocument,
)
from core.state.checkpoint import CheckpointStore
from core.state.machine import WorkflowState
from core.workflow.pipeline import PipelineDeps, build_pipeline
from integrations.image.base import ImageAsset
from integrations.llm.base import LLMResult
from integrations.search.base import SearchHit, SearchOutcome
from integrations.wechat import (
    DraftService,
    MediaService,
    TokenManager,
    WeChatClient,
    WeChatPublisher,
)
from validators import lint_gzh

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
INTENT = "写一篇讲清缓存穿透的公众号文章"
AUTHOR = "端到端作者"
IMG_URL = "https://mmbiz.qpic.cn/mmbiz_png/e2e_gate_diagram_001.png"
PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-cover-data"


# ---------------------------------------------------------------------------
# fixtures → LLM 响应（fixtures 即文档：研究/大纲/正文/排版四段全取自同一故事线）
# ---------------------------------------------------------------------------


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _llm_responses() -> list[str]:
    research, brief, draft, package, visual = (
        _fixture("research_result"),
        _fixture("content_brief"),
        _fixture("article_draft"),
        _fixture("content_package"),
        _fixture("visual_plan"),
    )
    research_json = json.dumps(
        {
            "facts": [
                {"claim": fact["claim"], "source_ids": fact["source_ids"]}
                for fact in research["facts"]
            ],
            "angles": research["angles"],
        },
        ensure_ascii=False,
    )
    brief_json = json.dumps(
        {
            "goal": brief["goal"],
            "framework": brief["framework"],
            "tone": brief["tone"],
            "sections": [
                {
                    "heading": section["heading"],
                    "key_points": section["key_points"],
                    "fact_ids": section["fact_ids"],
                }
                for section in brief["sections"]
            ],
        },
        ensure_ascii=False,
    )
    base_markdown = "\n".join(
        line
        for line in package["semantic_markdown"].split("\n")
        if not line.lstrip().startswith("![")
    )
    design_json = json.dumps(
        {
            "semantic_markdown": base_markdown,
            "cover_prompt": visual["cover"]["prompt"],
            "images": [
                {
                    "position": image["position"],
                    "purpose": image["purpose"],
                    "prompt": image["prompt"],
                }
                for image in visual["images"]
            ],
        },
        ensure_ascii=False,
    )
    return [research_json, brief_json, draft["markdown"], design_json]


# ---------------------------------------------------------------------------
# 外部依赖 stub（LLM / 搜索 / 图片）
# ---------------------------------------------------------------------------


class ScriptLLM:
    """按调用顺序回放预设响应，模拟真实 LLM 的四段产出。"""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def complete(self, messages, *, max_tokens=None, temperature=None) -> LLMResult:
        self.calls.append(messages[-1].content)
        response = self._responses.pop(0)
        return LLMResult(text=response)


class StaticSearch:
    """返回固定搜索命中，模拟 SafeSearchProvider 正常出口。"""

    def __init__(self, hits: list[SearchHit]) -> None:
        self._hits = list(hits)
        self.queries: list[str] = []

    def search(self, query: str, *, limit: int = 5) -> SearchOutcome:
        self.queries.append(query)
        return SearchOutcome(hits=list(self._hits), degraded=False)


class RoleImage:
    """封面 prompt 返回 data URI（Facade 可直接上传）；其余 prompt 返回 https 插图 URL。"""

    def __init__(self, cover_prompt: str, cover_uri: str, body_url: str) -> None:
        self._cover_prompt = cover_prompt
        self._cover_uri = cover_uri
        self._body_url = body_url
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, size: str = "1024x1024") -> ImageAsset:
        self.prompts.append(prompt)
        if prompt == self._cover_prompt:
            return ImageAsset(url=self._cover_uri, source="generated", prompt=prompt)
        return ImageAsset(url=self._body_url, source="generated", prompt=prompt)


# ---------------------------------------------------------------------------
# 微信 API mock（MockTransport，参考 tests/integration/test_wechat_publish_flow.py）
# ---------------------------------------------------------------------------


def make_wechat_api(*, api_status: int | None = None):
    requests: list[httpx.Request] = []
    state = {"tokens": 0, "uploads": 0, "drafts": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if api_status is not None:
            return httpx.Response(api_status, text="server error")
        if request.url.path == "/cgi-bin/token":
            state["tokens"] += 1
            return httpx.Response(200, json={"access_token": "TOKEN-1", "expires_in": 7200})
        if request.url.path == "/cgi-bin/material/add_material":
            state["uploads"] += 1
            return httpx.Response(
                200, json={"media_id": "MEDIA-9", "url": "https://mmbiz.qpic.cn/MEDIA-9.png"}
            )
        if request.url.path == "/cgi-bin/draft/add":
            state["drafts"] += 1
            return httpx.Response(200, json={"media_id": "DRAFT-9"})
        return httpx.Response(404, text="not found")

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    client = WeChatClient(transport=httpx.MockTransport(record))
    tokens = TokenManager(client, app_id="wx-e2e", app_secret="secret-e2e", clock=lambda: 1000.0)
    return client, tokens, requests, state


# ---------------------------------------------------------------------------
# 组装与运行
# ---------------------------------------------------------------------------


def run_e2e(tmp_path: Path, *, api_status: int | None = None):
    cover_uri = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()
    llm = ScriptLLM(_llm_responses())
    search = StaticSearch(
        [
            SearchHit(url="https://docs.example.com/cache-penetration.html", title="缓存穿透详解"),
            SearchHit(url="https://blog.example.com/bloom-filter.html", title="布隆过滤器入门"),
        ]
    )
    image = RoleImage(_fixture("visual_plan")["cover"]["prompt"], cover_uri, IMG_URL)
    client, tokens, requests, state = make_wechat_api(api_status=api_status)
    publisher = WeChatPublisher(
        client,
        tokens,
        media=MediaService(client, tokens),
        drafts=DraftService(client, tokens),
        output_dir=tmp_path / "exports",
    )
    deps = PipelineDeps(
        llm=llm,
        search=search,
        image=image,
        publisher=publisher,
        author=AUTHOR,
        audience="初中级后端工程师",
        word_target=600,
    )
    store = CheckpointStore(tmp_path / "runs")
    try:
        run = build_pipeline(store, deps).start(INTENT)
    finally:
        client.close()
    return run, store, requests, state


def _only_run_id(store: CheckpointStore) -> str:
    return next(path.name for path in store.base_dir.iterdir() if path.is_dir())


# ---------------------------------------------------------------------------
# DoD：一句话 → 校验通过的 WechatDocument + mock 草稿创建
# ---------------------------------------------------------------------------


def test_one_sentence_intent_to_wechat_draft(tmp_path: Path):
    run, store, requests, state = run_e2e(tmp_path)

    # 终态与三道门禁（真实 lint_content / lint_components / lint_gzh，无 mock）
    assert run.state == WorkflowState.DRAFT_CREATED
    gates = [(r.gate, r.verdict.decision) for r in run.checkpoint.adversarial_history]
    assert gates == [("content", "PASS"), ("render", "PASS"), ("publish", "PASS")]

    # 产出与 fixtures 逐字锚定（fixtures 即文档）
    research = run.artifact_typed("research_result", ResearchResult)
    fixture_research = _fixture("research_result")
    assert [fact.claim for fact in research.facts] == [
        fact["claim"] for fact in fixture_research["facts"]
    ]
    assert [source.source_id for source in research.sources] == ["src_001", "src_002"]

    draft = run.artifact_typed("article_draft", ArticleDraft)
    fixture_draft = _fixture("article_draft")
    # _ask 对 LLM 文本做 strip，锚定忽略正文尾部换行差异
    assert draft.markdown == fixture_draft["markdown"].rstrip("\n")
    assert draft.title == fixture_draft["title"]
    assert draft.word_count == fixture_draft["word_count"]
    assert draft.humanize.humanize_score == fixture_draft["humanize"]["humanize_score"]

    # 插图由 stub 注入语义稿（fixtures 语义稿中的图片行已剥离）
    package = run.artifact_typed("content_package", ContentPackage)
    assert f"![解法示意]({IMG_URL})" in package.semantic_markdown
    assert package.visual.cover is not None
    assert package.visual.cover.asset_path.startswith("data:image/png;base64,")
    assert package.visual.degraded is False

    # WechatDocument 通过发布门（lint_gzh 干净）且自洽
    doc = run.artifact_typed("wechat_document", WechatDocument)
    assert lint_gzh(doc.html) == []
    assert doc.size_bytes == len(doc.html.encode("utf-8"))
    assert IMG_URL in doc.html
    assert doc.image_assets == [IMG_URL]
    assert doc.plain_text and "<" not in doc.plain_text

    report = run.artifact_typed("validation_report", ValidationReport)
    assert report.status == "passed"

    # mock 微信 API：请求序列 token → 封面上传 → 草稿落位
    assert [request.url.path for request in requests] == [
        "/cgi-bin/token",
        "/cgi-bin/material/add_material",
        "/cgi-bin/draft/add",
    ]
    assert state == {"tokens": 1, "uploads": 1, "drafts": 1}
    article = json.loads(requests[-1].content)["articles"][0]
    assert article["title"] == draft.title
    assert article["author"] == AUTHOR
    assert article["digest"] == draft.digest
    assert article["thumb_media_id"] == "MEDIA-9"
    assert IMG_URL in article["content"]

    # 草稿创建结果 + 本地 HTML 留档
    result = run.artifact_typed("publish_result", PublishResult)
    assert result.status == "draft_created"
    assert result.media_id == "MEDIA-9"
    assert result.draft_id == "DRAFT-9"
    assert Path(result.html_path).read_text(encoding="utf-8") == doc.html

    # checkpoint 磁盘产物：7 份管线 artifact 落盘；攻防三件套记入 adversarial_history，
    # visual_plan 嵌于 content_package.visual，均不单独落盘
    checkpoint = store.load_checkpoint(_only_run_id(store))
    assert checkpoint.state == WorkflowState.DRAFT_CREATED
    expected_artifacts = {
        "research_result",
        "content_brief",
        "article_draft",
        "content_package",
        "validation_report",
        "wechat_document",
        "publish_result",
    }
    assert set(checkpoint.artifacts) == expected_artifacts
    assert len(checkpoint.adversarial_history) == 3
    run_dir = store.base_dir / _only_run_id(store)
    on_disk = {path.stem for path in run_dir.glob("*.json")}
    assert expected_artifacts <= on_disk


# ---------------------------------------------------------------------------
# 蓝图十二章：微信 API 不可用 → 发布降级为本地出口，workflow 终态不受影响
# ---------------------------------------------------------------------------


def test_wechat_outage_degrades_to_local_export(tmp_path: Path):
    run, _, requests, state = run_e2e(tmp_path, api_status=500)

    # 发布降级不是 workflow 失败：状态机照常走到终态
    assert run.state == WorkflowState.DRAFT_CREATED

    doc = run.artifact_typed("wechat_document", WechatDocument)
    result = run.artifact_typed("publish_result", PublishResult)
    assert result.status == "degraded"
    assert result.degraded is True
    assert result.draft_id == ""
    assert result.media_id == ""
    assert result.html_path
    assert Path(result.html_path).read_text(encoding="utf-8") == doc.html

    # 微信侧全部失败：没有草稿请求，只尝试过取 token
    assert state == {"tokens": 0, "uploads": 0, "drafts": 0}
    assert all(request.url.path == "/cgi-bin/token" for request in requests)
