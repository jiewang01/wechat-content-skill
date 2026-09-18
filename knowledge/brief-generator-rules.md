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

## 4. CTA 平台化（v1.1）

```text
CTA 按任务平台生成模板（knowledge 中 PLATFORM_CTA 查表），
未识别平台回退通用模板。所有平台口径统一：
走官方承接位 / 品牌方组件链接，禁止私域导流。

公众号 → 文末官方承接位（品牌方小程序/阅读原文链接），不引导私域加人
小红书 → 评论区置顶/笔记内官方链接（品牌方承接位），不加个人微信
抖音   → 小黄车/POI/官方话题组件（品牌方提供），不留个人联系方式
知乎   → 文末官方链接卡片，不引导私信加人
B站    → 简介/置顶评论官方链接，不引导私域
其他   → 通用：官方短链或组件，禁止私域导流
```

任务本身写明了 CTA/承接方式时，以任务要求为准并保留原文说明。