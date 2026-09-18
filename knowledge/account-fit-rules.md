# Decision Dimension — Account Fit 规则

> 来源：BLUEPRINT §14/§15、plan §4.2
> 版本：v1

## 1. 目标

回答：「该任务与账号的匹配程度」。所有维度基于 AccountProfile（`data/account-profile.json` 或用户提供），不允许无依据裸分（Rule 03）。

## 2. 子维度与权重

```text
Account Fit = 0.30×Audience Fit + 0.30×Content Fit + 0.20×Brand Fit + 0.20×Historical Fit
```

| 子维度 | 依据 | 说明 |
|---|---|---|
| Audience Fit | task.campaign.target_audience / 品类人群 vs 账号 audience.interest_tags、gender/age 分布 | 任务要求「男粉多」而账号恰是男粉为主 ⇒ 高分；相反 ⇒ 低分 |
| Content Fit | task.campaign.content_type / brand.category vs 账号 content.niches、content_formats | 品类与日常内容垂类一致 ⇒ 高分 |
| Brand Fit | brand.category 是否落在 account.commercial.preferred/rejected_categories | rejected ⇒ 0 分（触发 Hard Constraint）；preferred ⇒ 高分 |
| Historical Fit | 历史同类任务表现（performance.historical_campaigns / avg_views 基线） | 无同类历史 ⇒ 中性 50，并计 uncertainty |

## 3. 评分与证据要求

- 每个子维度输出 `score(0-100) + evidence_refs + uncertainty_reasons`。
- 数据缺失（如账号无 audience）⇒ 子维度 50 分 + `uncertainty_reasons` 注明缺失，不得默认低分或默认满分。
- 规则：**rejected_categories 命中 = 0 分，同时触发 Hard Constraint fail ⇒ REJECT**。