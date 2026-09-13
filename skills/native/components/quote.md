# 组件：quote（引用）

> 权威契约在 [renderer/components/registry.py](../../../renderer/components/registry.py)。

## 语法

```markdown
:::quote cite="出处（人名 / 书名 / 文章名，尽量带时间）"
引用的原话，逐字。
:::
```

## 属性

| 属性 | 必填 | 说明 |
|------|------|------|
| `cite` | 否 | 引用出处；有就必写，没有出处的「引用」不该存在 |

## 渲染效果（default 主题）

灰底（`#f7f7f7`）+ 左侧绿色竖线（`#07c160`）；正文 15px 灰字；有 cite 时右下角 13px 浅灰「—— 出处」。

## 什么时候用

- 逐字引用他人的话，且能给出出处。
- 强调一段来自外部的原文材料。
- card 内嵌入引用佐证（v0.3：quote 可被 card 嵌套，语法见 [card.md](card.md)）。

## 什么时候不用

- 自己的总结（用普通段落或 note）。
- 转述（非逐字）→ 写成正文并用括号标注来源，不要伪装成原话。

## 示例

```markdown
:::quote cite="Linus Torvalds, 2025"
Talk is cheap. Show me the code.
:::
```

## 语义等价形式

标准 `>` 块引用会被解析器统一收进 QuoteNode，序列化时规范为 `:::quote` 形式。写作期用哪种都行，落盘一律是标记形式。

## 误用与报错

| 写法 | 报错（error_type） |
|------|--------------------|
| `:::quote author="X"` | `unsupported_attribute` |
| cite 值含双引号 | 属性解析失败；cite 内不要用双引号，改用单引号 |
