---
name: wechat-content-skill
description: Agent-native workflow skill that turns one sentence into a validated WeChat Official Account (公众号) draft — research, write, humanize, semantic layout, theme rendering, adversarial validation, draft-box publishing. Invoke when the user wants to create, design, or publish a WeChat 公众号 article.
---

# WeChat Content Skill

## Purpose

Create, validate and publish high-quality WeChat Official Account content.
One sentence in, a validated draft-box article out:

> 一句话 → 研究 → 写作 → 排版 → 校验 → 微信草稿

## Hard Constraints (read first)

All stages MUST obey [references/adversarial-constraints.md](references/adversarial-constraints.md) (H1–H8):

- Defender produces, Attacker attacks with evidence, Judge (deterministic code only) rules.
- No evidence, no attack. No PASS verdict, no publishing. Max 3 repair rounds per gate, then degrade.

## Workflow

1. **Research** — search, read, extract, cross-verify → `ResearchResult`
2. **Plan** — select framework, outline → `ContentBrief`
3. **Write** — draft → `ArticleDraft`
4. **Humanize** — AI-flavor detection + rewrite loop (Quality Gate, not a prompt)
5. **Design** — structured `VisualPlan` (cover / images / diagrams)
6. **Native** — annotate with semantic markers (`:::note` / `:::quote` / `:::callout` / `:::card`) → `ContentPackage`
7. **Render** — ContentAST → theme-driven HTML → `WechatDocument`
8. **Validate** — 3 adversarial gates (content / render / publish) → `ValidationReport` + `Verdict`
9. **Repair** — targeted node-level fixes only, ≤ 3 rounds, never regenerate the whole article
10. **Publish** — WeChat draft box via API Facade; if API is down, degrade to local HTML export

Every stage: save artifact to checkpoint (`outputs/<run_id>/`), advance state machine, survive crash via `resume`.

## Rules

- Never invent factual claims; every fact carries `source_ids`.
- Never directly generate final HTML — LLM output stops at semantic markers; the deterministic renderer owns HTML.
- Always validate before publishing; never publish when validation fails.
- Prefer deterministic tools over LLM judgment (Judge = code, always).
- Preserve artifacts between stages; pass structured artifacts, never prose.
- Search / image / WeChat API failures degrade gracefully — publishing is not the only exit.

## Routing

| Stage | Sub-Skill | Output artifact |
|-------|-----------|-----------------|
| Research | [skills/research/SKILL.md](skills/research/SKILL.md) | `ResearchResult` |
| Plan + Write + Humanize | [skills/content/SKILL.md](skills/content/SKILL.md) | `ContentBrief` → `ArticleDraft` |
| Design | [skills/visual/SKILL.md](skills/visual/SKILL.md) | `VisualPlan` |
| Native | [skills/native/SKILL.md](skills/native/SKILL.md) | `ContentPackage` |
| Layout / Render | [skills/layout/SKILL.md](skills/layout/SKILL.md) | `WechatDocument` |
| Publish | [skills/publishing/SKILL.md](skills/publishing/SKILL.md) | `PublishResult` |

Artifact schemas: [schemas/](schemas/) (JSON Schema, exported from `core/artifacts/`).
State machine: `core/state/machine.py` (INIT → … → DRAFT_CREATED; see blueprint ch. 11).

## CLI

```bash
python scripts/render.py <content_package.json> -o wechat.html
python scripts/lint.py <content_ast.json>
python scripts/validate.py <wechat.html>
python scripts/preview.py <wechat.html>
python scripts/publish.py <run_id> --account default
```

## Resume

Any interrupted run can be resumed from its checkpoint:

```python
from core.state.checkpoint import CheckpointStore
from core.workflow.orchestrator import Orchestrator

run = Orchestrator(CheckpointStore("outputs"), stages).resume("<run_id>")
```
