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
5. **素材** —— 若配置了图片 provider，填充 `asset_path`；生成失败时降级：图片搜索 → `:::figure` 占位块（生图 prompt 直接呈现在正文，生图后回填替换），并置 `degraded: true`。

## Intake 偏好收集（占位开关）

管线启动前（intake 层，与主题选择同批询问）用 AskQuestion 收集占位策略，避免降级发生后再打断用户：

> 生图失败时，正文如何呈现缺失的插图？
> - A. 插入 `:::figure` 占位块，生图 prompt 呈现在正文（默认，成品必有图或占位符）
> - B. 不插占位块，正文保持干净；prompt 仅保留在 `VisualPlan.images` 供回填重渲染

答案物化为 `RunPreferences(figure_placeholders=...)`，经 `Orchestrator.start(preferences=...)` 写入 `checkpoint.preferences` 持久化（可 resume），由规划层 `_stage_plan_visual` 消费：占位块是否入文 = `主题启用 figure 组件 AND preferences.figure_placeholders`。渲染层零感知，`degraded` 审计信号不受影响。

## 确定性兜底（v0.4）

当流程拿不到 LLM 产出的 `VisualPlan`（离线回放、visual 阶段失败、存量 ContentPackage 补配图）时，由 [core/workflow/imagery.py](../../core/workflow/imagery.py) 确定性兜底：

- 依据主题的 `imagery.yaml` 风格画像 + 主题色，直接套用五要素模板生成封面与插图提示词（配额：每 600 字最多 1 张、至多 4 张，章节中点优先）。
- pipeline 的 `_stage_plan_visual` 在 design 缺失时自动走此路径；`scripts/imagery.py` CLI 可单独离线生成 brief 并可选 `--apply` 回写 `visual` 字段。
- 成品必有图或占位符：`asset_path` 为空的插图在主题启用 `figure` 组件时，以 `:::figure` 占位块把生图 prompt 呈现在正文（虚线卡片样式，六主题内置）；生图后回填 `asset_path` 重渲染即替换为真图。`--apply` 先清后插，幂等可重跑。
- 兜底产物同样遵守本技能全部规则（自包含、无指代、无文字水印收尾）。

## 规则（Defender 职责）

- 绝不以原始 HTML 形式内嵌图片；只给位置与提示词。
- 提示词必须自包含（不得出现「如上文那种」之类的指代）。
- 被攻击（素材损坏、比例错误）时，只修复被点名的条目（H3）。

## 参考资料

- [prompts/image-prompt-guide.md](prompts/image-prompt-guide.md)
- [references/visual-checklist.md](references/visual-checklist.md)
- [../../references/adversarial-constraints.md](../../references/adversarial-constraints.md)
