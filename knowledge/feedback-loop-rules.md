# Feedback Loop 规则（M4）

> 覆盖 plan §6.1~6.4：发布记录、性能采集、Prediction vs Actual、Postmortem。
> 配套 Schema：`publish-record.schema.json`、`performance-record.schema.json`、`feedback-report.schema.json`。
> 版本：v1

---

## 1. PublishRecord 铁律

发布记录是「实际发生的事实」，不是预测、也不是报价。

```text
Rule F01  只记录真实结算结果
实际收入 = 结算到账结果，而不是任务报价。
报价与实结不一致时，用 revenue_notes 说明口径。

Rule F02  未发布不写收入
status ∈ {published, canceled, rejected}。
canceled / rejected 的任务不采集 performance，也不进复盘收益对比。

Rule F03  工时/修改轮次如实记录
actual_production_hours 与 revision_count 为 null 表示未记录，
不得用账号均值"补"一个数（那是预测，不是记录）。

Rule F04  decision_id 必填回溯
每条发布记录必须挂回当时的 Decision，否则无法做
Prediction vs Actual（plan §6.3）与 Decision Debugging（plan §7.4）。
```

---

## 2. PerformanceRecord 规则

```text
Rule F05  缺失指标必须为 null
平台拿不到的指标（如流量不开放的小红书 clicks）置 null，
绝不填 0 或估算值（0 会被统计为"零互动"的假象）。

Rule F06  固定观察窗口
status=published 后默认 72h 采集一次，同任务多次回填以
window_hours 最大的记录为准（性能计算取最新窗口）。

Rule F07  互动率口径
engagement_rate = (likes + comments + saves + shares) / views。
views 为 0 / null 时互动率也为 null。
```

---

## 3. Prediction vs Actual

### 3.1 预测基线来源

预测值**必须标注来源**，禁止凭空预测：

| metric | 默认基线 | source 标注 |
|---|---|---|
| views | account.performance.median_views | account.performance.median_views |
| engagement_rate | account.performance.avg_engagement_rate | account.performance.avg_engagement_rate |
| production_hours | account.production.avg_production_hours | account.production.avg_production_hours |
| revision_count | task.requirements.revision_limit（若有） | adtask.requirements.revision_limit |
| revenue | 固定费=creator_fee；CPM=median_views×阅读单价（区间）；置换/未报价=no_baseline | adtask.commercial.* |

基线缺位时：`prediction=null, source="no_baseline", verdict="no_baseline"`。

### 3.2 偏差判定

```text
delta_pct = (actual - prediction) / prediction × 100

|delta_pct| ≤ 50%      → in_line
delta_pct > 50%         → above_baseline
delta_pct < -50%        → below_baseline
prediction 为 null/0    → no_baseline
```

### 3.3 复盘判据（自动生成 What Worked / What Failed / Errors）

```text
Rule F08  production_hours above_baseline（超基线 30%+）
         → error type=production, impact=high（plan §6.6：成本被低估）
         → what_failed: 生产成本低估

Rule F09  views below_baseline
         → error type=prediction, impact=medium
         → what_failed: 内容表现低于账号基线（需人工核对内容质量）

Rule F10  views above_baseline
         → what_worked: 内容/品类/角度表现超基线

Rule F11  revision_count > revision_limit（设了上限时）或 > 2
         → error type=commercial, impact=medium
         → what_failed: 品牌修改频繁（plan §6.6：哪些品牌修改次数最多）

Rule F12  actual_revenue < 报价
         → error type=commercial, impact=low
         → what_failed: 结算低于报价（如佣金未达成）

Rule F13  engagement_rate above_baseline
         → what_worked: 互动表现超基线
```

### 3.4 Confidence 一致性

```text
Rule F14  confidence_verdict
decision.confidence.status 与偏差格局合成一个标签：

  high/very_high + 全 in_line        → high-confidence-inline
  high/very_high + 存在偏差           → high-confidence-deviation（Decision Error 候选）
  medium/low + 存在偏差               → low-confidence-deviation（预期内，信度自我校准有效）
```

---

## 4. Next Recommendation

```text
Rule F15  只给"下一次任务的参数调整建议"，不给本次任务打分
示例（而非穷举）：
- 生产成本低估 → 建议将 account.production.avg_production_hours 上调至 EMA 值
- 品类表现超基线 → 建议将该品类/角度列为优先接单方向
- 修改频繁的品牌 → 建议接单前要求明确修改轮次上限
- 结算低于报价 → 建议核对佣金结算条件后再接同类
```

---

## 5. 复盘产物要求

```text
Rule F16  FeedbackReport 必须自带品类/角度快照
campaign_category 与 content_angle 用于跨任务聚合（plan §6.6 的
"哪些品类最适合""哪些内容方向表现最好"），不依赖回查其他文件。

Rule F17  每条结论可回溯
errors / recommendations 必须引用本条记录的数值（metric + delta_pct），
不引用则视为无效复盘。
```

---

## 6. 验收挂钩（plan §6.6）

30+ 已完成任务后，`summary` 聚合必须能回答：

```text
过去预测准不准？            → 各 metric 的 delta 分布
哪些品类最适合账号？        → 按 campaign_category 聚合 views 超基线率
哪些广告成本常被低估？      → production_hours 的 average delta
哪些品牌修改次数最多？      → 按品牌聚合 revision_count
哪些内容方向表现最好？      → 按 content_angle 聚合
哪些决策容易出错？          → confidence_verdict ≠ inline 的占比
```

（当前仅种子案例时，聚合输出如实标注样本数不足，不编造结论。）