---
name: research
description: Research sub-skill of wechat-content-skill. Search, read, extract and cross-verify sources, then emit a structured ResearchResult artifact. Never writes the article itself.
---

# Research Skill

## Purpose

Turn a topic into a verified, structured `ResearchResult` — the sole input contract for the content stage. Research never writes article prose.

## Input / Output

- Input: user intent (topic, audience, angle hints) + optional existing sources
- Output: `ResearchResult` (schema: `schemas/research_result.schema.json`)

```json
{
  "topic": "AI Agent 的下一阶段",
  "intent": "explainer",
  "audience": "AI 从业者",
  "sources": [{"source_id": "src_001", "title": "...", "url": "...", "credibility": 0.92}],
  "facts": [{"fact_id": "fact_001", "claim": "...", "source_ids": ["src_001"]}],
  "angles": ["...", "...", "..."]
}
```

## Workflow

```text
搜索 → 阅读 → 提取 → 交叉验证 → 结构化
```

1. **Search** — 3–8 queries from different angles (via `integrations/search/` provider).
2. **Read** — open top results; prefer primary sources; record `credibility` (0–1).
3. **Extract** — distill atomic claims; each fact gets a `fact_id` and MUST cite `source_ids`.
4. **Cross-verify** — a claim held by only one low-credibility source is either dropped or flagged `confidence < 0.5`.
5. **Structure** — 3–5 candidate angles for the content stage to pick from.

## Rules (Defender duties)

- Never invent facts; every claim carries at least one `source_id` that exists in `sources`.
- Never draft article sections here — that is the content skill's job.
- At least 3 sources and 5 facts before handing off; if search is unavailable, set `degraded: true` and proceed with existing sources (graceful degradation).
- When attacked (AttackReport targeting `facts`/`sources`), fix ONLY the cited entries — never rewrite the whole artifact (H3).

## References

- [references/source-credibility.md](references/source-credibility.md)
- [references/adversarial-constraints.md](../../../references/adversarial-constraints.md) (hard constraints H1–H8)
