---
name: native
description: wechat-content-skill 的原生信息子技能：为文章 Markdown 标注四种语义标记（:::note、:::quote、:::callout、:::card），由确定性渲染器转换为主题组件。LLM 绝不写 HTML。
---

# Native Skill（语义标记层）

## 目标

在写作与渲染之间加入原生信息结构：Agent 用语义标记表达意图，渲染器独占全部 HTML。这正是主题切换与微信兼容得以成立的前提。

## 输入 / 输出

- 输入：`ArticleDraft` + `VisualPlan`
- 输出：`ContentPackage`（schemas/content_package.schema.json）—— `semantic_markdown` 携带标记

## 四种标记（v0.1 全集，没有其他）

```markdown
:::note
默认蓝色提示。用于补充说明、背景信息。
:::

:::quote cite="Linus Torvalds, 2025"
引用原话。cite 可选。
:::

:::callout type="warning" title="注意"
type ∈ info | warning | tip | danger；title 可选。
:::

:::card title="核心要点"
- 第一条
- 第二条
:::
```

## 规则（Defender 职责）

- 标记只允许使用 [components/](components/) 与 `renderer/components/registry.py` 中定义的属性；未知属性是 lint 错误。
- **禁止嵌套**：一个 `:::` 块内绝不再出现另一个 `:::` 块（v0.1 硬限制）。
- 克制使用：大约每 300–500 字一个组件；文章不能变成幻灯片。
- 绝不输出 `<div>`、`<span>`、内联样式或任何 HTML —— 只用语义标记；HTML 由渲染器确定性生成。
- lint 攻击某个组件（`component_N`）时，只修复该组件（H3）。

## 组件规格

- [components/note.md](components/note.md)
- [components/quote.md](components/quote.md)
- [components/callout.md](components/callout.md)
- [components/card.md](components/card.md)

## 参考资料

- [../../../references/adversarial-constraints.md](../../../references/adversarial-constraints.md)
