---
name: content
description: Content sub-skill of wechat-content-skill. Turns a ResearchResult into a ContentBrief and a humanized ArticleDraft via framework-driven writing, with a deterministic humanize quality gate.
---

# Content Skill

## Purpose

Receive `ResearchResult` + brand voice + audience + content goal; emit `ContentBrief` then `ArticleDraft` that passes the humanize gate.

## Input / Output

- Input: `ResearchResult` (+ tone / word target / framework hint)
- Output: `ContentBrief` (schemas/content_brief.schema.json) → `ArticleDraft` (schemas/article_draft.schema.json)

## Workflow

```text
ContentBrief → Framework Selection → Outline → Draft → Critique → Rewrite → Humanize → Final
```

1. **Brief** — topic, audience, goal, tone, `word_target`, section skeletons with `fact_ids`.
2. **Framework selection** — route by topic type; v0.1 ships two frameworks (below). Adding a framework never touches the orchestrator.
3. **Draft** — plain Markdown; semantic markers are NOT added here (that is the native skill's job).
4. **Critique → Rewrite** — self-review against the chosen framework's checklist.
5. **Humanize** — run the deterministic detector (`skills/content/humanize/`), rewrite flagged sentences, re-run until `passed: true`.

## Frameworks (v0.1)

| Framework | When | Definition |
|-----------|------|------------|
| `tutorial` | 教程 / how-to / 上手指南 | [frameworks/tutorial.md](frameworks/tutorial.md) |
| `news-analysis` | 新闻解读 / 事件分析 | [frameworks/news-analysis.md](frameworks/news-analysis.md) |

(v0.2 backlog: opinion / case-study / listicle / deep-dive / narrative)

## Rules (Defender duties)

- Every factual statement must trace to a `fact_id` from the research result; no invented claims.
- Humanize is a **quality gate**, not a prompt: the draft ships only with `humanize.passed: true`.
- Do not output HTML or `:::` markers; plain Markdown only.
- When attacked (AI-flavor, fact, structure), fix ONLY the flagged sentences/sections (H3).

## Components

- [humanize/](humanize/) — deterministic AI-flavor detector (Attacker engine for the content gate)
- [writing/](writing/) — sentence craft notes consumed during rewrite
- [frameworks/](frameworks/) — writing framework definitions

## References

- [../../../references/writing-guide.md](../../../references/writing-guide.md)
- [../../../references/humanize.md](../../../references/humanize.md)
- [../../../references/adversarial-constraints.md](../../../references/adversarial-constraints.md)
