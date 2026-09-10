---
name: visual
description: Visual sub-skill of wechat-content-skill. Produces a structured VisualPlan (cover, images, diagrams) with prompts, before any rendering happens. Never generates the final HTML.
---

# Visual Skill

## Purpose

Decide what visuals the article needs, as a structured `VisualPlan` the renderer and image providers can consume — instead of letting the writing model casually pick images mid-prose.

## Input / Output

- Input: `ArticleDraft` (section structure drives positions)
- Output: `VisualPlan` (schemas/visual_plan.schema.json)

```json
{
  "cover": {"style": "editorial", "ratio": "2.35:1", "prompt": "..."},
  "images": [{"position": 2, "purpose": "concept", "prompt": "..."}],
  "diagrams": [{"position": 5, "type": "flowchart", "spec": "..."}]
}
```

## Workflow

1. **Read the draft** — identify concepts that benefit from visuals (position = insert before section N).
2. **Cover** — one cover spec; style must match theme tone; ratio defaults `2.35:1`.
3. **Images** — 1 image per 600–900 words max; each has a concrete `purpose` (concept / example / screenshot / mood) and a generation-ready prompt (see [prompts/](prompts/)).
4. **Diagrams** — flowchart / architecture / timeline described in `spec`; rendered later by the image provider or as a styled component.
5. **Assets** — if an image provider is configured, fill `asset_path`; if generation fails, fall back: image search → placeholder; set `degraded: true`.

## Rules (Defender duties)

- Never embed images as raw HTML; positions and prompts only.
- Prompts must be self-contained (no references like "like the one above").
- When attacked (broken asset, wrong ratio), fix ONLY the cited entry (H3).

## References

- [prompts/image-prompt-guide.md](prompts/image-prompt-guide.md)
- [references/visual-checklist.md](references/visual-checklist.md)
- [../../../references/adversarial-constraints.md](../../../references/adversarial-constraints.md)
