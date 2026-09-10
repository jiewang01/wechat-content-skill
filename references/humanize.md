# Humanize 检测器使用说明

humanize 是**确定性质量门**，不是提示词。判定逻辑在 `skills/content/humanize/detector.py`，规则全部外置于 `skills/content/humanize/rules.yaml`（硬约束 H7：调规则不改代码）。Judge 职责由代码承担，LLM 不参与打分（H8）。

## 调用方式

```python
from skills.content.humanize import analyze_text

report = analyze_text(markdown_text)
report.humanize_score  # int，0-100
report.passed  # bool，score >= pass_score(60)
report.issues  # list[dict]，每条 {type, severity, evidence, message}
```

自定义规则（如需临时放宽句长）：

```python
from skills.content.humanize import load_rules, analyze_text

rules = load_rules("my_rules.yaml")  # 缺省读取包内 rules.yaml
report = analyze_text(text, rules)
```

## 计分模型

从 100 分起扣，扣完为止（下限 0）；`passed = score >= pass_score`（默认 60）。

| issue 类型 | severity | 扣分/次 | 触发条件 |
|------------|----------|---------|----------|
| `blacklist_phrase` | error | -8 | 命中黑名单短语（「首先，」「赋能」「众所周知」等 23 条） |
| `paired_phrase` | error | -8 | 同一句内出现关联套话（「不仅…而且」「随着…的发展」等 4 组） |
| `long_sentence` | warning | -3 | 单句超过 60 字 |
| `avg_sentence_length` | warning | -5 | 平均句长超过 35 字（全文 ≥ 3 句才参与统计） |
| `long_paragraph` | warning | -3 | 单段超过 200 字 |
| `repetition` | warning | -5 | 同一 5 字中文片段重复 ≥ 3 次 |

## 检测前的规范化

检测器**只评正文**，以下内容自动剔除：

- 代码围栏（` ``` ` 块）整体剔除；
- 图片 `![alt](url)` 剔除；
- 标题前缀 `#`、列表标记 `-` / `*` / `+` / `1.` 剔除，只留文字。

句子按 `。！？!?；;` 与换行切分；段落按空行切分。

## 修复循环

1. 读 `report.issues`，按 `type` 查改写手册：[../skills/content/writing/style-basics.md](../skills/content/writing/style-basics.md)；
2. **只改被标记的句子/段落**（H3 定向修复），不整篇重写；
3. 重新运行 `analyze_text`，直到 `passed: true`；
4. 修复轮次上限 3 轮（H4，由工作流层强制）；超限即降级或终止。

## 规则调整（H7）

所有阈值都在 `skills/content/humanize/rules.yaml`：

```yaml
pass_score: 60          # 及格线
penalties:              # 每类问题的扣分
  phrase: 8
  paired_phrase: 8
  ...
limits:                 # 触发阈值
  max_sentence_chars: 60
  avg_sentence_chars: 35
  max_paragraph_chars: 200
  repeat_ngram_chars: 5
  repeat_min_occurrences: 3
  min_sentences_for_avg: 3
phrases: [...]          # 黑名单短语，可直接增删
pairs: [...]            # 关联套话对
```

调整规则**不需要改任何代码**；规则文件随包分发（`package-data`）。

## 边界说明

- 检测器不懂语义：它抓的是**统计特征**（套话、句长、重复）。语义层面的事实错误由对抗循环的 Attacker 与 content QA 门负责，不在此检测器的职责内。
- 分数不是越高越好：90+ 只说明没有统计特征，不保证内容质量。质量门的完整定义见 [adversarial-constraints.md](adversarial-constraints.md)。
