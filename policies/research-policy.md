# Research Policy

> 适用范围：Stage 2（Research）。对执行器与将来可能拆分的 Research Agent 都是硬性约束。

## 1. 目的

保证所有选题结论**来自真实外部检索**，而非模型记忆。Research 的任务边界：

```text
Research 回答：外部世界发生了什么？
Research 不回答：哪些值得写（Ranking 的事）、这个账号该不该写（Filter 的事）、怎么写（Editorial 的事）。
```

## 2. 检索纪律

1. **真实检索优先**：Trend / Demand / Content 结论必须来自检索结果（网页、社区、问答、官方文档、搜索趋势），禁止用模型自身知识冒充实时数据。
2. **领域半径**：一切 Query 以 `account_profile.domain` 为核心半径生成，防止泛搜索（如只搜 "AI" 而忽略账号的 "AI Coding"）。
3. **时效标注**：每条 evidence 必须标注 `date`；无法确认时写 `unknown` 并降 `confidence`。
4. **Queries 生成**：组合公式 `domain × audience 问题 × trend 关键词 × 用户问题句式`，默认 6~15 条，覆盖四 Lens。

## 3. 四 Lens 覆盖

| Lens | 问题 | 必带证据类型 |
|---|---|---|
| Trend | 最近发生了什么？ | news / product / official_doc |
| Demand | 用户关心什么？ | community / discussion / search_trend / 问答 |
| Content | 别人写什么？ | social / analytics / 高互动样本 |
| Gap | 什么已有需求但没被讲透？ | Demand + Content 交叉对照 |

任一 Lens 完全无产出时，在 findings 中说明原因，不静默忽略。

## 4. 输出与数量

- 正常输出 5~15 个 `research_finding`（遵循 `schemas/research-finding.yaml`）。
- 每个 finding 必须能回答：为什么值得关注 / 依据是什么 / 用户问题是什么 / 内容机会在哪里。

## 5. Research Insufficient 判定

满足任一条件即输出 `Research Insufficient`，**停止往下游产出**：

- 有效 finding < 3；
- 关键结论全部无 evidence；
- 检索反复失败且无可用替代来源。

输出内容：已获取什么、缺口是什么、建议补充的检索方向。

## 6. 禁止行为

- 编造来源、日期、数据；
- 用「最近很火」这类无出处判断替代证据；
- 在 Research 阶段生成标题或排序；
- 用账号适配度筛选 findings（那是 Stage 5 的职责）。