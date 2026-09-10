# 视觉检查清单（visual/references/visual-checklist.md）

> VisualPlan 定稿前逐项自检；渲染门与发布门的部分检查与此对应。

## 封面（cover）

- [ ] 恰好一份封面规格；`ratio` 为 `2.35:1`（或明确说明的例外）。
- [ ] `style` 与文章基调匹配（严肃题材不用卡通风）。
- [ ] prompt 自包含、五要素齐备、以「无文字、无水印」收尾。

## 插图（images）

- [ ] 数量 ≤ 字数 ÷ 600（每 600–900 字最多 1 张）。
- [ ] 每张 `position` 在 1..章节数 范围内，且不与 diagrams 重位。
- [ ] 每张有明确 `purpose`（concept / example / screenshot / mood）。
- [ ] prompt 自包含；同篇风格描述一致。

## 图表（diagrams）

- [ ] `type` ∈ flowchart / architecture / timeline（v0.1）。
- [ ] `spec` 用文字完整描述节点与连线（渲染方零上下文可复现）。
- [ ] 节点文字 ≤ 8 字/个，避免图内长句。

## 素材与降级（asset_path / degraded）

- [ ] 配置了图片 provider 时 `asset_path` 已填充；否则留空（发布前补齐）。
- [ ] 生成失败走 [降级路径](../prompts/image-prompt-guide.md#降级路径graceful-degradation)，且 `degraded: true`。
- [ ] 资产文件真实存在、可读、格式为 png/jpg、单张 < 10MB（公众号上限）。

## 一致性

- [ ] 视觉计划没有偷跑去改正文——位置调整只能反馈给 content 技能，不能自己改稿。
- [ ] 被攻击（素材损坏、比例错误）时只修复被点名条目（H3）。
