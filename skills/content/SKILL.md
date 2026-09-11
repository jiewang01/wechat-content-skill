---
name: content
description: wechat-content-skill 的内容子技能：把 ResearchResult 变成 ContentBrief 与通过去 AI 味质量门的 ArticleDraft。写作由框架驱动，humanize 检测器是确定性质量门，而非提示词。
---

# Content Skill（内容技能）

## 目标

接收 `ResearchResult` + 品牌语气 + 受众 + 内容目标；先产出 `ContentBrief`，再产出通过 humanize 质量门的 `ArticleDraft`。

## 输入 / 输出

- 输入：`ResearchResult`（+ 语气 / 字数目标 / 框架提示）
- 输出：`ContentBrief`（schemas/content_brief.schema.json）→ `ArticleDraft`（schemas/article_draft.schema.json）

## 工作流

```text
ContentBrief → 框架选择 → 大纲 → 初稿 → 批判 → 重写 → Humanize → 终稿
```

1. **Brief** —— 选题、受众、目标、语气、`word_target`、带 `fact_ids` 的章节骨架。
2. **框架选择** —— 按选题类型路由；内置 7 个写作框架（见下）。新增框架不需要改 Orchestrator。
3. **初稿** —— 纯 Markdown；这里不加语义标记（那是 native 技能的职责）。
4. **批判 → 重写** —— 依据所选框架的检查清单自审。
5. **Humanize** —— 运行确定性检测器（`skills/content/humanize/`），重写被标记的句子，反复运行直到 `passed: true`。

## 框架（7 个）

| 框架 | 适用场景 | 定义 |
|------|----------|------|
| `tutorial` | 教程 / how-to / 上手指南 | [frameworks/tutorial.md](frameworks/tutorial.md) |
| `news-analysis` | 新闻解读 / 事件分析 | [frameworks/news-analysis.md](frameworks/news-analysis.md) |
| `opinion` | 观点文 / 立场论证 | [frameworks/opinion.md](frameworks/opinion.md) |
| `case-study` | 案例复盘 / 成败归因 | [frameworks/case-study.md](frameworks/case-study.md) |
| `listicle` | 清单体 / 盘点合集 | [frameworks/listicle.md](frameworks/listicle.md) |
| `deep-dive` | 深度长文 / 原理拆解 | [frameworks/deep-dive.md](frameworks/deep-dive.md) |
| `narrative` | 叙事文 / 非虚构故事 | [frameworks/narrative.md](frameworks/narrative.md) |

## 规则（Defender 职责）

- 每条事实陈述必须能追溯到研究产物中的 `fact_id`；绝不编造论断。
- Humanize 是**质量门**而非提示词：只有 `humanize.passed: true` 的稿件才能交付。
- 不输出 HTML，也不输出 `:::` 标记；只写纯 Markdown。
- 被攻击（AI 味、事实、结构）时，只修复被标记的句子 / 章节（H3）。

## 组件

- [humanize/](humanize/) —— 确定性 AI 味检测器（内容门的 Attacker 引擎）
- [writing/](writing/) —— 重写时使用的句子工艺笔记
- [frameworks/](frameworks/) —— 写作框架定义

## 参考资料

- [../../references/writing-guide.md](../../references/writing-guide.md)
- [../../references/humanize.md](../../references/humanize.md)
- [../../references/adversarial-constraints.md](../../references/adversarial-constraints.md)
- [../../references/content-policy.md](../../references/content-policy.md)
