---
name: visual
description: wechat-content-skill 的视觉子技能：在任何渲染发生之前，产出结构化 VisualPlan（封面、插图、图表）与可直接使用的提示词。绝不生成最终 HTML。
---

# Visual Skill（视觉技能）

## 目标

决定文章需要哪些视觉元素，输出渲染器与图片 provider 都能消费的结构化 `VisualPlan` —— 而不是让写作模型在正文里随手插图。

## 输入 / 输出

- 输入：`ArticleDraft`（章节结构决定图片位置）
- 输出：`VisualPlan`（schemas/visual_plan.schema.json）

```json
{
  "cover": {"style": "editorial", "ratio": "2.35:1", "prompt": "..."},
  "images": [{"position": 2, "purpose": "concept", "prompt": "..."}],
  "diagrams": [{"position": 5, "type": "flowchart", "spec": "..."}]
}
```

## 工作流

1. **通读稿件** —— 找出适合配图的概念（position = 插入到第 N 节之前）。
2. **封面** —— 一份封面规格；风格须匹配主题基调；比例默认 `2.35:1`。
3. **插图** —— 每 600–900 字最多 1 张；每张都有明确的 `purpose`（concept / example / screenshot / mood）与可直接用于生成的提示词（见 [prompts/](prompts/)）。
4. **图表** —— 流程图 / 架构图 / 时间线以 `spec` 描述；稍后由图片 provider 或样式化组件渲染。
5. **素材** —— 若配置了图片 provider，填充 `asset_path`；生成失败时降级：图片搜索 → 占位图，并置 `degraded: true`。

## 规则（Defender 职责）

- 绝不以原始 HTML 形式内嵌图片；只给位置与提示词。
- 提示词必须自包含（不得出现「如上文那种」之类的指代）。
- 被攻击（素材损坏、比例错误）时，只修复被点名的条目（H3）。

## 参考资料

- [prompts/image-prompt-guide.md](prompts/image-prompt-guide.md)
- [references/visual-checklist.md](references/visual-checklist.md)
- [../../references/adversarial-constraints.md](../../references/adversarial-constraints.md)
