---
name: native
description: Native-information sub-skill of wechat-content-skill. Annotates article Markdown with the four semantic markers (:::note, :::quote, :::callout, :::card) that the deterministic renderer turns into theme components. The LLM never writes HTML.
---

# Native Skill (Semantic Marker Layer)

## Purpose

Add native information structure between writing and rendering: the Agent expresses intent with semantic markers; the renderer owns all HTML. This is what makes theme switching and WeChat-compatibility possible.

## Input / Output

- Input: `ArticleDraft` + `VisualPlan`
- Output: `ContentPackage` (schemas/content_package.schema.json) — `semantic_markdown` carries the markers

## The 4 markers (complete v0.1 set — no others)

```markdown
:::note
默认蓝色提示。用于补充说明、背景信息。
:::

:::quote cite="Linus Torvalds, 2025"
引用原话。cite 可选。
:::

:::callout type="warning" title="注意"
type ∈ info | warning | tip | danger；title 可选。
:::

:::card title="核心要点"
- 第一条
- 第二条
:::
```

## Rules (Defender duties)

- Markers use exactly the props defined in [components/](components/) and `renderer/components/registry.py`; unknown props are lint errors.
- **No nesting**: a `:::` block never contains another `:::` block (v0.1 hard limit).
- Use sparingly: roughly one component per 300–500 words; the article must not become a slideshow.
- Never emit `<div>`, `<span>`, inline styles, or any HTML — semantic markers only; the renderer generates HTML deterministically.
- When lint attacks a component (`component_N`), fix that component only (H3).

## Component specs

- [components/note.md](components/note.md)
- [components/quote.md](components/quote.md)
- [components/callout.md](components/callout.md)
- [components/card.md](components/card.md)

## References

- [../../../references/adversarial-constraints.md](../../../references/adversarial-constraints.md)
