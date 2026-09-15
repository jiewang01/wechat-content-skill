"""端到端内容管线（M6-T1）：一句话意图 → 公众号草稿。

按 references/adversarial-constraints.md 的 H1–H8 硬约束，把研究、写作、
标注、风格、配图、渲染、校验、修复、发布能力编排为 19 个状态的流水线，
由 Orchestrator 驱动：

    INIT → RESEARCHING → RESEARCHED → DRAFTING → DRAFTED
         → ANNOTATING → ANNOTATED（组件门禁）
         → STYLING → STYLED → IMAGERY（配图 prompt 规划，prompt-first）
         → RENDERING → VALIDATING ⇄ REPAIRING（发布门修复回环，≤3 轮）
         → VALIDATED → READY_TO_PUBLISH → UPLOADING → DRAFT_CREATED

新增三阶段分工：
- 标注（ANNOTATING）：LLM 产出语义组件标注的 ContentPackage 骨架；
- 风格（STYLING）：LLM 提议 + 确定性裁决产出 StyleDecision（主题、封面风格、
  否决记录），并回写 checkpoint.theme 与 package.theme；
- 配图（IMAGERY）：LLM 产出五要素配图 prompt（封面 2.35:1 + 正文 16:9），
  失败时确定性模板兜底；图片生成不在管线内（prompt-first：:::figure 占位块
  是主路产物，人工经 scripts/imagery.py --apply 回填真图）。

对抗角色分工（H1）：
- Attacker：lint_content / lint_components / lint_gzh 产出带证据的 Attack
- Defender：repair_document 定向修复（仅 unsupported_css 策略，H3）
- Judge：各阶段按错误严重度裁决 PASS / REPAIR / REJECT，并记入 adversarial_history（H6）

三级降级（蓝图 ch12）：
- research：LLM 提炼失败 → 只保留搜索来源，facts 为空
- brief：LLM 失败 → 确定性模板
- annotate：LLM 失败 → 纯正文（无组件标注，不视为降级，组件门禁照样通过）
- style：LLM 失败 → framework→theme 决策表（StyleDecision.degraded=True）
- imagery：LLM 失败 → 确定性五要素模板（VisualPlan.degraded=True）；
  prompt-first 下占位块是主路，仅连 prompt 都生成不了才标记降级
- draft：LLM 失败 → DraftGenerationError（正文不可伪造，不做降级）
- image：正文图不生成；封面在上传时（UPLOADING）按 cover prompt 兜底生成

门禁与状态机约束（core/state/machine.py）：
- DRAFTED / ANNOTATED / RENDERING 无通往 REJECTED 的转移，内容/组件/渲染门禁
  失败以异常中断，checkpoint 保留现场可 resume；
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
    RejectedTheme,
    ResearchResult,
    Source,
    StyleDecision,
    Verdict,
    VisualPlan,
    WechatDocument,
)
from core.config.config import load_account, resolve_credentials
from core.state.checkpoint import CheckpointStore
from core.state.machine import WorkflowState
from core.utils import estimate_word_count
from core.workflow.imagery import (
    SectionAnchor,
    extract_anchors,
    image_quota,
    insert_images,
    plan_visual,
    strip_figure_blocks,
)
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
from validators import lint_components, lint_content, lint_gzh, lint_visual_consistency

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
_ANNOTATE_SYSTEM = "你是一名微信公众号排版标注师。只输出一个 JSON 对象，不要输出任何解释文字。"
_STYLE_SYSTEM = "你是一名微信公众号视觉风格顾问。只输出一个 JSON 对象，不要输出任何解释文字。"
_IMAGERY_SYSTEM = "你是一名公众号配图规划师。只输出一个 JSON 对象，不要输出任何解释文字。"

_THEME_CATALOG: dict[str, str] = {
    "default": "中性默认版式，适合教程与说明文",
    "editorial": "编辑风格，衬线标题与强留白，适合观点与评论",
    "minimal": "极简黑白，信息密度低，适合严肃技术说明",
    "tech": "科技感版式，冷色强调，适合深度技术解析",
    "magazine": "杂志风格，大标题与分栏感，适合案例与盘点",
    "orange-heart": "暖色调人文风格，适合叙事与情感表达",
}

_FRAMEWORK_THEME_FALLBACK: dict[str, str] = {
    "tutorial": "default",
    "news-analysis": "default",
    "opinion": "editorial",
    "case-study": "magazine",
    "listicle": "magazine",
    "deep-dive": "tech",
    "narrative": "orange-heart",
}


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
    auto_release: bool = False


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


def _insert_images(markdown: str, images: list[ImageSpec], theme: Theme | None = None) -> str:
    """插图入文：有资产插 `![purpose](asset)`；无资产且主题启用 figure 组件时，
    以 :::figure 占位块把生图 prompt 呈现在正文（供读者取用、生图后回填替换）。
    先移除既有 figure 块再插入，保证幂等。"""
    placeholders = bool(theme is not None and theme.components_enabled.get("figure"))
    return insert_images(strip_figure_blocks(markdown), images, placeholders=placeholders)


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


def _annotate_prompt(draft: ArticleDraft) -> str:
    preview = draft.markdown[:2000]
    return (
        f"文章标题：{draft.title}\n\n文章 Markdown：\n{preview}\n\n"
        "请在原文基础上插入语义组件标注，只输出 JSON 对象，字段：\n"
        '- "semantic_markdown"：插入组件标注后的全文。组件为三行块，'
        '如 :::note\\n提示文字\\n:::；:::quote cite="出处"\\n引文\\n:::；'
        ':::callout\\n强调内容\\n:::；:::card title="标题"\\n- 要点\\n:::'
        "（card 正文必须是列表）。组件块前后各留一个空行；"
        "标注服务于内容结构（提示、引文、强调、要点卡），不要为标而标；"
        "无需组件则原样返回全文。\n"
    )


def _style_prompt(draft: ArticleDraft, brief: ContentBrief) -> str:
    catalog_lines = [f"- {name}：{desc}" for name, desc in _THEME_CATALOG.items()]
    return (
        f"文章标题：{draft.title}\n摘要：{draft.digest}\n"
        f"写作框架：{brief.framework}；语气：{brief.tone}\n\n"
        f"候选主题：\n" + "\n".join(catalog_lines) + "\n\n"
        "请为这篇文章选择最合适的排版主题，只输出 JSON 对象：\n"
        '{"theme": "主题 id", "cover_style": "封面视觉风格一句话标签", '
        '"rationale": "选择理由（一句话）", '
        '"rejected": [{"theme": "落选 id", "reason": "落选原因"}]}\n'
        "theme 只能取候选列表中的 id；cover_style 描述封面画面的视觉气质"
        "（如「冷峻杂志封面」「暖色手绘感」），不是主题 id。"
    )


def _imagery_prompt(
    package: ContentPackage, anchors: list[SectionAnchor], quota: int
) -> str:
    anchor_lines = [
        f"- 第 {a.position} 位：「{a.title}」" + (f"——{a.summary}" if a.summary else "")
        for a in anchors
    ] or ["-（无可用插入位）"]
    preview = package.semantic_markdown[:2000]
    return (
        f"文章标题：{package.title}\n摘要：{package.digest}\n\n"
        f"正文（语义 Markdown）：\n{preview}\n\n"
        f"可插入位置（插图插到该位之前）：\n" + "\n".join(anchor_lines) + "\n\n"
        f"配额：正文插图最多 {quota} 张。\n\n"
        "请规划配图，只输出 JSON 对象：\n"
        '- "cover_prompt"：封面图中文 prompt，五要素结构（主体+风格+构图/比例+'
        "色调+约束），横向封面构图（2.35:1），以「画面中不出现任何文字、无水印、"
        '无 logo」收尾。\n'
        '- "images"：正文插图数组，数量不超过配额，每项 {"position": 1, '
        '"purpose": "概念图", "prompt": "五要素中文 prompt"}；构图一律横构图'
        "（16:9）；position 只能取上面列出的插入位；每条 prompt 自包含、"
        "可直接粘贴到任意文生图工具。\n"
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
    run.advance(WorkflowState.ANNOTATING)


def _annotate_with_llm(deps: PipelineDeps, draft: ArticleDraft) -> str:
    try:
        data = _llm_json(deps.llm, _ANNOTATE_SYSTEM, _annotate_prompt(draft))
    except (ProviderError, PipelineError, ValueError):
        return ""
    return str(data.get("semantic_markdown", "")).strip()


def _stage_annotate(run: WorkflowRun, deps: PipelineDeps) -> None:
    """ANNOTATING：LLM 语义标注 → ContentPackage 骨架（主题沿用 checkpoint，风格阶段再定）。

    标注有语法错误时宁可丢弃（回退纯正文，不视为降级）；组件兼容留待门禁裁决。"""
    draft = run.artifact_typed("article_draft", ArticleDraft)
    semantic_markdown = _annotate_with_llm(deps, draft)
    if semantic_markdown and lint_components(semantic_markdown, None):
        semantic_markdown = ""
    if not semantic_markdown:
        semantic_markdown = draft.markdown
    package = ContentPackage(
        title=draft.title,
        digest=draft.digest,
        author=deps.author,
        semantic_markdown=semantic_markdown,
        visual=VisualPlan(),
        theme=run.checkpoint.theme,
        word_count=draft.word_count,
    )
    run.save("content_package", package)
    run.advance(WorkflowState.ANNOTATED)


def _stage_judge_components(run: WorkflowRun, deps: PipelineDeps) -> None:
    """ANNOTATED：组件门禁（自 RENDERING 前移）；失败以异常中断，现场可 resume。"""
    package = run.artifact_typed("content_package", ContentPackage)
    theme = _theme_or_render_error(run.checkpoint.theme)
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
        raise ContentGateError(f"组件门禁失败：{len(component_errors)} 个错误", component_errors)
    _record_round(
        run,
        gate="content",
        round_no=1,
        attacks=[],
        decision="PASS",
        reason="组件门禁全部通过",
    )
    run.advance(WorkflowState.STYLING)


def _rejected_themes(data: dict[str, Any]) -> list[RejectedTheme]:
    rejected: list[RejectedTheme] = []
    for item in _as_list(data.get("rejected")):
        if not isinstance(item, dict):
            continue
        theme = str(item.get("theme", "")).strip()
        if not theme:
            continue
        rejected.append(RejectedTheme(theme=theme, reason=str(item.get("reason", "")).strip()))
    return rejected


def _style_with_llm(
    deps: PipelineDeps, draft: ArticleDraft, brief: ContentBrief
) -> StyleDecision | None:
    try:
        data = _llm_json(deps.llm, _STYLE_SYSTEM, _style_prompt(draft, brief))
    except (ProviderError, PipelineError, ValueError):
        return None
    theme = str(data.get("theme", "")).strip()
    if not theme:
        return None
    return StyleDecision(
        theme=theme,
        rationale=str(data.get("rationale", "")).strip(),
        rejected=_rejected_themes(data),
        cover_style=str(data.get("cover_style", "")).strip(),
        framework=brief.framework,
        tone=brief.tone,
        degraded=False,
    )


def _used_components(semantic_markdown: str) -> set[str]:
    """扫描正文使用的组件名（:::xxx 标记行；组件门禁已保证标记合法）。"""
    used: set[str] = set()
    for line in semantic_markdown.split("\n"):
        stripped = line.strip()
        if stripped.startswith(":::") and stripped != ":::" and len(stripped) > 3:
            used.add(stripped[3:].split()[0])
    return used


def _components_missing(theme: Theme, used: set[str]) -> list[str]:
    """组件兼容安全网：正文用到的组件，主题必须启用且有样式定义。"""
    return [
        name
        for name in sorted(used)
        if not theme.components_enabled.get(name, False) or name not in theme.components
    ]


def _stage_style(run: WorkflowRun, deps: PipelineDeps) -> None:
    """STYLING：LLM 提议 → 确定性裁决（主题可加载 + 组件兼容）→ 决策表兜底。

    决策写入 StyleDecision 工件（含否决记录），并回写 checkpoint.theme 与
    package.theme，供渲染与配图阶段取用。"""
    draft = run.artifact_typed("article_draft", ArticleDraft)
    brief = run.artifact_typed("content_brief", ContentBrief)
    package = run.artifact_typed("content_package", ContentPackage)
    decision = _style_with_llm(deps, draft, brief)
    rejected_proposal: RejectedTheme | None = None
    if decision is not None:
        try:
            theme = load_theme(decision.theme)
        except ThemeError:
            theme = None
        if theme is None or _components_missing(theme, _used_components(package.semantic_markdown)):
            rejected_proposal = RejectedTheme(
                theme=decision.theme, reason="主题不可用或组件不兼容，回退决策表"
            )
            decision = None
    if decision is None:
        decision = StyleDecision(
            theme=_FRAMEWORK_THEME_FALLBACK.get(brief.framework, "default"),
            rationale=f"LLM 风格提议不可用，按框架「{brief.framework}」查决策表",
            rejected=[rejected_proposal] if rejected_proposal else [],
            framework=brief.framework,
            tone=brief.tone,
            degraded=True,
        )
    run.save("style_decision", decision)
    run.checkpoint.theme = decision.theme
    run.store.save_checkpoint(run.checkpoint)
    run.save("content_package", package.model_copy(update={"theme": decision.theme}))
    run.advance(WorkflowState.STYLED)


def _imagery_with_llm(
    deps: PipelineDeps, package: ContentPackage, anchors: list[SectionAnchor], quota: int
) -> dict[str, Any]:
    try:
        return _llm_json(deps.llm, _IMAGERY_SYSTEM, _imagery_prompt(package, anchors, quota))
    except (ProviderError, PipelineError, ValueError):
        return {}


def _llm_body_images(data: dict[str, Any], positions: set[int], quota: int) -> list[ImageSpec]:
    """LLM 规划的正文插图：只取 prompt（prompt-first，asset_path 一律留空，
    真图由人工经 scripts/imagery.py --apply 回填）。"""
    specs: list[ImageSpec] = []
    for item in _as_list(data.get("images"))[:quota]:
        if not isinstance(item, dict):
            continue
        try:
            position = int(item.get("position", 0))
        except (TypeError, ValueError):
            continue
        prompt = str(item.get("prompt", "")).strip()
        purpose = str(item.get("purpose", "")).strip() or "concept"
        if not prompt or position not in positions:
            continue
        specs.append(ImageSpec(position=position, purpose=purpose, prompt=prompt))
    return specs


def _stage_begin_imagery(run: WorkflowRun, deps: PipelineDeps) -> None:
    run.advance(WorkflowState.IMAGERY)


def _stage_plan_imagery(run: WorkflowRun, deps: PipelineDeps) -> None:
    """IMAGERY：prompt-first 配图规划（封面 2.35:1 + 正文 16:9 五要素 prompt）。

    图片生成不在管线内：正文 :::figure 占位块是主路产物，封面在上传时按
    prompt 兜底生成；LLM 整体不可用时确定性模板兜底（degraded=True），
    部分结果与兜底合并不算降级。"""
    package = run.artifact_typed("content_package", ContentPackage)
    decision = run.artifact_typed("style_decision", StyleDecision)
    theme = _theme_or_render_error(run.checkpoint.theme)
    fallback = plan_visual(package, theme, cover_style=decision.cover_style or decision.theme)
    fallback_cover = fallback.cover or CoverSpec()
    anchors = extract_anchors(package.semantic_markdown)
    quota = image_quota(package.word_count)
    data = _imagery_with_llm(deps, package, anchors, quota)
    images = _llm_body_images(data, {a.position for a in anchors}, quota) if data else []
    cover_prompt = str(data.get("cover_prompt", "")).strip() if data else ""
    visual = VisualPlan(
        cover=CoverSpec(
            style=fallback_cover.style,
            ratio="2.35:1",
            prompt=cover_prompt or fallback_cover.prompt,
        ),
        images=images or fallback.images,
        diagrams=[],
        degraded=not data,
    )
    run.save(
        "content_package",
        package.model_copy(
            update={
                "semantic_markdown": _insert_images(package.semantic_markdown, visual.images, theme),
                "visual": visual,
            }
        ),
    )
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
    """RENDERING：解析 + 渲染 + 渲染层修复 + 渲染门禁
    （组件门禁已前移至 ANNOTATED；visual↔figure 一致性在此终检）。"""
    package = run.artifact_typed("content_package", ContentPackage)
    html, ast, outcome, renderer = _render_package(package)
    visual_issues = lint_visual_consistency(package)
    report = (
        outcome.report.model_copy(
            update={
                "errors": list(outcome.report.errors)
                + [i for i in visual_issues if i.severity == "error"],
                "warnings": list(outcome.report.warnings)
                + [i for i in visual_issues if i.severity == "warning"],
            }
        )
        if visual_issues
        else outcome.report
    )
    run.save("validation_report", report)
    render_errors = [issue for issue in report.errors if issue.severity == "error"]
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
    """UPLOADING：创建公众号草稿；封面缺资产但有 prompt 时按 prompt 兜底生成（增强 C）。

    生成的 URL 原样交给 publisher：data: URI 原生可用；https 由 publisher 侧
    裁决（v0.1 仅收 data: 与本地路径，无封面走降级发布）。生成结果回写
    package.visual.cover.asset_path，重试时不重复生图。"""
    doc = run.artifact_typed("wechat_document", WechatDocument)
    package = run.artifact_typed("content_package", ContentPackage)
    cover = package.visual.cover
    cover_path = cover.asset_path if cover else ""
    if not cover_path and cover and cover.prompt:
        try:
            cover_path = deps.image.generate(cover.prompt).url
        except ProviderError:
            cover_path = ""
    if cover_path and cover and not cover.asset_path:
        cover = cover.model_copy(update={"asset_path": cover_path})
        run.save(
            "content_package",
            package.model_copy(
                update={"visual": package.visual.model_copy(update={"cover": cover})}
            ),
        )
    result = deps.publisher.create_draft(
        doc,
        author=deps.author or package.author,
        cover_path=cover_path or None,
    )
    run.save("publish_result", result)
    run.advance(WorkflowState.DRAFT_CREATED)
    if deps.auto_release and result.status == "draft_created" and result.draft_id:
        released = deps.publisher.release(
            result.draft_id,
            media_id=result.media_id,
            html_path=result.html_path,
        )
        run.save("publish_result", released)
        if released.status == "published":
            run.advance(WorkflowState.PUBLISHED)


# ---------------------------------------------------------------------------
# 装配
# ---------------------------------------------------------------------------


def build_pipeline(store: CheckpointStore, deps: PipelineDeps) -> Orchestrator:
    """构建端到端 Orchestrator：16 个阶段函数覆盖 19 个状态
    （DRAFT_CREATED / PUBLISHED / REJECTED 为终态，不绑定阶段函数）。"""

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
            Stage(entry=WorkflowState.ANNOTATING, func=bind(_stage_annotate)),
            Stage(entry=WorkflowState.ANNOTATED, func=bind(_stage_judge_components)),
            Stage(entry=WorkflowState.STYLING, func=bind(_stage_style)),
            Stage(entry=WorkflowState.STYLED, func=bind(_stage_begin_imagery)),
            Stage(entry=WorkflowState.IMAGERY, func=bind(_stage_plan_imagery)),
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
    auto_release: bool = False,
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
        auto_release=auto_release,
    )
