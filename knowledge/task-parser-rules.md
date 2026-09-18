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
- **计费形态识别**（新增，依据真实任务 task-021）：
  - 固定费：`commercial.creator_fee` 直接记录。
  - 佣金/CPS：`commission` + `settlement_rule`。
  - **CPM/按阅读计费**：无固定费，`settlement_rule` 记录「单价×阅读数」与结算周期（如 `阅读单价 0.5025 元/阅读，推文后 48 小时结算`）；收入为区间预测而非确定额，进入 Economics 时必须带 confidence，禁止当作固定收入。
  - 置换/寄样/无现金：`creator_fee = null` + `settlement_rule` 说明实物。
  - 未写明：`creator_fee = null` + `status: unknown`（禁止默认 0 或默认有费）。
- 时间：统一 `YYYY-MM-DDTHH:mm:ssZ`（ISO-8601），相对的「9月20日」按任务捕获日推断，并在 Evidence 中标注推断来源。**推广期/截稿期**：任务给出起止窗口（如 `2025-10-07 至 2027-05-01`）时，`production.deadline` 记录窗口结束时间，窗口起始时间记入 Evidence，不能只记起止之一。

## 4. 缺失处理（RULE 05）

- 任何抽取不到的内容一律为 `null` 或空数组，并在 Evidence 中标注 `unknown`。
- **禁止**把「没写」当成「没有」。

## 5. 输出

最终形成：

```text
Raw Task → AdTask → Evidence[]
```

原始任务中的事实逐条转换为 `EVD-*`（type 以 `task_fact` 为主）。