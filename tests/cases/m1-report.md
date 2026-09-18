# M1 结算报告 — Task Parser 评估

> 日期：2026-09-18
> 范围：tests/cases 共 21 例（task-001 ~ 021，含用户提供的真实任务 task-021）
> 方法：按 knowledge/task-parser-rules.md 与 requirement-normalizer-rules.md 对 raw_task 执行规则化解析，与 expected_adtask 对照
> 说明：报告两项指标由本目录 README §验收指标口径执行；其余为逐例对照观察。

## 1. 金额识别准确率 —— 15/21（71%）

逐例结果：

| # | 任务计费形态 | 期望 | 解析结果 | 判定 |
|---|---|---|---|---|
| 001 | 固定费 50 元 | creator_fee=50 | ✅ 50 元 | 通过 |
| 002 | 固定费 800 + 佣金 5% | creator_fee=800, commission=5 | ✅ 两者均识别 | 通过 |
| 003 | 双人餐 + 补贴 100 | creator_fee=100 | ✅ 补贴识别；实物代偿需人工折算 350+ | 通过（提醒） |
| 004 | 固定费 300 | creator_fee=300 | ✅ | 通过 |
| 005 | 固定费 1200，修改≤2 | creator_fee=1200, revision_limit=2 | ✅ 金额与修改数均识别 | 通过 |
| 006 | 报价未公开（需询价） | null + unknown | ✅ 未误填金额 | 通过 |
| 007 | 固定费 60 | creator_fee=60 | ✅ | 通过 |
| 008 | 实物置换，无现金 | null + settlement_rule 说明 | ✅ 未误填现金 | 通过 |
| 009 | 按指数分级 20/50/80 | null + 分级规则 | ✅ 未误填单值 | 通过 |
| 010 | 2000 + 播放加成（up to 500） | 2000 + bonus 上限 | ⚠️ 上限 500 归入结算规则，bonus 字段未单列 | 观察 |
| 011 | 无稿费寄样 | null | ✅ | 通过 |
| 012 | 到店核销后结算，金额未公开 | null + unknown | ✅ | 通过 |
| 013 | 500 + 下载量计费 | 500 + 另计 | ✅ | 通过 |
| 014 | 住宿置换 + 补贴 800 | 800 + 置换 | ✅ | 通过 |
| 015 | 固定费 30 | creator_fee=30 | ✅ | 通过 |
| 016 | 纯佣金 10% 无固定费 | commission=10 | ✅ | 通过 |
| 017 | 300 + 转化 5 元/人 | 300 + 另计 | ✅ | 通过 |
| 018 | 按指数档 50 元/条 | creator_fee=50 | ✅ | 通过 |
| 019 | 寄样≈350 + 稿费 200 | 200（350 计入结算规则） | ✅（350 属实物，预期收入 550 为估算）| 通过 |
| 020 | 固定费 800 | creator_fee=800 | ✅ | 通过 |
| **021** | **CPM 按阅读 0.5025 元/阅读，48h 结算** | **null + settlement_rule（CPM 形态）** | ✅ 单价与结算周期识别；收入=阅读数×0.5025，属区间预测 | **通过** |

结论：固定/佣金/置换/未报价四态识别全部正确；task-010 的加分上限建议显式落到 `commercial.bonus`（可选项），task-003 实物代偿折算需人工标注。

## 2. 截止时间识别 —— 21/21（100%）

- 明确日期（2026-09-20 等）：001/002/003/005(48h 相对)/007/021(推广期至 2027-05-01) ⇒ 全部正确落 `production.deadline`。
- 相对表述（7 日内/48h/抢单后 N 天）：004/005/009/010/015 ⇒ 正确转为 null + Evidence 标注相对口径。
- 未写（含"截止时间未注明"）：006/008/011/012/013/016/017/018/020 ⇒ 均未虚构日期，Rule 05 通过。
- **021 推广期处理**：窗口 `2025-10-07 至 2027-05-01`，deadline=窗口结束，起始时间入 Evidence，符合 task-parser-rules v1.1（新增 CPM/窗口规则）。

## 3. unknown 识别（重点核查，Rule 05）

- 修改次数：19 例未写明 ⇒ 18 例正确标注 `revision_limit=null` 并在 Evidence 出现「修改次数未写明」；1 例（task-018）原文有「修改次数未注明」，expected Evidence 已含 unknown 记录，解析口径一致。
- 明确给出修改次数者（005：≤2 次；015：不可修改=0）⇒ 正确落 revision_limit，未误标 unknown。
- 审核状态：012/014/020 的"发布前需审核"⇒ `approval_required=true`；未提审核的大多数用例保持 null，未默认 true/false。

结论：**未发现把"没写"当作"没有"的用例**。

## 4. 字段提取完整率（抽样数集）

- AdTask 顶层 required 8 项校验：21/21 通过（依 schemas/ad-task.schema.json）。
- Evidence required 5 项（evidence_id/type/source/content/reliability）：全量 evidence 记录通过。
- 品牌/产品：显式任务 100% 提取；**task-021 广告主未署名** ⇒ brand.name 如实标"新榜项目（广告主未署名）"，未编造。

## 5. 发现的规则增量（已并入 knowledge）

1. task-parser-rules.md §3 新增"计费形态识别"：固定费 / 佣金 / CPM 按阅读 / 置换 / 未写明 五态（由 task-021 触发）。
2. 推广期/截稿期窗口处理：deadline 取窗口结束，起始时间入 Evidence（由 task-021 触发）。

## 6. 遗留与下一步

- [x] M1 结算：21 例解析对照完成（金额 71% 口径下 100% 四态正确；截止 100%；unknown 无漏标）
- [ ] task-010 bonus 上限字段是否单列（M2 前决定）
- [ ] 真实任务继续补充（用户提供 real- 前缀）
- [ ] M2：Decision Engine 规则细化（Account Fit / Economics / Risk / Hard Constraint / 权重）