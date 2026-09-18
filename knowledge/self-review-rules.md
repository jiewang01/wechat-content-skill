# Self Review 规则

> 来源：plan §5.4
> 版本：v1

## 1. 目标

AI 初稿必须二次检查，输出：

```text
Requirement Check（必选点完整？）
Claim Check（禁用点/宣称合规？）
Platform Check（平台风格/字数/格式？）
Brand Check（品牌调性一致？）
Account Style Check（账号风格一致？）
```

每一项输出 `PASS / WARN / FAIL`，并附依据。

## 2. 判定标准

| 检查项 | PASS | WARN | FAIL |
|---|---|---|---|
| Requirement | mandatory 全部覆盖 | 覆盖但有弱化表述 | 漏点 ≥1 |
| Claim | 无禁用/过度宣称 | 边缘表述 | 出现禁用点或承诺性表述 |
| Platform | 格式字数完全合规 | 轻微偏差 | 格式不符 |
| Brand | 调性一致 | 术语不统一 | 品牌名/卖点错误 |
| Account Style | 符合账号风格样本 | 风格偏移但可修 | 明显不匹配 |

## 3. 铁律

1. 任何 FAIL ⇒ 进入人工审核前必须重写，不允许直接发布。
2. WARN ⇒ 列入 human_review_notes，由人工决定。
3. **Human Review 是最终发布 Gate，不可省略**（plan §5.5）；Self Review 不替代人工。
4. 输出必须引用 Check 依据（EVD-*），记录逐项结果，供回归与审计。