"""确定性 AI 味检测器：内容质量门（content gate）的 Attacker 引擎。

规则外置于 rules.yaml（硬约束 H7），本模块只实现判定逻辑；
Judge 职责由确定性代码承担，LLM 不参与打分。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from core.artifacts.models import HumanizeReport

RULES_PATH = Path(__file__).parent / "rules.yaml"

_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")
_HEADING_RE = re.compile(r"^#{1,6}\s+")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.、)])\s+")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")

_EVIDENCE_MAX = 60


class _RuleModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Penalties(_RuleModel):
    phrase: int = Field(default=8, ge=0)
    paired_phrase: int = Field(default=8, ge=0)
    long_sentence: int = Field(default=3, ge=0)
    avg_sentence_length: int = Field(default=5, ge=0)
    long_paragraph: int = Field(default=3, ge=0)
    repetition: int = Field(default=5, ge=0)


class Limits(_RuleModel):
    max_sentence_chars: int = 60
    avg_sentence_chars: int = 35
    max_paragraph_chars: int = 200
    repeat_ngram_chars: int = 5
    repeat_min_occurrences: int = 3
    min_sentences_for_avg: int = 3


class HumanizeRules(_RuleModel):
    version: int = 1
    pass_score: int = Field(default=60, ge=0, le=100)
    penalties: Penalties = Field(default_factory=Penalties)
    limits: Limits = Field(default_factory=Limits)
    phrases: list[str] = Field(default_factory=list)
    pairs: list[tuple[str, str]] = Field(default_factory=list)


def load_rules(path: str | Path | None = None) -> HumanizeRules:
    """加载检测规则；默认读取本目录下的 rules.yaml。"""
    rules_path = Path(path) if path is not None else RULES_PATH
    data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    return HumanizeRules.model_validate(data)


def _clip(text: str, limit: int = _EVIDENCE_MAX) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _strip_line(line: str) -> str:
    line = _IMAGE_RE.sub("", line)
    line = _HEADING_RE.sub("", line)
    line = _LIST_ITEM_RE.sub("", line)
    return line.strip()


def _normalize(markdown: str) -> str:
    text = _CODE_FENCE_RE.sub("", markdown)
    return "\n".join(_strip_line(line) for line in text.split("\n"))


def _sentences(paragraph: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(paragraph) if s.strip()]


def _issue(kind: str, severity: str, evidence: str, message: str) -> dict[str, str]:
    return {"type": kind, "severity": severity, "evidence": evidence, "message": message}


def analyze_text(markdown: str, rules: HumanizeRules | None = None) -> HumanizeReport:
    """对 Markdown 正文做 AI 味检测，返回 HumanizeReport（含分数与逐条问题）。"""
    rules = rules if rules is not None else load_rules()
    text = _normalize(markdown)
    issues: list[dict[str, str]] = []
    score = 100

    for phrase in rules.phrases:
        count = text.count(phrase)
        if count:
            score -= rules.penalties.phrase * count
            issues.append(
                _issue(
                    "blacklist_phrase",
                    "error",
                    phrase,
                    f"命中 AI 高频套话「{phrase}」共 {count} 次，请改写为具体表述。",
                )
            )

    paragraphs = [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(text) if p.strip()]
    all_sentences: list[str] = []
    for paragraph in paragraphs:
        all_sentences.extend(_sentences(paragraph))

    for sentence in all_sentences:
        for first, second in rules.pairs:
            if first in sentence and second in sentence:
                score -= rules.penalties.paired_phrase
                issues.append(
                    _issue(
                        "paired_phrase",
                        "error",
                        _clip(sentence),
                        f"同一句内出现「{first}…{second}」，典型 AI 关联句式，请拆分或改写。",
                    )
                )

    limits = rules.limits
    for sentence in all_sentences:
        if len(sentence) > limits.max_sentence_chars:
            score -= rules.penalties.long_sentence
            issues.append(
                _issue(
                    "long_sentence",
                    "warning",
                    _clip(sentence),
                    f"句子超过 {limits.max_sentence_chars} 字（实际 {len(sentence)} 字），请拆短。",
                )
            )

    if len(all_sentences) >= limits.min_sentences_for_avg:
        avg = sum(len(s) for s in all_sentences) / len(all_sentences)
        if avg > limits.avg_sentence_chars:
            score -= rules.penalties.avg_sentence_length
            issues.append(
                _issue(
                    "avg_sentence_length",
                    "warning",
                    f"{avg:.1f} 字/句",
                    f"平均句长 {avg:.1f} 字，超过 {limits.avg_sentence_chars} 字，整体节奏偏拖沓。",
                )
            )

    for paragraph in paragraphs:
        if len(paragraph) > limits.max_paragraph_chars:
            score -= rules.penalties.long_paragraph
            issues.append(
                _issue(
                    "long_paragraph",
                    "warning",
                    _clip(paragraph),
                    f"段落超过 {limits.max_paragraph_chars} 字"
                    f"（实际 {len(paragraph)} 字），请分段。",
                )
            )

    ngram_counts: dict[str, int] = {}
    n = limits.repeat_ngram_chars
    for run in _CJK_RUN_RE.findall(text):
        for i in range(len(run) - n + 1):
            gram = run[i : i + n]
            ngram_counts[gram] = ngram_counts.get(gram, 0) + 1
    for gram, count in ngram_counts.items():
        if count >= limits.repeat_min_occurrences:
            score -= rules.penalties.repetition
            issues.append(
                _issue(
                    "repetition",
                    "warning",
                    gram,
                    f"片段「{gram}」重复出现 {count} 次，请替换表述。",
                )
            )

    score = max(0, min(100, score))
    return HumanizeReport(humanize_score=score, issues=issues, passed=score >= rules.pass_score)
