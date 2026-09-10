# wechat-content-skill

An agent-native workflow skill for creating, designing, validating, and publishing high-quality WeChat Official Account (公众号) content. 新一代、可扩展、Agent-native 的微信公众号 AI Workflow Skill。

> **一句话 → 研究 → 写作 → 排版 → 校验 → 微信草稿**

## 架构速览

- **Artifact Flow**：阶段间只传结构化 Artifact（`ResearchResult → ContentBrief → ArticleDraft → VisualPlan → ContentPackage → WechatDocument → ValidationReport → PublishResult`），不传自然语言。
- **Thin Orchestrator + Deep Skills**：根 `SKILL.md` 是薄编排入口（≤150 行），深度规则在各 Sub-Skill。
- **对抗式质量门**：Defender / Attacker / Judge 三角色硬约束（见 [references/adversarial-constraints.md](references/adversarial-constraints.md)），Judge 一律为确定性代码。
- **Targeted Repair**：验证失败只修被命中的节点，最多 3 轮，绝不整篇重写。
- **Graceful Degradation**：搜索 / 图片 / 微信 API 任一失败均有兜底出口；发布不是唯一出口。

完整架构见 [blueprint.md](blueprint.md)，v0.1 落地计划见 [v0.1-implementation-plan.md](v0.1-implementation-plan.md)。

## Quick Start

```bash
pip install -e .[dev]

# 离线全链路测试（全部 mock，不触网）
pytest

# 渲染一个 ContentPackage 为公众号 HTML
python scripts/render.py outputs/<run_id>/content_package.json -o wechat.html

# 校验渲染产物（Content Gate / Render Gate / Publish Gate）
python scripts/validate.py outputs/<run_id>/wechat.html
python scripts/lint.py outputs/<run_id>/content_ast.json
```

## 入口

- **Agent 入口**：根 [SKILL.md](SKILL.md)（编排 6 个 Sub-Skill：research / content / visual / native / layout / publishing）
- **CLI 入口**：`scripts/`（render / validate / lint / preview / publish）

## 约束

所有实现遵守 [references/adversarial-constraints.md](references/adversarial-constraints.md) 的 H1–H8 硬约束。

## License

MIT
