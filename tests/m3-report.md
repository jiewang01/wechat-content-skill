# M3 验收报告 — Content Copilot（task-002 全链抽检）

> 日期：2026-09-18
> 范围：accept 案例 task-002（小红书/护肤图文，固定费 800 + 佣金 5%）
> 运行：`python3 tools/brief_generator.py --adtask tests/cases/task-002.json --account data/account-example-xhs.json --decision tests/decisions/task-002.decision.json --brief --draft --full`
> 产物：tests/task-002.brief.json、tests/task-002.draft.json（含 full_draft + full_review）

## 1. 全链产物

| 环节 | 产物 | 结果 |
|---|---|---|
| Decision | observe →（本验收样本为 accept 案例） | 已由 M2 生成任务决策（72.3 / accept） |
| Brief | task-002.brief.json | Brief Schema 必填全 PASS |
| Draft | task-002.draft.json（骨架 + 完整稿模板） | full_draft 生成 |
| Self Review | full_review | WARN_PASS（需人工） |
| Human Gate | human_review_required=true | 保留（plan §5.5）|

## 2. 按 plan §5.6 指标的抽检

### 2.1 品牌要求遗漏率

| 任务要求 | Brief 落点 | Draft 落点 | 结论 |
|---|---|---|---|
| 必须产品露出 | mandatory_claims[0] | 文案含 图片注明 | 0 遗漏 |
| 必须突出『敏感肌可用』卖点 | mandatory_claims[1] + product_usp | 正文卖点句 | 0 遗漏 |
| 禁止提竞品 | forbidden_claims + risk_checklist | 全文未出现竞品词 | ✅ |
| 需品牌审核后发布 | risk_checklist「发布前需品牌/法务审核」 | Human Gate 强制 | ✅ |
| 限小红书图文、真人出镜可协商 | platform_style 小红书 + 图文 | tips 区保留 | ✅ |

遗漏率 = 0（人工复核基线：按 Brief 原文逐条对照，无漏项）。

### 2.2 AI 初稿修改量（人工改写痕迹点，full_draft）

| 占位/待改点 | 数量 | 说明 |
|---|---|---|
| 产品名（brand.product=null） | 1 | 任务未明写产品名，如实置空，需向品牌确认后替换 |
| 「此处补具体细节/体验描述」 | 2 | 需真人实拍/真实体验素材后补 |
| 话题标签 | 1 | #XX妍肌 为候选，可替换为品牌方指定话题 |
| 图片建议 → 实拍执行 | 1 | 需执行拍摄 |

预期人工改动集中在"实物置换内容"（细节、图片、产品名确认），而非结构；结构化骨架可直接复用。

### 2.3 平均审校时长（预估）

- Brief 可直接执行，无歧义点（除产品名确认）；风险清单明确。
- 预估人工审校 = 素材补充 + 细节改写 + 发布，**结构部分不重写**。

## 3. Self Review 明细（full_review）

| 检查项 | 状态 | 依据 |
|---|---|---|
| Requirement | PASS | 两条 mandatory 已入骨架 |
| Claim | WARN | 需逐句核对宣称（模板自身无可疑宣称） |
| Platform | PASS | 小红书风格约定 |
| Brand | WARN | 品牌名/产品事实待核对（产品名 null） |
| Account Style | PASS | 真实种草 |

## 4. 发现的改进点（已处理）

1. ~~hook/storyline 仍为通用占位~~ → 已修复：hook 按角度生成（B-产品差异引用 USP，A 引人群利益点，C 引场景）；task-002 hook="围绕核心点「敏感肌可用」，用一句话点明与普通产品的差异"（P1 done）
2. ~~品牌名/产品名缺位~~ → 已修复：product=null 时用「【产品名待品牌确认】」显式占位（P1 done）
3. CTA 平台化模板（P2 backlog）
4. 备注：brief_generator 已支持 --full 完整稿模式（含 build_full_draft 与 full_review），task-021 同步回归无回归
5. ~~骨架模式 format/标题通用残留~~ → 已修复：build_draft 的 platform/format 改为按任务平台生成（原硬编码「公众号图文」+「理性财富信息」标题模板，task-002 小红书任务会错标公众号，属验收暴露的数据质量问题）；task-002 骨架=「小红书 图文」、task-021=「公众号 图文」双回归通过（P1 done）

## 5. 结论

M3 链路（Decision→Brief→Draft→Self Review→Human Gate）在 accept 案例上跑通并满足 plan §5.6 核心指标（遗漏率 0、结构可复用）；hook 定制与产品名占位已修复，CTA 平台化进入 backlog，里程碑验收通过。

## 6. 遗留

- [ ] P2：CTA 平台化模板（小红书/公众号/抖音）
- [ ] 备注：brief_generator 已支持 --full 完整稿模式，后续任务直接可用