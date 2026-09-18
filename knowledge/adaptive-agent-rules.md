# Adaptive Agent 规则（M5，plan §7）

> 从「固定规则」演进到「基于历史结果持续优化」的最终形态。
> 配套：schemas/version-log.schema.json、knowledge/model-update-rules.md、knowledge/feedback-loop-rules.md。
> 版本：v1

---

## 1. Adaptive AccountProfile（§7.1）

```text
Rule A01  只有 applied 的提案才进画像
M4 的 model_update_proposals 全部默认 proposed；
人工确认后（人工或已确认的批处理）才应用并生成画像新版本。

Rule A02  画像版本化
每次应用生成 v2/v3… 新文件（data/accounts/account-*.vN.json），
顶层写 profile_version，并写一条 ModelVersionLog（schemas/version-log.schema.json）。
原版本文件不改（可回滚），禁止"改了但没版本记录"（plan §16）。

Rule A03  学习输入门槛
仅 status=published 且有 performance 复盘的任务进入画像更新；
canceled / rejected 任务不产生任何学习（F02 / M06 呼应）。
```

---

## 2. Adaptive Cost Model（§7.2）

目标：从「账号平均工时」学习到「按任务特征预测工时」。

```text
Rule A04  基线 = 自适应后的账号成本基线
base_hours = account.production.avg_production_hours
（该字段已被 M4 EMA 提案维护，v1→v2 会从 3h 更新到 3.4h 等）

Rule A05  任务特征因子表（加成系数，乘法叠加）
  内容格式含 视频/短视频            → +40%
  特要求含 出镜/实拍/探店/拍摄      → +30%
  内容格式为图文且无特殊要求        → +0%
  任务写明了 estimated_hours        → base 取 max(base, estimated_hours)
  历史修改轮次平均未知              → 不加缓冲（如实，不臆造）

Rule A06  输出必须带特征与来源
cost-predict 输出 base_hours / adjustments[]（因子+值） / predicted_hours / source，
source = "account.production.avg_production_hours(@版本)+任务特征调整"。
```

---

## 3. Adaptive Decision Model / 校准（§7.3）

```text
Rule A07  校准样本门槛
核对维度权重/阈值的调整：< 3 例反馈样本只输出"候选建议（research）"，
不动权重；≥ 3 例且偏差方向一致才提出 confirm 级建议。
单样本不显著（M05 呼应）。

Rule A08  False Positive / False Negative 判定
FP 候选 = 决策 accept/observe，但实际：
          revenue < 报价 且 views 低于基线（商业/曝光双差）
FN 判定 = 决策 reject/observe 未接任务，但后续信息显示实际会好；
          需要"拒单审计"回填才能评估 —— 无样本时如实标注"无法评估"，
          不得臆造。

Rule A09  决策校准建议字段
每条建议含：target（如 decision_engine.W.production_cost）/ from / to /
rationale（引用聚合偏差与样本量）/ status=research|confirm。
```

---

## 4. Decision Debugging（§7.4）

任何一次失败/偏差决策都必须能回放，并回答：

> 当时为什么做出这个判断？如果重新判断，哪些证据会改变结果？

```text
Rule A10  回放链路必须完整
Task → Evidence(n) → Analysis(dimensions) → Score → Decision → Actual Result

Rule A11  Counterfactual：只有真实偏差进入重算
若 actual_production_hours 存在且 > 决策时基线：
  r = (actual - base) / base
  penalty = min(30, round(r × 30))
  production_cost' = max(20, production_cost - penalty)
  score' = score - W.production_cost × penalty
其余维度不变（若无其他偏差证据，不无端调整）。
结论由阈值判定：score' ≥ ACCEPT_MIN → accept；≥ OBSERVE_MIN → observe；否则 reject。

Rule A12  输出"会改变结论的证据清单"
列出导致结论翻转（或不足以翻转）的 metric 与数值，
标注哪些证据来自复盘实际值、哪些仍是估计。
```

---

## 5. 人工 Gate 与诚实性

```text
Rule A13  自动应用（放开人工 gate，2026-09-18 起）
adaptive_agent auto-apply 可按账号批量应用 proposed 提案（画像升级），
校准 confirm 达门槛时自动落权重配置；decision_engine 无 --config 时自动加载
auto_enabled=true 的配置。
『放开 gate』不等于『放开护栏』，底线不变：
  · 权重归一化（总和=1）与回归护栏（action 翻转>0 则拒自动启用）
  · 只写新版本文件 + VersionLog，原画像不覆盖（可回滚）
  · <3 例样本的校准保持 research，不落权重（A07）

Rule A14  无样本不下结论
FN、历史修改缓冲、方差等无真实数据支撑的项，输出"无样本/待回填"，
禁止用默认值假装已学习。
```