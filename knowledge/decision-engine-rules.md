# Decision Engine 规则

> 来源：BLUEPRINT §11-§16、plan §4.6/§4.7
> 版本：v1

## 1. 流程

```text
AdTask + AccountProfile + Evidence[]
    ↓
Hard Constraint Engine（knowledge/hard-constraint-rules.md）
    ↓ Pass
Account Fit（account-fit-rules.md）
Economics（economics-rules.md）
Risk（risk-rules.md）
    ↓
加权 Score → Confidence
    ↓
Action 判定
    ↓
Decision
```

## 2. 维度权重（v1，人为设定，不引入 ML）

```text
Decision Score = 0.30×Revenue + 0.30×AccountFit + 0.15×ProductionCost + 0.05×OpportunityCost + 0.20×Risk
```

所有维度 0-100，方向一致（分越高越有利；Risk 分越高 = 风险越低，见 risk-rules）。

> 权重只作为运营辅助指标（Rule 02），不能作为业务规则唯一依据；M2 后按 Phase 4 实际结果校正。

## 3. Confidence 计算（v1）

```text
Confidence = 0.75 − 0.06×(出现 unknown 的维度数) + 0.25×(平均 Evidence Reliability)
```

- 每维度若含 `null + unknown` 数据（如修改次数、工时、报价）即计入 unknown 维度。
- `平均 Evidence Reliability` = 本决策引用 Evidence 的 reliability 均值；无 Evidence 时按 0.9 计。
- 结果夹取 [0.3, 0.95]。
- `level` 映射：0.70-0.89 → high，0.40-0.69 → medium，<0.40 → low（BLUEPRINT §9）。

## 4. Action 判定

先 Hard Constraint（命中 ⇒ reject），否则按分数与必要信息完整性：

| 条件 | action |
|---|---|
| 任一 Hard Constraint fail | `reject` |
| 任一 Hard Constraint 为 unknown（如 H6 无账号基线）| `need_information`（写入对应 blocker，不得静默 observe）|
| 关键收益信息缺失（无固定费且无结算规则）| `need_information` |
| score ≥ 70 且无 blockers | `accept` |
| 50 ≤ score < 70 | `observe`（存在价值但条件不足）|
| score < 50 | `reject` |

- **高分不覆盖 Hard Constraint**；score≥70 但 risk 维度 <45 ⇒ downgrade 到 `observe` 并列入 blockers。
- `next_actions` 依据 action 给出（如 accept → 生成 Campaign Brief；need_information → 补齐哪些信息）。

## 5. reasons 生成规范

- 每条 reason 必须是 `{ statement, evidence_refs[] }`，evidence_refs 非空（Schema 强制）。
- 至少输出 2 条「主要依据」；存在 uncertainty 时必须输出对应 reason（statement 描述不确定性，evidence_refs 引用 unknown 类证据）。

## 6. 输出

符合 `schemas/decision.schema.json` 的结构化 Decision 对象，含 dimensions、reasons、blockers、next_actions、confidence、evidence_refs、created_at。