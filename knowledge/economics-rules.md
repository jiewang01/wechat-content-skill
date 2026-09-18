# Decision Dimension — Economics 规则

> 来源：BLUEPRINT §14、plan §4.3
> 版本：v1

## 1. 模型

```text
Expected Net Income = Expected Income − Production Cost − Opportunity Cost
```

M2 阶段 Expected Income / Production Cost / Opportunity Cost 均为 0-100 归一得分，不做金额级拟合。

## 2. Revenue 判定（依据 adtask.commercial + Parser 规则 v1.1 五态）

| 计费形态 | 识别字段 | Revenue 得分 |
|---|---|---|
| 固定费 | creator_fee 明确 | 区间映射：收入越高分越高；低于 100 元属低价引流 ⇒ 50-60 |
| 固定费 + 佣金/CPS | creator_fee + commission | 在固定费基础上 +10（若佣金有明确比例） |
| CPM / 按阅读计费 | settlement_rule 含「单价×阅读数」 | 用 预估阅读数×单价 估算（预估必须带 confidence，Rule 04）；阅读数取账号 performance 同类基线，无基线 ⇒ 中性 55 + uncertainty |
| 置换 / 实物 | creator_fee=null + 实物说明 | 折算价值 >500 ⇒ 55-65；<500 ⇒ 40-55；无法折算 ⇒ 45 ± uncertainty |
| 未报价 / 需询价 | null + unknown | 45 + uncertainty（**禁止默认正常**，Rule 05） |

任何情况下都不允许把预测收入当作确定收入（blueprint §21.4）。

## 3. Production Cost 判定

```text
Production Cost 分 = f(estimated_hours, content_format, 素材要求)
```

- 用时越少、素材越全 ⇒ 分越高（低生产成本=高分）。
- 未知工时 ⇒ 中性 60 + uncertainty；代发类（纯素材，revision_limit=0）可 85+。
- 涉及外出拍摄/寄拍/需拍摄素材量大 ⇒ 降分。

## 4. Opportunity Cost 判定

- 参照：账号历史单篇公众号平均收益（account.commercial.historical_revenue/篇或 CPM）。
- 任务窗口越紧急（临近 deadline）⇒ 分越低；长窗口/不限制 ⇒ 中性 65+。
- 无账号基线 ⇒ 中性 60 + uncertainty。

## 5. 输出

```text
dimensions: { revenue, production_cost, opportunity_cost }
+ expected_income 区间（预测类，必须带 confidence 与 evidence_refs）
```