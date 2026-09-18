# M5 验收报告 — Adaptive Agent（task-002 自适应闭环）

> 日期：2026-09-18
> 范围：基于 M4 复盘结果，验证 plan §7 四项自适应能力：Dynamic AccountProfile / Adaptive Cost / Decision 校准 / Decision Debugging
> 运行：
> `python3 tools/adaptive_agent.py profile-update --account data/account-example-xhs.json --feedback tests/feedback/task-002.feedback.json --out data/accounts/account-example-xhs.v2.json --log tests/version-log.json`
> `python3 tools/adaptive_agent.py cost-predict --task tests/cases/task-002.json --account data/accounts/account-example-xhs.v2.json`
> `python3 tools/adaptive_agent.py calibrate --feedback tests/feedback/`
> `python3 tools/adaptive_agent.py debug --adtask tests/cases/task-002.json --account data/account-example-xhs.json --decision tests/decisions/task-002.decision.json --feedback tests/feedback/task-002.feedback.json`
> 产物：data/accounts/account-example-xhs.v2.json、tests/version-log.json、tests/debug/task-002.debug.json、tests/calibration-report.json、tests/cost-predict-task-002.json

## 1. 新增资产

| 资产 | 说明 |
|---|---|
| schemas/version-log.schema.json | ModelVersionLog@v1（每次 applied 留痕，产物校验 PASS） |
| knowledge/adaptive-agent-rules.md | A01~A14（动态画像版本化 / 成本因子表 / 校准门槛 / 回放与 counterfactual / 人工 gate / 诚实性） |
| tools/adaptive_agent.py | profile-update / cost-predict / calibrate / debug 四子命令 |

## 2. §7.1 Adaptive AccountProfile → v2

| 提案（来自 M4 FDB-0001） | 应用结果 | method |
|---|---|---|
| production.avg_production_hours | 3 → 3.4h | ema |
| performance.median_views | 6500 → 6040 | ema |
| performance.historical_campaigns | +「护肤 图文 ×1」 | append |

VersionLog（tests/version-log.json）：3 条 entries 全 applied，`profile_version=v2`，Schema 校验 PASS；
v1 原文件未动（可回滚）。

**修复**：M4 提案 target 形如 `account.production.*`（面向 Schema 顶层属性），初版 set/get 按字面路径写进了内嵌 `account` 对象；已加路径归一化 `_locate_path`，v2 落点正确。

## 3. §7.2 Adaptive Cost Model

```text
base（@v2）= 3.4h
+ 特要求含「真人出镜」因子 +30%
predicted_hours = 4.4h     （实际 5.0h，学习后预测贴近真实；v1 基线 3h 明显低估）
source: account.production.avg_production_hours(@v2)+任务特征调整
```

## 4. §7.3 Adaptive Decision（校准）

- 生产成本偏差：1 例，mean +66.7%
- 校准建议：`W.production_cost 0.15→0.18` 仅标 **research**（样本 <3，不动权重，A07）
- FP 候选：无（task-002 收入与报价一致，不构成 FP）
- FN：无拒单审计数据，如实标注"无法评估"（A08/A14）

## 5. §7.4 Decision Debugging（回放 + Counterfactual）

```text
回放：task-002 / 4 条 Evidence → dimensions(80/61/60/40/95) → score 72.3
      → accept(conf high) → actual(views 4200 / hours 5.0h / rev 800)

Counterfactual（A11）：
  实际工时 5.0h > 决策时基线 3h → r=0.667, penalty=20
  production_cost 60→40，score 72.3→69.3（< ACCEPT_MIN 70）
  → 结论 accept→observe

答复 plan §7.4 提问：
  · 当时为什么 accept？收益 80 与风险 95 被高信度采信，成本维度仅 60 分且"工时未写明"被归为未知而非成本风险
  · 哪些证据会改变结果？production_hours 实际值（5.0h vs 基线 3h）——若当时采用自适应成本基线，
    production_cost 下调 20 分，结论翻转
```

## 6. 验收对照（plan §17 M5）

| 能力 | 状态 |
|---|---|
| Historical Data → Adaptive Model（画像进化） | ✅ v1→v2 迁移 + 版本日志 |
| 成本自适应学习 | ✅ 基线 3→3.4，含特征因子预测 4.4h |
| Decision Optimization（校准） | ✅ 机制就绪，样本门槛诚实控制 |
| Decision Debugging | ✅ 完整回放 + 可翻转结论的证据链 |

## 7. 遵循的诚实性铁律

- 单样本不显著：校准仅 research 候选，不动权重（A07）
- FN 无数据不可评估，未虚构（A08/A14）
- 所有更新均写版本日志，v1 可回滚（A02/M03）
- 全程不静默改写线上画像，产出新版本文件（A13）

## 8. 遗留（进入 M0~M5 总体待办）

- [ ] P2：CTA 平台化模板
- [ ] observe 占比校准：真实数据回填后校正阈值/权重（A07 达 ≥3 例后转 confirm）
- [ ] 真实回填 30+ 完成案例：summary/校准结论正式化
- [ ] 拒单审计回填：让 FN 评估可用（A08）
- [ ] 自适应上生产：proposed→applied 自动化批处理 + 权重重算回归（M5 后续）

## 9. 结论

M5 四项自适应能力在 task-002 上全部跑通：画像 v2 迁移、成本学习（含任务特征）、决策校准（诚实门槛）、决策回放与 counterfactual（发现"成本低估会导致 accept→observe"的可翻转证据）。里程碑验收通过，M0~M5 全链路（FACT→EVIDENCE→DECISION→ACTION→RESULT→LEARNING→UPDATE）成型。