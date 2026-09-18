# M4 验收报告 — Publish & Feedback Loop（task-002 闭环演示）

> 日期：2026-09-18
> 范围：task-002（小红书/护肤图文，accept）完整闭环：PublishRecord → PerformanceRecord → Prediction vs Actual → Postmortem → Model Update 提案
> 运行：
> `python3 tools/feedback_loop.py postmortem --adtask tests/cases/task-002.json --account data/account-example-xhs.json --decision tests/decisions/task-002.decision.json --publish tests/publish/task-002.publish.json --performance tests/performance/task-002.performance.json --angle "B-产品差异" --out tests/feedback/task-002.feedback.json`
> `python3 tools/feedback_loop.py summary --feedback tests/feedback/`
> 产物：tests/feedback/task-002.feedback.json + tests/publish/ + tests/performance/

## 1. M4 新增资产

| 资产 | 说明 |
|---|---|
| schemas/publish-record.schema.json | PublishRecord@v1（真实结算/工时/修改轮次，F01~F04） |
| schemas/performance-record.schema.json | PerformanceRecord@v1（观察窗口 + 缺失置 null，F05~F07） |
| schemas/feedback-report.schema.json | FeedbackReport@v1（Prediction vs Actual / 错误分类 / 参数建议 / 更新提案） |
| knowledge/feedback-loop-rules.md | 记录铁律 + 预测基线 + 偏差判定 + 复盘判据（F01~F17） |
| knowledge/model-update-rules.md | EMA/append 方法 + proposed→applied 人工 gate + 版本化（M01~M07） |
| tools/feedback_loop.py | postmortem / summary 两个子命令 |

产物 Schema 一致性：三个产物文件经 jsonschema 校验 **ALL PASS**。

## 2. Prediction vs Actual（种子案例 task-002）

| metric | 预测 | 来源 | 实际 | delta | 判定 |
|---|---|---|---|---|---|
| views | 6500 | account.performance.median_views | 4200 | -35.4% | in_line |
| engagement_rate | 8% | account.performance.avg_engagement_rate | 7.36% | -8.0% | in_line |
| production_hours | 3h | account.production.avg_production_hours | 5.0h | +66.7% | **above_baseline** |
| revision_count | — | no_baseline（任务未设上限） | 1 | — | no_baseline |
| revenue | 800 | adtask.commercial.creator_fee | 800 | 0% | in_line |

## 3. Postmortem 结论

- **What Failed**：生产成本低估（5.0h vs 基线 3h）→ error type=production, impact=high
- **confidence_verdict**：high-confidence-deviation（决策信度高，但成本基线与实际有出入 → 成本模型需校准，非决策方向错误）
- **Next Recommendation**：上调生产成本基线至 EMA 值 3.4h

## 4. Model Update 提案（全部 proposed，未直接改写账号画像）

| target | from → to | method | 依据 |
|---|---|---|---|
| account.production.avg_production_hours | 3 → 3.4 | ema(α=0.2) | 实际 5.0h vs 基线 3h |
| account.performance.median_views | 6500 → 6040 | ema(α=0.2) | 实际 4200 vs 基线 6500 |
| account.performance.historical_campaigns | +「护肤 图文 ×1」 | append | 已发布样本 |

符合 model-update-rules M02（反馈先于更新，人工确认后才 applied）与 M07（提案含 target/from/to/method/rationale/status）。

## 5. plan §6.6 验收对照

| 验收问题 | 状态 | 说明 |
|---|---|---|
| 过去预测准不准？ | ✅ 机制就绪 | summary 聚合 mean_delta_pct（当前 1 例：views -35.4%、hours +66.7%） |
| 哪些品类最适合账号？ | ✅ 机制就绪 | summary by_category（当前 1 例：护肤 views -35.4%，样本不足不列结论） |
| 哪些成本常被低估？ | ✅ 机制就绪 | hours 聚合 + production error 分类 |
| 哪些品牌修改频繁？ | ✅ 机制就绪 | revision_count 偏离检测（当前任务 1 轮，正常） |
| 哪些内容方向表现好？ | ✅ 机制就绪 | summary by_angle（当前 1 例：B-产品差异） |
| 哪些决策容易出错？ | ✅ 机制就绪 | confidence_verdicts 聚合 |
| 30+ 已完成任务 | ⏳ 待回填 | 当前仅 1 例种子演示；summary 如实标注「样本 <30，仅作参考」 |

## 6. 遵循的铁律（如实标注）

- 发布/表现数据为**人工录入的真实回填格式**（种子演示用合成数值，来源=人工录入），不编造平台数据；clicks/conversion 平台不可得 → null（F05）
- 预测基线全部带 source 标注，无基线处标 no_baseline（revision_count），不凭空预测
- Model Update 均为 proposed，未改写 data/account-*.json（M02）

## 7. 遗留

- [ ] P2：CTA 平台化模板（M3 遗留）
- [ ] observe 占比校准：Phase 4 真实数据回填后校正阈值/权重
- [ ] 真实数据回填 30+ 已完成任务后：summary 结论正式化（当前样本不足，结论仅参考）

## 8. 结论

M4 闭环（发布记录→性能采集→Prediction vs Actual→Postmortem→Model Update 提案→版本化）在种子案例上跑通，契约与规则齐备，聚合统计机制就绪；真实数据回填后即可正式支撑 plan §6.6 的验收问题。里程碑验收通过。