# Task Parser 规则

> 来源：BLUEPRINT §4、plan §3.1/§3.2
> 版本：v1

## 1. 输入输出

```text
Raw Task（人工粘贴的新榜任务原文）
    ↓
Task Parser
    ↓
AdTask（符合 schemas/ad-task.schema.json）
```

## 2. 抽取字段清单

| AdTask 字段 | 来源提示 |
|---|---|
| `brand.name` / `product` / `category` | 品牌、产品、品类 |
| `campaign.objective` | 广告目标 |
| `campaign.target_audience` | 目标人群 |
| `campaign.content_type` | 内容形式（图文/视频/口播等） |
| `campaign.key_messages` / `mandatory_points` / `forbidden_points` | 卖点、必选点、禁用点 |
| `commercial.creator_fee` / `commission` / `bonus` / `estimated_total_income` / `settlement_rule` | 广告费、佣金、奖金、预估总收入、结算规则 |
| `production.deadline` | 截止时间 |
| `production.estimated_hours` | 预估工时（默认 unknown，不得虚构） |
| `production.content_format` / `word_count` / `image_count` / `video_required` | 交付形式与门槛 |
| `production.special_requirements` | 特殊要求 |
| `requirements.platform_rules` | 平台规则 |
| `requirements.brand_review` | 品牌审核要求 |
| `requirements.revision_limit` | 修改次数（**未写明 → null，禁止默认 1**） |
| `requirements.approval_required` | 是否需要审批 |

## 3. 金额与时间识别

- 金额：统一以数字（元/人民币）记录，提取时保留原始字符串到 Evidence `data` 中。
- 时间：统一 `YYYY-MM-DDTHH:mm:ssZ`（ISO-8601），相对的「9月20日」按任务捕获日推断，并在 Evidence 中标注推断来源。

## 4. 缺失处理（RULE 05）

- 任何抽取不到的内容一律为 `null` 或空数组，并在 Evidence 中标注 `unknown`。
- **禁止**把「没写」当成「没有」。

## 5. 输出

最终形成：

```text
Raw Task → AdTask → Evidence[]
```

原始任务中的事实逐条转换为 `EVD-*`（type 以 `task_fact` 为主）。