# M2 验收报告 — Decision Engine 盲测

> 日期：2026-09-18
> 方法：对 tests/cases 21 例以示例账号（按平台自动匹配，见 data/account-example-*.json）运行 decision_engine，校验 Schema 关键约束、Evidence 回引、Confidence 区间与解释可读性。
> 运行：`python3 tools/decision_engine.py --batch`（输出 tests/decisions/）

## 1. 决策分布（21 例）

| 动作 | 数量 | 用例 |
|---|---|---|
| accept | 1 | task-002（固定费 800 + 佣金 5%，高收益低风险） |
| observe | 19 | 其余（信息部分未知，符合"条件未完全满足"） |
| reject | 1 | task-012（医美，账号拒绝品类 H1 fail） |

- 无 need_information：示例账号均提供了 performance 基线（H6 门槛检查有数据）。
- **observe 占 19 例为 v1 权重预期的保守表现**：大量合成用例缺失 `estimated_hours`/`revision_limit`，unknown 惩罚 + 阈值 70 未跨过 ⇒ observe 而非 accept，符合"未知不掩盖"原则。

## 2. 关键用例核验

| 用例 | 期望行为 | 引擎输出 | 判定 |
|---|---|---|---|
| task-002 护肤 800+5% | accept（收益高、品牌fit、有审核） | accept / 72.3 / conf 0.85 | ✅ |
| task-012 医美 | REJECT（H1 账号拒绝品类） | reject / 46.8 / blockers=账号拒绝品类医美 | ✅ |
| task-020 金融 | 不误杀（有合规审核=保护） | observe / 59.2（含金融敏感度扣分） | ✅ |
| task-013 游戏（门槛≥5000播放） | H6 检查账号数据 | pass（账号 3.5万）→ observe | ✅ |
| task-021 真实任务 | observe（证据完整、收入区间预测） | observe / 62.2 / conf 0.80 | ✅ |

## 3. 结构性校验（21/21 通过）

- reasons 每条含非空 `evidence_refs` ✅
- 顶层与 confidence 的 `evidence_refs` 非空 ✅
- `decision_score` ∈ [0,100]、`confidence` ∈ [0.3,0.95] ✅
- 硬约束记录完整（hard_constraints 含 pass/fail/unknown 状态）✅

## 4. 引擎修正记录（本批发现并修复）

1. **source.platform 语义统一**：新榜是聚合平台，用例 `source.platform` 统一改为内容平台（小红书/抖音/知乎/B站/公众号），避免 H2 误拒 20 例。与该约定一致，"知乎任务 ≠ 小红书账号"判 reject 属正确行为。
2. **H6 扫描范围**：门槛文字可能出现在 mandatory_points / special_requirements 而非 platform_rules；v1 已扩展扫描，且账号有基线时自动 pass。
3. **unknown 硬约束升级**：H6 等状态为 unknown 时，决策升级为 need_information 并写入 blockers（不再静默 observe）。
4. **平台盲测账号补齐**：新增 account-example-dy/zh/bz.json，五平台可独立盲测。
5. **合成用例日期修正**：task-001/007 deadline 早于运行日（2026-07-29 / 2026-09-22）触发 H4 误拒，已改为未来日期；提醒：真实运行须以接单当日为准核对 deadline。

## 5. 遗留 / 已清理

- [x] ~~task-010 bonus 上限（播放量加成 ≤500）是否单列~~ → 已单列，见 §7.1
- [x] ~~"need_information 占比为 0"对抗回归~~ → 已补 no-baseline 回归，见 §7.2
- [ ] observe 占比偏高（19/21）：属 v1 权重预期的保守表现，待 Phase 4 真实数据回填后校准阈值/权重

## 6. 结论

M2 决策引擎 v1 验收通过：**硬约束优先、分数可解释、unknown 显式、Evidence 全回引**。任务 021 真实用例及 21 例盲测均符合预期语义。下一步 M3（Content Copilot / Brief Generator）或先回填 Part 4 数据校准权重。

## 7. M2 遗留清理（2026-09-18）

### 7.1 bonus 字段单列（task-010）

- task-010「播放量阶梯加成上限 500 元」显式落入 `commercial.bonus = 500`，`estimated_total_income = 2500`（fee+上限）。
- 语义统一（economics-rules v1.1）：**有确定上限的加成 ⇒ bonus；依结果浮动无上限的计费（每千/每人）⇒ 留在 settlement_rule，bonus=null**。task-013/017 属后者，保持不变。
- task-013/017 的表单识别结论不随之变化（已复核决策分布无偏移，task-010 仍 observe）。

### 7.2 "账号缺基线"对抗回归

- 新增 `data/account-minimal.json`（无 performance/无画像基线），引擎新增 `--no-baseline` 批量入口（输出到 tests/decisions_nobaseline/）。
- 结果符合预期：
  - 含视频/时长/拍摄门槛的用例升级 `need_information`：task-003、task-008、task-014、task-019（blocker=无 performance 基线需人工确认）✅
  - 平台不符任务正常 H2 reject：task-004/005/009/010/013/017/018/020/021 ✅
  - 无门槛用例维持 observe；task-002 因账号无历史基线从 accept 降级 observe（≈69.2，保守正确）✅
- 回归入口：`python3 tools/decision_engine.py --batch --no-baseline`
- decision-engine-rules §4 已明确 unknown 硬约束 ⇒ need_information（此前于引擎实现，本次固化为文档）。

### 7.3 结论

M2 遗留两项均已闭环；副作用：清理过程中未引入新的决策分布偏移（除对抗回归本身的预期变化）。