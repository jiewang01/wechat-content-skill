---
name: wechat-content-skill
description: 微信公众号内容 Agent 工作流技能：一句话输入，经研究、写作、去 AI 味、语义排版、主题渲染、对抗校验，产出一篇通过校验的公众号草稿箱文章。当用户想要创作、排版或发布微信公众号文章时调用。
---

# WeChat Content Skill（微信公众号内容技能）

## 目标

创建、校验并发布高质量微信公众号内容。
一句话进，校验通过的草稿箱文章出：

> 一句话 → 研究 → 写作 → 排版 → 校验 → 微信草稿

## 硬约束（必读）

所有阶段必须遵守 [references/adversarial-constraints.md](references/adversarial-constraints.md)（H1–H8）：

- Defender 负责产出，Attacker 必须带证据攻击，Judge（只允许确定性代码）负责裁决。
- 无证据不攻击；无 PASS 裁决不发布。每道门最多修复 3 轮，超限降级。

## 工作流

1. **Research（研究）** — 搜索、阅读、提取、交叉验证 → `ResearchResult`
2. **Plan（规划）** — 选框架、定大纲 → `ContentBrief`
3. **Write（写作）** — 成稿 → `ArticleDraft`
4. **Humanize（去 AI 味）** — AI 味检测 + 重写循环（质量门，不是提示词）
5. **Design（视觉）** — 结构化 `VisualPlan`（封面 / 插图 / 图表）
6. **Native（原生组件）** — 用语义标记（`:::note` / `:::quote` / `:::callout` / `:::card`）标注，card 可嵌套 note / quote / callout（深度上限 2）→ `ContentPackage`
7. **Render（渲染）** — ContentAST → 主题驱动 HTML → `WechatDocument`
8. **Validate（校验）** — 3 道对抗门（content / render / publish；四道 validator 与门禁流转见 [skills/quality/SKILL.md](skills/quality/SKILL.md)）→ `ValidationReport` + `Verdict`
9. **Repair（修复）** — 只做节点级定向修复，≤ 3 轮，绝不整篇重写
10. **Publish（发布）** — 经 API Facade 写入微信草稿箱；API 不可用时降级为本地 HTML 导出

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
| 视觉 | [skills/visual/SKILL.md](skills/visual/SKILL.md) | `VisualPlan` |
| 原生组件 | [skills/native/SKILL.md](skills/native/SKILL.md) | `ContentPackage` |
| 排版 / 渲染 | [skills/layout/SKILL.md](skills/layout/SKILL.md) | `WechatDocument` |
| 校验（质量门） | [skills/quality/SKILL.md](skills/quality/SKILL.md) | `ValidationReport` |
| 发布 | [skills/publishing/SKILL.md](skills/publishing/SKILL.md) | `PublishResult` |

主题（5 个，`renderer/themes/`）：`default` / `editorial` / `minimal` / `tech` / `magazine`。
写作框架（7 个，[skills/content/frameworks/](skills/content/frameworks/)）：`tutorial` / `news-analysis` / `opinion` / `case-study` / `listicle` / `deep-dive` / `narrative`。
产物 Schema：[schemas/](schemas/)（JSON Schema，由 `core/artifacts/` 导出）。
状态机：`core/state/machine.py`（INIT → … → DRAFT_CREATED，见蓝图第 11 章）。

## CLI

```bash
python scripts/render.py <content_package.json> -o wechat.html
python scripts/lint.py <draft.json | package.json | doc.md | page.html>
python scripts/validate.py <content_package.json>
python scripts/preview.py <wechat.html>
python scripts/stats.py [--date YYYY-MM-DD] [--account <name>]
python scripts/run_evals.py
```

发布走库调用而非 CLI：`WeChatPublisher.create_draft()` / `.release()`（见 [skills/publishing/SKILL.md](skills/publishing/SKILL.md)）。

## 恢复

任何中断的运行都可以从 checkpoint 恢复：

```python
from core.state.checkpoint import CheckpointStore
from core.workflow.orchestrator import Orchestrator

run = Orchestrator(CheckpointStore("outputs"), stages).resume("<run_id>")
```
