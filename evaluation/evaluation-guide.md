# Evaluation Guide

> 依据：`plan/plan.md` §14-16（Evaluation Dataset、Evaluation Dimensions、目标表）。
> 数据：`evaluation/evaluation-dataset.yaml`（15 个账号，覆盖技术/职场/育儿/生活方式/教育/商业/个人品牌）。

## 1. 目的

Skill 落地后不能只靠「看起来不错」验收。本指南定义**如何跑、打什么分、达到什么标准**，让每次迭代可度量。

## 2. 运行流程

1. 对 `evaluation-dataset.yaml` 中每个 case，将 `account_brief` 作为 Skill 输入，跑完整链路（Stage 1→6）。
2. 采集各阶段的中间产物与最终 `article_brief`。
3. 按 §3 六个维度逐项打分（0~100），理由必须引用实际输出。
4. 将单个 case 的分数填入 §5 记录表，最后汇总到 §6 总表。

## 3. 评估维度（对应 plan.md §15）

| 维度 | 评估问题 | 打分依据 |
|---|---|---|
| Profile Accuracy | 账号定位解析是否正确？ | `account_profile` 与 `expected_positioning` 的重合度；`unknown`/`[inferred]` 使用是否合理 |
| Research Relevance | Research 是否真正围绕账号，而非泛搜索？ | findings 是否落在 `domain` 半径内；evidence 是否真实可追溯 |
| Candidate Quality | 候选质量如何？ | 用户需求、明确问题、可写性、差异化四要素是否齐备；20~50 条 |
| Ranking Quality | TopN 是否真的来自高潜候选？ | market_score 与 evidence/信号是否一致；多样性 |
| Positioning Fit | Top1 是否符合账号？ | Audience / Authority / Value / Boundary 四方面 |
| Editorial Quality | Brief 是否可以直接交给写作 Agent？ | pain 非模板化、insight 有证据、outline 每节有实质要点、标题非标题党 |

## 4. 目标（plan.md §16）

| 维度 | 目标 |
|---|---|
| Profile Accuracy | ≥ 90 |
| Research Relevance | ≥ 85 |
| Candidate Validity | ≥ 85 |
| TopN Quality | ≥ 80 |
| Positioning Fit | ≥ 90 |
| Brief Usability | ≥ 85 |

说明：这些是工程目标（本阶段可达成的工作目标），不是统计显著性的保证。

## 5. 单 case 记录模板

```yaml
case_id: tech-01
run_date: YYYY-MM-DD
scores:
  profile_accuracy: 0
  research_relevance: 0
  candidate_quality: 0
  ranking_quality: 0
  positioning_fit: 0
  editorial_quality: 0
notes: |
  亮点 / 问题 / 改进点（引用实际输出片段）
exceptions:
  - 如遇到 Research Insufficient / NO_VALID_TOP1，记录场景与触发原因
```

## 6. 汇总表

```text
| case | Profile | Research | Candidate | Ranking | Fit | Editorial | 备注 |
|------|---------|----------|-----------|---------|-----|-----------|------|
| tech-01 | | | | | | | |
| ...     | | | | | | | |
| 平均     | | | | | | | |
```

未达标维度进入下一轮优化（对应 plan.md §17 常见问题清单）。

## 7. 判定纪律

- 出现 `NO_VALID_TOP1` 却强行输出了 Top1 → Positioning Fit 记为 0。
- evidence 编造（无法追溯来源/日期）→ Research Relevance 与 Editorial Quality 各扣 30 分起。
- Top1 的 `why_selected` 缺失任一理由 → Positioning Fit ≤ 60。