---
name: layout
description: Layout sub-skill of wechat-content-skill. Chooses theme and drives the deterministic AST → HTML rendering pipeline (parser, theme engine, renderer). LLM never generates final HTML.
---

# Layout Skill

## Purpose

Own the transformation `ContentPackage → ContentAST → theme-driven HTML → WechatDocument`. Layout decisions are expressed as theme selection + component usage, never as hand-written HTML.

## Input / Output

- Input: `ContentPackage` (semantic markdown + visual plan + theme)
- Output: `WechatDocument` (schemas/wechat_document.schema.json) — GZH-safe HTML, inline styles only

## Pipeline

```text
semantic_markdown
    ↓  renderer/ast/parser.py
ContentAST (nodes carry stable ids: node_N / component_N)
    ↓  renderer/html/renderer.py + renderer/themes/<theme>/
wechat.html (inline CSS, WeChat-safe tags)
```

## Theme selection

v0.1 ships `default` only ([renderer/themes/default/](../../renderer/themes/default/)): `theme.yaml` (colors, enabled components), `typography.yaml`, `components.yaml`. The Theme Engine reads any directory with the same three files — new themes drop in without code changes (v0.2 backlog: editorial / minimal / tech / magazine).

## Rules (Defender duties)

- **The renderer is deterministic code; the LLM never emits final HTML.**
- All styles inline; no `<style>`/`<script>`, no class/id hooks, no external resources.
- WeChat-safe tags only: `section` / `span` / `strong` / `em` / `img`.
- Targeted repair: when the render gate attacks `component_N`, re-render/fix that node only; the repair loop (`core/workflow/repair.py`) enforces ≤ 3 rounds (H3/H4).

## CLI

```bash
python scripts/render.py <content_package.json> -o wechat.html   # package → HTML
python scripts/preview.py <wechat.html>                          # local browser preview
```

## References

- [../../renderer/themes/default/](../../renderer/themes/default/)
- [../../../references/wechat-rules.md](../../../references/wechat-rules.md)
- [../../../references/adversarial-constraints.md](../../../references/adversarial-constraints.md)
