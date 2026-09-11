---
name: layout
description: wechat-content-skill 的排版子技能：选择主题并驱动确定性 AST → HTML 渲染管线（解析器、主题引擎、渲染器）。LLM 绝不生成最终 HTML。
---

# Layout Skill（排版技能）

## 目标

负责 `ContentPackage → ContentAST → 主题驱动 HTML → WechatDocument` 的转换。排版决策表达为主题选择 + 组件使用，绝不手写 HTML。

## 输入 / 输出

- 输入：`ContentPackage`（语义 Markdown + 视觉计划 + 主题）
- 输出：`WechatDocument`（schemas/wechat_document.schema.json）—— 公众号安全 HTML，仅内联样式

## 管线

```text
semantic_markdown
    ↓  renderer/ast/parser.py
ContentAST（节点携带稳定 id：node_N / component_N）
    ↓  renderer/html/renderer.py + renderer/themes/<theme>/
wechat.html（内联 CSS，微信安全标签）
```

## 主题选择

内置主题：`default`、`editorial`（编辑部衬线风）、`minimal`（极简黑白灰）、`tech`（科技蓝 + 深色代码块）、`magazine`（杂志高对比），均位于 [renderer/themes/](../../renderer/themes/)，每个主题包含 `theme.yaml`（颜色、启用组件）、`typography.yaml`、`components.yaml`。主题引擎读取任何包含这三个文件的目录 —— 新主题零代码接入。

## 规则（Defender 职责）

- **渲染器是确定性代码；LLM 绝不产出最终 HTML。**
- 全部样式内联；无 `<style>`/`<script>`，无 class/id 钩子，无外部资源。
- 只用微信安全标签：`section` / `span` / `strong` / `em` / `img`。
- 定向修复：渲染门攻击 `component_N` 时，只重渲染 / 修复该节点；修复循环（`core/workflow/repair.py`）强制 ≤ 3 轮（H3/H4）。

## CLI

```bash
python scripts/render.py <content_package.json> -o wechat.html   # 产物包 → HTML
python scripts/preview.py <wechat.html>                          # 本地浏览器预览
```

## 参考资料

- [../../renderer/themes/default/](../../renderer/themes/default/)
- [../../references/wechat-rules.md](../../references/wechat-rules.md)
- [../../references/adversarial-constraints.md](../../references/adversarial-constraints.md)
