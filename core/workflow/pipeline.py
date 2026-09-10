"""端到端内容管线（M6-T1）：一句话意图 → 公众号草稿。

按 references/adversarial-constraints.md 的 H1–H8 硬约束，把研究、写作、
排版、渲染、校验、修复、发布能力编排为 13 个状态的流水线，由 Orchestrator 驱动：

    INIT → RESEARCHING → RESEARCHED → DRAFTING → DRAFTED
         → DESIGNING → RENDERING → VALIDATING ⇄ REPAIRING（发布门修复回环，≤3 轮）
         → VALIDATED → READY_TO_PUBLISH → UPLOADING → DRAFT_CREATED

对抗角色分工（H1）：
- Attacker：lint_content / lint_components / lint_gzh 产出带证据的 Attack
- Defender：repair_document 定向修复（仅 unsupported_css 策略，H3）
- Judge：各阶段按错误严重度裁决 PASS / REPAIR / REJECT，并记入 adversarial_history（H6）

三级降级（蓝图 ch12）：
- research：LLM 提炼失败 → 只保留搜索来源，facts 为空
- brief / design：LLM 失败 → 确定性模板 / 纯正文（VisualPlan.degraded=True）
- draft：LLM 失败 → DraftGenerationError（正文不可伪造，不做降级）
- image：封面与插图经 fallback provider 兜底；非 https 资产不进入正文

门禁与状态机约束（core/state/machine.py）：
- DRAFTED / RENDERING 无通往 REJECTED 的转移，内容/组件门禁失败以异常中断，
  checkpoint 保留现场可 resume；
- REJECTED 仅能从 REPAIRING 进入（发布门修复轮次耗尽或无手段，H4）；
- VALIDATED → READY_TO_PUBLISH 强制 publish_verdict_pass=True（H5，PublishGateError 兜底）。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.artifacts.models import (
    ArticleDraft,
    Attack,
    AttackReport,
    BriefSection,
    ContentBrief,
    ContentPackage,
    CoverSpec,
    Decision,
    DefenseFix,
    DefenseReport,
    Fact,
    Gate,
    ImageSpec,
    ResearchResult,
    Source,
    Verdict,
    VisualPlan,
    WechatDocument,
)
from core.config.config import load_account, resolve_credentials
from core.state.checkpoint import CheckpointStore
from core.state.machine import WorkflowState
from core.utils import estimate_word_count
from core.workflow.orchestrator import Orchestrator, Stage, WorkflowRun
from core.workflow.repair import (
    HtmlSegment,
    RepairOutcome,
    repair_document,
    repair_rendered,
)
from integrations.errors import ProviderError
from integrations.image import load_fallback_image_provider
from integrations.image.base import ImageProvider
from integrations.llm import load_llm_provider
from integrations.llm.base import LLMMessage, LLMProvider
from integrations.search import SafeSearchProvider, load_safe_search_provider
from integrations.wechat import TokenManager, WeChatClient
from integrations.wechat.publish import WeChatPublisher
from renderer.ast.nodes import ContentAST
from renderer.ast.parser import ParseError, parse
from renderer.html.renderer import HtmlRenderer
from renderer.themes import Theme, ThemeError, load_theme
from skills.content.humanize.detector import analyze_text
from validators import lint_components, lint_content, lint_gzh

_MAX_PUBLISH_ROUNDS = 3
_DIGEST_MAX_CHARS = 54
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")

_RESEARCH_SYSTEM = "你是一名严谨的中文技术内容研究员。只输出一个 JSON 对象，不要输出任何解释文字。"
_BRIEF_SYSTEM = "你是一名中文技术内容策划编辑。只输出一个 JSON 对象，不要输出任何解释文字。"
_DRAFT_SYSTEM = (
    "你是一名资深中文技术作者。直接输出 Markdown 正文，不要任何解释文字。"
    "第一行必须是一级标题。写作要求：多用短句；单段不超过 200 字；"
    "不使用「首先」「其次」「最后」「总而言之」「众所周知」等套话；"
    "不堆砌形容词；结尾不给行动号召口号。"
)
_DESIGN_SYSTEM = "你是一名微信公众号排版设计师。只输出一个 JSON 对象，不要输出任何解释文字。"


class PipelineError(RuntimeError):
    """管线阶段异常基类；抛出后 run 停留在当前状态，checkpoint 保留现场可 resume。"""


class DraftGenerationError(PipelineError):
    """DRAFTING 阶段 LLM 不可用；正文不可伪造（蓝图 ch12），不做降级。"""


class ContentGateError(PipelineError):
    """内容/组件门禁失败；DRAFTED 与 RENDERING 无通往 REJECTED 的转移，只能中断。"""

    def __init__(self, message: str, issues: list) -> None:
        super().__init__(message)
        self.issues = list(issues)


class RenderError(PipelineError):
    """语义 Markdown 解析或渲染失败。"""


class _LLMJSONError(PipelineError):
    """LLM 返回的 JSON 不可用；调用方按阶段策略降级。"""


@dataclass
class PipelineDeps:
    """管线外部依赖集合（生产由 load_deps 装配，测试注入 stub）。"""

    llm: LLMProvider
    search: SafeSearchProvider
    image: ImageProvider
    publisher: WeChatPublisher
    author: str = ""
    audience: str = "通用技术读者"
    word_target: int = 1500


# ---------------------------------------------------------------------------
# LLM 与文本工具
# ---------------------------------------------------------------------------


def _ask(llm: LLMProvider, system: str, user: str) -> str:
    result = llm.complete(
        [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=user),
        ]
    )
    return result.text.strip()


def _llm_json(llm: LLMProvider, system: str, user: str) -> dict[str, Any]:
    text = _ask(llm, system, user)
    fenced = re.search(r"```(?:json)?\s*(.+?)\s*```", text, re.DOTALL)
    payload = fenced.group(1) if fenced else text
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise _LLMJSONError("LLM 未返回 JSON 对象")
    return data


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _extract_title(markdown: str) -> str:
    for line in markdown.splitlines():
        matched = _HEADING_RE.match(line.strip())
        if matched and matched.group(1) == "#":
            return matched.group(2).strip()
    for line in markdown.splitlines():
        if line.strip():
            return line.strip().lstrip("#").strip()
    return "未命名文章"


def _make_digest(markdown: str) -> str:
    for line in markdown.splitlines():
        text = line.strip()
        if not text or _HEADING_RE.match(text) or text.startswith("!["):
            continue
        cleaned = re.sub(r"[*_`>\-#]+", "", text).strip()
        if cleaned:
            return cleaned[:_DIGEST_MAX_CHARS]
    return ""


# ---------------------------------------------------------------------------
# 对抗记录工具（H2 证据、H3 定向修复、H6 审计）
# ---------------------------------------------------------------------------


def _attacks_from(issues: list, *, prefix: str) -> list[Attack]:
    attacks: list[Attack] = []
    for index, issue in enumerate(issues, start=1):
        location = issue.node or "document"
        if issue.property:
            location = f"{location}.{issue.property}"
        attacks.append(
            Attack(
                attack_id=f"{prefix}-{index}",
                category=issue.type,
                severity=issue.severity,
                location=location,
                evidence=issue.message or issue.type,
                suggestion=f"修复 {issue.type}（{location}）",
            )
        )
    return attacks


def _record_round(
    run: WorkflowRun,
    *,
    gate: Gate,
    round_no: int,
    attacks: list[Attack],
    decision: Decision,
    reason: str,
    unresolved: list[str] | None = None,
    defense_fixes: list[DefenseFix] | None = None,
) -> None:
    defense = (
        DefenseReport(gate=gate, round=round_no, fixes=defense_fixes)
        if defense_fixes is not None
        else None
    )
    run.record_round(
        AttackReport(gate=gate, round=round_no, attacks=attacks),
        defense,
        Verdict(
            gate=gate,
            round=round_no,
            decision=decision,
            reason=reason,
            unresolved=unresolved or [],
        ),
    )


def _publish_rounds(run: WorkflowRun) -> int:
    return max(
        (r.round for r in run.checkpoint.adversarial_history if r.gate == "publish"),
        default=0,
    )


# ---------------------------------------------------------------------------
# 排版工具
# ---------------------------------------------------------------------------


def _theme_or_render_error(name: str) -> Theme:
    try:
        return load_theme(name)
    except ThemeError as exc:
        raise RenderError(f"主题「{name}」加载失败：{exc}") from exc


def _insert_images(markdown: str, images: list[ImageSpec]) -> str:
    """把插图插到第 N 个小节标题之前（首标题视为文章标题，不作为锚点）。"""
    if not images:
        return markdown
    lines = markdown.split("\n")
    heading_indices = [i for i, line in enumerate(lines) if _HEADING_RE.match(line.strip())]
    anchors = heading_indices[1:]
    insertions: dict[int, str] = {}
    for spec in images:
        index = spec.position - 1
        if 0 <= index < len(anchors):
            insertions[anchors[index]] = f"![{spec.purpose}]({spec.asset_path})"
    if not insertions:
        return markdown
    out: list[str] = []
    for i, line in enumerate(lines):
        if i in insertions:
            out.extend(["", insertions[i], ""])
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Prompt 构造（中文优先）
# ---------------------------------------------------------------------------


def _research_prompt(topic: str, audience: str, sources: list[Source]) -> str:
    src_lines = [f"- {s.source_id}｜{s.title}｜{s.url}" for s in sources]
    return (
        f"主题：{topic}\n受众：{audience}\n\n搜索结果：\n" + "\n".join(src_lines) + "\n\n"
        "请基于以上搜索结果提炼关键事实与切入角度，只输出 JSON 对象：\n"
        '{"facts": [{"fact_id": "fact_001", "claim": "事实陈述", '
        '"source_ids": ["src_001"]}], "angles": ["角度一", "角度二", "角度三"]}\n'
        "facts 最多 8 条；claim 必须有搜索结果支撑；source_ids 只能引用上面列出的编号。"
    )


def _brief_prompt(research: ResearchResult, word_target: int) -> str:
    fact_lines = [
        f"- {f.fact_id}：{f.claim}（来源：{','.join(f.source_ids) or '无'}）"
        for f in research.facts
    ] or ["-（暂无研究事实，可自行补充常识性内容）"]
    angle_lines = [f"- {a}" for a in research.angles] or ["-（无）"]
    return (
        f"主题：{research.topic}\n受众：{research.audience}\n意图：{research.intent}\n"
        f"目标字数：约 {word_target} 字\n\n"
        "研究事实：\n" + "\n".join(fact_lines) + "\n\n"
        "切入角度：\n" + "\n".join(angle_lines) + "\n\n"
        "请制定文章大纲，只输出 JSON 对象：\n"
        '{"goal": "一句话目标", "framework": "tutorial 或 news-analysis", "tone": "语气",'
        ' "sections": [{"heading": "小节标题", "key_points": ["要点"], '
        '"fact_ids": ["fact_001"]}]}\n'
        "sections 数量 3 到 6；fact_ids 只能引用上面列出的编号。"
    )


def _draft_prompt(brief: ContentBrief) -> str:
    lines = [
        f"主题：{brief.topic}",
        f"受众：{brief.audience}",
        f"目标：{brief.goal}",
        f"框架：{brief.framework}；语气：{brief.tone}",
        f"目标字数：约 {brief.word_target} 字",
        "",
        "大纲：",
    ]
    for i, section in enumerate(brief.sections, start=1):
        points = "；".join(section.key_points) if section.key_points else "（自行补充）"
        lines.append(f"{i}. {section.heading}：{points}")
    return "\n".join(lines)


def _design_prompt(draft: ArticleDraft) -> str:
    preview = draft.markdown[:2000]
    return (
        f"文章标题：{draft.title}\n\n文章 Markdown：\n{preview}\n\n"
        "请输出排版方案 JSON，字段：\n"
        '- "semantic_markdown"：在原文基础上插入语义组件标注后的全文。组件为三行块，'
        '如 :::note\\n提示文字\\n:::；:::quote cite="出处"\\n引文\\n:::；'
        ':::callout\\n强调内容\\n:::；:::card title="标题"\\n- 要点\\n:::'
        "（card 正文必须是列表）。组件块前后各留一个空行；无需组件则原样返回全文。\n"
        '- "cover_prompt"：封面图中文描述（一句话）。\n'
        '- "images"：正文插图数组，最多 2 项，每项 {"position": 1, "purpose": "概念图",'
        ' "prompt": "中文描述"}，position 表示插入到第几个小节标题之前。\n'
    )


# ---------------------------------------------------------------------------
# 阶段函数（状态 → 行为）
# ---------------------------------------------------------------------------


def _stage_begin_research(run: WorkflowRun, deps: PipelineDeps) -> None:
    run.advance(WorkflowState.RESEARCHING)


def _stage_do_research(run: WorkflowRun, deps: PipelineDeps) -> None:
    outcome = deps.search.search(run.intent, limit=5)
    sources = [
        Source(source_id=f"src_{i:03d}", title=hit.title or hit.url, url=hit.url)
        for i, hit in enumerate(outcome.hits, start=1)
    ]
    facts: list[Fact] = []
    angles: list[str] = []
    if sources:
        try:
            data = _llm_json(
                deps.llm, _RESEARCH_SYSTEM, _research_prompt(run.intent, deps.audience, sources)
            )
            known = {s.source_id for s in sources}
            for item in _as_list(data.get("facts"))[:8]:
                if not isinstance(item, dict):
                    continue
                claim = str(item.get("claim", "")).strip()
                refs = [str(r) for r in _as_list(item.get("source_ids")) if str(r) in known]
                if claim and refs:
                    facts.append(
                        Fact(
                            fact_id=f"fact_{len(facts) + 1:03d}",
                            claim=claim,
                            source_ids=refs,
                        )
                    )
            angles = [str(a).strip() for a in _as_list(data.get("angles")) if str(a).strip()][:3]
        except (ProviderError, PipelineError, ValueError):
            facts, angles = [], []
    research = ResearchResult(
        topic=run.intent,
        intent="explainer",
        audience=deps.audience,
        sources=sources,
        facts=facts,
        angles=angles,
        degraded=outcome.degraded,
    )
    run.save("research_result", research)
    run.advance(WorkflowState.RESEARCHED)


def _brief_with_llm(research: ResearchResult, deps: PipelineDeps) -> ContentBrief | None:
    try:
        data = _llm_json(deps.llm, _BRIEF_SYSTEM, _brief_prompt(research, deps.word_target))
    except (ProviderError, PipelineError, ValueError):
        return None
    known = {f.fact_id for f in research.facts}
    sections: list[BriefSection] = []
    for item in _as_list(data.get("sections"))[:6]:
        if not isinstance(item, dict):
            continue
        heading = str(item.get("heading", "")).strip()
        if not heading:
            continue
        fact_ids = [str(f) for f in _as_list(item.get("fact_ids")) if str(f) in known]
        key_points = [str(p).strip() for p in _as_list(item.get("key_points")) if str(p).strip()]
        sections.append(BriefSection(heading=heading, key_points=key_points, fact_ids=fact_ids))
    if not sections:
        return None
    return ContentBrief(
        topic=research.topic,
        audience=research.audience,
        goal=str(data.get("goal", "")).strip() or f"向{research.audience}讲清{research.topic}",
        framework=str(data.get("framework", "tutorial")).strip() or "tutorial",
        tone=str(data.get("tone", "")).strip() or "专业克制",
        word_target=deps.word_target,
        sections=sections,
    )


def _degraded_brief(research: ResearchResult, deps: PipelineDeps) -> ContentBrief:
    fact_ids = [f.fact_id for f in research.facts]
    groups = [fact_ids[i::3] for i in range(3)]
    headings = ["背景与问题", "核心原理", "实践要点"]
    sections = [
        BriefSection(
            heading=heading,
            key_points=[f.claim for f in research.facts if f.fact_id in group][:4],
            fact_ids=group,
        )
        for heading, group in zip(headings, groups, strict=True)
    ]
    return ContentBrief(
        topic=research.topic,
        audience=research.audience,
        goal=f"向{research.audience}讲清{research.topic}",
        framework="tutorial",
        tone="专业克制",
        word_target=deps.word_target,
        sections=sections,
    )


def _stage_plan_brief(run: WorkflowRun, deps: PipelineDeps) -> None:
    research = run.artifact_typed("research_result", ResearchResult)
    brief = _brief_with_llm(research, deps) or _degraded_brief(research, deps)
    run.save("content_brief", brief)
    run.advance(WorkflowState.DRAFTING)


def _stage_write_draft(run: WorkflowRun, deps: PipelineDeps) -> None:
    brief = run.artifact_typed("content_brief", ContentBrief)
    try:
        markdown = _ask(deps.llm, _DRAFT_SYSTEM, _draft_prompt(brief))
    except ProviderError as exc:
        raise DraftGenerationError(f"LLM 生成正文失败：{exc}") from exc
    if not markdown:
        raise DraftGenerationError("LLM 返回了空正文")
    draft = ArticleDraft(
        title=_extract_title(markdown),
        digest=_make_digest(markdown),
        framework=brief.framework,
        markdown=markdown,
        word_count=estimate_word_count(markdown),
        fact_ids=sorted({fid for section in brief.sections for fid in section.fact_ids}),
        humanize=analyze_text(markdown),
    )
    run.save("article_draft", draft)
    run.advance(WorkflowState.DRAFTED)


def _stage_judge_content(run: WorkflowRun, deps: PipelineDeps) -> None:
    draft = run.artifact_typed("article_draft", ArticleDraft)
    research = run.artifact_typed("research_result", ResearchResult)
    brief = run.artifact_typed("content_brief", ContentBrief)
    issues = lint_content(draft, research=research, brief=brief)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        attacks = _attacks_from(errors, prefix="content")
        _record_round(
            run,
            gate="content",
            round_no=1,
            attacks=attacks,
            decision="REJECT",
            reason=f"内容门禁发现 {len(errors)} 个错误",
            unresolved=[a.attack_id for a in attacks],
        )
        raise ContentGateError(f"内容门禁失败：{len(errors)} 个错误", errors)
    _record_round(
        run,
        gate="content",
        round_no=1,
        attacks=[],
        decision="PASS",
        reason="内容门禁全部通过",
    )
    run.advance(WorkflowState.DESIGNING)


def _design_with_llm(deps: PipelineDeps, draft: ArticleDraft) -> dict[str, Any]:
    try:
        return _llm_json(deps.llm, _DESIGN_SYSTEM, _design_prompt(draft))
    except (ProviderError, PipelineError, ValueError):
        return {}


def _plan_body_images(deps: PipelineDeps, design: dict[str, Any]) -> list[ImageSpec]:
    specs: list[ImageSpec] = []
    for item in _as_list(design.get("images"))[:2]:
        if not isinstance(item, dict):
            continue
        try:
            position = int(item.get("position", 1))
        except (TypeError, ValueError):
            continue
        prompt = str(item.get("prompt", "")).strip()
        purpose = str(item.get("purpose", "")).strip() or "concept"
        if not prompt:
            continue
        try:
            asset = deps.image.generate(prompt)
        except ProviderError:
            continue
        if not asset.url.startswith("https://"):
            continue
        specs.append(
            ImageSpec(
                position=max(position, 1),
                purpose=purpose,
                prompt=prompt,
                asset_path=asset.url,
            )
        )
    return specs


def _stage_plan_visual(run: WorkflowRun, deps: PipelineDeps) -> None:
    draft = run.artifact_typed("article_draft", ArticleDraft)
    design = _design_with_llm(deps, draft)
    theme = _theme_or_render_error(run.checkpoint.theme)
    base_markdown = str(design.get("semantic_markdown", "")).strip()
    if base_markdown and lint_components(base_markdown, theme):
        base_markdown = ""
    if not base_markdown:
        base_markdown = draft.markdown
    cover_prompt = str(design.get("cover_prompt", "")).strip() or f"{draft.title} 概念插画"
    cover_asset = ""
    try:
        cover_asset = deps.image.generate(cover_prompt).url
    except ProviderError:
        cover_asset = ""
    images = _plan_body_images(deps, design)
    package = ContentPackage(
        title=draft.title,
        digest=draft.digest,
        author=deps.author,
        semantic_markdown=_insert_images(base_markdown, images),
        visual=VisualPlan(
            cover=CoverSpec(prompt=cover_prompt, asset_path=cover_asset),
            images=images,
            diagrams=[],
            degraded=not design or not cover_asset,
        ),
        theme=run.checkpoint.theme,
        word_count=draft.word_count,
    )
    run.save("content_package", package)
    run.advance(WorkflowState.RENDERING)


def _parse_ast(package: ContentPackage) -> ContentAST:
    """把语义 Markdown 解析为 AST；解析失败抛 RenderError。"""
    try:
        return parse(package.semantic_markdown, title=package.title, digest=package.digest)
    except ParseError as exc:
        raise RenderError(f"语义 Markdown 解析失败：{exc.message}") from exc


def _render_package(package: ContentPackage) -> tuple[str, ContentAST, RepairOutcome, HtmlRenderer]:
    """解析 + 渲染 + 渲染层修复，一次计算全部产物；返回 (完整 HTML, AST, 修复结果, renderer)。"""
    ast = _parse_ast(package)
    renderer = HtmlRenderer(_theme_or_render_error(package.theme))
    outcome = repair_rendered(ast, renderer)
    return renderer.wrap_document(outcome.html), ast, outcome, renderer


def _stage_render_document(run: WorkflowRun, deps: PipelineDeps) -> None:
    package = run.artifact_typed("content_package", ContentPackage)
    theme = _theme_or_render_error(package.theme)
    component_errors = lint_components(package.semantic_markdown, theme)
    if component_errors:
        attacks = _attacks_from(component_errors, prefix="component")
        _record_round(
            run,
            gate="content",
            round_no=1,
            attacks=attacks,
            decision="REJECT",
            reason=f"组件门禁发现 {len(component_errors)} 个错误",
            unresolved=[a.attack_id for a in attacks],
        )
        raise ContentGateError(f"组件校验失败：{len(component_errors)} 个错误", component_errors)
    html, ast, outcome, renderer = _render_package(package)
    run.save("validation_report", outcome.report)
    render_errors = [issue for issue in outcome.report.errors if issue.severity == "error"]
    if render_errors:
        attacks = _attacks_from(render_errors, prefix="render")
        _record_round(
            run,
            gate="render",
            round_no=1,
            attacks=attacks,
            decision="REJECT",
            reason=f"渲染修复后仍有 {len(render_errors)} 个错误",
            unresolved=[a.attack_id for a in attacks],
        )
        raise RenderError(f"渲染门禁失败：{len(render_errors)} 个错误")
    _record_round(
        run,
        gate="render",
        round_no=1,
        attacks=[],
        decision="PASS",
        reason="渲染门禁通过",
    )
    doc = WechatDocument(
        title=package.title,
        digest=package.digest,
        html=html,
        plain_text=renderer.render_plain_text(ast),
        cover_asset=package.visual.cover.asset_path if package.visual.cover else "",
        image_assets=[img.asset_path for img in package.visual.images],
        size_bytes=len(html.encode("utf-8")),
    )
    run.save("wechat_document", doc)
    run.advance(WorkflowState.VALIDATING)


def _stage_judge_publish(run: WorkflowRun, deps: PipelineDeps) -> None:
    doc = run.artifact_typed("wechat_document", WechatDocument)
    round_no = min(_publish_rounds(run) + 1, _MAX_PUBLISH_ROUNDS)
    errors = lint_gzh(doc.html)
    if errors:
        attacks = _attacks_from(errors, prefix="publish")
        _record_round(
            run,
            gate="publish",
            round_no=round_no,
            attacks=attacks,
            decision="REPAIR",
            reason=f"发布门禁发现 {len(errors)} 个平台问题",
            unresolved=[a.attack_id for a in attacks],
        )
        run.advance(WorkflowState.REPAIRING)
        return
    _record_round(
        run,
        gate="publish",
        round_no=round_no,
        attacks=[],
        decision="PASS",
        reason="发布门禁通过",
    )
    run.advance(WorkflowState.VALIDATED)


def _stage_repair_publish(run: WorkflowRun, deps: PipelineDeps) -> None:
    package = run.artifact_typed("content_package", ContentPackage)
    doc = run.artifact_typed("wechat_document", WechatDocument)
    rounds_used = _publish_rounds(run)
    previous_errors = lint_gzh(doc.html)
    if rounds_used >= _MAX_PUBLISH_ROUNDS:
        attacks = _attacks_from(previous_errors, prefix="publish")
        _record_round(
            run,
            gate="publish",
            round_no=_MAX_PUBLISH_ROUNDS,
            attacks=attacks,
            decision="REJECT",
            reason="修复轮次已用尽（H4）",
            unresolved=[a.attack_id for a in attacks],
        )
        run.advance(WorkflowState.REJECTED)
        return
    renderer = HtmlRenderer(_theme_or_render_error(package.theme))
    ast = _parse_ast(package)
    outcome = repair_document(
        [
            HtmlSegment(node_id=node_id, html=segment_html)
            for node_id, segment_html in renderer.render_segments(ast)
        ]
    )
    html = renderer.wrap_document(outcome.html)
    remaining = lint_gzh(html)
    attack_ids = [f"publish-{i}" for i in range(1, len(previous_errors) + 1)]
    fixes = (
        [
            DefenseFix(
                attack_id=attack_id,
                action="移除不支持的 CSS 属性并重渲染",
                scope="、".join(sorted(outcome.repaired_nodes)) or "document",
            )
            for attack_id in attack_ids
        ]
        if outcome.repaired_nodes
        else []
    )
    if not remaining:
        new_doc = doc.model_copy(update={"html": html, "size_bytes": len(html.encode("utf-8"))})
        run.save("wechat_document", new_doc)
        _record_round(
            run,
            gate="publish",
            round_no=rounds_used + 1,
            attacks=_attacks_from(previous_errors, prefix="publish"),
            decision="REPAIR",
            reason="Defender 修复完成，待 Judge 终审",
            unresolved=[],
            defense_fixes=fixes,
        )
        run.advance(WorkflowState.VALIDATING)
        return
    attacks = _attacks_from(remaining, prefix="publish")
    _record_round(
        run,
        gate="publish",
        round_no=rounds_used + 1,
        attacks=attacks,
        decision="REJECT",
        reason=f"修复后仍有 {len(remaining)} 个平台问题，无可行修复手段",
        unresolved=[a.attack_id for a in attacks],
        defense_fixes=fixes,
    )
    run.advance(WorkflowState.REJECTED)


def _stage_approve_publish(run: WorkflowRun, deps: PipelineDeps) -> None:
    run.advance(WorkflowState.READY_TO_PUBLISH, publish_verdict_pass=run.publish_gate_passed)


def _stage_begin_upload(run: WorkflowRun, deps: PipelineDeps) -> None:
    run.advance(WorkflowState.UPLOADING)


def _stage_upload_draft(run: WorkflowRun, deps: PipelineDeps) -> None:
    doc = run.artifact_typed("wechat_document", WechatDocument)
    package = run.artifact_typed("content_package", ContentPackage)
    cover = package.visual.cover
    result = deps.publisher.create_draft(
        doc,
        author=deps.author or package.author,
        cover_path=cover.asset_path if cover and cover.asset_path else None,
    )
    run.save("publish_result", result)
    run.advance(WorkflowState.DRAFT_CREATED)


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------


def build_pipeline(store: CheckpointStore, deps: PipelineDeps) -> Orchestrator:
    """构建端到端 Orchestrator：12 个阶段函数覆盖 13 个状态（DRAFT_CREATED 为终态）。"""

    def bind(
        func: Callable[[WorkflowRun, PipelineDeps], None],
    ) -> Callable[[WorkflowRun], None]:
        return lambda run: func(run, deps)

    return Orchestrator(
        store,
        [
            Stage(entry=WorkflowState.INIT, func=bind(_stage_begin_research)),
            Stage(entry=WorkflowState.RESEARCHING, func=bind(_stage_do_research)),
            Stage(entry=WorkflowState.RESEARCHED, func=bind(_stage_plan_brief)),
            Stage(entry=WorkflowState.DRAFTING, func=bind(_stage_write_draft)),
            Stage(entry=WorkflowState.DRAFTED, func=bind(_stage_judge_content)),
            Stage(entry=WorkflowState.DESIGNING, func=bind(_stage_plan_visual)),
            Stage(entry=WorkflowState.RENDERING, func=bind(_stage_render_document)),
            Stage(entry=WorkflowState.VALIDATING, func=bind(_stage_judge_publish)),
            Stage(entry=WorkflowState.REPAIRING, func=bind(_stage_repair_publish)),
            Stage(entry=WorkflowState.VALIDATED, func=bind(_stage_approve_publish)),
            Stage(entry=WorkflowState.READY_TO_PUBLISH, func=bind(_stage_begin_upload)),
            Stage(entry=WorkflowState.UPLOADING, func=bind(_stage_upload_draft)),
        ],
    )


def load_deps(
    env: Mapping[str, str] | None = None,
    *,
    account: str = "default",
    accounts_dir: str | Path = "accounts",
    output_dir: str | Path = "artifacts/wechat",
    author: str = "",
    audience: str = "通用技术读者",
    word_target: int = 1500,
) -> PipelineDeps:
    """从环境变量与账号配置装配生产依赖（LLM / 安全搜索 / 兜底图片 / 微信发布）。"""
    account_config = load_account(accounts_dir, account=account)
    app_id, app_secret = resolve_credentials(account_config)
    client = WeChatClient()
    tokens = TokenManager(client, app_id=app_id, app_secret=app_secret)
    publisher = WeChatPublisher(client, tokens, output_dir=Path(output_dir))
    return PipelineDeps(
        llm=load_llm_provider(env),
        search=load_safe_search_provider(env),
        image=load_fallback_image_provider(env),
        publisher=publisher,
        author=author,
        audience=audience,
        word_target=word_target,
    )
