# Confidence 规则

> 来源：BLUEPRINT §8/§9、plan P0-05
> 版本：v1

## 1. 核心区分

```text
Evidence Reliability ≠ Confidence
```

- **Evidence Reliability**：这个数据源本身可靠吗？
- **Confidence**：基于现有证据，这个判断有多确定？

示例：

| 场景 | Reliability | Confidence |
|---|---|---|
| 新榜任务明确写明广告费 ¥1000 | 0.98 | 0.99 |
| 预测这篇内容能获得 20000 阅读 | 0.95 | 0.62 |

「历史表现可靠」不等于「未来预测确定」。

## 2. Confidence Object

```json
{
  "value": 0.72,
  "level": "medium",
  "status": "estimated",
  "evidence_refs": ["EVD-001", "EVD-008", "EVD-011"],
  "uncertainty_reasons": ["历史同类广告样本不足", "品牌修改轮次未知"]
}
```

## 3. Level 分档

| value | level |
|---|---|
| 0.00 - 0.39 | `low` |
| 0.40 - 0.69 | `medium` |
| 0.70 - 0.89 | `high` |
| 0.90 - 1.00 | `very_high` |

## 4. 规则

1. Confidence 不是准确率，只是系统对当前判断确定程度的表达。
2. 所有预测类数据（`expected_views`、`expected_profit`、`estimated_hours` 等）必须至少含 `value + confidence + evidence`。
3. `uncertainty_reasons` 在判断不确定时必须填写，不允许留空代替。
4. 缺失信息（Rule 05）触发时，相应预测的 Confidence 必须降低，并列入 `uncertainty_reasons`。