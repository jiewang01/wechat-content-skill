# Model Update 规则（M4，plan §6.5）

> 复盘结果如何回流到 AccountProfile / Cost Model / Historical Performance / Decision Evidence。
> 版本：v1

---

## 1. 更新目标与默认方法

```text
Rule M01  只有复盘确认的偏差才更新
字段                默认方法   触发条件
account.production.avg_production_hours   ema(α=0.2)   F08 确认成本低估/高估
account.performance.median_views          ema(α=0.2)   有 views 实际值且 ≠ no_baseline
account.performance.avg_views             ema(α=0.2)   同上
account.performance.historical_campaigns  append        该任务已发布 → 追加 "品类 内容格式 ×1"
account.commercial.historical_cpm         ema(α=0.2)   CPM 任务且 revenue/views 可计算
```

`ema(new, old, α) = α × new + (1-α) × old`。

---

## 2. 反馈先于更新

```text
Rule M02  顺序：记录 → 复盘 → 提案 → 应用（自动或人工） → 版本留痕

FeedbackReport.model_update_proposals 一律以 status=proposed 输出。
应用方式两种：
  a) 人工：挑选文件逐条确认（profile-update / apply-calibration）
  b) 自动：adaptive_agent auto-apply 批量应用（放开人工 gate，2026-09-18）
自动模式仍遵守护栏（下述 M03/M05），且只写新版本文件、不覆盖原画像；
权重配置仅在回归 flips=0 时 auto_enabled=true（否则只落盘不启用）。
```

---

## 3. 更新必须版本化（plan §16）

```text
Rule M03  任何对 AccountProfile / 规则权重的修改都必须留版本记录
每次 applied 在 data/ 中产生新文件或 VersionChangelog，
禁止"修改无版本记录"。

Rule M04  不改写给验证过的口径
示例：gender_distribution 的 male 语义（比例/百分比）已由决策引擎适配，
Model Update 不得改变该字段的写入格式，避免破坏回归。
```

---

## 4. 不建议更新的情形

```text
Rule M05  单样本不显著
1 条发布记录就上调 median_views 属于噪声；
ema(α=0.2) 本身已稀释单样本影响，但 proposal 的 rationale 必须
写明样本量（"基于 1 例"）。

Rule M06  取消/被拒任务不进模型
status=canceled/rejected 的发布记录不产生任何更新提案。
```

---

## 5. 提案格式要求

```text
Rule M07  每条提案必须包含
target（完整路径，如 account.performance.avg_production_hours）
from / to（数值或字符串）
method（ema / append / replace / noop）
rationale（引用 feedback_id 与 metric 数值）
status（proposed）
```

`method=noop` 表示"复盘确认无偏差，无需更新"，用于留痕。