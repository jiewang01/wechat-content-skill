# Hard Constraint Engine 规则

> 来源：BLUEPRINT §16、plan §4.5
> 版本：v1

## 1. 原则

任何一条 Hard Constraint 命中 ⇒ 直接 REJECT，**在 Soft Score 之前执行**，不得被高分抵消。

```text
Hard Constraints
   ↓
Fail → REJECT
Pass → Soft Scoring → Decision
```

## 2. 约束清单（v1）

| # | 约束 | 判定依据 | 命中 |
|---|---|---|---|
| H1 | 账号明确拒绝该品类 | account.commercial.rejected_categories ⊇ task.brand.category | REJECT |
| H2 | 平台禁止 / 账号平台不符 | account.platform ≠ task.source.platform（如小红书任务 vs 公众号账号） | REJECT |
| H3 | 品牌要求无法满足 | mandatory_points 与账号 content.forbidden_topics 冲突 | REJECT |
| H4 | 时间无法完成 | deadline 距当前 < 1 天（或预设 min_lead_days，默认 1） | REJECT |
| H5 | 法律 / 合规风险不可接受 | risk.policy_risk / claim_risk 达风险上限且无合规保护（如无 brand_review、无法务审核） | REJECT |
| H6 | 账号能力门槛不满足 | platform_rules 中的硬门槛（如「近30天平均播放≥5000」）与 account.performance 不符 | REJECT（内部再确认）|

## 3. 输出

- 全部通过 ⇒ `hard_constraints: [{constraint, status: "pass"}]`
- 任一命中 ⇒ Decision.action = `reject`，blockers 记录命中的约束，reason 引用对应 Evidence。