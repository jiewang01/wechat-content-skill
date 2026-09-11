from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Gate = Literal["content", "render", "publish"]
Decision = Literal["PASS", "REPAIR", "REJECT"]


class ArtifactBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Artifact creation timestamp (UTC).",
    )


class Source(ArtifactBase):
    source_id: str = Field(description="Stable id referenced by Fact.source_ids, e.g. src_001.")
    title: str
    url: str = ""
    credibility: float = Field(default=0.5, ge=0.0, le=1.0)
    published_at: str = ""


class Fact(ArtifactBase):
    fact_id: str = Field(
        description="Stable id referenced by ArticleDraft.fact_ids, e.g. fact_001."
    )
    claim: str
    source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class ResearchResult(ArtifactBase):
    topic: str
    intent: str = "explainer"
    audience: str = ""
    sources: list[Source] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    angles: list[str] = Field(default_factory=list)
    degraded: bool = Field(
        default=False,
        description=(
            "True when search was unavailable and existing sources were reused "
            "(graceful degradation)."
        ),
    )


class BriefSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    heading: str
    key_points: list[str] = Field(default_factory=list)
    fact_ids: list[str] = Field(default_factory=list)


class ContentBrief(ArtifactBase):
    topic: str
    audience: str = ""
    goal: str = ""
    framework: str = Field(
        description="Writing framework id: tutorial | news-analysis | opinion | case-study "
        "| listicle | deep-dive | narrative."
    )
    tone: str = "professional"
    word_target: int = Field(default=1500, ge=200, le=10000)
    sections: list[BriefSection] = Field(default_factory=list)


class HumanizeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    humanize_score: int = Field(ge=0, le=100)
    issues: list[dict[str, str]] = Field(default_factory=list)
    passed: bool = False


class ArticleDraft(ArtifactBase):
    title: str
    digest: str = ""
    framework: str = ""
    markdown: str = Field(description="Plain Markdown body without semantic markers.")
    word_count: int = Field(default=0, ge=0)
    fact_ids: list[str] = Field(default_factory=list)
    humanize: HumanizeReport | None = None


class CoverSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: str = "editorial"
    ratio: str = "2.35:1"
    prompt: str = ""
    asset_path: str = ""


class ImageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=1, description="Insert before the section at this 1-based position.")
    purpose: str = "concept"
    prompt: str = ""
    asset_path: str = ""


class DiagramSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: int = Field(ge=1)
    type: str = "flowchart"
    spec: str = ""


class VisualPlan(ArtifactBase):
    cover: CoverSpec | None = None
    images: list[ImageSpec] = Field(default_factory=list)
    diagrams: list[DiagramSpec] = Field(default_factory=list)
    degraded: bool = Field(
        default=False, description="True when the primary image pipeline failed."
    )


class ContentPackage(ArtifactBase):
    title: str
    digest: str = ""
    author: str = ""
    semantic_markdown: str = Field(
        description=(
            "Markdown annotated with :::note / :::quote / :::callout / :::card semantic markers."
        )
    )
    visual: VisualPlan = Field(default_factory=VisualPlan)
    theme: str = "default"
    word_count: int = Field(default=0, ge=0)


class WechatDocument(ArtifactBase):
    title: str
    digest: str = ""
    html: str = Field(description="Final GZH-compatible HTML with inline styles only.")
    plain_text: str = ""
    cover_asset: str = ""
    image_assets: list[str] = Field(default_factory=list)
    size_bytes: int = Field(default=0, ge=0)


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    node: str = ""
    property: str = ""
    message: str = ""
    severity: Literal["error", "warning"] = "error"


class ValidationReport(ArtifactBase):
    status: Literal["passed", "failed"]
    gate: Gate = Field(default="publish", description="Gate this report belongs to.")
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    humanize_score: int | None = Field(default=None, ge=0, le=100)


class PublishResult(ArtifactBase):
    status: Literal["draft_created", "published", "degraded", "failed"]
    media_id: str = ""
    draft_id: str = ""
    publish_id: str = Field(
        default="",
        description="Freepublish task id; set once the draft was submitted for release.",
    )
    article_url: str = Field(
        default="",
        description="Published article URL; set only on the confirmed published exit.",
    )
    html_path: str = Field(
        default="",
        description="Local HTML export path; set on success, degraded and failed exits alike.",
    )
    degraded: bool = Field(
        default=False,
        description="True when WeChat API was unavailable and the run ended with a local artifact.",
    )
    message: str = ""


class Attack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attack_id: str
    category: str
    severity: Literal["error", "warning"] = "error"
    location: str = Field(description="Node id, source id or section locator of the attacked spot.")
    evidence: str = Field(
        min_length=1, description="Verbatim evidence backing the attack (hard constraint H2)."
    )
    suggestion: str = ""


class AttackReport(ArtifactBase):
    gate: Gate
    round: int = Field(
        ge=1, le=3, description="Adversarial round number, capped at 3 (hard constraint H4)."
    )
    attacks: list[Attack] = Field(default_factory=list)


class DefenseFix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attack_id: str
    action: str
    scope: str = Field(
        description=(
            "Node ids / fields actually modified; must stay inside attacked locations "
            "(hard constraint H3)."
        )
    )


class DefenseReport(ArtifactBase):
    gate: Gate
    round: int = Field(ge=1, le=3)
    fixes: list[DefenseFix] = Field(default_factory=list)


class Verdict(ArtifactBase):
    gate: Gate
    round: int = Field(ge=1, le=3)
    decision: Decision
    reason: str = ""
    unresolved: list[str] = Field(
        default_factory=list, description="Attack ids still unresolved when decision != PASS."
    )


ARTIFACT_MODELS: dict[str, type[ArtifactBase]] = {
    "research_result": ResearchResult,
    "content_brief": ContentBrief,
    "article_draft": ArticleDraft,
    "visual_plan": VisualPlan,
    "content_package": ContentPackage,
    "wechat_document": WechatDocument,
    "validation_report": ValidationReport,
    "publish_result": PublishResult,
    "attack_report": AttackReport,
    "defense_report": DefenseReport,
    "verdict": Verdict,
}


__all__ = [
    "ARTIFACT_MODELS",
    "ArtifactBase",
    "ArticleDraft",
    "Attack",
    "AttackReport",
    "ContentBrief",
    "ContentPackage",
    "CoverSpec",
    "DefenseFix",
    "DefenseReport",
    "DiagramSpec",
    "Fact",
    "HumanizeReport",
    "ImageSpec",
    "PublishResult",
    "ResearchResult",
    "Source",
    "ValidationIssue",
    "ValidationReport",
    "Verdict",
    "WechatDocument",
]
