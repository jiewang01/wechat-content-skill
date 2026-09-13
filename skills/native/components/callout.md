# 组件：callout（强调提示框）

> 权威契约在 [renderer/components/registry.py](../../../renderer/components/registry.py)。

## 语法

```markdown
:::callout type="warning" title="注意"
提示正文。
:::
```

## 属性

| 属性 | 必填 | 取值 | 说明 |
|------|------|------|------|
| `type` | 否 | `info` / `warning` / `tip` / `danger`（默认 `info`） | 决定配色与严重程度 |
| `title` | 否 | 任意短语 | 粗体标题行；不写则只有正文 |

## 渲染效果（default 主题）

| type | 底色 | 左线 | 标题色 |
|------|------|------|--------|
| info | `#eef6ff` | `#1677ff` 蓝 | 蓝 |
| warning | `#fff7e6` | `#fa8c16` 橙 | 深橙 |
| tip | `#f0fff4` | `#07c160` 绿 | 绿 |
| danger | `#fff1f0` | `#f5222d` 红 | 深红 |

## 什么时候用

- `warning`：操作有风险、可能造成数据损失。
- `danger`：强风险（删库、不可逆、合规红线）。
- `tip`：能省时间的小技巧。
- `info`：比 note 更醒目的中性强调。

一篇之内 callout 总数建议 ≤ 3；全是警示框等于没有警示框。

v0.3 起 callout 可被 card 嵌套，做卡片内的局部警示（语法见 [card.md](card.md)）；嵌套的 callout 同样计入上面的总数建议。

## 示例

```markdown
:::callout type="danger" title="不可逆操作"
执行下面的命令会清空测试库全部数据，请先确认已备份。
:::
```

## 误用与报错

| 写法 | 报错（error_type） |
|------|--------------------|
| `:::callout type="error"` | `invalid_prop_value`（不在枚举内） |
| `:::callout style="bold"` | `unsupported_attribute` |
| 缺 `type` | 不报错，按 `info` 渲染（显式写出更清晰） |
