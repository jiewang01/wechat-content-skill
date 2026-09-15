---
name: wechat-content-skill
description: 微信公众号内容 Agent 工作流技能：一句话输入，经研究、写作、去 AI 味、语义排版、主题渲染、对抗校验，产出一篇通过校验的公众号草稿箱文章。当用户想要创作、排版或发布微信公众号文章时调用。
---

# WeChat Content Skill（微信公众号内容技能）

## 目标

创建、校验并发布高质量微信公众号内容。
一句话进，校验通过的草稿箱文章出：

> 一句话 → 研究 → 写作 → 标注 → 风格 → 配图 → 渲染 → 校验 → 微信草稿

## 硬约束（必读）

所有阶段必须遵守 [references/adversarial-constraints.md](references/adversarial-constraints.md)（H1–H8）：

- Defender 负责产出，Attacker 必须带证据攻击，Judge（只允许确定性代码）负责裁决。
- 无证据不攻击；无 PASS 裁决不发布。每道门最多修复 3 轮，超限降级。

## 工作流

1. **Research（研究）** — 搜索、阅读、提取、交叉验证 → `ResearchResult`
2. **Plan（规划）** — 选框架、定大纲 → `ContentBrief`
3. **Write（写作）** — 成稿 → `ArticleDraft`；内容门（`lint_content`）有 error 则拒绝进入标注
4. **Humanize（去 AI 味）** — AI 味检测 + 重写循环（质量门，不是提示词）
5. **Annotate（标注）** — LLM 用语义标记（`:::note` / `:::quote` / `:::callout` / `:::card`，card 可嵌套 note / quote / callout，深度上限 2）标注成语义 Markdown → `ContentPackage`；标注先过组件门预检，有错整段弃用、回退纯 Markdown
6. **Gate（组件门禁）** — `lint_components` 全量检查（`ANNOTATED` 状态），error → `ContentGateError`，组件错误全部拦截在风格与渲染之前
7. **Style（风格）** — LLM 提议主题 + 确定性裁决（主题可加载、组件兼容）；失败走框架决策表回退，被否决提议记入审计 → `StyleDecision`
8. **Imagery（配图 prompt）** — 按锚点与配额产出五要素生图提示词，正文以 `:::figure` 占位块呈现 prompt（prompt-first：配图生成不阻塞管线，封面推迟到上传阶段）→ `VisualPlan`
9. **Render（渲染）** — ContentAST → 主题驱动 HTML → `WechatDocument`
10. **Validate（校验）** — 3 道对抗门（content / render / publish；五层 validator 与门禁流转见 [skills/quality/SKILL.md](skills/quality/SKILL.md)）→ `ValidationReport` + `Verdict`
11. **Repair（修复）** — 只做节点级定向修复，≤ 3 轮，绝不整篇重写
12. **Publish（发布）** — 经 API Facade 写入微信草稿箱；封面在 UPLOADING 阶段按 `StyleDecision` 兜底生成；API 不可用时降级为本地 HTML 导出

每个阶段：产物存入 checkpoint（`outputs/<run_id>/`），推进状态机，崩溃后可 `resume` 恢复。

## 规则

- 绝不编造事实；每条事实都携带 `source_ids`。
- 绝不直接生成最终 HTML —— LLM 输出止步于语义标记；确定性渲染器独占 HTML。
- 发布前必须校验；校验不通过绝不发布。
- 确定性工具优先于 LLM 判断（Judge 永远是代码）。
- 阶段之间传递结构化产物，绝不传递自然语言。
- 搜索 / 图片 / 微信 API 失败时优雅降级 —— 发布不是唯一出口。

## 路由

| 阶段 | 子技能 | 输出产物 |
|------|--------|----------|
| 研究 | [skills/research/SKILL.md](skills/research/SKILL.md) | `ResearchResult` |
| 规划 + 写作 + 去 AI 味 | [skills/content/SKILL.md](skills/content/SKILL.md) | `ContentBrief` → `ArticleDraft` |
| 标注（原生组件） | [skills/native/SKILL.md](skills/native/SKILL.md) | `ContentPackage` |
| 风格 | [skills/layout/SKILL.md](skills/layout/SKILL.md) | `StyleDecision` |
| 配图 prompt | [skills/visual/SKILL.md](skills/visual/SKILL.md) | `VisualPlan` |
| 排版 / 渲染 | [skills/layout/SKILL.md](skills/layout/SKILL.md) | `WechatDocument` |
| 校验（质量门） | [skills/quality/SKILL.md](skills/quality/SKILL.md) | `ValidationReport` |
| 发布 | [skills/publishing/SKILL.md](skills/publishing/SKILL.md) | `PublishResult` |

主题（6 个，`renderer/themes/`）：`default` / `editorial` / `minimal` / `tech` / `magazine` / `orange-heart`。
写作框架（7 个，[skills/content/frameworks/](skills/content/frameworks/)）：`tutorial` / `news-analysis` / `opinion` / `case-study` / `listicle` / `deep-dive` / `narrative`。
产物 Schema：[schemas/](schemas/)（JSON Schema，由 `core/artifacts/` 导出）。
状态机：`core/state/machine.py`（INIT → … → DRAFT_CREATED，见蓝图第 11 章）。

## CLI

```bash
python scripts/render.py <content_package.json> -o wechat.html
python scripts/lint.py <draft.json | package.json | doc.md | page.html>
python scripts/validate.py <content_package.json>
python scripts/imagery.py <pkg.json> [--apply [--asset N=<URL> ...]]
python scripts/preview.py <wechat.html>
python scripts/stats.py [--date YYYY-MM-DD] [--account <name>]
python scripts/run_evals.py
```

发布走库调用而非 CLI：`WeChatPublisher.create_draft()` / `.release()`（见 [skills/publishing/SKILL.md](skills/publishing/SKILL.md)）。

**配图回填环（prompt-first）**：`:::figure` 占位块里的 prompt 由人生图或图 provider 生成；本地文件须先经 `MediaService.upload_content_image` 上传素材库取 CDN URL（发布门禁只认 `https://` 图片地址），再用 `python scripts/imagery.py <pkg.json> --apply --asset N=<URL>` 按插入位回填，先清后插、幂等可重跑。

## 恢复

任何中断的运行都可以从 checkpoint 恢复：

```python
from core.state.checkpoint import CheckpointStore
from core.workflow.orchestrator import Orchestrator

run = Orchestrator(CheckpointStore("outputs"), stages).resume("<run_id>")
```
