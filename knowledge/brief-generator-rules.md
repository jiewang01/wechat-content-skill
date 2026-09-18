# Brief Generator 规则

> 来源：BLUEPRINT §19 Phase2 分支、plan §5.1
> 版本：v1

## 1. 输入输出

```text
AdTask + AccountProfile + Decision
        ↓
Brief Generator
        ↓
CampaignBrief（符合 schemas/campaign-brief.schema.json）
```

## 2. 字段来源映射

| Brief 字段 | 来源 |
|---|---|
| campaign_objective | adtask.campaign.objective；缺失时由 decision.dimensions 推断并标注推断 |
| target_audience | adtask.campaign.target_audience + account.audience 合并 |
| product_usp | adtask.campaign.key_messages / brand.product（2-4 条）|
| mandatory_claims | adtask.requirements 归一后 mandatory_points（逐条搬运，不可遗漏）|
| forbidden_claims | forbidden_points（逐条搬运 + 合规风险提示）|
| content_angle | Content Strategy 3 选 1（见 content-strategy-rules）|
| hook / storyline / cta | 依据 platform_style 与 account_style 生成 |
| platform_style | 平台特征（公众号→温和科普、小红书→真实种草、抖音→快节奏口播等）|
| account_style | account.content.style（如"温和科普"）|
| risk_checklist | decision.blockers + hard_constraints + risk 字段派生 |
| evidence_refs | 全程引用 EVD-*，追溯链不中断 |

## 3. 铁律

1. **mandatory_claims 必须完整搬运，禁止增删**（品牌要求遗漏是最严重缺陷，plan §5.6 核心指标）。
2. forbidden_claims 进入 risk_checklist，draft 阶段不得触碰。
3. 出现 unknown（如修改轮次）时，Brief 必须显式写"待与品牌确认 N 项"。
4. Brief 不写完整文案，只写方向与约束（交给 Content Strategy 与 Draft）。