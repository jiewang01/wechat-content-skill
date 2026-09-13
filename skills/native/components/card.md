# 组件：card（要点卡片）

> 权威契约在 [renderer/components/registry.py](../../../renderer/components/registry.py)。

## 语法

```markdown
:::card title="卡片标题" footer="脚注（数据口径、来源、时间）"
- 第一个要点
- 第二个要点
- 第三个要点
:::
```

## 属性

| 属性 | 必填 | 说明 |
|------|------|------|
| `title` | 否 | 卡片标题（绿色粗体） |
| `footer` | 否 | 底部小字脚注；放数据口径与截止时间最合适 |

## 内容规则（与其他组件不同）

**正文必须是列表**：每行以 `- `（或 `1. `）开头。非列表内容触发 `invalid_card_content` 解析错误。嵌套子组件块（见下节）不算列表行，不受此约束。

## 嵌套子组件（v0.3）

card 是四种组件中唯一的容器：正文可与 note / quote / callout 子组件块混排，深度上限 2 层（card + 一层子组件，子组件内不可再嵌套任何 `:::` 标记）。

```markdown
:::card title="上线检查单" footer="口径：灰度 5% 起"
- 先备份配置目录，保留回滚脚本
:::note
回滚脚本与备份文件放在同一目录，缺一不可。
:::
- 灰度期间观察错误率 30 分钟
:::callout type="warning" title="窗口期"
切换期间写入会丢失，请确认业务低峰再操作。
:::
:::quote cite="运维手册, 2026"
先备份，后动手。
:::
- 无异常则全量放开
:::
```

规则：

- 子组件**不加** `- ` 前缀，顶格写 `:::name …` 与 `:::`，和文本要点行任意交错
- 子组件按容器内出现顺序编号 `component_N.1`、`component_N.2`…（父 card 为 `component_N`；编号是 lint 定向修复的定位键）
- 子组件自身的属性错误（如 `unsupported_attribute`）归属子组件；嵌套违例（`invalid_nesting`）归属父 card
- 深度上限 `MAX_COMPONENT_DEPTH = 2`（权威契约：[registry.py](../../../renderer/components/registry.py)）

## 渲染效果（default 主题）

浅灰底（`#fafafa`）+ 灰边圆角卡片；标题绿 16px 粗体；要点 15px，绿色 `•` 前缀；脚注 13px 浅灰。

## 什么时候用

- 文末「核心要点」回顾（3–6 条）。
- 并列选项 / 对比清单的紧凑呈现。
- 步骤总览（详细步骤仍用正文列表展开）。

## 示例

```markdown
:::card title="三种降级路径" footer="数据截至 2026-09"
- 生成失败 → 改写风格要素重试一次
- 仍失败 → 图片搜索替代
- 再失败 → 占位图并置 degraded
:::
```

## 误用与报错

| 写法 | 报错（error_type） |
|------|--------------------|
| 正文写成了普通段落 | `invalid_card_content` |
| `:::card color="red"` | `unsupported_attribute` |
| 要点里嵌 `**加粗**` | 正常：行内标记在卡片内可用 |
| card 内嵌 `:::card` | `invalid_nesting`（归属父 card） |
| 子组件内再嵌 `:::` 标记（三层） | `invalid_nesting`（归属该子组件；子组件都不是容器） |
