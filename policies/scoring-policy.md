# Scoring Policy

> 适用范围：Stage 4（Market Ranking）与 Stage 5（Positioning Filter）。
> 两套评分模型必须严格分离，禁止互相污染。

## 1. 分数约定

- 所有单维度与总分范围：**0~100**（允许一位小数）。
- 每个维度必须给出评分理由（引用 evidence / 信号 / account_profile 字段），禁止凭感觉打分。
- 分数 + 理由一起输出；只有分数没有理由视为不合格。

## 2. Market Score（Stage 4 — 只评市场潜力）

```text
Market Score
= Demand      × 25%  用户是否明确存在需求？
+ Pain        × 20%  问题是否真实、具体、有损失？
+ Trend       × 15%  当前关注度是否上升？
+ Novelty     × 15%  是否存在新的切入角度？
+ ContentGap  × 15%  现有内容是否有明显缺口？
+ Evidence    × 10%  研究证据是否充分可靠？
```

评分锚点（每维）：

| 分数 | 含义 |
|---|---|
| 90~100 | 证据充足、信号极强（如多源一致 + 一手数据） |
| 70~89 | 证据明确、信号可信 |
| 50~69 | 有证据但强度中等 |
| 30~49 | 仅弱信号 / 单源 |
| 0~29 | 无证据支撑 |

**红线**：不得因「适合账号」而调整 Market Score。「适合账号」属于 Stage 5。

## 3. Market Ranking 流程

```text
Candidate Pool
  → 六维打分（带理由）
  → 语义去重（合并后记录 analysis.deduplicated）
  → 多样性检查（TopN 同质时降分）
  → 输出 TopN（默认 5），备选（与 Top5 分差 ≤5 的）记入 analysis
```

## 4. Boundary Risk（Stage 5 — 先于评分执行）

| 级别 | 判定 | 处理 |
|---|---|---|
| HIGH | 明确落入 `account_profile.boundaries` | **一票否决 → REJECT**（不做降分处理） |
| MEDIUM | 与边界部分重叠，需谨慎处理 | 进入评分，输出时标注风险 |
| LOW | 与边界无关或仅轻微擦边 | 正常进入评分 |

## 5. Account Fit（Stage 5 — 只评账号适配）

```text
Account Fit
= Audience Fit    × 20%  读者是否就是账号的核心/次要读者？
+ Problem Fit     × 20%  问题是否属于账号所解决的问题域？
+ Authority Fit   × 20%  账号能否有说服力地讲好（strengths 支撑）？
+ Value Fit       × 15%  是否强化账号的核心价值主张？
+ Differentiation × 15%  与账号已有内容 / 同赛道是否足够差异化？
+ Style Fit       × 10%  是否符合账号的内容风格与形式？
```

## 6. Top1 选择规则

- 综合 `market_score` 与 `account_fit` 决策，**禁止只取 fit 最高**；
- 输出 `why_selected`（market / audience / account / differentiation 四理由）+ risks + confidence；
- 未入选的 TopN 每个都要有被拒原因。

## 7. NO_VALID_TOP1 触发

满足任一条件：

- TopN 全部 boundary REJECT；
- 通过 Boundary 后全部 fit 不达标（无任一候选满足「账号立场成立」的最低标准）。

处理：输出 `NO_VALID_TOP1` + 建议重新 Research（调整/缩小领域搜索范围），**禁止强行选择**。

## 8. 阶段隔离（贯穿全流程）

```text
Stage 4 只看       值不值得做（市场）
Stage 5 只看       该不该做（账号）
禁止：Stage 4 混入账号判断；Stage 5 用市场分压过边界判断。
```