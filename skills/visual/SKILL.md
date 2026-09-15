---
name: visual
description: wechat-content-skill 的配图子技能（prompt-first）：在渲染之前，按锚点与配额产出五要素生图提示词，以 :::figure 占位块呈现在正文；配图生成永不阻塞管线，生图后按插入位回填。绝不生成最终 HTML。
---

# Visual Skill（配图技能）

## 目标

决定文章在哪里、放什么图，输出「提示词优先」的结构化 `VisualPlan` —— `asset_path` 留空即可走通全管线（渲染 / 校验 / 发布），生图是回填动作而不是前置依赖。

## 输入 / 输出

- 输入：`ContentPackage`（`semantic_markdown` 锚点决定图片位置）+ `StyleDecision`（主题决定风格画像与封面风格）
- 输出：`VisualPlan`（schemas/visual_plan.schema.json，prompt-only）

```json
{
  "cover": {"style": "editorial", "ratio": "2.35:1", "prompt": "..."},
  "images": [{"position": 2, "purpose": "concept", "prompt": "..."}],
  "diagrams": [{"position": 5, "type": "flowchart", "spec": "..."}],
  "degraded": false
}
```

## 工作流

1. **锚点** —— 从 `semantic_markdown` 提取可配图位置（`position` = 插入到第 N 个锚点之前）：章节标题优先（首个标题是文章题目，不作锚点；开头位置由封面覆盖，从第 2 位起选），标题不足配额时回退块级锚点（引用块 / 列表 / 代码块等）。
2. **配额** —— 每 600 字 1 张（向上取整），下限 1 张、上限 4 张（`image_quota`）。
3. **提示词** —— 每张五要素：主体 + 风格 + 构图/比例（封面 `2.35:1`，正文 `16:9`）+ 色调 + 约束；收尾必须是「画面中不出现任何文字、无水印、无 logo」；`purpose` ∈ concept / example / screenshot / mood（见 [prompts/](prompts/)）。
4. **图表** —— 流程图 / 架构图 / 时间线以 `spec` 描述，稍后由样式化组件渲染。
5. **占位块** —— `asset_path` 为空的插图以 `:::figure` 占位块把生图 prompt 呈现在正文（虚线卡片样式，六主题内置）；封面只产出 prompt 规格，生成推迟到 UPLOADING 阶段（按 prompt 兜底生成，失败不阻塞建草稿）。

## 降级与回填

- **LLM 不可用 / 配图阶段整体失败** → [core/workflow/imagery.py](../../core/workflow/imagery.py) 确定性兜底：按主题 `imagery.yaml` 风格画像 + 主题色套用五要素模板（pipeline 的 `_stage_plan_imagery` 在 LLM 无产出时自动走此路径），置 `degraded: true`；LLM 部分产出与兜底合并不算降级。
- **回填** —— 生图后用 CLI 按插入位回填，先清后插、字节级幂等，可多轮分批回填：

```bash
python scripts/imagery.py <pkg.json>                          # 离线查看配图 brief
python scripts/imagery.py <pkg.json> --apply                  # 规划并回写 visual 字段
python scripts/imagery.py <pkg.json> --apply --asset 2=<URL>  # 按插入位回填图片
```

- **本地文件** —— 发布门禁只认微信素材域名的 `https://` 图片地址；本地文件先经 `MediaService.upload_content_image` 上传素材库取 CDN URL，再回填。
- **一致性终检** —— `lint_visual_consistency`（[validators/visual/lint.py](../../validators/visual/lint.py)）在渲染门校验 `VisualPlan` ↔ 正文一一对应：资产已回填但正文缺图（`visual_asset_missing_in_body`）、计划中的 prompt 缺占位块（`visual_figure_missing`）、正文出现无主占位块（`figure_orphan`）均按 severity 并入渲染门报告，error 即拒绝（见 [../quality/SKILL.md](../quality/SKILL.md)）。

## 规则（Defender 职责）

- 绝不以原始 HTML 形式内嵌图片；只给位置与提示词。
- 提示词必须自包含（不得出现「如上文那种」之类的指代）。
- 配图失败永不阻塞：占位块本身就是合法产物，全管线可带占位块走通。
- 被攻击（素材损坏、比例错误）时，只修复被点名的条目（H3）。

## 参考资料

- [prompts/image-prompt-guide.md](prompts/image-prompt-guide.md)
- [references/visual-checklist.md](references/visual-checklist.md)
- [../../references/adversarial-constraints.md](../../references/adversarial-constraints.md)
