# 组件：note（补充说明）

> 权威契约在 [renderer/components/registry.py](../../../renderer/components/registry.py)；本文是写作侧的使用说明。

## 语法

```markdown
:::note
正文（纯文本 / 行内标记）。
:::
```

## 属性

无。note 不接受任何属性——加属性会触发 `unsupported_attribute` lint 错误。

## 渲染效果（default 主题）

浅蓝底（`#f0f7ff`）+ 左侧蓝色竖线（`#1677ff`）的说明块；15px 灰蓝文字。

## 什么时候用

- 补充背景信息、术语解释、版本差异说明。
- 不影响主流程、但读者可能需要的旁注。

## 什么时候不用

- 警告 / 风险提示 → 用 `callout type="warning"` 或 `danger`。
- 引用他人原话 → 用 `quote`（带 cite）。
- 并列要点清单 → 用 `card`。

## 示例

```markdown
:::note
公众号图文的封面比例分 2.35:1 与 1:1 两种；本文统一使用前者。
:::
```

## 误用与报错

| 写法 | 报错（error_type） |
|------|--------------------|
| `:::note type="info"` | `unsupported_attribute` |
| `:::note` 未闭合 | `unclosed_marker`（解析期） |
| note 内再嵌 `:::quote` | `invalid_nesting` |
