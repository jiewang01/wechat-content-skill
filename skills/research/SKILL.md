---
name: research
description: wechat-content-skill 的研究子技能：搜索、阅读、提取并交叉验证信息源，输出结构化 ResearchResult 产物。本技能绝不撰写文章正文。
---

# Research Skill（研究技能）

## 目标

把一个选题变成经过验证、结构化的 `ResearchResult` —— 内容阶段的唯一输入契约。研究阶段绝不写文章正文。

## 输入 / 输出

- 输入：用户意图（选题、受众、角度提示）+ 可选的已有资料
- 输出：`ResearchResult`（schema：`schemas/research_result.schema.json`）

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

## 工作流

```text
搜索 → 阅读 → 提取 → 交叉验证 → 结构化
```

1. **搜索** —— 从不同角度构造 3–8 组查询（经 `integrations/search/` provider）。
2. **阅读** —— 打开头部结果；优先一手来源；记录 `credibility`（0–1）。
3. **提取** —— 蒸馏出原子化论断；每条事实有 `fact_id`，必须引用 `source_ids`。
4. **交叉验证** —— 只被单一低可信度来源持有的论断，要么丢弃，要么标记 `confidence < 0.5`。
5. **结构化** —— 输出 3–5 个候选角度供内容阶段挑选。

## 规则（Defender 职责）

- 绝不编造事实；每条论断至少携带一个存在于 `sources` 中的 `source_id`。
- 绝不在这里起草文章章节 —— 那是 content 技能的职责。
- 交接前至少 3 个来源、5 条事实；搜索不可用时置 `degraded: true`，用已有来源继续（优雅降级）。
- 被攻击（AttackReport 指向 `facts`/`sources`）时，只修复被点名的条目 —— 绝不重写整个产物（H3）。

## 参考资料

- [references/source-credibility.md](references/source-credibility.md)
- [references/adversarial-constraints.md](../../references/adversarial-constraints.md)（硬约束 H1–H8）
