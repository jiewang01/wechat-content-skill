# 写作总则（Writing Guide）

本文是所有文章写作的**通用纪律**：事实、语气、句子、结构。结构骨架由具体框架负责（教程见 [../skills/content/frameworks/tutorial.md](../skills/content/frameworks/tutorial.md)，新闻解读见 [../skills/content/frameworks/news-analysis.md](../skills/content/frameworks/news-analysis.md)）；被检测器标记后的逐条改法见 [../skills/content/writing/style-basics.md](../skills/content/writing/style-basics.md)。本文管的是**写之前就要照着做**的规则。

## 一、事实纪律（最重要）

1. **每条事实陈述必须可溯源。** 引用研究产物中的 `fact_id`；没有 `fact_id` 支撑的数字、时间、引语，一律不得出现。
2. **观点必须显式标记为观点。** 「我认为」「笔者判断」是合法的；把推测伪装成事实不是。
3. **数字必须原样来自 `Fact.value`。** 不四舍五入到「约」、不换算单位、不脑补量级。
4. **不确定就删。** 写作阶段不做新的检索；缺证据的论断直接删除，不降格为模糊表述。

## 二、语气与视角

| 做 | 不做 |
|----|------|
| 第一人称单数「我」 | 「我们」「本文将为大家」 |
| 口语连接：其实、说白了、这里有个坑 | 首先/其次/最后/再者（检测器黑名单） |
| 具体动词：跑通、踩坑、卡住 | 赋能、抓手、闭环、底层逻辑 |
| 承认局限：这里我没测过 | 毫无疑问、众所周知、由此可见 |
| 全角标点，中英文之间留空格 | 半角逗号句号混排 |

## 三、句子与段落纪律

这些不是风格偏好，而是质量门的扣分项（见 [humanize.md](humanize.md)）：

1. **单句 ≤ 60 字**；超过就拆。
2. **平均句长 ≤ 35 字**；整体节奏靠短句维持。
3. **单段 ≤ 200 字，一段只说一件事**；说第二件事就换段。
4. **同一 5 字片段不重复出现 3 次以上**；换个说法。

## 四、结构纪律

1. 开头 3 段之内必须给出「这篇文章解决什么问题」；铺垫不超过 150 字。
2. 每个章节标题可独立成立（脱离正文也能看懂在讲什么）。
3. 教程类：每个步骤必须有**可验证的完成标志**；命令全文粘贴，不给「参考官方文档」这类指路。
4. 新闻解读类：事实与观点分节；多方立场平衡呈现；不预测股价、不做投资建议。

## 五、批判 → 重写循环

初稿完成后，按所选框架的检查清单自审一轮，再交付检测：

```text
初稿 → 框架 checklist 自审 → 重写 → humanize 检测 → passed: true → 终稿
```

- 检测未通过时，**只改被标记的句子/段落**（硬约束 H3），不整篇重写。
- 重写手法按 issue 类型查 [../skills/content/writing/style-basics.md](../skills/content/writing/style-basics.md)。

## 六、交付标准

一份可交付的 `ArticleDraft` 必须同时满足：

1. 通过 `schemas/article_draft.schema.json` 结构校验；
2. `humanize.passed: true`（分数 ≥ 60，见 [humanize.md](humanize.md)）；
3. 每条事实陈述在研究产物中有对应 `fact_id`；
4. 纯 Markdown：不含 HTML、不含 `:::` 语义标记（那是 native 技能的职责）。
